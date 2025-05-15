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
LOG_FILE_NAME = "advertisement_log.txt"
DB_PATH = "advertisement_db.db"
TARGET_MANUFACTURER_ID = 0xFFFF
EXPECTED_PAYLOAD_HEX_LEN = 8 + 8
EXPECTED_TOTAL_HEX_LEN = 4 + EXPECTED_PAYLOAD_HEX_LEN
SCAN_DURATION = 10.0

# --- Initialize Database ---
def init_database():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS advertisements (
            timestamp TEXT,
            mac_address TEXT,
            rssi INTEGER,
            device_id INTEGER,
            sensor_value REAL
        )
    ''')
    conn.commit()
    conn.close()

# --- Insert Log into Database ---
def insert_log_to_db(timestamp, mac_address, rssi, device_id, sensor_value):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO advertisements (timestamp, mac_address, rssi, device_id, sensor_value)
        VALUES (?, ?, ?, ?, ?)
    ''', (timestamp, mac_address, rssi, device_id, sensor_value))
    conn.commit()
    conn.close()

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

    # Process scanned devices
    with open(LOG_FILE_NAME, 'a', encoding='utf-8') as log_file:
        if log_needs_header:
            log_file.write("Timestamp, MAC Address, RSSI, Device ID, Sensor Value\n")
            print(f"Writing header to new log file: {LOG_FILE_NAME}")

        print(f"Processing devices, logging to {LOG_FILE_NAME}...")

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

                                    timestamp = datetime.datetime.now().isoformat()
                                    log_entry = f"{timestamp},{dev.addr},{dev.rssi},{device_id},{sensor_value:.4f}\n"
                                    log_file.write(log_entry)
                                    print(f"    Logged data to {LOG_FILE_NAME}")
                                    insert_log_to_db(timestamp, dev.addr, dev.rssi, device_id, sensor_value)
                                    break # Break after successful parse and log
                                else:
                                    print(f"  Matching Manuf ID, but data length insufficient.")
                        except (ValueError, struct.error, Exception) as e:
                            print(f"  Error processing Manufacturer Specific Data: {e}", file=sys.stderr)

            if manufacturer_data_found and not parsed_data:
                print("  Manufacturer Specific Data found, but did not match target format/ID or failed parsing.")
            elif not manufacturer_data_found:
                print("  No Manufacturer Specific Data found for this device.")

            print("-" * 20)

    print(f"Processing complete. Data appended to {LOG_FILE_NAME}.")

# --- Run the main ---
if __name__ == "__main__":
    main()