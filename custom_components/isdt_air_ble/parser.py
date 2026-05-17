"""BLE packet parser for ISDT Air BLE device responses."""

import logging

from .const import (
    RESP_HARDWARE_INFO,
    RESP_ALARM_TONE,
    RESP_ELECTRIC,
    RESP_WORKSTATE,
    RESP_IR,
    RESP_MASS2_SETTINGS,
    RESP_MASS2_WORK_STATUS,
    WORK_STATE_MAP,
    BATTERY_TYPE_MAP,
    AIR8_WORK_STATE_MAP,
    AIR8_BATTERY_TYPE_MAP,
    BALANCE_CHARGER_MODELS,
    MASS2_PORT_COUNT,
    MASS2_PROTOCOL_MAP,
)

_LOGGER = logging.getLogger(__name__)
_RAW_LOGGER = logging.getLogger(__name__ + ".raw")
_RAW_LOGGER.setLevel(logging.WARNING)  # silent unless explicitly enabled


def _parse_a8_air_workstate_mega(data: bytes) -> list[bytearray] | None:
    """Parse A8 Air WorkState mega-packet (A8WorkStateResp) for all channels.

    The A8 Air sends all channel data in a single 203-byte packet instead of
    individual per-channel responses like the C4 Air.

    Format: [0x31, 0xE7, total_channels, channel_data × 8]
    203 bytes total: 3 header + 8 × 25 bytes per channel.

    Per-channel format (25 bytes, from A8WorkStateResp.java):
      Offset 0:     work_state (1)
      Offset 1:     capacity_% (1)
      Offset 2-5:   capacity_mAh (4 LE)
      Offset 6-9:   energy_mWh (4 LE)
      Offset 10-13: work_period_ms (4 LE)
      Offset 14:    battery_type (1)
      Offset 15-18: work_current_mA (4 LE)
      Offset 19-20: voltage_mV (2 LE)
      Offset 21-22: IR (2 LE, 0.1 mΩ)
      Offset 23-24: error_code (2 LE)

    Returns a list of 42-byte responses in C4 Air standard format, or None.
    """
    if len(data) < 28:  # header + at least 1 channel
        _LOGGER.warning("A8 Air mega-packet too short: %d bytes", len(data))
        return None

    total_channels = data[2]
    header_size = 3
    bytes_per_channel = 25

    expected = header_size + total_channels * bytes_per_channel
    if len(data) < expected:
        _LOGGER.warning(
            "A8 Air mega-packet truncated: %d bytes (need %d for %d channels)",
            len(data), expected, total_channels,
        )
        return None

    _RAW_LOGGER.debug("A8 Air mega-packet (%d bytes, %d channels)", len(data), total_channels)

    responses = []
    pos = header_size

    for ch in range(total_channels):
        cd = data[pos:pos + bytes_per_channel]

        # Map to C4 Air standard 42-byte WorkState format so parse_workstate
        # can handle both identically.
        r = bytearray(42)
        r[0] = 0x31                             # frame header
        r[1] = RESP_WORKSTATE                   # cmd
        r[2] = ch                               # channel
        r[3] = cd[0]                            # work_state
        r[4] = cd[1]                            # capacity_%
        r[5:9] = cd[2:6]                        # capacity_mAh (4 LE)
        r[9:13] = cd[6:10]                      # energy_mWh (4 LE)
        r[13:17] = cd[10:14]                    # work_period_ms (4 LE)
        r[17] = cd[14]                          # battery_type
        r[18] = 0                               # unit_serials (not in A8)
        r[19] = 0                               # link_type (not in A8)
        r[20:22] = cd[19:21]                    # voltage_mV (2 LE)
        r[22:26] = cd[15:19]                    # work_current_mA (4 LE)
        # r[26:38] stays zero (fields not in A8 mega-packet)
        r[36:38] = cd[23:25]                    # error_code (2 LE)

        responses.append(r)
        pos += bytes_per_channel

    _LOGGER.debug("A8 Air mega-packet: extracted %d channel responses", len(responses))
    return responses if responses else None



