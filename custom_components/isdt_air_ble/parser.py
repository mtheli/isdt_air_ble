"""BLE packet parser for ISDT C4 Air charger responses."""

import logging

from .const import (
    RESP_HARDWARE_INFO,
    RESP_ALARM_TONE,
    RESP_ELECTRIC,
    RESP_WORKSTATE,
    RESP_IR,
    WORK_STATE_MAP,
    BATTERY_TYPE_MAP,
)

_LOGGER = logging.getLogger(__name__)


def parse_responses(responses: list[bytes]) -> tuple[dict, bool | None]:
    """Parse all BLE notification responses and assign to channels.

    Returns:
        (parsed, alarm_tone_on)
        parsed:        dict {channel (int): {key: value, ...}}
        alarm_tone_on: bool | None
    """
    parsed = {ch: {} for ch in range(6)}
    alarm_tone_on = None

    for raw in responses:
        _LOGGER.debug("RAW DATA from C4 Air: %s", raw.hex(" "))

        if len(raw) < 3:
            continue

        cmd = raw[1]

        # AlarmToneResp: no channel field, state is in byte 2
        if cmd == RESP_ALARM_TONE:
            alarm_tone_on = raw[2] != 0
            _LOGGER.debug("Alarm tone: %s", alarm_tone_on)
            continue

        ch = raw[2]
        if ch not in parsed:
            _LOGGER.warning("Unexpected channel %d in response", ch)
            continue

        if cmd == RESP_ELECTRIC:
            parsed[ch].update(parse_electric(raw))
        elif cmd == RESP_WORKSTATE:
            parsed[ch].update(parse_workstate(raw))
        elif cmd == RESP_IR:
            parsed[ch].update(parse_ir(raw))
        else:
            _LOGGER.debug(
                "Unknown CMD 0x%02x for channel %d: %s", cmd, ch, raw.hex(" ")
            )

    _LOGGER.debug("Parsed data: %s", parsed)
    return parsed, alarm_tone_on


def parse_electric(data: bytes) -> dict:
    """Parse ElectricResp (CMD RESP_ELECTRIC): voltages, currents, cell voltages.

    Format: [addr, RESP_ELECTRIC, channel,
              input_v (2 or 4 bytes LE),
              input_a (4 bytes LE),
              output_v (2 or 4 bytes LE),
              charge_a (4 bytes LE),
              cell_v × N (2 bytes LE each)]
    Long format (>35 bytes): 4-byte voltages, 16 cells.
    Short format:            2-byte voltages, 8 cells.
    All values in mV / mA → divided by 1000 to get V / A.
    """
    if len(data) < 15:
        _LOGGER.warning("ElectricResp too short: %d bytes", len(data))
        return {}

    channel_id = data[2]
    _LOGGER.debug("Parse ElectricResp for channel %d, length: %d", channel_id, len(data))

    long_fmt = len(data) > 35

    # Input Voltage
    if long_fmt:
        input_v = int.from_bytes(data[3:7], "little") / 1000.0
        pos = 7
    else:
        input_v = int.from_bytes(data[3:5], "little") / 1000.0
        pos = 5

    # Input Current (always 4 bytes)
    input_a = int.from_bytes(data[pos : pos + 4], "little") / 1000.0
    pos += 4

    # Output Voltage
    if long_fmt:
        output_v = int.from_bytes(data[pos : pos + 4], "little") / 1000.0
        pos += 4
    else:
        output_v = int.from_bytes(data[pos : pos + 2], "little") / 1000.0
        pos += 2

    # Charging Current (always 4 bytes)
    charge_a = int.from_bytes(data[pos : pos + 4], "little") / 1000.0
    pos += 4

    # Cell voltages (16 cells in long format, 8 in short format)
    num_cells = 16 if long_fmt else 8
    cell_voltages = []
    for _ in range(num_cells):
        if pos + 2 <= len(data):
            cell_voltages.append(int.from_bytes(data[pos : pos + 2], "little") / 1000.0)
            pos += 2
        else:
            break

    _LOGGER.debug(
        "Channel %d: In=%.2fV/%.3fA, Out=%.2fV, Charge=%.3fA, Cells=%d",
        channel_id, input_v, input_a, output_v, charge_a,
        len([c for c in cell_voltages if c > 0]),
    )

    return {
        "channel_id": channel_id,
        "input_voltage": input_v,
        "input_current": input_a,
        "output_voltage": output_v,
        "charging_current": charge_a,
        "cell_voltages": cell_voltages,
    }


