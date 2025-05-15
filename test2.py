import dbus
import dbus.service
import dbus.mainloop.glib
from gi.repository import GLib
import struct
import sys
import os
import threading # Not used in this version, but good practice to import if needed
import time    # Not used in this version
import sqlite3
from datetime import datetime

# --- Configuration ---
APP_BASE_PATH = '/org/zavrsni/example' # D-Bus path for your application
SERVICE_NAME = 'service0'             # Part of the D-Bus path for the service
CHARACTERISTIC_NAME = 'char0'         # Part of the D-Bus path for the characteristic

# --- USE FULL 128-bit UUIDs consistently ---
CONFIRMATION_SERVICE_UUID = '00001234-0000-1000-8000-00805f9b34fb'
CONFIRMATION_CHAR_UUID = '00005678-0000-1000-8000-00805f9b34fb'
# --- End UUID Change ---

MANUFACTURER_ID = 0xFFFF # Your custom manufacturer ID
# CONFIRMATION_BROADCAST_MANUFACTURER_ID = 0xFFFE # Not used currently
DB_PATH = "adv_log_dbsssss.db"  # Database file for logging confirmations

# --- BlueZ/DBus Constants ---
BLUEZ_SERVICE_NAME = 'org.bluez'
DBUS_OM_IFACE = 'org.freedesktop.DBus.ObjectManager'
DBUS_PROP_IFACE = 'org.freedesktop.DBus.Properties'
GATT_MANAGER_IFACE = 'org.bluez.GattManager1'
LE_ADVERTISING_MANAGER_IFACE = 'org.bluez.LEAdvertisingManager1'
ADAPTER_IFACE = 'org.bluez.Adapter1'
GATT_SERVICE_IFACE = 'org.bluez.GattService1'
GATT_CHRC_IFACE = 'org.bluez.GattCharacteristic1'
LE_ADVERTISEMENT_IFACE = 'org.bluez.LEAdvertisement1' # Added for completeness

