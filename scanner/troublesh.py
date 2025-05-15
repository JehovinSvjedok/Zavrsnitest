from bluepy import btle
import time

ADVERTISER_MAC_ADDRESS = "D8:3A:DD:37:64:E3"

def test_gatt_connectivity():
    print(f"Attempting to connect to GATT server: {ADVERTISER_MAC_ADDRESS}")
    peripheral = None
    try:
        peripheral = btle.Peripheral(ADVERTISER_MAC_ADDRESS, addrType=btle.ADDR_TYPE_PUBLIC)
        time.sleep(0.5)  # Add a 0.5-second delay after connecting
        print("Connection successful.")
        return True
    except btle.BTLEException as e:
        print(f"Error during connection: {e}")
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