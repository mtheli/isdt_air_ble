"""Unit tests for the PS200 (Power 200 family) packet parser.

Frames are built synthetically from the documented wire layout:
  * WorkingStatusResp 0x95: channel count in byte 2, timestamp, then
    34 bytes per channel.
  * DCStatusResp 0x97: timestamp first, channel count in byte 6, then
    22 bytes per channel (signed voltage — negative means DC input).
  * AlarmToneResp 0x93: shared with the chargers.
"""

from __future__ import annotations

import struct

from isdt_air_ble.const import (
    AdapterProtocol,
    DEVICE_MODEL_MAP,
    DeviceType,
    PS200_PORT_LABELS,
    detect_model_from_mfg_data,
    get_adapter_protocol,
    get_device_type,
    get_port_count,
    get_port_labels,
)
from isdt_air_ble.parser import parse_ps200_responses


# --- Frame builders -----------------------------------------------------------


def _work_status_channel(
    channel_id: int,
    valid_id: int = 0,
    protocol: int = 0,
    reserve: int = 0,
    reserve1: int = 0,
    voltage_mv: int = 0,
    current_ma: int = 0,
    power_mw: int = 0,
    max_power_mw: int = 0,
    current_power: int = 0,
    work_time_s: int = 0,
    energy_mwh: int = 0,
) -> bytes:
    return struct.pack(
        "<BbBBBb7I",
        channel_id,
        valid_id,
        0,  # channel_type
        protocol,
        reserve,
        reserve1,
        voltage_mv,
        current_ma,
        power_mw,
        max_power_mw,
        current_power,
        work_time_s,
        energy_mwh,
    )


def _work_status_frame(channels: list[bytes], timestamp: int = 12345) -> bytes:
    return bytes([0x31, 0x95, len(channels)]) + struct.pack("<I", timestamp) + b"".join(channels)


def _dc_status_channel(
    channel_type: int = 0,
    valid_id: int = 0,
    voltage_mv: int = 0,
    current_ma: int = 0,
) -> bytes:
    return struct.pack("<BB5i", channel_type, valid_id, voltage_mv, current_ma, 0, 0, 0)


def _dc_status_frame(channels: list[bytes], timestamp: int = 12345) -> bytes:
    return bytes([0x31, 0x97]) + struct.pack("<I", timestamp) + bytes([len(channels)]) + b"".join(channels)


# --- Model detection / classification -----------------------------------------


def test_power200_family_model_ids():
    assert DEVICE_MODEL_MAP["01080000"] == "Power 200"
    assert detect_model_from_mfg_data(bytes.fromhex("affa010d0000")) == "Power 200H"
    assert detect_model_from_mfg_data(bytes.fromhex("affa010e0000")) == "Power 200X"


def test_power200_family_is_ps200_adapter():
    for model in ("Power 200", "Power 200H", "Power 200X"):
        assert get_device_type(model) == DeviceType.ADAPTER
        assert get_adapter_protocol(model) == AdapterProtocol.PS200
        assert get_port_count(model) == 5
        assert get_port_labels(model) == PS200_PORT_LABELS


def test_mass2_keeps_its_protocol():
    assert get_adapter_protocol("MASS2") == AdapterProtocol.MASS2
    assert get_port_count("MASS2") == 8


# --- WorkingStatusResp --------------------------------------------------------


def test_work_status_active_usb_port():
    """USB-C1 (channel 2) delivering 9 V / 2 A / 18 W via PD3.0."""
    channels = [_work_status_channel(i) for i in range(5)]
    channels[2] = _work_status_channel(
        2,
        valid_id=1,
        protocol=5,
        voltage_mv=9000,
        current_ma=2000,
        power_mw=18000,
        max_power_mw=65000,
        work_time_s=600,
        energy_mwh=3000,
    )
    ports, dc, alarm = parse_ps200_responses([_work_status_frame(channels)])

    assert dc is None and alarm is None
    assert ports is not None
    port = ports[2]
    assert port["status"] == 1
    assert port["protocol_str"] == "pd3"
    assert port["voltage"] == 9.0
    assert port["current"] == 2.0
    assert port["power"] == 18.0
    assert port["max_power"] == 65.0
    assert port["work_time"] == 600
    assert port["energy_wh"] == 3.0
    # Only active ports count towards the total
    assert ports["_total_power"] == 18.0


