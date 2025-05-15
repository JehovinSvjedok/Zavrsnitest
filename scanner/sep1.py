from bluepy import btle
import struct
import datetime
import os
import time
import threading
import queue
import sqlite3
import sys

# --- Configuration ---
LOG_FILE_NAME = "log_scan.txt"
DB_PATH = "log_db.db"
TARGET_MANUFACTURER_ID = 0xFFFF
EXPECTED_PAYLOAD_HEX_LEN = 8 + 8
EXPECTED_TOTAL_HEX_LEN = 4 + EXPECTED_PAYLOAD_HEX_LEN
CONFIRMATION_SERVICE_UUID = "00001234-0000-1000-8000-00805f9b34fb"
CONFIRMATION_CHAR_UUID = "00005678-0000-1000-8000-00805f9b34fb"
SCAN_DURATION = 10.0
CONNECT_TIMEOUT = 10.0 

# --- Global Queue ---
data_queue = queue.Queue()
confirmation_status_dict = {}  # Dictionary to store confirmation status

# --- Initialize Database ---
def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS ble_logs (
            timestamp TEXT,
            mac_address TEXT,
            rssi INTEGER,
            device_id INTEGER,
            sensor_value REAL,
            confirmation_status TEXT
        )
    ''')
    conn.commit()
    conn.close()

# --- Insert Log into Database ---
def insert_log_to_db(timestamp, mac_address, rssi, device_id, sensor_value, confirmation_status):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO ble_logs (timestamp, mac_address, rssi, device_id, sensor_value, confirmation_status)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (timestamp, mac_address, rssi, device_id, sensor_value, confirmation_status))
    conn.commit()
    conn.close()

# --- Placeholder Database Function (optional) ---
def query_database(mac_address, device_id, sensor_value):
    print(f"  [Scanner DB Placeholder] MAC: {mac_address}, Device ID: {device_id}, Sensor Value: {sensor_value:.4f}")

# --- Function to Send Confirmation ---
def confirmation_worker():
    while True:
        item = data_queue.get()
        if item is None:
            break
        dev, device_id = item
        status = send_confirmation(dev, device_id)
        confirmation_status_dict[dev.addr] = status
        data_queue.task_done()

def send_confirmation(target_device, parsed_device_id):
    mac_address = target_device.addr
    addr_type = target_device.addrType
    print(f"  [Confirmation Worker] Attempting to send confirmation for Device ID {parsed_device_id} to {mac_address}...")

    peripheral = None
    try:
        confirmation_payload = struct.pack('<I', parsed_device_id)
        print(f"    [Confirmation Worker] Prepared confirmation payload: {confirmation_payload.hex()}")

        print(f"    [Confirmation Worker] Connecting to {mac_address} (Type: {addr_type})...")
        peripheral = btle.Peripheral()
        peripheral.connect(mac_address, addr_type, timeout=CONNECT_TIMEOUT)
        print(f"    [Confirmation Worker] Connected.") # Moved print to after successful connect

        # --- MODIFICATION START ---
        print(f"    [Confirmation Worker] Discovering ALL services...")
        services = peripheral.getServices() # Get a list of all services
        print(f"    [Confirmation Worker] Discovery finished. Found {len(services)} services:")

        target_service_obj = None
        target_service_uuid_obj = btle.UUID(CONFIRMATION_SERVICE_UUID) # Create UUID object for comparison

        for srv in services:
            print(f"      -> Service [UUID: {str(srv.uuid).upper()}] (Handle Start: {srv.hndStart:04X}, Handle End: {srv.hndEnd:04X})")
            # Compare UUID objects directly
            if srv.uuid == target_service_uuid_obj:
                 print(f"         MATCH FOUND for target UUID {str(target_service_uuid_obj).upper()}")
                 target_service_obj = srv
                 # Don't break here, let it print all services found

        if not target_service_obj:
            print(f"    [Confirmation Worker] ERROR: Target service UUID {CONFIRMATION_SERVICE_UUID} not found among discovered services.")
            return "Service Not Found"

        print(f"    [Confirmation Worker] Proceeding with matched service {str(target_service_obj.uuid).upper()}")

        # --- MODIFICATION START for Characteristic Discovery ---
        print(f"    [Confirmation Worker] Discovering ALL characteristics within service {str(target_service_obj.uuid).upper()}...")
        characteristics = target_service_obj.getCharacteristics() # Get all characteristics for this service
        print(f"    [Confirmation Worker] Characteristic discovery finished. Found {len(characteristics)} characteristics in this service:")

        target_char_obj = None
        # Ensure CONFIRMATION_CHAR_UUID is the full 128-bit string
        target_char_uuid_obj = btle.UUID(CONFIRMATION_CHAR_UUID)

        for char_obj in characteristics:
            # char_obj.uuid might be a UUID object, ensure comparison is robust
            # Properties can be helpful for debugging: char_obj.propertiesToString()
            print(f"      -> Characteristic [UUID: {str(char_obj.uuid).upper()}] (Handle: {char_obj.handle:04X}, Properties: {char_obj.propertiesToString()})")
            if char_obj.uuid == target_char_uuid_obj:
                print(f"         MATCH FOUND for target characteristic UUID {str(target_char_uuid_obj).upper()}")
                target_char_obj = char_obj
                # We can break if we only care about the first match
                # break

        if not target_char_obj:
            print(f"    [Confirmation Worker] ERROR: Target characteristic UUID {CONFIRMATION_CHAR_UUID} not found among discovered characteristics for this service.")
            return "Characteristic Not Found"

        print(f"    [Confirmation Worker] Proceeding with matched characteristic {str(target_char_obj.uuid).upper()}")
        # Use the handle from the discovered characteristic object
        characteristic_handle = target_char_obj.handle
        # --- MODIFICATION END ---

        # Original logic was:
        # characteristic = target_service_obj.getCharacteristics(CONFIRMATION_CHAR_UUID)[0]
        # characteristic_handle = characteristic.getHandle()
        # We now use target_char_obj.handle from the loop above.

        print(f"    [Confirmation Worker] Found Characteristic UUID {CONFIRMATION_CHAR_UUID} (Handle: {characteristic_handle:04X})") # This line might be redundant now but fine

        print(f"    [Confirmation Worker] Writing confirmation payload to handle {characteristic_handle:04X}...")
        peripheral.writeCharacteristic(characteristic_handle, confirmation_payload, withResponse=False)
        print(f"    [Confirmation Worker] Confirmation successfully sent to {mac_address}.")
        return "Success"

    # Keep the rest of the exception handling and finally block the same
    except btle.BTLEException as e:
        print(f"  [Confirmation Worker] ERROR: BLE error during confirmation to {mac_address}: {e}", file=sys.stderr)
        if "Failed to connect" in str(e): return "Connection Failed"
        elif "disconnected" in str(e): return "Disconnected"
        # Check if error happened during discovery phase
        elif "discover" in str(e) or "Attribute handle" in str(e): return "Discovery Failed"
        else: return f"BLE Error: {e}"
    except IndexError:
        print(f"  [Confirmation Worker] ERROR: Confirmation Characteristic UUID {CONFIRMATION_CHAR_UUID} not found on {mac_address}.", file=sys.stderr)
        return "Characteristic Not Found"
    except Exception as e:
        print(f"  [Confirmation Worker] ERROR: Unexpected error during confirmation to {mac_address}: {e}", file=sys.stderr)
        return f"Unexpected Error: {e}"
    finally:
        if peripheral and peripheral.getState() == "conn":
            try:
                print(f"    [Confirmation Worker] Disconnecting from {mac_address}...")
                peripheral.disconnect()
                print(f"    [Confirmation Worker] Disconnected.")
            except btle.BTLEException as e:
                print(f"    [Confirmation Worker] Note: Error during disconnect: {e}", file=sys.stderr)

# --- Main Execution ---
def main():
    # Initialize database
    init_database()

    # Scanner setup
    scanner = btle.Scanner()
    print(f"Scanning for BLE devices for {SCAN_DURATION} seconds...")
    devices = scanner.scan(SCAN_DURATION)
    print(f"Scan complete. Found {len(devices)} devices.")
    print("-" * 30)

    # Check if log file needs a header
    log_needs_header = not os.path.exists(LOG_FILE_NAME) or os.path.getsize(LOG_FILE_NAME) == 0

    # Start confirmation thread
    confirmation_thread = threading.Thread(target=confirmation_worker, daemon=True)
    confirmation_thread.start()

    # Process scanned devices
    with open(LOG_FILE_NAME, 'a', encoding='utf-8') as log_file:
        if log_needs_header:
            log_file.write("Timestamp, MAC Address, RSSI, Device ID, Sensor Value, Confirmation Status\n")
            print(f"Writing header to new log file: {LOG_FILE_NAME}")

        print(f"Processing devices, logging to {LOG_FILE_NAME}, and queuing confirmations...")

        for dev in devices:
            print(f"Device (MAC: {dev.addr}, AddrType: {dev.addrType}, RSSI: {dev.rssi} dB)")
            manufacturer_data_found = False
            parsed_data = False
            confirmation_status = "N/A"

            for (adtype, desc, value) in dev.getScanData():
                if adtype == 0xFF:
                    manufacturer_data_found = True
                    if len(value) >= 4:
                        try:
                            manufacturer_id = struct.unpack("<H", bytes.fromhex(value[:4]))[0]
                            if manufacturer_id == TARGET_MANUFACTURER_ID:
                                print(f"  Found matching Manufacturer ID: 0x{manufacturer_id:04X}")
                                if len(value) >= EXPECTED_TOTAL_HEX_LEN:
                                    device_id = struct.unpack("<I", bytes.fromhex(value[4:12]))[0]
                                    sensor_value = struct.unpack("<f", bytes.fromhex(value[12:20]))[0]
                                    parsed_data = True
                                    print(f"    Parsed data: Device ID={device_id}, Sensor Value={sensor_value:.4f}")

                                    data_queue.put((dev, device_id))
                                    confirmation_status = "Queued"

                                    query_database(dev.addr, device_id, sensor_value)

                                    break
                                else:
                                    print(f"  Matching Manuf ID, but data length insufficient.")
                        except (ValueError, struct.error, Exception) as e:
                            print(f"  Error processing Manufacturer Specific Data: {e}", file=sys.stderr)

            timestamp = datetime.datetime.now().isoformat()
            if parsed_data:
                if dev.addr in confirmation_status_dict:
                    confirmation_status = confirmation_status_dict.pop(dev.addr)
                log_entry = f"{timestamp},{dev.addr},{dev.rssi},{device_id},{sensor_value:.4f},{confirmation_status}\n"
                log_file.write(log_entry)
                print(f"    Logged data to {LOG_FILE_NAME} (Confirmation: {confirmation_status})")
                insert_log_to_db(timestamp, dev.addr, dev.rssi, device_id, sensor_value, confirmation_status)
            elif manufacturer_data_found:
                print("  Manufacturer Specific Data found, but did not match target format/ID or failed parsing.")
                log_entry = f"{timestamp},{dev.addr},{dev.rssi},N/A,N/A,Not Parsed\n"
                log_file.write(log_entry)
                insert_log_to_db(timestamp, dev.addr, dev.rssi, None, None, "Not Parsed")
            else:
                print("  No Manufacturer Specific Data found for this device.")
                log_entry = f"{timestamp},{dev.addr},{dev.rssi},N/A,N/A,No Manuf Data\n"
                log_file.write(log_entry)
                insert_log_to_db(timestamp, dev.addr, dev.rssi, None, None, "No Manuf Data")

            print("-" * 20)

    print(f"Processing complete. Data appended to {LOG_FILE_NAME}. Confirmation attempts are running in the background.")

    data_queue.put(None)
    confirmation_thread.join()

# --- Run the main ---
if __name__ == "__main__":
    main()