def parse_charger_responses(responses: list[bytes], num_channels: int = 6, model: str = "C4 Air") -> tuple[dict, bool | None]:
    """Parse all BLE notification responses and assign to channels.

    All responses share the common frame format [0x31, CMD, ...].
    The A8 Air sends a single mega-packet for WorkState instead of per-channel
    responses; this is expanded before the normal per-response loop.

    Args:
        responses: List of raw BLE notification bytes.
        num_channels: Number of channels (6 for C4 Air, 8 for A8 Air).
        model: Device model name.

    Returns:
        (parsed, alarm_tone_on)
        parsed:        dict {channel (int): {key: value, ...}}
        alarm_tone_on: bool | None
    """
    is_a8_air = "A8" in model.upper()
    parsed = {ch: {} for ch in range(num_channels)}
    alarm_tone_on = None

    # Pre-process: expand A8 Air mega-packets into per-channel responses
    expanded = []
    for raw in responses:
        if len(raw) < 3:
            continue
        # A8 Air mega-packet: CMD=WorkState and much larger than a single response
        if is_a8_air and raw[1] == RESP_WORKSTATE and len(raw) > 100:
            a8_parsed = _parse_a8_air_workstate_mega(raw)
            if a8_parsed:
                expanded.extend(a8_parsed)
                continue
        expanded.append(raw)

    for raw in expanded:
        _RAW_LOGGER.debug("RAW DATA (%d bytes): %s", len(raw), raw.hex(" "))

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
            # A8 Air firmware sends ElectricResp with a hardcoded channel
            # value >= num_channels (device-level data, not per-slot).
            # Remap to channel 0 so device-level sensors can read it.
            if is_a8_air and cmd == RESP_ELECTRIC:
                _LOGGER.debug(
                    "Remapping A8 Air ElectricResp channel %d → 0 (device-level)",
                    ch,
                )
                ch = 0
            else:
                _LOGGER.warning(
                    "Unexpected channel %d in response (expected 0-%d for %s)",
                    ch, num_channels - 1, model,
                )
                continue

        if cmd == RESP_ELECTRIC:
            parsed[ch].update(parse_electric(raw))
        elif cmd == RESP_WORKSTATE:
            parsed[ch].update(parse_workstate(raw, model=model))
        elif cmd == RESP_IR:
            parsed[ch].update(parse_ir(raw))
        else:
            _LOGGER.debug(
                "Unknown CMD 0x%02x for channel %d: %s", cmd, ch, raw.hex(" ")
            )

    _RAW_LOGGER.debug("Parsed data: %s", parsed)
    return parsed, alarm_tone_on


def parse_electric(data: bytes) -> dict:
    """Parse ElectricResp (CMD RESP_ELECTRIC): voltages, currents, cell voltages.

    Format: [0x31, RESP_ELECTRIC, channel,
              input_v (2 or 4 bytes LE),
              input_a (4 bytes LE),
              output_v (2 or 4 bytes LE),
              charge_a (4 bytes LE),
              cell_v × N (2 bytes LE each)]
    Long format (>35 bytes): 4-byte voltages, 16 cells.
    Short format:            2-byte voltages, 8 cells.
    All values in mV / mA → divided by 1000 to get V / A.
    """
    # A8 Air sends 9-byte ElectricResp — input voltage and current only.
    # Format: [0x31, 0xE5, channel, input_v(2B LE), input_a(4B LE)]
    if len(data) == 9:
        channel_id = data[2]
        input_v = int.from_bytes(data[3:5], "little") / 1000.0
        input_a = int.from_bytes(data[5:9], "little") / 1000.0
        
        _LOGGER.debug(
            "Parse ElectricResp for channel %d: 9-byte format, In=%.2fV/%.3fA",
            channel_id, input_v, input_a
        )
        
        return {
            "channel_id": channel_id,
            "input_voltage": input_v,
            "input_current": input_a,
            # No output_voltage / charging_current in 9-byte format —
            # those come from the WorkState mega-packet for A8 Air.
            "cell_voltages": [],
        }
    
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


def parse_workstate(data: bytes, model: str = "C4 Air") -> dict:
    """Parse ChargerWorkStateResp (CMD RESP_WORKSTATE): charge state, capacity, time, etc.

    Format: [0x31, RESP_WORKSTATE, channel,
              work_state (1), capacity_% (1),
              capacity_mAh (4 LE), energy_mWh (4 LE), period_ms (4 LE),
              battery_type (1), unit_serials (1), link_type (1),
              full_volt_mV (2 LE), work_current_mA (4 LE),
              bat_num_whole (2 LE), bat_num_current (2 LE),
              min_input_mV (2 LE), max_power_mW (4 LE),
              error_code (2 LE), [parallel_state (1)]]

    A8 Air mega-packet data is pre-converted to this format by
    _parse_a8_air_workstate_mega() before reaching this function.

    LiPo balance chargers (Air 8, K2 Air) use different work-state and
    battery-type enums than the round-cell chargers — pass the matching
    model name to apply the balance-charger maps.
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

    if model in BALANCE_CHARGER_MODELS:
        ws_map = AIR8_WORK_STATE_MAP
        bt_map = AIR8_BATTERY_TYPE_MAP
    else:
        ws_map = WORK_STATE_MAP
        bt_map = BATTERY_TYPE_MAP

    work_state_str   = ws_map.get(work_state, f"unknown_{work_state}")
    battery_type_str = bt_map.get(battery_type, f"unknown_{battery_type}")

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
        # Aliases: sensors read these keys from ElectricResp on C4 Air,
        # but on A8 Air the 9-byte ElectricResp only has input V/I.
        # WorkState provides the per-slot values instead. For C4 Air
        # these are harmlessly overwritten by the subsequent ElectricResp.
        "output_voltage":                full_charged_volt,
        "charging_current":              work_current,
    }


def parse_ir(data: bytes) -> dict:
    """Parse IRResp (CMD RESP_IR): internal resistance per cell.

    Format: [0x31, RESP_IR, channel, ir0_lo, ir0_hi, ir1_lo, ir1_hi, ...]
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
    elif ir_values:
        # Log why IR is being rejected (especially for channel 8 debugging)
        _LOGGER.debug(
            "Channel %d: IR value %d rejected (must be >0 and <10000)",
            channel_id, ir_values[0]
        )

    _LOGGER.debug(
        "Channel %d: IR raw data (%d bytes): %s, values=%s, primary=%.1f mOhm",
        channel_id, len(data), data.hex(" "), ir_values[:4], ir_mohm if ir_mohm is not None else 0.0,
    )

    return {
        "ir_raw":  ir_values,
        "ir_mohm": ir_mohm,
    }


