from enum import StrEnum

DOMAIN = "isdt_air_ble"


class DeviceType(StrEnum):
    """Device type classification."""

    CHARGER = "charger"
    ADAPTER = "adapter"

# Options
CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 5  # seconds

# Adapter phantom-load filter (MASS2 etc.)
# Charging pads in standby periodically pulse small amounts of power
# (Apple pads ~0.2 W, Samsung pads up to ~0.6 W) to probe for devices.
# These pulses flip the port_status sensor and pollute the recorder.
# The filter zeroes out a port's data when power stays below the
# threshold, and requires it to stay above the threshold for at least
# the debounce window before reporting it as active.
CONF_PHANTOM_THRESHOLD = "phantom_threshold"   # watts — instant-active
CONF_PHANTOM_DEBOUNCE = "phantom_debounce"     # seconds — down-hysteresis
CONF_PHANTOM_SUSTAIN = "phantom_sustain"       # seconds — sustained low-power
DEFAULT_PHANTOM_THRESHOLD = 1.0
DEFAULT_PHANTOM_DEBOUNCE = 2.5
DEFAULT_PHANTOM_SUSTAIN = 5.0

# BLE GATT characteristic UUIDs
CHAR_UUID_AF01 = "0000af01-0000-1000-8000-00805f9b34fb"  # Notify/Write (normal polling)
CHAR_UUID_AF02 = "0000af02-0000-1000-8000-00805f9b34fb"  # Write (hardware info)

# BLE request commands (written to CHAR_UUID_AF02)
#   BindReq: registers the client with the charger (once after connect, before data polling)
#   Response CMD: 0x19 on AF02 (bound_status: 0=ok)
CMD_BIND_REQ = 0x18
RESP_BIND = 0x19

# BindReq status byte (last byte). The manufacturer app always sends 1.
# The device decides itself whether the UUID is known or pairing is needed.
BIND_STATUS = 0x01

# BindResp result codes (second byte after RESP_BIND)
#   0 = bound (UUID known or just stored after user pressed the button)
#   1 = waiting — device beeps and waits for the user to press a button;
#       a second BindResp with code 0 follows after the press
BIND_RESULT_OK = 0
BIND_RESULT_WAITING = 1

# Config entry data keys
CONF_BIND_UUID = "bind_uuid"

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
    "010f00a8": "A8 Air",
    "01100000": "PB70W",
    "01100001": "PB70W",
    "01110000": "EDGE",
    "01120000": "PB100W",
    "01120001": "PB100W",
    "81c00000": "PB10DW",
    "81c00100": "PB25DW",
    "81c00200": "PB50DW",
    "01350000": "MASS2",
    "C4Air": "C4 Air",
    "NP2Air": "NP2 Air",
    "LP2Air": "LP2 Air",
    "A4Air": "A4 Air",
    "A8Air": "A8 Air",
}

# Map model names to device types
MODEL_DEVICE_TYPE_MAP: dict[str, DeviceType] = {
    "MASS2": DeviceType.ADAPTER,
}

# Map model names to channel/slot counts
MODEL_CHANNEL_COUNT_MAP: dict[str, int] = {
    "A8 Air": 8,  # Channels 0-7
    "A4 Air": 4,
    # Default for most chargers is 6 channels
}

MASS2_PORT_COUNT = 8

# MASS2 physical port layout (from MASS2Base.java line 119)
# Slots 1-6 are USB-C, slots 7-8 are USB-A
MASS2_PORT_LABELS = [
    "USB-C1", "USB-C2", "USB-C3", "USB-C4",
    "USB-C5", "USB-C6", "USB-A1", "USB-A2",
]


def get_device_type(model: str) -> DeviceType:
    """Get device type for a model name. Defaults to CHARGER."""
    return MODEL_DEVICE_TYPE_MAP.get(model, DeviceType.CHARGER)


def get_channel_count(model: str) -> int:
    """Get number of channels/slots for a charger model. Defaults to 6."""
    return MODEL_CHANNEL_COUNT_MAP.get(model, 6)


# ---------------------------------------------------------------------------
# MASS2 adapter commands (written to CHAR_UUID_AF01)
# ---------------------------------------------------------------------------

# WorkStatusReq: polls real-time port status (voltage, current, protocol)
# Response CMD: 0xC3
CMD_MASS2_WORK_STATUS_REQ = bytearray([0x12, 0xC2])

# SettingsReq: query device settings (beep, volume, mute schedule, alarms)
# Response CMD: 0xCB
CMD_MASS2_SETTINGS_REQ = bytearray([0x12, 0xCA])

# SettingsSetReq: write device settings
# (full 21-byte frame: scheduledMute, volume, operationSoundRepeatDay,
#  openingTime[2], closingTime[2], 4 × (switchRepeatDay, openingTime[2]))
CMD_MASS2_SETTINGS_SET = bytearray([0x12, 0xC8])

# SetTimeReq: push current wall-clock time + tz offset to the device RTC.
# The manufacturer app sends this on every successful connect; without
# it, the device clock stays on whatever it booted with (typically
# 2000-01-01) and per-port schedules / alarm clocks would not fire at
# the right time. Payload follows MASS2Fragment.isConnected(true).
CMD_MASS2_SET_TIME = bytearray([0x12, 0xCE])

# MASS2 response command bytes
RESP_MASS2_WORK_STATUS = 0xC3   # WorkStatusResp (8 ports × 7 bytes)
RESP_MASS2_SETTINGS    = 0xCB   # SettingsResp (21 bytes)

# Frame header byte (byte 0) for normal MASS2 data packets.
# Verified against MASS2Fragment.onBleByte: `if (bArr[0] != 49)` = 0x31.
# Special packets like HardwareInfoResp (0xE1) use a different prefix.
MASS2_FRAME_HEADER = 0x31

# MASS2 charging protocol mapping
MASS2_PROTOCOL_MAP = {
    0: "none",
    1: "pd",
    2: "fast_charge",
}

# ---------------------------------------------------------------------------
# Firmware update check (public ISDT OTA API, no auth required)
# ---------------------------------------------------------------------------
OTA_BLE_URL = "https://www.isdt.co/ota/newble.json"

# Map our model names → deviceName in ISDT OTA JSON
MODEL_OTA_NAME_MAP: dict[str, str] = {
    "C4 Air": "C4Air",
    "C4 EVO": "C4Air",
    "A4 Air": "A4Air",
    "A8 Air": "A8Air",
    "NP2 Air": "NP2Air",
    "LP2 Air": "LP2Air",
    "MASS2": "MASS2",
    "608PD": "608PD",
    "EDGE": "EDGE",
    "Power 200": "Power200",
}
