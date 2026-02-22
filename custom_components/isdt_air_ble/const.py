DOMAIN = "isdt_air_ble"

# Options
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 5  # seconds

# BLE GATT characteristic UUIDs
CHAR_UUID_AF01 = "0000af01-0000-1000-8000-00805f9b34fb"  # Notify/Write (normal polling)
CHAR_UUID_AF02 = "0000af02-0000-1000-8000-00805f9b34fb"  # Write (hardware info)

# BLE request commands (written to CHAR_UUID_AF02)
#   BindReq: registers the client with the charger (once after connect, before data polling)
#   Response CMD: 0x19 on AF02 (bound_status: 0=ok)
CMD_BIND_REQ = 0x18
RESP_BIND = 0x19

#   HardwareInfoReq: queries HW version, FW version, and serial number (once after connect)
#   Response CMD: 0xE1 on AF02
CMD_HARDWARE_INFO_REQ = bytearray([0xE0])

# BLE request commands (written to CHAR_UUID_AF01, response via notifications)
#   AlarmToneReq: queries the current alarm tone status (on/off)
#   Response CMD: 0x93
CMD_ALARM_TONE_REQ = bytearray([0x12, 0x92])
CMD_ALARM_TONE_SET = bytearray([0x13, 0x9C])

#   ElectricReq: queries voltages and currents for a channel (+ cell voltages)
#   Byte 2: channel (0–5), Response CMD: 0xE5
CMD_ELECTRIC_REQ = bytearray([0x12, 0xE4])

#   WorkStateReq: queries charge state, capacity, battery type etc. for a channel
#   Byte 2: channel (0–5), Response CMD: 0xE7
CMD_WORKSTATE_REQ = bytearray([0x13, 0xE6])

#   IRReq: queries internal resistance of cells for a channel
#   Byte 2: channel (0–5), Response CMD: 0xFB
CMD_IR_REQ = bytearray([0x13, 0xFA])

# BLE response command bytes (received via AF01/AF02 notifications)
RESP_HARDWARE_INFO = 0xE1   # HardwareInfoResp on AF02
RESP_ALARM_TONE    = 0x93   # AlarmToneResp
RESP_ELECTRIC      = 0xE5   # ElectricResp
RESP_WORKSTATE     = 0xE7   # ChargerWorkStateResp
RESP_IR            = 0xFB   # IRResp

# WorkState status mapping (from C4AirModel.java)
WORK_STATE_MAP = {
    0: "idle",
    1: "charging",  # Pre-charge / trickle phase
    2: "charging",  # Confirmed: active charging (CC phase)
    3: "charging",  # Confirmed: orange with lightning bolt in app
    4: "charging",  # CV phase / topping
    5: "error",
    6: "done",      # Confirmed: 100% capacity_percentage, fully charged
}

# Battery type mapping (from C4AirModel.java setChemistryCapacity)
BATTERY_TYPE_MAP = {
    0: "LiHV",     # 4.35V Lithium High Voltage
    1: "LiIon",    # 4.20V Standard Lithium-Ion
    2: "LiFe",     # 3.65V Lithium Iron Phosphate (LiFePO4)
    3: "NiZn",     # Nickel-Zinc
    4: "NiMH/Cd",  # Nickel Metal Hydride / Cadmium
    5: "LiIon",    # 1.50V Lithium-Ion (special variant)
    6: "Auto",     # Automatic detection
}

# Manufacturer data company ID (ISDT)
ISDT_MANUFACTURER_ID = 43962  # 0xABBA

# Device model lookup from manufacturer_data bytes [2:6]
# Extracted from MyScanItemModel.java
DEVICE_MODEL_MAP = {
    "01010000": "NP2 Air",
    "01020000": "LP2 Air",
    "01030000": "C4 Air",
    "01040000": "C4 EVO",
    "01050000": "608PD",
    "01060000": "K4",
    "01070000": "C4 Air",
    "01080000": "Power 200",
    "01100000": "PB70W",
    "01100001": "PB70W",
    "01110000": "EDGE",
    "01120000": "PB100W",
    "01120001": "PB100W",
    "81c00000": "PB10DW",
    "81c00100": "PB25DW",
    "81c00200": "PB50DW",
    "C4Air": "C4 Air",
    "NP2Air": "NP2 Air",
    "LP2Air": "LP2 Air",
    "A4Air": "A4 Air",
    "A8Air": "A8 Air",
}
