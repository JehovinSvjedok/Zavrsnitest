from bluepy import btle
import struct
import time

ADVERTISER_MAC_ADDRESS = "d8:3a:dd:37:64:e3"  # Replace with the actual MAC address
CONFIRMATION_SERVICE_UUID = "1234"
CONFIRMATION_CHAR_UUID = "5678"
SCAN_TIMEOUT = 5.0
CONNECT_TIMEOUT = 5.0

def test_gatt_connectivity():
    print(f"Attempting to connect to GATT server: {ADVERTISER_MAC_ADDRESS}")
    peripheral = None
    try:
        scanner = btle.Scanner()
        devices = scanner.scan(SCAN_TIMEOUT)
        found_advertiser = False
        for dev in devices:
            if dev.addr == ADVERTISER_MAC_ADDRESS:
                found_advertiser = True
                print(f"Advertiser found with RSSI: {dev.rssi} dB")
                break

        if not found_advertiser:
            print(f"Error: Advertiser with MAC address {ADVERTISER_MAC_ADDRESS} not found within {SCAN_TIMEOUT} seconds.")
            return False

        print(f"Connecting to {ADVERTISER_MAC_ADDRESS}...")
        peripheral = btle.Peripheral(ADVERTISER_MAC_ADDRESS, addrType=btle.ADDR_TYPE_PUBLIC, timeout=CONNECT_TIMEOUT)
        print("Connection successful.")

        print(f"Discovering service with UUID: {CONFIRMATION_SERVICE_UUID}")
        service = peripheral.getServiceByUUID(CONFIRMATION_SERVICE_UUID)
        if service:
            print(f"Service found: {service.uuid}")
            characteristics = service.getCharacteristics(CONFIRMATION_CHAR_UUID)
            if characteristics:
                characteristic = characteristics[0]
                print(f"Characteristic found: {characteristic.uuid}, Handle: {characteristic.getHandle():04X}, Properties: {characteristic.propertiesToString()}")

                if characteristic.supports_write():
                    test_data = struct.pack("<I", 12345)  # Example 4-byte data
                    try:
                        print(f"Attempting to write value: {test_data.hex()} to characteristic...")
                        peripheral.writeCharacteristic(characteristic.getHandle(), test_data, withResponse=True)
                        print("Write operation successful.")
                        return True
                    except btle.BTLEException as e:
                        print(f"Error during write operation: {e}")
                        return False
                else:
                    print("Error: Characteristic does not support write.")
                    return False
            else:
                print(f"Error: Characteristic with UUID {CONFIRMATION_CHAR_UUID} not found in service.")
                return False
        else:
            print(f"Error: Service with UUID {CONFIRMATION_SERVICE_UUID} not found on the device.")
            return False

    except btle.BTLEException as e:
        print(f"Error during connection or scanning: {e}")
        return False
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return False
    finally:
        if peripheral:
            try:
                peripheral.disconnect()
                print("Disconnected.")
            except btle.BTLEException as e:
                print(f"Error during disconnection: {e}")
        else:
            print("No active connection to disconnect.")

if __name__ == "__main__":
    if test_gatt_connectivity():
        print("GATT connectivity test successful.")
    else:
        print("GATT connectivity test failed.")