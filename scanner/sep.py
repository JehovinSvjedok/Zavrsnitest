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
TARGET_MANUFACTURER_ID = 0xFFFFF  # MODIFIED: Target the specific 20-bit ID

# Lengths in HEX CHARACTERS (1 byte = 2 hex chars)
MANUFACTURER_ID_HEX_LEN = 6      # 3 bytes for 0xFFFFF (e.g., "FFFFFF" if 0xFFFFFF, "FFFF0F" for 0x0FFFFF)
DEVICE_ID_HEX_LEN = 8            # 4 bytes for unsigned int (<I)
SENSOR_VALUE_HEX_LEN = 8         # 4 bytes for float (<f)

# Total length of the expected data part within the manufacturer specific data field
# This is Device ID + Sensor Value
EXPECTED_PAYLOAD_HEX_LEN = DEVICE_ID_HEX_LEN + SENSOR_VALUE_HEX_LEN

# Total length of the manufacturer specific data value string we are interested in
# This is Manufacturer ID + Device ID + Sensor Value
EXPECTED_TOTAL_HEX_LEN = MANUFACTURER_ID_HEX_LEN + EXPECTED_PAYLOAD_HEX_LEN

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
        confirmation_payload = struct.pack('<I', parsed_device_id) # Device ID is <I (4 bytes)
        print(f"    [Confirmation Worker] Prepared confirmation payload: {confirmation_payload.hex()}")

        print(f"    [Confirmation Worker] Connecting to {mac_address} (Type: {addr_type})...")
        peripheral = btle.Peripheral()
        # Ensure connect timeout is explicitly passed if needed by your bluepy version or setup
        peripheral.connect(mac_address, addr_type) # Removed timeout=CONNECT_TIMEOUT if not supported or causing issues
                                                  # Add it back if your bluepy version expects it:
                                                  # peripheral.connect(mac_address, addr_type, timeout=CONNECT_TIMEOUT)
        print(f"    [Confirmation Worker] Connected.")

        print(f"    [Confirmation Worker] Discovering ALL services...")
        services = peripheral.getServices()
        print(f"    [Confirmation Worker] Discovery finished. Found {len(services)} services:")

        target_service_obj = None
        target_service_uuid_obj = btle.UUID(CONFIRMATION_SERVICE_UUID)

        for srv in services:
            print(f"      -> Service [UUID: {str(srv.uuid).upper()}] (Handle Start: {srv.hndStart:04X}, Handle End: {srv.hndEnd:04X})")
            if srv.uuid == target_service_uuid_obj:
                print(f"          MATCH FOUND for target UUID {str(target_service_uuid_obj).upper()}")
                target_service_obj = srv
                # Don't break here, let it print all services found

        if not target_service_obj:
            print(f"    [Confirmation Worker] ERROR: Target service UUID {CONFIRMATION_SERVICE_UUID} not found among discovered services.")
            return "Service Not Found"

        print(f"    [Confirmation Worker] Proceeding with matched service {str(target_service_obj.uuid).upper()}")

        print(f"    [Confirmation Worker] Discovering ALL characteristics within service {str(target_service_obj.uuid).upper()}...")
        characteristics = target_service_obj.getCharacteristics()
        print(f"    [Confirmation Worker] Characteristic discovery finished. Found {len(characteristics)} characteristics in this service:")

        target_char_obj = None
        target_char_uuid_obj = btle.UUID(CONFIRMATION_CHAR_UUID)

        for char_obj in characteristics:
            print(f"      -> Characteristic [UUID: {str(char_obj.uuid).upper()}] (Handle: {char_obj.handle:04X}, Properties: {char_obj.propertiesToString()})")
            if char_obj.uuid == target_char_uuid_obj:
                print(f"          MATCH FOUND for target characteristic UUID {str(target_char_uuid_obj).upper()}")
                target_char_obj = char_obj
                # break # Uncomment if you only need the first match

        if not target_char_obj:
            print(f"    [Confirmation Worker] ERROR: Target characteristic UUID {CONFIRMATION_CHAR_UUID} not found.")
            return "Characteristic Not Found"

        print(f"    [Confirmation Worker] Proceeding with matched characteristic {str(target_char_obj.uuid).upper()}")
        characteristic_handle = target_char_obj.handle

        print(f"    [Confirmation Worker] Writing confirmation payload to handle {characteristic_handle:04X}...")
        peripheral.writeCharacteristic(characteristic_handle, confirmation_payload, withResponse=False)
        print(f"    [Confirmation Worker] Confirmation successfully sent to {mac_address}.")
        return "Success"

    except btle.BTLEException as e:
        print(f"  [Confirmation Worker] ERROR: BLE error during confirmation to {mac_address}: {e}", file=sys.stderr)
        if "Failed to connect" in str(e): return "Connection Failed"
        elif "disconnected" in str(e): return "Disconnected"
        elif "discover" in str(e) or "Attribute handle" in str(e): return "Discovery Failed"
        else: return f"BLE Error: {type(e).__name__}" # More concise error
    except IndexError: # Should be less likely with current characteristic discovery
        print(f"  [Confirmation Worker] ERROR: Confirmation Characteristic UUID {CONFIRMATION_CHAR_UUID} not found on {mac_address}.", file=sys.stderr)
        return "Characteristic Not Found"
    except Exception as e:
        print(f"  [Confirmation Worker] ERROR: Unexpected error during confirmation to {mac_address}: {e}", file=sys.stderr)
        return f"Unexpected Error: {type(e).__name__}"
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
    init_database()
    scanner = btle.Scanner()
    print(f"Scanning for BLE devices for {SCAN_DURATION} seconds...")
    try:
        devices = scanner.scan(SCAN_DURATION)
    except btle.BTLEException as e:
        print(f"ERROR: Failed to scan. Ensure Bluetooth is enabled and you have permissions. Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e: # Catch other potential errors during scan initialization
        print(f"ERROR: An unexpected error occurred during scanning setup: {e}", file=sys.stderr)
        sys.exit(1)
        
    print(f"Scan complete. Found {len(devices)} devices.")
    print("-" * 30)

    log_needs_header = not os.path.exists(LOG_FILE_NAME) or os.path.getsize(LOG_FILE_NAME) == 0

    confirmation_thread = threading.Thread(target=confirmation_worker, daemon=True)
    confirmation_thread.start()

    with open(LOG_FILE_NAME, 'a', encoding='utf-8') as log_file:
        if log_needs_header:
            log_file.write("Timestamp,MAC Address,RSSI,Device ID,Sensor Value,Confirmation Status\n")
            print(f"Writing header to new log file: {LOG_FILE_NAME}")

        print(f"Processing devices, logging to {LOG_FILE_NAME}, and queuing confirmations...")

        for dev in devices:
            print(f"Device (MAC: {dev.addr}, AddrType: {dev.addrType}, RSSI: {dev.rssi} dB)")
            manufacturer_data_found_for_device = False
            parsed_data_successfully = False
            # Reset for each device before attempting to parse and log
            device_id_to_log = None
            sensor_value_to_log = None
            current_confirmation_status = "N/A" # Default if not parsed or not queued

            for (adtype, desc, value_hex_str) in dev.getScanData():
                # adtype 0xFF is Manufacturer Specific Data
                if adtype == 0xFF:
                    manufacturer_data_found_for_device = True
                    print(f"  Found Manufacturer Specific Data (Type 0xFF): {value_hex_str}")

                    # Check if the hex string length is sufficient for the 3-byte Manufacturer ID
                    if len(value_hex_str) >= MANUFACTURER_ID_HEX_LEN:
                        try:
                            # Extract the Manufacturer ID part (first 3 bytes / 6 hex chars)
                            manuf_id_hex = value_hex_str[:MANUFACTURER_ID_HEX_LEN]
                            manuf_id_bytes = bytes.fromhex(manuf_id_hex)

                            # Parse 3-byte little-endian manufacturer ID
                            # (byte0 + byte1*256 + byte2*256*256)
                            if len(manuf_id_bytes) == 3: # Ensure we got 3 bytes
                                extracted_manufacturer_id = manuf_id_bytes[0] + (manuf_id_bytes[1] << 8) + (manuf_id_bytes[2] << 16)
                            else:
                                print(f"    [Parser] Error: Expected 3 bytes for Manuf ID from '{manuf_id_hex}', got {len(manuf_id_bytes)} bytes.")
                                continue # Skip this manufacturer data block

                            print(f"    [Parser] Extracted Manuf ID: 0x{extracted_manufacturer_id:06X}") # Use 6 hex digits for 3 bytes

                            if extracted_manufacturer_id == TARGET_MANUFACTURER_ID:
                                print(f"    [Parser] MATCH! Target Manufacturer ID: 0x{TARGET_MANUFACTURER_ID:06X}")

                                # Check if the length of value_hex_str is sufficient for the full payload
                                if len(value_hex_str) >= EXPECTED_TOTAL_HEX_LEN:
                                    # Define start and end for Device ID (immediately after Manuf ID)
                                    dev_id_start_idx = MANUFACTURER_ID_HEX_LEN
                                    dev_id_end_idx = MANUFACTURER_ID_HEX_LEN + DEVICE_ID_HEX_LEN

                                    # Define start and end for Sensor Value (immediately after Device ID)
                                    sensor_val_start_idx = dev_id_end_idx
                                    sensor_val_end_idx = dev_id_end_idx + SENSOR_VALUE_HEX_LEN
                                    
                                    device_id_hex = value_hex_str[dev_id_start_idx:dev_id_end_idx]
                                    sensor_value_hex = value_hex_str[sensor_val_start_idx:sensor_val_end_idx]

                                    device_id_to_log = struct.unpack("<I", bytes.fromhex(device_id_hex))[0]
                                    sensor_value_to_log = struct.unpack("<f", bytes.fromhex(sensor_value_hex))[0]
                                    
                                    parsed_data_successfully = True
                                    print(f"      [Parser] Parsed: Device ID={device_id_to_log}, Sensor Value={sensor_value_to_log:.4f}")

                                    data_queue.put((dev, device_id_to_log)) # Queue for confirmation
                                    current_confirmation_status = "Queued"
                                    
                                    # Optional: Call query_database if needed for immediate action
                                    # query_database(dev.addr, device_id_to_log, sensor_value_to_log)
                                    
                                    break # Found and processed target manufacturer data for this device, move to next device
                                else:
                                    print(f"    [Parser] Matching Manuf ID (0x{extracted_manufacturer_id:06X}), but data length insufficient for full payload. Expected hex len {EXPECTED_TOTAL_HEX_LEN}, got {len(value_hex_str)}.")
                            # else: # Optional: Log if a non-target manufacturer ID is found
                            #    print(f"    [Parser] Manuf ID 0x{extracted_manufacturer_id:06X} does not match target 0x{TARGET_MANUFACTURER_ID:06X}.")

                        except ValueError: # Catches errors from bytes.fromhex if hex string is invalid
                            print(f"    [Parser] Error: Invalid hex characters in manufacturer data segment: '{value_hex_str[:EXPECTED_TOTAL_HEX_LEN]}'", file=sys.stderr)
                        except struct.error as se:
                            print(f"    [Parser] Error: Struct unpacking error (likely wrong data format/length) for value '{value_hex_str}': {se}", file=sys.stderr)
                        except Exception as e:
                            print(f"    [Parser] Error processing Manufacturer Specific Data (value: '{value_hex_str}'): {e}", file=sys.stderr)
                    else:
                        print(f"  Manufacturer Specific Data found, but too short for even a 3-byte ID. Hex length: {len(value_hex_str)}, Data: '{value_hex_str}'")
                    # Do not break here if you want to check multiple ManufacturerData entries for the same device.
                    # If only one is expected, or the first one found with the ID is enough, then `break` inside the `if extracted_manufacturer_id == TARGET_MANUFACTURER_ID:` block is appropriate.
            
            # Logging logic after checking all scan data entries for the current device
            timestamp = datetime.datetime.now().isoformat()
            
            if parsed_data_successfully:
                # Confirmation status will be "Queued" or later updated by the thread
                # For immediate logging, we use "Queued". If the confirmation finishes fast, it might be updated before this.
                # To get the *final* status, you'd wait for the queue, but here we log what we know at processing time.
                log_status = confirmation_status_dict.pop(dev.addr, current_confirmation_status) # Get status if ready, else use current
                
                log_entry = f"{timestamp},{dev.addr},{dev.rssi},{device_id_to_log},{sensor_value_to_log:.4f},{log_status}\n"
                log_file.write(log_entry)
                print(f"    Logged data to {LOG_FILE_NAME} (Confirmation: {log_status})")
                insert_log_to_db(timestamp, dev.addr, dev.rssi, device_id_to_log, sensor_value_to_log, log_status)
            elif manufacturer_data_found_for_device: # Manufacturer data was found, but not the target or not parsable
                print("  Manufacturer Specific Data found, but did not match target format/ID or failed parsing.")
                log_entry = f"{timestamp},{dev.addr},{dev.rssi},N/A,N/A,Not Parsed\n"
                log_file.write(log_entry)
                insert_log_to_db(timestamp, dev.addr, dev.rssi, None, None, "Not Parsed")
            else: # No manufacturer data at all for this device
                print("  No Manufacturer Specific Data (Type 0xFF) found for this device.")
                log_entry = f"{timestamp},{dev.addr},{dev.rssi},N/A,N/A,No Manuf Data\n"
                log_file.write(log_entry)
                insert_log_to_db(timestamp, dev.addr, dev.rssi, None, None, "No Manuf Data")
            
            print("-" * 20)

    print(f"Processing complete. Data appended to {LOG_FILE_NAME}.")
    print("Confirmation attempts are running/completed. Waiting for any remaining confirmation tasks...")

    data_queue.put(None) # Signal the confirmation worker to exit
    confirmation_thread.join() # Wait for the confirmation thread to finish all tasks
    
    print("All confirmations attempted. Finalizing logs if any status changed.")
    # Re-check and update logs for statuses that might have finished after initial logging pass
    # This is a bit complex as we'd need to either hold off DB writing or update it.
    # For simplicity, the current log reflects status at time of processing or "Queued".
    # A more robust system might update DB records after confirmation_thread.join().
    # For now, we'll just print any remaining statuses in the dictionary (should be empty if processed).
    if confirmation_status_dict:
        print("Note: Some confirmation statuses were updated after initial logging:")
        for mac, status in confirmation_status_dict.items():
            print(f"  Device {mac}: {status} (This status might not be in the CSV/DB if logged as 'Queued' initially)")


if __name__ == "__main__":
    main()