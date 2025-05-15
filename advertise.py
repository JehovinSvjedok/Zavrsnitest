import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import struct
import sys
import os
# import threading # Not used in this version
# import time     # Not used in this version

# --- Configuration ---
APP_BASE_PATH = '/org/zavrsni/example' # D-Bus path for your application
# SERVICE_NAME = 'service0'          # Part of the D-Bus path for the service
# CHARACTERISTIC_NAME = 'char0'      # Part of the D-Bus path for the characteristic

# --- USE FULL 128-bit UUIDs consistently ---
ADVERTISING_SERVICE_UUID = '0000abcd-0000-1000-8000-00805f9b34fb' # Changed UUID
# CONFIRMATION_CHAR_UUID = '00005678-0000-1000-8000-00805f9b34fb'

MANUFACTURER_ID = 0xFFFF # Your custom manufacturer ID
DB_PATH = "advertisements.db"   # Database file (not used in this version)

# --- BlueZ/DBus Constants ---
BLUEZ_SERVICE_NAME = 'org.bluez'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
ADAPTER_IFACE = 'org.bluez.Adapter1'
# GATT_SERVICE_IFACE = 'org.bluez.GattService1'
# GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1'

# --- Find Bluetooth Adapter ---
def find_adapter(bus):
    """Finds the first Bluetooth adapter path."""
    try:
        remote_om = dbus.Interface(bus.get_object(BLUEZ_SERVICE_NAME, '/'), DBUS_OM_IFACE)
        objects = remote_om.GetManagedObjects()
        for path, interfaces in objects.items():
            if ADAPTER_IFACE in interfaces:
                print(f"Found adapter at {path}")
                return path
    except dbus.exceptions.DBusException as e:
        print(f"Error finding adapter: {e}", file=sys.stderr)
        print("Is the BlueZ service running?", file=sys.stderr)
    return None

# --- Advertisement Definition ---
class Advertisement(dbus.service.Object):
    """
    Custom D-Bus object representing the LE Advertisement data.
    """
    PATH_BASE = os.path.join(APP_BASE_PATH, 'advertisement')

    def __init__(self, bus, index, device_id, sensor_value):
        self.path = self.PATH_BASE + str(index)
        self.bus = bus
        self.ad_type = 'peripheral' # Connectable advertisement
        # --- Use Full UUID in advertisement data ---
        self.service_uuids = [ADVERTISING_SERVICE_UUID] # Using a different UUID
        # --- End UUID Change ---
        self.local_name = "Pikachu_Adv_Only" # Updated name
        self.include_tx_power = True # Include TX power level in advertisement
        self.device_id = device_id
        self.sensor_value = sensor_value
        dbus.service.Object.__init__(self, bus, self.path)
        print(f"Advertisement Object created at {self.path}")

    def get_properties(self):
        """Returns the properties dictionary for this advertisement."""
        # Pack Device ID (4 bytes, unsigned int, little-endian)
        # Pack Sensor Value (4 bytes, float, little-endian)
        try:
            manuf_data_payload = struct.pack("<I", self.device_id) + struct.pack("<f", self.sensor_value)
            # print(f"  Manufacturer Data Payload: {manuf_data_payload.hex()}") # Debug
        except struct.error as e:
             print(f"ERROR packing manufacturer data: {e}", file=sys.stderr)
             manuf_data_payload=b'' # Empty payload on error

        properties = {
            LE_ADVERTISEMENT_IFACE: {
                'Type': self.ad_type,
                'LocalName': dbus.String(self.local_name),
                'ServiceUUIDs': dbus.Array(self.service_uuids, signature='s'),
                'ManufacturerData': dbus.Dictionary({
                    dbus.UInt16(MANUFACTURER_ID): dbus.ByteArray(manuf_data_payload)
                }, signature='qv'),
                'IncludeTxPower': dbus.Boolean(self.include_tx_power)
                # Add other advertisement options here if needed
                # 'Discoverable': dbus.Boolean(True),
            }
        }
        return properties

    def get_path(self):
        """Returns the D-Bus object path for this advertisement."""
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        """Handles GetAll method for D-Bus Properties interface."""
        if interface != LE_ADVERTISEMENT_IFACE:
            raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")
        return self.get_properties()[LE_ADVERTISEMENT_IFACE]

    @dbus.service.method(LE_ADVERTISEMENT_IFACE, in_signature='', out_signature='')
    def Release(self):
        """Called by BlueZ when the advertisement is unregistered."""
        print(f"Advertisement {self.path} Released.")

