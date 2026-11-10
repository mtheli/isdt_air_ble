"""Advertisement decoding for BattAir smart packs and plugins.

BattAir packs broadcast their readings about once a second without a
connection. The pack re-measures voltage, charge level and temperature
about once a minute; in between only the status bits change.

This module has no Home Assistant imports so it can be unit tested on its
own.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

BATTAIR_MANUFACTURER_ID = 0xABBA  # same company ID as the chargers
BATTAIR_SERVICE_UUID = "0000ba00-0000-1000-8000-00805f9b34fb"
BATTAIR_NAME_PREFIX = "BATAIR"

# Chargers and adapters start their manufacturer data with these bytes.
_CHARGER_MFR_PREFIX = b"\xaf\xfa"

ADVERT_MIN_LENGTH = 11  # up to and including the cell count

BATTERY_TYPES = {
    0: "lihv",
    1: "lipo",
    2: "liion",
    3: "life",
    4: "pb",
    5: "nimh",
    6: "liuhv",
}

# Per-cell low voltage the pack itself treats as over-discharge. Only set
# for the lithium-polymer types; other chemistries get no low-voltage
# entity rather than a guessed threshold.
LOW_CELL_VOLTAGE = {
    "lipo": 3.0,
    "lihv": 3.0,
    "liuhv": 3.0,
}

# Byte 13: 0 for a smart pack, 1 for a plugin on a regular pack.
ASSEMBLY_PLUGIN = 1

MODEL_PACK = "BattAir"
MODEL_PLUGIN = "BattAir Plugin"

# Status byte bits
STATUS_SHAKE = 0x01
STATUS_STORAGE_DISCHARGE = 0x02
STATUS_ERROR_LOG = 0x08
STATUS_TRANSPORT = 0x10
STATUS_NOT_INITIALIZED = 0x40


@dataclass(frozen=True)
class BattAirAdvert:
    """Readings from one BattAir advertisement."""

    device_type: int
    battery_type: str | None
    status: int
    voltage: float
    percentage: int
    temperature: int
    cycles: int
    cells: int
    capacity_mah: int | None
    assembly: int | None
    filter_text: str | None

    @property
    def is_plugin(self) -> bool:
        """The advert comes from a plugin rather than a smart pack."""
        return self.assembly == ASSEMBLY_PLUGIN

    @property
    def model(self) -> str:
        """Model name for the device registry."""
        return MODEL_PLUGIN if self.is_plugin else MODEL_PACK

    @property
    def storage_discharge(self) -> bool:
        """The pack is discharging itself to storage voltage."""
        return bool(self.status & STATUS_STORAGE_DISCHARGE)

    @property
    def error_log(self) -> bool:
        """The pack has recorded at least one error.

        The pack writes the record at the end of a charge cycle and keeps it
        until it is erased, so this is not a live alarm.
        """
        return bool(self.status & STATUS_ERROR_LOG)

    @property
    def transport_mode(self) -> bool:
        """Transport mode is switched on."""
        return bool(self.status & STATUS_TRANSPORT)

    @property
    def cell_voltage_avg(self) -> float | None:
        """Pack voltage divided by the cell count."""
        if not self.cells:
            return None
        return round(self.voltage / self.cells, 3)

    @property
    def low_cell_voltage_threshold(self) -> float | None:
        """Per-cell threshold for the low-voltage problem, if known."""
        if self.battery_type is None:
            return None
        return LOW_CELL_VOLTAGE.get(self.battery_type)

    @property
    def cell_voltage_low(self) -> bool | None:
        """Average cell voltage is below the over-discharge threshold."""
        threshold = self.low_cell_voltage_threshold
        avg = self.cell_voltage_avg
        if threshold is None or avg is None:
            return None
        return avg < threshold

    def values_key(self) -> tuple:
        """Everything except the shake bit, to detect real changes."""
        return (
            self.device_type,
            self.battery_type,
            self.status & ~STATUS_SHAKE,
            self.voltage,
            self.percentage,
            self.temperature,
            self.cycles,
            self.cells,
            self.capacity_mah,
            self.assembly,
            self.filter_text,
        )


def _u16(data: bytes, offset: int) -> int:
    return data[offset] | (data[offset + 1] << 8)


def _text(data: bytes) -> str | None:
    """ASCII up to the first NUL/0xFF; None when empty."""
    out = bytearray()
    for byte in data:
        if byte in (0x00, 0xFF):
            break
        out.append(byte)
    text = out.decode("ascii", errors="replace").strip()
    return text or None


def decode_advert(payload: bytes | None) -> BattAirAdvert | None:
    """Decode BattAir manufacturer data (company ID already stripped).

    Returns None for payloads that are too short or that belong to an ISDT
    charger.
    """
    if payload is None or len(payload) < ADVERT_MIN_LENGTH:
        return None
    if payload.startswith(_CHARGER_MFR_PREFIX):
        return None
    temperature = payload[7] - 256 if payload[7] > 127 else payload[7]
    battery_code = (payload[0] >> 4) & 0x0F
    capacity = _u16(payload, 11) * 10 if len(payload) >= 13 else None
    return BattAirAdvert(
        device_type=payload[0] & 0x0F,
        battery_type=BATTERY_TYPES.get(battery_code),
        status=payload[3],
        voltage=round(_u16(payload, 4) / 100, 2),
        percentage=payload[6],
        temperature=temperature,
        cycles=_u16(payload, 8),
        cells=payload[10],
        capacity_mah=capacity or None,
        assembly=payload[13] if len(payload) >= 14 else None,
        filter_text=_text(payload[14:18]) if len(payload) >= 18 else None,
    )


def is_battair(
    service_uuids: list[str] | None,
    local_name: str | None,
    manufacturer_data: dict[int, bytes] | None,
) -> bool:
    """Return True when an advertisement comes from a BattAir pack or plugin."""
    uuids = [uuid.lower() for uuid in service_uuids or []]
    if BATTAIR_SERVICE_UUID in uuids:
        return True
    if (local_name or "").upper().startswith(BATTAIR_NAME_PREFIX):
        return True
    return False


_MAC_NAME_RE = re.compile(r"^[0-9A-Fa-f]{2}([-:][0-9A-Fa-f]{2}){5}$")


def pack_name(local_name: str | None) -> str | None:
    """Return the user-given pack name from the advertised name.

    The advertised name is 'BATAIR' followed by the name set for the pack,
    padded with spaces and '0000'. Packs that were never named advertise
    'BattAir' or their MAC address; those return None.
    """
    if not local_name or not local_name.upper().startswith(BATTAIR_NAME_PREFIX):
        return None
    name = local_name[len(BATTAIR_NAME_PREFIX):]
    name = re.sub(r"\s+0000$", "", name).strip()
    if not name or name.lower() == "battair" or _MAC_NAME_RE.match(name):
        return None
    return name


def default_title(
    advert: BattAirAdvert | None, address: str, local_name: str | None = None
) -> str:
    """Build a name that tells several packs apart.

    'BattAir ovonic1550' when the pack has its own name, otherwise
    'BattAir 4S 1300 mAh 88AD'.
    """
    model = advert.model if advert is not None else MODEL_PACK
    name = pack_name(local_name)
    if name:
        return f"{model} {name}"
    suffix = address.replace(":", "")[-4:].upper()
    parts = [model]
    if advert is not None:
        if advert.cells:
            parts.append(f"{advert.cells}S")
        if advert.capacity_mah:
            parts.append(f"{advert.capacity_mah} mAh")
    parts.append(suffix)
    return " ".join(parts)