def test_work_status_negative_valid_id_is_active():
    """The app treats |valid_id| == 1 as active (signed byte)."""
    channels = [_work_status_channel(i) for i in range(5)]
    channels[1] = _work_status_channel(1, valid_id=-1, voltage_mv=5000, power_mw=2500)
    ports, _, _ = parse_ps200_responses([_work_status_frame(channels)])
    assert ports[1]["status"] == 1
    assert ports["_total_power"] == 2.5


def test_work_status_wireless_pad_phone_battery():
    """Channel 0 is the wireless pad and carries phone brand + battery."""
    channels = [_work_status_channel(i) for i in range(5)]
    channels[0] = _work_status_channel(
        0, valid_id=1, reserve=76, reserve1=1, voltage_mv=5000, power_mw=7500
    )
    ports, _, _ = parse_ps200_responses([_work_status_frame(channels)])
    assert ports[0]["phone_brand"] == "Apple"
    assert ports[0]["phone_battery"] == 76


def test_work_status_wireless_pad_without_phone():
    """No phone on the pad → no brand, no battery level."""
    channels = [_work_status_channel(i) for i in range(5)]
    ports, _, _ = parse_ps200_responses([_work_status_frame(channels)])
    assert ports[0]["phone_brand"] is None
    assert ports[0]["phone_battery"] is None
    assert ports[0]["status"] == 0


def test_work_status_truncated_frame_rejected():
    channels = [_work_status_channel(i) for i in range(5)]
    frame = _work_status_frame(channels)[:-10]
    ports, _, _ = parse_ps200_responses([frame])
    assert ports is None


def test_work_status_variable_channel_count():
    """Channel count comes from the frame, not from a hardcoded layout."""
    channels = [_work_status_channel(i, valid_id=1, power_mw=1000) for i in range(4)]
    ports, _, _ = parse_ps200_responses([_work_status_frame(channels)])
    assert ports is not None
    assert ports["_total_power"] == 4.0


# --- DCStatusResp -------------------------------------------------------------


def test_dc_status_output():
    frame = _dc_status_frame([
        _dc_status_channel(valid_id=1, voltage_mv=12000, current_ma=1500),
        _dc_status_channel(),
    ])
    _, dc, _ = parse_ps200_responses([frame])
    assert dc is not None
    ch = dc["channels"][0]
    assert ch["voltage"] == 12.0
    assert ch["current"] == 1.5
    assert ch["is_input"] is False


def test_dc_status_negative_voltage_is_input():
    """Negative DC voltage means the jack is acting as an input."""
    frame = _dc_status_frame([
        _dc_status_channel(valid_id=1, voltage_mv=-20000, current_ma=3000),
    ])
    _, dc, _ = parse_ps200_responses([frame])
    assert dc["channels"][0]["voltage"] == -20.0
    assert dc["channels"][0]["is_input"] is True


def test_dc_status_truncated_frame_rejected():
    frame = _dc_status_frame([_dc_status_channel(valid_id=1)])[:-5]
    _, dc, _ = parse_ps200_responses([frame])
    assert dc is None


# --- AlarmToneResp / mixed cycles ---------------------------------------------


def test_alarm_tone_parsed_from_cycle():
    channels = [_work_status_channel(i) for i in range(5)]
    responses = [
        _work_status_frame(channels),
        _dc_status_frame([_dc_status_channel()]),
        bytes([0x31, 0x93, 0x01]),
    ]
    ports, dc, alarm = parse_ps200_responses(responses)
    assert ports is not None
    assert dc is not None
    assert alarm is True


def test_alarm_tone_off():
    _, _, alarm = parse_ps200_responses([bytes([0x31, 0x93, 0x00])])
    assert alarm is False


def test_unknown_command_ignored():
    ports, dc, alarm = parse_ps200_responses([bytes([0x31, 0xC3, 0x00, 0x00])])
    assert ports is None and dc is None and alarm is None