# --- Store confirmation to SQLite ---
def log_confirmation_to_db(received_device_id):
    """Logs the received device ID and timestamp to the SQLite database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        timestamp = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO confirmations (device_id, timestamp) VALUES (?, ?)",
            (received_device_id, timestamp)
        )
        conn.commit()
        conn.close()
        print(f"[DB] Logged Confirmation: Device ID = {received_device_id}, Timestamp = {timestamp}")
    except Exception as e:
        print(f"[DB ERROR] Could not log confirmation: {e}", file=sys.stderr)

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

# --- GATT Characteristic Definition ---
class ConfirmationCharacteristic(dbus.service.Object):
    """
    Custom D-Bus object representing the Confirmation Characteristic.
    """
    def __init__(self, bus, index, service_path):
        self.path = os.path.join(service_path, CHARACTERISTIC_NAME + str(index))
        self.bus = bus
        self.uuid = CONFIRMATION_CHAR_UUID # Use the full UUID
        self.service = dbus.ObjectPath(service_path)
        # Flags determine permissions. 'write' usually allows write w/o response.
        # Add 'write-request' if write *with* response is strictly needed,
        # but start with just 'write'.
        self.flags = ['write']
        dbus.service.Object.__init__(self, bus, self.path)
        print(f"  Characteristic Object created at {self.path} with UUID {self.uuid}")

    def get_properties(self):
        """Returns the properties dictionary for this characteristic."""
        return {
            GATT_CHRC_IFACE: {
                'Service': self.service,
                'UUID': self.uuid,
                'Flags': self.flags,
                # Add Notify/Indicate properties if needed later
                # 'Notifying': dbus.Boolean(False),
            }
        }

    def get_path(self):
        """Returns the D-Bus object path for this characteristic."""
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        """Handles GetAll method for D-Bus Properties interface."""
        if interface != GATT_CHRC_IFACE:
            raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")
        return self.get_properties()[GATT_CHRC_IFACE]

    @dbus.service.method(GATT_CHRC_IFACE, in_signature='aya{sv}', out_signature='')
    def WriteValue(self, value, options):
        """Handles write requests to this characteristic."""
        received_bytes = bytes(value)
        print(f"\n[Advertiser] Received WriteValue on {self.uuid[-4:]}:")
        print(f"  Raw Bytes: {received_bytes.hex()}")
        # print(f"  Options: {options}") # Options dictionary can be verbose

        try:
            # Expecting 4 bytes for the device ID (unsigned int, little-endian)
            if len(received_bytes) == 4:
                device_id = struct.unpack("<I", received_bytes)[0]
                print(f"  Parsed Device ID: {device_id}")
                # Log the confirmed device ID to the database
                log_confirmation_to_db(device_id)
            else:
                print(f"[Advertiser] ERROR: Unexpected confirmation data length received ({len(received_bytes)} bytes, expected 4).")
        except struct.error as e:
            print(f"[Advertiser] ERROR: Could not unpack received data: {e}")
        except Exception as e:
            print(f"[Advertiser] ERROR: Unexpected error processing WriteValue: {e}")

    # Add ReadValue method if characteristic needs to be readable
    # @dbus.service.method(GATT_CHRC_IFACE, in_signature='a{sv}', out_signature='ay')
    # def ReadValue(self, options):
    #     print("[Advertiser] Read request received (not implemented)")
    #     # Return some value as bytes if readable
    #     return dbus.Array([], signature='y')

# --- GATT Service Definition ---
class ConfirmationService(dbus.service.Object):
    """
    Custom D-Bus object representing the Confirmation Service.
    """
    def __init__(self, bus, index):
        self.path = os.path.join(APP_BASE_PATH, SERVICE_NAME + str(index))
        self.bus = bus
        self.uuid = CONFIRMATION_SERVICE_UUID # Use the full UUID
        self.primary = True
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)
        print(f" Service Object created at {self.path} with UUID {self.uuid}")
        # Add the characteristic to this service
        self.add_characteristic(0)

    def add_characteristic(self, index):
        """Creates and adds a characteristic object to this service."""
        char = ConfirmationCharacteristic(self.bus, index, self.path)
        self.characteristics.append(char)

    def get_properties(self):
        """Returns the properties dictionary for this service."""
        return {
            GATT_SERVICE_IFACE: {
                'UUID': self.uuid,
                'Primary': self.primary,
                'Characteristics': dbus.Array([char.get_path() for char in self.characteristics], signature='o')
            }
        }

    def get_path(self):
        """Returns the D-Bus object path for this service."""
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        """Handles GetAll method for D-Bus Properties interface."""
        if interface != GATT_SERVICE_IFACE:
            raise dbus.exceptions.DBusException(f"Unknown interface: {interface}")
        return self.get_properties()[GATT_SERVICE_IFACE]

# --- GATT Application Definition ---
class Application(dbus.service.Object):
    """
    Root D-Bus object for the GATT application, managing services.
    """
    def __init__(self, bus):
        self.path = APP_BASE_PATH
        self.bus = bus
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)
        print(f"Application Object created at {self.path}")
        # Add the service to this application
        self.add_service(0)

    def add_service(self, index):
        """Creates and adds a service object to this application."""
        service = ConfirmationService(self.bus, index)
        self.services.append(service)

    def get_path(self):
        """Returns the D-Bus object path for this application."""
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_OM_IFACE, out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        """Returns all managed objects (services and characteristics) for this application."""
        response = {}
        # Add application's own properties (if any, usually empty for simple apps)
        # response[self.get_path()] = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            # Add characteristics belonging to this service
            for char in service.characteristics:
                response[char.get_path()] = char.get_properties()
        # print(f"GetManagedObjects response: {response}") # Debug print
        return response

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
        self.service_uuids = [CONFIRMATION_SERVICE_UUID]
        # --- End UUID Change ---
        self.local_name = "PIkachu_Adv"
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
            time.sleep(1) # Give it a moment to power up
            powered = adapter_props.Get(ADAPTER_IFACE, "Powered")
            if not powered:
                 print("ERROR: Failed to power on adapter.", file=sys.stderr)
                 # sys.exit(1) # Decide if you want to exit or continue
        else:
             print("Adapter is already powered on.")
    except Exception as e:
        print(f"Warning: Could not get/set adapter power state: {e}", file=sys.stderr)

    # Get manager objects
    gatt_manager = dbus.Interface(adapter_obj, GATT_MANAGER_IFACE)
    adv_manager = dbus.Interface(adapter_obj, LE_ADVERTISING_MANAGER_IFACE)

    # Create our application, service, characteristic objects
    app = Application(bus)

    # Create our advertisement object with example data
    # Use different device ID/sensor value if desired
    adv_device_id = 98765
    adv_sensor_value = 23.0
    adv = Advertisement(bus, 0, adv_device_id, adv_sensor_value)

    # Main event loop
    mainloop = GLib.MainLoop()

    # --- Register GATT Application ---
    print("\nRegistering GATT Application...")
    try:
        gatt_manager.RegisterApplication(app.get_path(), {},
            reply_handler=lambda: print("  GATT Application registered successfully."),
            error_handler=lambda e: print(f"  ERROR: Failed to register GATT Application: {e}", file=sys.stderr)
        )
    except dbus.exceptions.DBusException as e:
         print(f"  ERROR: DBusException during GATT registration: {e}", file=sys.stderr)
         mainloop.quit() # Stop if critical registration fails
         return

    # --- Register Advertisement ---
    print("Registering Advertisement...")
    try:
        adv_manager.RegisterAdvertisement(adv.get_path(), {},
            reply_handler=lambda: print("  Advertisement registered successfully."),
            error_handler=lambda e: print(f"  ERROR: Failed to register Advertisement: {e}", file=sys.stderr)
        )
    except dbus.exceptions.DBusException as e:
         print(f"  ERROR: DBusException during Advertisement registration: {e}", file=sys.stderr)
         # Consider unregistering GATT app if adv fails
         try:
             print("  Attempting to unregister GATT Application due to advertisement failure...")
             gatt_manager.UnregisterApplication(app.get_path())
         except Exception as unreg_e:
             print(f"  Note: Error unregistering GATT app on cleanup: {unreg_e}", file=sys.stderr)
         mainloop.quit()
         return


    # --- Run Main Loop ---
    try:
        print("\nAdvertiser running with confirmation service.")
        print(f"Advertising Name: {adv.local_name}")
        print(f"Service UUID: {CONFIRMATION_SERVICE_UUID}")
        print(f"Characteristic UUID: {CONFIRMATION_CHAR_UUID} (Flags: {adv.get_properties()[LE_ADVERTISEMENT_IFACE]['Type']})")
        print(f"Manufacturer ID: 0x{MANUFACTURER_ID:04X}")
        print(f" Data: DeviceID={adv_device_id}, SensorVal={adv_sensor_value}")
        print("Logging confirmations to:", DB_PATH)
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

        print("Unregistering GATT Application...")
        try:
            gatt_manager.UnregisterApplication(app.get_path())
            print("  GATT Application unregistered.")
        except Exception as e:
            print(f"  Warning: Error unregistering GATT application: {e}", file=sys.stderr)

        if mainloop.is_running():
            mainloop.quit()
        print("Advertiser stopped.")


if __name__ == '__main__':
    # --- Initialize Advertiser Database ---
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Create table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS confirmations (
                device_id INTEGER,
                timestamp TEXT
            )
        ''')
        conn.commit()
        conn.close()
        print(f"[DB] Initialized or found database: {DB_PATH}")
    except Exception as e:
        print(f"[DB ERROR] Could not initialize advertiser database: {e}", file=sys.stderr)
        sys.exit(1) # Exit if database cannot be prepared

    main()