"""MASS2 regression tests against a real capture.

The fixtures under ``fixtures/mass2`` were cut from a btsnoop recording of
a MASS2 connected to Home Assistant (MTU 247, so every response arrived in
one notification). They cover a reconnect with settings readout, one to
five loaded ports with and without USB-PD, beep/volume writes and all
ports unplugged. The MTU-23 test splits the same frames into 20-byte
notifications to cover the reassembly path.

Every USB-C port has a cable attached for the whole capture: C1 an Apple
Watch charging pad, C2 a Samsung charging pad, C3 a micro-USB cable, C4
a Lightning cable, C5 and C6 plain USB-C to USB-C cables. C1..C4 report
status 1 at 5 V even when nothing charges (a cable to a legacy connector
presents itself as a sink, so the port switches on); C5 and C6 stay at
status 0 until a device is plugged in. The idle pads show small standby
pulses.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from isdt_air_ble.const import MASS2_PORT_COUNT
from isdt_air_ble.parser import (
    build_mass2_set_time_req,
    build_mass2_settings_set_req,
    parse_hardware_info,
    parse_mass2_responses,
)

FIXTURES = Path(__file__).parent / "fixtures" / "mass2"
ALL_FIXTURES = sorted(p.name for p in FIXTURES.glob("*.jsonl"))

# Port index -> label (MASS2_PORT_LABELS order: C1..C6, A1, A2)
C1, C2, C3, C4, C5, C6, A1, A2 = range(8)


def _events(fixture: str) -> list[dict]:
    return [
        json.loads(line)
        for line in (FIXTURES / fixture).read_text().splitlines()
        if line.strip()
    ]


def _raw(event: dict) -> bytes:
    return bytes.fromhex(event["hex"].replace(" ", ""))


def _notifies(fixture: str, char: str = "AF01") -> list[bytes]:
    return [
        _raw(e)
        for e in _events(fixture)
        if e["kind"] == "notify" and e["char"] == char
    ]


def _writes(fixture: str, purpose: str) -> list[bytes]:
    return [
        _raw(e)
        for e in _events(fixture)
        if e["kind"] == "write" and e.get("purpose") == purpose
    ]


def _status_frames(fixture: str) -> list[bytes]:
    return [f for f in _notifies(fixture) if f[1] == 0xC3]


def _loaded(ports: dict) -> set[int]:
    return {p for p in range(MASS2_PORT_COUNT) if ports[p]["current"] > 0}


@pytest.mark.parametrize("fixture", ALL_FIXTURES)
def test_every_status_frame_decodes(fixture):
    frames = _status_frames(fixture)
    assert frames
    for frame in frames:
        assert len(frame) == 59
        ports, _, _ = parse_mass2_responses([frame])
        assert ports is not None
        assert all(key in ports[p] for p in range(8) for key in ("voltage", "current"))
        # Byte 2 is the device's own total, which tracks the port sum.
        port_sum = sum(ports[p]["power"] for p in range(MASS2_PORT_COUNT))
        assert ports["_total_power"] == pytest.approx(port_sum, abs=1.5)


def test_connect_bind_and_hardware_info():
    bind = _writes("connect.jsonl", "BindReq")
    assert len(bind) == 1 and bind[0][0] == 0x18 and len(bind[0]) == 19
    assert _notifies("connect.jsonl", "AF02")[0] == bytes([0x19, 0x00])  # known UUID

    hw_resp = next(f for f in _notifies("connect.jsonl", "AF02") if f[0] == 0xE1)
    hw, sw, serial = parse_hardware_info(hw_resp)
    assert (hw, sw) == ("1.0", "1.24")
    assert serial is None  # device id is the padded model name "MASS2   "


def test_connect_settings_response():
    _, settings, _ = parse_mass2_responses(_notifies("connect.jsonl"))
    assert settings == {
        "scheduledMute": 0,
        "volume": 0,
        "operationSoundRepeatDay": 0,
        "openingTime": 9,
        "closingTime": 21,
        "alarmClocks": [
            {"switchRepeatDay": 0, "openingTime": 8},
            {"switchRepeatDay": 0, "openingTime": 9},
            {"switchRepeatDay": 0, "openingTime": 10},
            {"switchRepeatDay": 0, "openingTime": 11},
        ],
    }


def test_connect_set_time_matches_builder():
    """The captured SetTimeReq equals what the builder makes for that moment."""
    (captured,) = _writes("connect.jsonl", "SetTimeReq")
    tz = dt.timezone(dt.timedelta(hours=1))
    now = dt.datetime(2026, 11, 23, 21, 4, 15, 338000, tzinfo=tz)
    assert build_mass2_set_time_req(now, 1) == captured


def test_connect_all_ports_unloaded():
    ports, _, _ = parse_mass2_responses(_status_frames("connect.jsonl")[-1:])
    assert _loaded(ports) == set()
    assert ports["_total_power"] == 0
    # C1..C4 (pads, micro-USB, Lightning) are powered at 5.088 V, 0 mA;
    # C5/C6 (bare USB-C cables), A1 and A2 stay off (status 0).
    assert [ports[p]["status"] for p in range(8)] == [1, 1, 1, 1, 0, 0, 0, 0]


def test_one_port_usb_pd_5v():
    ports, _, _ = parse_mass2_responses(_status_frames("one_port_pd5v.jsonl")[-1:])
    assert _loaded(ports) == {C2}
    assert ports[C2]["protocol_str"] == "pd"
    assert ports[C2]["voltage"] == pytest.approx(5.088)


def test_two_ports_usb_pd_9v():
    ports, _, _ = parse_mass2_responses(_status_frames("two_ports_pd9v.jsonl")[-1:])
    assert _loaded(ports) == {C2, C6}
    assert ports[C6]["protocol_str"] == "pd"
    assert 9.0 < ports[C6]["voltage"] < 9.5
    assert ports[C6]["current"] > 2.0
    assert ports["_total_power"] >= 20


def test_five_ports_mixed_protocols():
    ports, _, _ = parse_mass2_responses(_status_frames("five_ports.jsonl")[-1:])
    assert _loaded(ports) >= {C2, C3, C5, C6, A1}
    assert ports[C2]["protocol_str"] == "pd"
    assert ports[C6]["protocol_str"] == "pd"
    for port in (C3, C5, A1):
        assert ports[port]["protocol_str"] == "none"
        assert 5.0 < ports[port]["voltage"] < 5.3


@pytest.mark.parametrize("fixture", ["five_ports.jsonl", "all_unplugged.jsonl"])
def test_idle_pad_on_c1_shows_phantom_pulses(fixture):
    """The idle Apple Watch pad on C1 alternates between 0 and ~38 mA.

    That is the standby probe pulse (~0.2 W) the coordinator's phantom-load
    filter has to hide; the raw parser must pass it through unchanged.
    """
    currents = {
        parse_mass2_responses([f])[0][C1]["current"] for f in _status_frames(fixture)
    }
    assert 0.0 in currents
    assert any(0 < c < 0.1 for c in currents)


def test_all_unplugged_ends_at_zero():
    ports, _, _ = parse_mass2_responses(_status_frames("all_unplugged.jsonl")[-1:])
    assert ports["_total_power"] == 0
    assert _loaded(ports) <= {C1, C2}  # at most the idle pads' pulses


def test_settings_writes_match_builder():
    """Beep on, volume medium, volume low, beep off — byte-exact."""
    _, settings, _ = parse_mass2_responses(_notifies("connect.jsonl"))
    writes = _writes("settings_set.jsonl", "SettingsSetReq")
    steps = [{"scheduledMute": 1}, {"volume": 1}, {"volume": 0}, {"scheduledMute": 0}]
    assert len(writes) == len(steps)
    for update, captured in zip(steps, writes):
        settings = {**settings, **update}
        assert build_mass2_settings_set_req(settings) == captured

    acks = [f for f in _notifies("settings_set.jsonl") if f[1] == 0xC9]
    assert acks == [bytes([0x31, 0xC9, 0x01])] * 4


@pytest.mark.parametrize("fixture", ALL_FIXTURES)
def test_reassembly_at_mtu_23(fixture):
    """Split every notification into 20-byte chunks and reassemble.

    Uses the coordinator's real handler. Status, settings, schedule and
    the 3-byte ack frames must all come out unchanged.
    """
    coord = pytest.importorskip("isdt_air_ble.coordinator")
    import asyncio

    c = object.__new__(coord.ISDTDataUpdateCoordinator)
    c._mass2_buffer = bytearray()
    c._response_queue = asyncio.Queue()
    c._on_response = lambda: None

    frames = _notifies(fixture)
    for frame in frames:
        for i in range(0, len(frame), 20):
            c._handle_adapter_notification(frame[i : i + 20])

    out = []
    while not c._response_queue.empty():
        out.append(c._response_queue.get_nowait())
    expected = [
        f for f in frames if f[1] in (0xC3, 0xCB, 0xC7, 0xC5, 0xC9, 0xCD, 0xCF)
    ]
    assert out == expected
