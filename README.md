# BLE Advertisement Data Logger

This project is a Python script that scans for Bluetooth Low Energy (BLE) devices and logs specific information found within the manufacturer-specific data of their advertisements. It filters for advertisements with a defined manufacturer ID and extracts a device ID and sensor value from the payload. This data is then stored in a log file and an SQLite database.

## Purpose

The primary goal of this script is to passively collect data being broadcasted by BLE devices adhering to a specific manufacturer data format. This can be useful for monitoring sensor readings, identifying devices, or other data acquisition tasks where devices are advertising information.

## Prerequisites

Before running this script, ensure you have the following installed:

* **Python 3:** (Recommended version 3.6 or higher)
* **bluepy:** A Python interface to Bluetooth LE on Linux. You can install it using pip:
    ```bash
    pip install bluepy
    ```
    **Note:** `bluepy` often requires root privileges to run due to its direct interaction with the Bluetooth hardware.
* **SQLite3:** Python has built-in support for SQLite3, so you likely don't need to install it separately.

## Setup and Configuration

1.  **Clone the repository** (if you downloaded the script from one) or save the Python code as a `.py` file (e.g., `ble_logger.py`).

2.  **Configuration:** Open the Python script (`ble_logger.py`) and review the `--- Configuration ---` section. Adjust the following variables as needed:

    * `LOG_FILE_NAME`: The name of the text file where the raw log data will be appended. Defaults to `advertisement_log.txt`.
    * `DB_PATH`: The path to the SQLite database file where the parsed data will be stored. Defaults to `advertisement_db.db`.
    * `TARGET_MANUFACTURER_ID`: The 16-bit manufacturer ID (in hexadecimal format, e.g., `0xFFFF`) that the script will look for in the advertisement data. Only advertisements with this ID will be processed. Defaults to `0xFFFF`.
    * `EXPECTED_PAYLOAD_HEX_LEN`: The expected length of the data payload (excluding the manufacturer ID) in hexadecimal characters. In the current script, it's set to 16 (8 bytes for device ID + 8 bytes for sensor value).
    * `EXPECTED_TOTAL_HEX_LEN`: The expected total length of the manufacturer-specific data in hexadecimal characters (4 bytes for manufacturer ID + `EXPECTED_PAYLOAD_HEX_LEN`).
    * `SCAN_DURATION`: The duration (in seconds) for which the script will scan for BLE devices in each run. Defaults to `10.0`.

## Running the Script

1.  Open your terminal or command prompt.
2.  Navigate to the directory where you saved the `ble_logger.py` file.
3.  Run the script with root privileges (required by `bluepy`):
    ```bash
    sudo python3 ble_logger.py
    ```

    You might be prompted for your administrator password.

## Output

The script will output information to the console during its execution, including:

* Scanning status and the number of devices found.
* Details of each scanned device (MAC address, address type, RSSI).
* Information about whether the target manufacturer ID was found.
* Parsed `device_id` and `sensor_value` if the manufacturer data matches the expected format.
* Logs written to the log file and the SQLite database.

The data will be stored in two places:

* **Log File (`advertisement_log.txt`):** A simple text file where each line represents a processed advertisement, containing the timestamp, MAC address, RSSI, device ID, and sensor value.
* **SQLite Database (`advertisement_db.db`):** A structured database with a table named `advertisements` containing the same information as the log file. You can use any SQLite browser to view and query this database.

## Stopping the Script

To stop the script, press `Ctrl + C` in the terminal where it is running.

## Notes and Limitations

* **Root Privileges:** Running `bluepy` typically requires root privileges. Be aware of the security implications of running scripts with elevated permissions.
* **BLE Hardware:** This script relies on the Bluetooth hardware of the system it's running on. Ensure your system has a working Bluetooth adapter.
* **Manufacturer Data Format:** The script is specifically designed to parse manufacturer data with a 16-bit manufacturer ID followed by a 4-byte unsigned integer (`device_id`) and a 4-byte float (`sensor_value`), both in little-endian byte order. If the advertising devices use a different format, you'll need to modify the `struct.unpack` calls in the script.
* **Error Handling:** The script includes basic error handling for parsing manufacturer data, but you might want to enhance it based on your specific needs.
* **Scanning Frequency:** The `SCAN_DURATION` determines how long the script scans in each run. You might want to adjust this and potentially wrap the main logic in a loop with a delay to continuously monitor advertisements.

## Further Development

Potential enhancements for this project could include:

* More robust error handling and logging.
* Configuration options via command-line arguments or a separate configuration file.
* Filtering based on device name or service UUIDs in addition to manufacturer ID.
* Real-time data visualization or integration with other data processing systems.
* More flexible parsing of manufacturer-specific data based on different formats.