def parse_hardware_info(data: bytes) -> tuple[str, str, str] | None:
    """Parse HardwareInfoResp (CMD RESP_HARDWARE_INFO) received on characteristic AF02.

    The CMD byte may be at position 0 (no 0x31 frame header) or 1 (with 0x31 prefix).
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


# ---------------------------------------------------------------------------
# MASS2 adapter parsing
# ---------------------------------------------------------------------------


def parse_mass2_responses(responses: list[bytes]) -> tuple[dict | None, dict | None]:
    """Parse MASS2 BLE notification responses.

    Returns:
        (ports, settings)
        ports: dict {port (int): {key: value, ...}} when at least one valid
               WorkStatusResp was parsed; None otherwise.
        settings: dict with device settings when at least one SettingsResp
                  was parsed; None otherwise.
    """
    ports: dict = {p: {} for p in range(MASS2_PORT_COUNT)}
    ports_valid = False
    settings: dict | None = None

    for raw in responses:
        _LOGGER.debug("RAW BLE DATA from MASS2 (%d bytes): %s", len(raw), raw.hex(" "))

        if len(raw) < 3:
            continue

        cmd = raw[1]

        if cmd == RESP_MASS2_WORK_STATUS:
            if _parse_mass2_work_status(raw, ports):
                ports_valid = True
        elif cmd == RESP_MASS2_SETTINGS:
            parsed_settings = _parse_mass2_settings(raw)
            if parsed_settings is not None:
                settings = parsed_settings
        else:
            _LOGGER.debug("Unknown MASS2 CMD 0x%02x: %s", cmd, raw.hex(" "))

    return (ports if ports_valid else None, settings)


def _parse_mass2_work_status(data: bytes, parsed: dict) -> bool:
    """Parse MASS2 WorkStatusResp (CMD 0xC3).

    Returns True if the response was complete and parsed successfully,
    False if it was truncated (e.g. fragmented across BLE notifications)
    so the caller can discard partial data.

    Format:
      Byte 0: 0x31 frame header
      Byte 1: 0xC3 cmd word
      Byte 2: total power in W (NOT port count — the protocol always
              includes 8 ports regardless, and byte 2 is the total power)
      Per port (7 bytes each, starting at byte 3):
        +0: status   (uint8) — 1 means actively delivering power
        +1: protocol (uint8: 0=none, 1=PD, 2=fast_charge)
        +2: flags    (uint8) — semantics unclear; stored internally as
                     alarm indicator but never surfaced to the user
        +3-4: voltage (uint16 LE, mV)
        +5-6: current (uint16 LE, mA)
    """
    # The protocol always includes exactly 8 ports regardless of byte 2.
    expected_len = 3 + MASS2_PORT_COUNT * 7

    if len(data) < expected_len:
        _LOGGER.warning(
            "Incomplete MASS2 WorkStatus response: %d bytes (need %d). "
            "Likely BLE fragmentation due to small MTU.",
            len(data), expected_len,
        )
        return False

    # Store the device-reported total power (byte 2) instead of summing
    # the per-port values, which can drift slightly from the device's own
    # internal accounting and includes phantom-pulse noise.
    parsed["_total_power"] = data[2]

    pos = 3
    for port in range(MASS2_PORT_COUNT):
        if port not in parsed:
            parsed[port] = {}

        status = data[pos]
        protocol = data[pos + 1]
        alarm = data[pos + 2]
        voltage_mv = int.from_bytes(data[pos + 3 : pos + 5], "little")
        current_ma = int.from_bytes(data[pos + 5 : pos + 7], "little")

        voltage = voltage_mv / 1000.0
        current = current_ma / 1000.0
        power = round(voltage * current, 2)

        parsed[port].update({
            "status": status,
            "protocol": protocol,
            "protocol_str": MASS2_PROTOCOL_MAP.get(protocol, "none"),
            "alarm": alarm,
            "voltage": voltage,
            "current": current,
            "power": power,
        })

        pos += 7

    _LOGGER.debug("MASS2 WorkStatus parsed (8 ports)")
    return True


def _parse_mass2_settings(data: bytes) -> dict | None:
    """Parse MASS2 SettingsResp (CMD 0xCB).

    Format (verified against MASS2Settings.initData):
      Byte 0: 0x31 frame header
      Byte 1: 0xCB cmd word
      Byte 2: scheduledMute (uint8) — beep mode (0=mute, !=0=beep)
      Byte 3: volume (uint8) — 0=low, 1=medium, 2=high
      Byte 4: operationSoundRepeatDay (uint8) — bit 7 = mute timer enabled
      Byte 5-6: openingTime (uint16 LE) — mute timer start, in minutes
      Byte 7-8: closingTime (uint16 LE) — mute timer end, in minutes
      Bytes 9-20: 4 × AlarmClock (3 bytes each)
    Total: 21 bytes
    """
    if len(data) < 21:
        _LOGGER.warning(
            "Incomplete MASS2 Settings response: %d bytes (need 21)", len(data),
        )
        return None

    settings = {
        "scheduledMute": data[2],
        "volume": data[3],
        "operationSoundRepeatDay": data[4],
        "openingTime": int.from_bytes(data[5:7], "little"),
        "closingTime": int.from_bytes(data[7:9], "little"),
        "alarmClocks": [],
    }
    pos = 9
    for _ in range(4):
        settings["alarmClocks"].append({
            "switchRepeatDay": data[pos],
            "openingTime": int.from_bytes(data[pos + 1 : pos + 3], "little"),
        })
        pos += 3

    _LOGGER.debug(
        "MASS2 Settings: scheduledMute=%d, volume=%d, opSoundRepeat=0x%02x",
        settings["scheduledMute"],
        settings["volume"],
        settings["operationSoundRepeatDay"],
    )
    return settings


def build_mass2_settings_set_req(settings: dict) -> bytearray:
    """Build a MASS2SettingsSetReq packet from a settings dict.

    Assembles a MASS2 settings-set request per the device protocol.
    """
    cmd = bytearray([0x12, 0xC8])
    cmd.append(settings.get("scheduledMute", 0) & 0xFF)
    cmd.append(settings.get("volume", 0) & 0xFF)
    cmd.append(settings.get("operationSoundRepeatDay", 0) & 0xFF)
    cmd += int(settings.get("openingTime", 0)).to_bytes(2, "little")
    cmd += int(settings.get("closingTime", 0)).to_bytes(2, "little")
    for alarm in settings.get("alarmClocks", []):
        cmd.append(alarm.get("switchRepeatDay", 0) & 0xFF)
        cmd += int(alarm.get("openingTime", 0)).to_bytes(2, "little")
    # Pad with default alarms if fewer than 4 were provided
    while len(cmd) < 21:
        cmd.append(0)
    return cmd


def build_mass2_set_time_req(now, tz_offset_hours: int, is_24h: bool = True) -> bytearray:
    """Build SetTimeReq packet (CMD 0x12 0xCE) for the MASS2 RTC.

    Pushes the current wall-clock time on every successful connect. The
    payload (after the 0x12 0xCE header) is::

        byte 0     : is_24h (0/1)
        byte 1     : hour (0-23)
        byte 2     : minute (0-59)
        byte 3     : second (0-59)
        bytes 4-5  : millisecond (uint16 LE)
        byte 6     : year - 2000
        byte 7     : month (1-12)
        byte 8     : day (1-31)
        byte 9     : ISO weekday (Mon=1 .. Sun=7)
        byte 10    : timezone offset hours (signed int8)

    `now` is expected to be a tz-aware ``datetime`` in the local zone the
    user wants displayed on the device.
    """
    cmd = bytearray([0x12, 0xCE])
    cmd.append(1 if is_24h else 0)
    cmd.append(now.hour & 0xFF)
    cmd.append(now.minute & 0xFF)
    cmd.append(now.second & 0xFF)
    cmd += (now.microsecond // 1000).to_bytes(2, "little")
    cmd.append((now.year - 2000) & 0xFF)
    cmd.append(now.month & 0xFF)
    cmd.append(now.day & 0xFF)
    cmd.append(now.isoweekday() & 0xFF)
    cmd.append(tz_offset_hours & 0xFF)  # signed int8 → wrap to byte
    return cmd
