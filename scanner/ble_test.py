from bluepy import btle
import struct
import datetime # Import datetime for timestamps
import os       # Import os to check if file exists for header

# --- Configuration ---
LOG_FILE_NAME = "log_scan.txt"
TARGET_MANUFACTURER_ID = 0xFFFF
EXPECTED_PAYLOAD_HEX_LEN = 8 + 8
EXPECTED_TOTAL_HEX_LEN = 4 + EXPECTED_PAYLOAD_HEX_LEN

# --- Scanner Setup ---
scanner = btle.Scanner()
print("Scanning for BLE devices for 10 seconds...")
devices = scanner.scan(10.0)
print(f"Scan complete. Found {len(devices)} devices.")
print("-" * 30)

# --- Placeholder Database Function ---
# (You can keep this or remove if only logging is needed now)
def query_database(mac_address, device_id, sensor_value):
    """Placeholder function for database interaction."""
    print(f"  [Database Query Placeholder] MAC: {mac_address}, Device ID: {device_id}, Sensor Value: {sensor_value:.4f}")

# --- Check if log file needs a header ---
# Add header only if the file doesn't exist or is empty
log_needs_header = not os.path.exists(LOG_FILE_NAME) or os.path.getsize(LOG_FILE_NAME) == 0

# --- Processing Devices and Logging ---
# Open the log file in append mode ('a'). The 'with' statement ensures it's closed properly.
with open(LOG_FILE_NAME, 'a', encoding='utf-8') as log_file:

    # Write header if needed
    if log_needs_header:
        log_file.write("Timestamp, MAC Address, RSSI, Device ID, Sensor Value\n")
        print(f"Writing header to new log file: {LOG_FILE_NAME}")

    print(f"Processing devices and logging to {LOG_FILE_NAME}...")

    for dev in devices:
        # Print device info to console for real-time feedback
        print(f"Device (MAC: {dev.addr}, AddrType: {dev.addrType}, RSSI: {dev.rssi} dB)")
        manufacturer_data_found = False
        parsed_data = False

        # Iterate through Advertising Data elements
        for (adtype, desc, value) in dev.getScanData():
            # AD Type 0xFF means Manufacturer Specific Data
            if adtype == 0xFF:
                manufacturer_data_found = True
                if len(value) >= 4:
                    try:
                        # 1. Extract and check Manufacturer ID
                        manufacturer_id_hex = value[:4]
                        manufacturer_id_bytes = bytes.fromhex(manufacturer_id_hex)
                        manufacturer_id = struct.unpack("<H", manufacturer_id_bytes)[0]

                        # 2. Check if it matches our target
                        if manufacturer_id == TARGET_MANUFACTURER_ID:
                            print(f"  Found matching Manufacturer ID: 0x{manufacturer_id:04X}")

                            # 3. Check if there's enough data for the payload
                            if len(value) >= EXPECTED_TOTAL_HEX_LEN:
                                # Extract the specific parts
                                device_id_hex = value[4:12]
                                sensor_value_hex = value[12:20]
                                device_id_bytes = bytes.fromhex(device_id_hex)
                                sensor_value_bytes = bytes.fromhex(sensor_value_hex)

                                # 4. Unpack the data
                                device_id = struct.unpack("<I", device_id_bytes)[0]
                                sensor_value = struct.unpack("<f", sensor_value_bytes)[0]

                                print(f"    Successfully parsed data:")
                                print(f"      Raw Hex Payload: {value[4:]}")
                                print(f"      Device ID (hex {device_id_hex}): {device_id}")
                                print(f"      Sensor Value (hex {sensor_value_hex}): {sensor_value:.4f}")

                                # 5. Get current timestamp
                                timestamp = datetime.datetime.now().isoformat()

                                # 6. Format the log entry (CSV style)
                                log_entry = f"{timestamp},{dev.addr},{dev.rssi},{device_id},{sensor_value:.4f}\n"

                                # 7. Write the log entry to the file
                                log_file.write(log_entry)
                                print(f"    Logged data to {LOG_FILE_NAME}")

                                parsed_data = True

                                # 8. Optional: Call database function if still needed
                                query_database(dev.addr, device_id, sensor_value)

                                # Optional: break if only one matching entry needed per device
                                # break

                            else:
                                print(f"  Matching Manufacturer ID, but data length insufficient.")
                                print(f"    Expected total hex length >= {EXPECTED_TOTAL_HEX_LEN}, Got: {len(value)}")
                                print(f"    Full Value: {value}")

                    except ValueError as e:
                        print(f"  Error converting hex string to bytes: {e}. Value: {value}")
                    except struct.error as e:
                        print(f"  Error unpacking data: {e}. Value: {value}")
                    except Exception as e:
                        print(f"  An unexpected error occurred during parsing: {e}. Value: {value}")

        if not manufacturer_data_found:
            print("  No Manufacturer Specific Data found for this device.")
        elif not parsed_data:
             # This condition might be met if manuf ID matches but length is wrong
             print("  Matching Manufacturer Specific Data found, but failed to parse required fields.")


        print("-" * 20) # Separator in console output

print(f"Logging complete. Data appended to {LOG_FILE_NAME}")

# --- Main Guard ---
if __name__ == "__main__":
    pass