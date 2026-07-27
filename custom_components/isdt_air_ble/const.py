import re
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

# BindReq status byte (last byte). Always 1 per the protocol.
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

# WorkState status mapping for round-cell chargers (C4 Air, A8 Air, …)
WORK_STATE_MAP = {
    0: "idle",
    1: "charging",  # Pre-charge / trickle phase
    2: "charging",  # Active charging (CC phase)
    3: "charging",  # Active charging
    4: "charging",  # CV phase / topping
    5: "error",
    6: "done",      # 100% capacity_percentage, fully charged
}

# Battery type mapping for round-cell chargers
BATTERY_TYPE_MAP = {
    0: "LiHV",     # 4.35V Lithium High Voltage
    1: "LiIon",    # 4.20V Standard Lithium-Ion
    2: "LiFe",     # 3.65V Lithium Iron Phosphate (LiFePO4)
    3: "NiZn",     # Nickel-Zinc
    4: "NiMH/Cd",  # Nickel Metal Hydride / Cadmium
    5: "LiIon",    # 1.50V Lithium-Ion (special variant)
    6: "Auto",     # Automatic detection
}

# WorkState mapping for the Air 8 LiPo balance charger.
# The Air 8 firmware uses a different state enum than the round-cell
# chargers (idle/CC/CV plus storage, discharge and balance modes).
# v1 collapses every non-idle, non-done state to "charging" so the
# existing status sensor enum (empty/idle/charging/done/error) stays valid.
AIR8_WORK_STATE_MAP = {
    0: "idle",
    3: "charging",     # CC fast-charge
    4: "charging",
    5: "charging",     # ≥90% / CV
    6: "done",         # full
    7: "charging",     # storage modes
    8: "charging",
    9: "charging",
    10: "charging",
    11: "done",        # storage complete
    12: "charging",    # discharge in progress
    13: "done",        # discharge complete
    14: "charging",    # balance/destroy
    15: "done",
    16: "charging",
    17: "charging",
    18: "charging",
}

# Battery chemistry mapping for LiPo balance chargers (Air 8, K2 Air).
# The enum is different from the round-cell chargers — index 1 is LiPo
# (not LiIon) and the higher indices are LiPo-specific chemistries.
AIR8_BATTERY_TYPE_MAP = {
    0: "LiHV",     # 4.35V Lithium High Voltage
    1: "LiPo",     # 4.20V Lithium Polymer
    2: "LiIon",    # 4.20V Lithium-Ion
    3: "LiFe",     # 3.65V Lithium Iron Phosphate
    4: "Pb",       # Lead-Acid
    5: "NiMH/Cd",  # Nickel Metal Hydride / Cadmium
    6: "ULiHV",    # Ultra-High Voltage LiHV
}

# Charger families that share the LiPo balance-charger work-state and
# battery-chemistry enums. The wire protocol is identical to the round-cell
# chargers; only the byte 17 (battery_type) and byte 3 (work_state) field
# semantics differ.
#
# Members:
#   - "Air 8" (single channel, 1S-8S)
#   - "K2 Air" (two independent channels, 1S-6S each, parallel mode 1S-12S)
BALANCE_CHARGER_MODELS = frozenset({"Air 8", "K2 Air"})

# Manufacturer data company ID (ISDT)
ISDT_MANUFACTURER_ID = 43962  # 0xABBA

# Device model lookup from manufacturer_data bytes [2:6]
DEVICE_MODEL_MAP = {
    "01010000": "NP2 Air",
    "01020000": "LP2 Air",
    "01030000": "Air 8",
    "01040000": "K2 Air",
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
    "K2 Air": 2,  # Two-slot round-cell charger
    "Air 8": 1,   # Single LiPo pack port (up to 6 cells on one channel)
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


def supports_cell_voltages(model: str) -> bool:
    """Whether a charger reports per-cell voltages.

    The A8 Air charges single round cells per slot and has no balance
    leads, so it never produces cell-voltage data.
    """
    return "A8" not in model.upper()


_CHANNEL_UID_RE = re.compile(r"ch(\d+)_(.+)$")
_SLOT_UID_RE = re.compile(r"slot(\d+)_")
_CELL_KEY_RE = re.compile(r"cell\d+$")


def is_stale_charger_unique_id(
    unique_id: str, address: str, model: str, channel_count: int
) -> bool:
    """Whether an entity-registry unique_id is stale for this charger.

    Entities can outlive the code that created them: before a model is
    known (or before it was supported at all) the integration falls back
    to a generic 6-channel charger profile, registering entities the real
    device never provides. Those registry entries stick around as
    permanently disabled/unavailable ghosts, so setup prunes:

    - per-channel entities on channels the model doesn't have,
    - per-slot entities on slots the model doesn't have,
    - cell-voltage entities on models without per-cell data.
    """
    prefix = f"{address}_"
    if not unique_id.startswith(prefix):
        return False
    rest = unique_id[len(prefix):]

    m = _CHANNEL_UID_RE.match(rest)
    if m:
        if int(m.group(1)) >= channel_count:
            return True
        return bool(_CELL_KEY_RE.fullmatch(m.group(2))) and not supports_cell_voltages(model)

    m = _SLOT_UID_RE.match(rest)
    if m:
        return int(m.group(1)) > channel_count

    return False


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
# Sent on every successful connect; without it, the device clock stays
# on whatever it booted with (typically 2000-01-01) and per-port
# schedules / alarm clocks would not fire at the right time.
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


def detect_model_from_mfg_data(mfr_data: bytes | None) -> str | None:
    """Best-effort device-model detection from ISDT BLE manufacturer data.

    ISDT advertisements carry a 2-byte magic prefix ``af fa`` followed by a
    4-byte ``DeviceModelID`` at offset 2-5.  Many devices additionally
    embed their marketing name as a NUL-terminated ASCII string starting
    at offset 6 (e.g. ``K2Air`` on the K2 Air, ``C4Air`` on the C4 Air).

    Resolution order:
      1. Exact ``DeviceModelID`` lookup in ``DEVICE_MODEL_MAP``.
      2. ASCII fallback from the embedded name, normalised so a digit
         followed by a letter gets a space ("K2Air" → "K2 Air").

    Returning ``None`` means "unknown" — the caller should keep the
    previously stored model name or log a warning, but never invent one.
    """
    if not mfr_data or len(mfr_data) < 6:
        return None

    model_id = mfr_data[2:6].hex()
    model = DEVICE_MODEL_MAP.get(model_id)
    if model:
        return model

    name_bytes = mfr_data[6:].split(b"\x00", 1)[0]
    if not name_bytes:
        return None
    try:
        name = name_bytes.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    if not name.isprintable() or not name:
        return None
    # ISDT joins the model line and the product suffix without a space
    # ("K2Air"), but the integration uses spaced names ("K2 Air").
    return re.sub(r"(\d)([A-Za-z])", r"\1 \2", name)