# --- Registration Success/Error Handlers ---
def generic_reply_handler(message):
    print(f"  -> D-Bus Reply: {message if message else 'Success (No specific reply)'}")

def generic_error_handler(error):
    print(f"  -> D-Bus Error: {error}", file=sys.stderr)

# --- Main ---
def main():
    # Set up DBus main loop
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus() # Use System Bus for BlueZ

    adapter_path = find_adapter(bus)
    if not adapter_path:
        print("ERROR: No Bluetooth adapter found. Exiting.", file=sys.stderr)
        sys.exit(1)

    # Get BlueZ objects for the adapter
    adapter_obj = bus.get_object(BLUEZ_SERVICE_NAME, adapter_path)
    adapter_props = dbus.Interface(adapter_obj, DBUS_PROP_IFACE)

    # Optional: Power on the adapter if it's off
    try:
        powered = adapter_props.Get(ADAPTER_IFACE, "Powered")
        if not powered:
            print("Adapter is off. Attempting to power on...")
            adapter_props.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(1))
            # time.sleep(1) # Give it a moment to power up
            powered = adapter_props.Get(ADAPTER_IFACE, "Powered")
            if not powered:
                print("ERROR: Failed to power on adapter.", file=sys.stderr)
                # sys.exit(1) # Decide if you want to exit or continue
        else:
            print("Adapter is already powered on.")
    except Exception as e:
        print(f"Warning: Could not get/set adapter power state: {e}", file=sys.stderr)

    # Get manager objects
    adv_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)

    # Create our advertisement object with example data
    # Use different device ID/sensor value if desired
    adv_device_id = 12345
    adv_sensor_value = 25
    adv = Advertisement(bus, 0, adv_device_id, adv_sensor_value)

    # Main event loop
    mainloop = GLib.MainLoop()

    # --- Register Advertisement ---
    print("Registering Advertisement...")
    try:
        adv_manager.RegisterAdvertisement(adv.get_path(), {},
            reply_handler=lambda: print("  Advertisement registered successfully."),
            error_handler=lambda e: print(f"  ERROR: Failed to register Advertisement: {e}", file=sys.stderr)
        )
    except dbus.exceptions.DBusException as e:
        print(f"  ERROR: DBusException during Advertisement registration: {e}", file=sys.stderr)
        mainloop.quit()
        return

    # --- Run Main Loop ---
    try:
        print("\nAdvertising only.")
        print(f"Advertising Name: {adv.local_name}")
        print(f"Service UUID: {ADVERTISING_SERVICE_UUID}")
        print(f"Manufacturer ID: 0x{MANUFACTURER_ID:04X}")
        print(f" Data: DeviceID={adv_device_id}, SensorVal={adv_sensor_value}")
        print("Press Ctrl+C to stop.")
        mainloop.run()
    except KeyboardInterrupt:
        print("\nStopping advertiser...")
    except Exception as e:
        print(f"\nERROR during main loop: {e}", file=sys.stderr)
    finally:
        # --- Cleanup ---
        print("Unregistering Advertisement...")
        try:
            adv_manager.UnregisterAdvertisement(adv.get_path())
            print("  Advertisement unregistered.")
        except Exception as e:
            print(f"  Warning: Error unregistering advertisement: {e}", file=sys.stderr)

        if mainloop.is_running():
            mainloop.quit()
        print("Advertiser stopped.")

if __name__ == '__main__':
    main()