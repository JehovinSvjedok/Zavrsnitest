from bluepy import btle
import struct
import datetime
import os
import time
import threading
import queue
import sqlite3

# --- Configuration ---
LOG_FILE_NAME = "log_scan.txt"
DB_PATH = "log_db.db"
TARGET_MANUFACTURER_ID = 0xFFFF
EXPECTED_PAYLOAD_HEX_LEN = 8 + 8
EXPECTED_TOTAL_HEX_LEN = 4 + EXPECTED_PAYLOAD_HEX_LEN
CONFIRMATION_SERVICE_UUID = "1234"
CONFIRMATION_CHAR_UUID = "5678"
SCAN_DURATION = 10.0

# --- Global Queue ---
data_queue = queue.Queue()

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
        send_confirmation(dev, device_id)
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
        peripheral = btle.Peripheral(mac_address, addr_type, timeout=5.0)

        print(f"    [Confirmation Worker] Connected. Discovering services...")
        service = peripheral.getServiceByUUID(CONFIRMATION_SERVICE_UUID)
        print(f"    [Confirmation Worker] Found Service UUID {CONFIRMATION_SERVICE_UUID}")
        characteristic = service.getCharacteristics(CONFIRMATION_CHAR_UUID)[0]
        characteristic_handle = characteristic.getHandle()
        print(f"    [Confirmation Worker] Found Characteristic UUID {CONFIRMATION_CHAR_UUID} (Handle: {characteristic_handle:04X})")

        print(f"    [Confirmation Worker] Writing confirmation payload to handle {characteristic_handle:04X}...")
        peripheral.writeCharacteristic(characteristic_handle, confirmation_payload, withResponse=True)
        print(f"    [Confirmation Worker] Confirmation successfully sent to {mac_address}.")
        return True
    except btle.BTLEException as e:
        print(f"  [Confirmation Worker] ERROR: BLE error during confirmation to {mac_address}: {e}")
        return False
    except IndexError:
        print(f"  [Confirmation Worker] ERROR: Confirmation Characteristic UUID {CONFIRMATION_CHAR_UUID} not found on {mac_address}.")
        return False
    except Exception as e:
        print(f"  [Confirmation Worker] ERROR: Unexpected error during confirmation to {mac_address}: {e}")
        return False
    finally:
        if peripheral:
            try:
                print(f"    [Confirmation Worker] Disconnecting from {mac_address}...")
                peripheral.disconnect()
                print(f"    [Confirmation Worker] Disconnected.")
            except btle.BTLEException as e:
                print(f"    [Confirmation Worker] Note: Error during disconnect: {e}")

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
            log_file.write("Timestamp, MAC Address, RSSI, Device ID, Sensor Value, Confirmation Attempted\n")
            print(f"Writing header to new log file: {LOG_FILE_NAME}")

        print(f"Processing devices, logging to {LOG_FILE_NAME}, and queuing confirmations...")

        for dev in devices:
            print(f"Device (MAC: {dev.addr}, AddrType: {dev.addrType}, RSSI: {dev.rssi} dB)")
            manufacturer_data_found = False
            parsed_data = False

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
                            print(f"  Error processing Manufacturer Specific Data: {e}")

            if parsed_data:
                timestamp = datetime.datetime.now().isoformat()
                log_entry = f"{timestamp},{dev.addr},{dev.rssi},{device_id},{sensor_value:.4f},{confirmation_status}\n"
                log_file.write(log_entry)
                print(f"    Logged data to {LOG_FILE_NAME} (Confirmation: {confirmation_status})")

                # Insert into SQLite DB
                insert_log_to_db(timestamp, dev.addr, dev.rssi, device_id, sensor_value, confirmation_status)
            elif manufacturer_data_found:
                print("  Manufacturer Specific Data found, but did not match target format/ID or failed parsing.")
            else:
                print("  No Manufacturer Specific Data found for this device.")

            print("-" * 20)

    print(f"Processing complete. Data appended to {LOG_FILE_NAME}. Confirmation attempts are running in the background.")

    # Optional cleanup
    # data_queue.join()
    # print("Confirmation queue is empty. Exiting.")
    # data_queue.put(None)
    # confirmation_thread.join()

# --- Run the main ---
if __name__ == "__main__":
    main()