def parse_workstate(data: bytes) -> dict:
    """Parse ChargerWorkStateResp (CMD RESP_WORKSTATE): charge state, capacity, time, etc.

    Format: [addr, RESP_WORKSTATE, channel,
              work_state (1), capacity_% (1),
              capacity_mAh (4 LE), energy_mWh (4 LE), period_ms (4 LE),
              battery_type (1), unit_serials (1), link_type (1),
              full_volt_mV (2 LE), work_current_mA (4 LE),
              bat_num_whole (2 LE), bat_num_current (2 LE),
              min_input_mV (2 LE), max_power_mW (4 LE),
              error_code (2 LE), [parallel_state (1)]]
    """
    if len(data) < 38:
        _LOGGER.warning("WorkStateResp too short: %d bytes", len(data))
        return {}

    channel_id = data[2]
    _LOGGER.debug("Parse WorkStateResp for channel %d", channel_id)

    work_state          = data[3]
    capacity_percentage = data[4]
    capacity_done       = int.from_bytes(data[5:9],   "little")        # mAh
    energy_done         = int.from_bytes(data[9:13],  "little")        # mWh
    work_period_ms      = int.from_bytes(data[13:17], "little")        # ms
    work_period         = work_period_ms // 1000                        # s
    battery_type        = data[17]
    unit_serials_num    = data[18]
    link_type           = data[19]
    full_charged_volt   = int.from_bytes(data[20:22], "little") / 1000.0   # V
    work_current        = int.from_bytes(data[22:26], "little") / 1000.0   # A
    charging_battery_num_whole   = int.from_bytes(data[26:28], "little")
    charging_battery_num_current = int.from_bytes(data[28:30], "little")
    min_input_volt      = int.from_bytes(data[30:32], "little") / 1000.0   # V
    max_output_power    = int.from_bytes(data[32:36], "little") / 1000.0   # W
    error_code          = int.from_bytes(data[36:38], "little")
    parallel_state      = data[38] == 1 if len(data) > 38 else None

    work_state_str   = WORK_STATE_MAP.get(work_state, f"unknown_{work_state}")
    battery_type_str = BATTERY_TYPE_MAP.get(battery_type, f"unknown_{battery_type}")

    hours, rem = divmod(work_period, 3600)
    minutes, seconds = divmod(rem, 60)
    work_period_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    _LOGGER.debug(
        "Channel %d: State=%s, %d%%, %d mAh, %s (ms=%d), Type=%s",
        channel_id, work_state_str, capacity_percentage, capacity_done,
        work_period_str, work_period_ms, battery_type_str,
    )

    return {
        "work_state":                    work_state,
        "work_state_str":                work_state_str,
        "capacity_percentage":           capacity_percentage,
        "capacity_done":                 capacity_done,
        "energy_done":                   energy_done,
        "energy_done_wh":                energy_done / 1000.0,
        "work_period":                   work_period,
        "work_period_ms":                work_period_ms,
        "work_period_str":               work_period_str,
        "battery_type":                  battery_type,
        "battery_type_str":              battery_type_str,
        "unit_serials_num":              unit_serials_num,
        "link_type":                     link_type,
        "full_charged_volt":             full_charged_volt,
        "work_current":                  work_current,
        "charging_battery_num_whole":    charging_battery_num_whole,
        "charging_battery_num_current":  charging_battery_num_current,
        "min_input_volt":                min_input_volt,
        "max_output_power":              max_output_power,
        "error_code":                    error_code,
        "parallel_state":                parallel_state,
    }


def parse_ir(data: bytes) -> dict:
    """Parse IRResp (CMD RESP_IR): internal resistance per cell.

    Format: [addr, RESP_IR, channel, ir0_lo, ir0_hi, ir1_lo, ir1_hi, ...]
    Values are little-endian uint16, unit = 0.1 mΩ.
    Number of cells derived from response length:
      ≥20 bytes → 16 cells, >15 → 8, =15 → 6, else (len-3)//2.
    Primary IR (first cell) is returned in mΩ; 0 and values ≥10000 are treated as invalid.
    """
    if len(data) < 5:
        _LOGGER.warning("IRResp too short: %d bytes", len(data))
        return {}

    channel_id = data[2]
    pos = 3

    payload_len = len(data)
    if payload_len >= 20:
        num_cells = 16
    elif payload_len > 15:
        num_cells = 8
    elif payload_len == 15:
        num_cells = 6
    else:
        num_cells = (payload_len - 3) // 2

    ir_values = []
    for _ in range(num_cells):
        if pos + 2 <= len(data):
            ir_values.append(data[pos] | (data[pos + 1] << 8))
            pos += 2
        else:
            break

    ir_mohm = None
    if ir_values and 0 < ir_values[0] < 10000:
        ir_mohm = ir_values[0] / 10.0

    _LOGGER.debug(
        "Channel %d: IR values=%s, primary=%.1f mOhm",
        channel_id, ir_values[:4], ir_mohm if ir_mohm is not None else 0.0,
    )

    return {
        "ir_raw":  ir_values,
        "ir_mohm": ir_mohm,
    }


def parse_hardware_info(data: bytes) -> tuple[str, str, str] | None:
    """Parse HardwareInfoResp (CMD RESP_HARDWARE_INFO) received on characteristic AF02.

    The CMD byte may be at position 0 (no address prefix) or 1 (with prefix).
    Layout after CMD: hw_main (1), hw_sub (1), sw_main (1), sw_sub (1), device_id (8 LE).

    Returns:
        (hw_version, sw_version, serial_number) or None on error.
    """
    if len(data) < 5:
        _LOGGER.warning("HardwareInfoResp too short: %d bytes", len(data))
        return None

    if data[0] == RESP_HARDWARE_INFO:
        offset = 0
    elif len(data) > 1 and data[1] == RESP_HARDWARE_INFO:
        offset = 1
    else:
        _LOGGER.debug(
            "Response is not HardwareInfoResp: first bytes = 0x%02x 0x%02x",
            data[0], data[1] if len(data) > 1 else 0,
        )
        return None

    needed = offset + 13  # CMD + 4 version bytes + 8 device-ID bytes
    if len(data) < needed:
        _LOGGER.warning(
            "HardwareInfoResp too short: %d bytes (need %d)", len(data), needed
        )
        return None

    hw_version    = f"{data[offset + 1]}.{data[offset + 2]}"
    sw_version    = f"{data[offset + 3]}.{data[offset + 4]}"
    device_id     = int.from_bytes(data[offset + 5 : offset + 13], "little")
    serial_number = f"{device_id:016X}"

    return hw_version, sw_version, serial_number
