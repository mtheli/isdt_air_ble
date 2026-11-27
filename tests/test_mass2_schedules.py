"""MASS2 quiet hours, USB-C port schedules and force-on against a real capture.

``fixtures/mass2/app_schedules.jsonl`` was cut from an HCI snoop of the
vendor app (Polying 2.1.6 on Android) changing every schedule setting once;
see the fixture's meta line for the sequence. Each test replays one UI
change on top of the previously captured state and requires the builder to
produce exactly the frame the app sent.
"""

from __future__ import annotations

import asyncio
import json
from datetime import time
from pathlib import Path

import pytest

from isdt_air_ble.const import (
    MASS2_SCHEDULE_STATE_FORCED,
    MASS2_SCHEDULE_STATE_OFF,
    MASS2_SCHEDULE_STATE_ON,
    MASS2_SCHEDULE_STATE_WAITING,
)
from isdt_air_ble.mass2_schedule import (
    build_repeat,
    days_list,
    days_option,
    mask_from_days,
    time_to_word,
    with_days,
    with_enabled,
    word_to_time,
)
from isdt_air_ble.parser import (
    build_mass2_force_on_req,
    build_mass2_settings_set_req,
    build_mass2_usb_schedules_set_req,
    parse_mass2_responses,
    parse_mass2_usb_schedules,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mass2" / "app_schedules.jsonl"
C1, C5 = 0, 4


def _events() -> list[dict]:
    return [json.loads(line) for line in FIXTURE.read_text().splitlines() if line]


def _raw(event: dict) -> bytes:
    return bytes.fromhex(event["hex"].replace(" ", ""))


def _writes(purpose: str) -> list[bytes]:
    return [_raw(e) for e in _events() if e["kind"] == "write" and e["purpose"] == purpose]


def _notifies(cls: str) -> list[bytes]:
    return [_raw(e) for e in _events() if e["kind"] == "notify" and e["cls"] == cls]


def _t(hour: int, minute: int) -> int:
    return time_to_word(time(hour, minute))


def test_usb_schedules_response_decodes():
    (frame,) = _notifies("USBSchedulesResp")
    schedules = parse_mass2_usb_schedules(frame)
    # What the app showed for each port before any change
    assert [s["repeat"] for s in schedules] == [0x7F, 0x18, 0x00, 0x01, 0x00, 0x7F]
    assert word_to_time(schedules[C1]["openingTime"]) == time(18, 0)
    assert word_to_time(schedules[C1]["closingTime"]) == time(19, 0)
    assert word_to_time(schedules[C5]["openingTime"]) == time(0, 26)
    assert word_to_time(schedules[C5]["closingTime"]) == time(19, 34)
    assert days_list(schedules[1]["repeat"]) == ["thursday", "friday"]
    # parse_mass2_responses routes the frame too
    assert parse_mass2_responses([frame])[2] == schedules


def test_usb_schedule_writes_match_builder():
    (frame,) = _notifies("USBSchedulesResp")
    schedules = parse_mass2_usb_schedules(frame)
    steps = [
        (C1, {"repeat": with_enabled(0x7F, True)}),          # on   -> ff
        (C1, {"closingTime": _t(19, 12)}),
        (C1, {"openingTime": _t(19, 2)}),
        (C1, {"repeat": with_days(0xFF, 0x3F)}),             # Sunday out -> bf
        (C1, {"repeat": with_enabled(0xBF, False)}),         # off  -> 3f
        (C1, {"repeat": with_enabled(0x3F, True)}),          # on   -> bf
        (C1, {"repeat": with_enabled(0xBF, False)}),         # off  -> 3f
        (C5, {"repeat": 0x80}),   # app allows "on" without days (one-shot)
        (C5, {"repeat": with_enabled(0x80, False)}),         # off  -> 00
    ]
    writes = _writes("USBSchedulesSetReq")
    assert len(writes) == len(steps)
    for (port, update), captured in zip(steps, writes):
        schedules = [dict(s) for s in schedules]
        schedules[port].update(update)
        assert build_mass2_usb_schedules_set_req(schedules) == captured
    assert _notifies("USBSchedulesSetAck") == [bytes([0x31, 0xC5, 0x01])] * len(steps)


def test_enabling_without_days_selects_every_day():
    """Unlike the app, the switch never sends a one-shot schedule."""
    assert with_enabled(0x00, True) == 0xFF
    assert with_enabled(0x18, True) == 0x98
    assert with_enabled(0x98, False) == 0x18


def test_end_force_on_sequence_is_off_then_on():
    """Ending force-on = schedule off and back on, as captured on C1."""
    (frame,) = _notifies("USBSchedulesResp")
    schedules = parse_mass2_usb_schedules(frame)
    schedules[C1].update(repeat=0xBF, openingTime=_t(19, 2), closingTime=_t(19, 12))
    cleared = [dict(s) for s in schedules]
    cleared[C1]["repeat"] = with_enabled(0xBF, False)
    writes = _writes("USBSchedulesSetReq")
    assert build_mass2_usb_schedules_set_req(cleared) == writes[4]
    assert build_mass2_usb_schedules_set_req(schedules) == writes[5]


def test_force_on_matches_builder():
    assert _writes("ForceOnReq") == [build_mass2_force_on_req(1)]
    assert _notifies("ForceOnAck") == [bytes([0x31, 0xCD, 0x01])]
    with pytest.raises(ValueError):
        build_mass2_force_on_req(7)


def test_schedule_state_follows_force_on():
    """WorkStatus byte +2: 2 outside the window, 3 forced, 0 when off."""
    states = [
        parse_mass2_responses([f])[0][C1]["schedule_state"]
        for f in _notifies("WorkStatusResp")
    ]
    # first C1 schedule on (inside window), moved out of the window, forced,
    # schedule off clears it, on again waits, off again
    assert states[:2] == [MASS2_SCHEDULE_STATE_OFF, MASS2_SCHEDULE_STATE_ON]
    assert MASS2_SCHEDULE_STATE_WAITING in states
    # consecutive duplicates come from other bytes of the frame changing
    changes = [s for i, s in enumerate(states) if i == 0 or s != states[i - 1]]
    forced_at = changes.index(MASS2_SCHEDULE_STATE_FORCED)
    assert changes[forced_at - 1] == MASS2_SCHEDULE_STATE_WAITING
    assert changes[forced_at + 1] == MASS2_SCHEDULE_STATE_OFF


def test_settings_writes_match_builder():
    """Quiet hours and alarm changes from the app, byte-exact."""
    _, settings, _ = parse_mass2_responses(_notifies("SettingsResp"))
    r = settings["operationSoundRepeatDay"]
    assert r == 0x7E and days_option(r) == "custom"

    def alarm4(repeat):
        alarms = [dict(a) for a in settings["alarmClocks"]]
        alarms[3]["switchRepeatDay"] = repeat
        return {"alarmClocks": alarms}

    steps = [
        {"scheduledMute": 1},
        {"volume": 1},
        {"operationSoundRepeatDay": with_enabled(0x7E, True)},       # fe
        {"operationSoundRepeatDay": with_days(0xFE, 0x3E)},          # be
        {"openingTime": _t(19, 6), "closingTime": _t(20, 11)},
        {"openingTime": _t(20, 7)},
        {"operationSoundRepeatDay": with_enabled(0xBE, False)},      # 3e
        alarm4(0x80),
        alarm4(0xC4),
        alarm4(0x44),
    ]
    writes = _writes("SettingsSetReq")
    assert len(writes) == len(steps)
    for update, captured in zip(steps, writes):
        settings = {**settings, **update}
        assert build_mass2_settings_set_req(settings) == captured


def test_day_presets():
    assert days_option(0xFF) == "every_day"
    assert days_option(0x9F) == "weekdays"
    assert days_option(0x60) == "weekend"
    assert days_option(0x80) == "custom"
    assert with_days(0xBE, 0x1F) == 0x9F
    assert with_days(0x3E, 0x60) == 0x60


def test_time_word_roundtrip():
    assert word_to_time(0x0A12) == time(18, 10)
    assert time_to_word(time(20, 11)) == 0x0B14
    assert word_to_time(0x3C18) is None  # 24:60 out of range


class _FakeClient:
    is_connected = True

    def __init__(self):
        self.writes: list[bytes] = []

    async def write_gatt_char(self, char, data, response=False):
        self.writes.append(bytes(data))


def _coordinator(schedules):
    coord = pytest.importorskip("isdt_air_ble.coordinator")
    c = object.__new__(coord.ISDTDataUpdateCoordinator)
    c._mass2_usb_schedules = schedules
    c._connection_lock = asyncio.Lock()
    c._client = _FakeClient()
    c.data = None
    return c


def test_coordinator_write_keeps_other_ports():
    (frame,) = _notifies("USBSchedulesResp")
    c = _coordinator(parse_mass2_usb_schedules(frame))
    asyncio.run(c.async_set_mass2_usb_schedule(1, repeat=0xFF))
    assert c._client.writes == [_writes("USBSchedulesSetReq")[0]]


def test_coordinator_end_force_on_restores_schedule():
    (frame,) = _notifies("USBSchedulesResp")
    schedules = parse_mass2_usb_schedules(frame)
    schedules[C1].update(repeat=0xBF, openingTime=_t(19, 2), closingTime=_t(19, 12))
    c = _coordinator(schedules)
    asyncio.run(c.async_mass2_end_force_on(1))
    writes = _writes("USBSchedulesSetReq")
    assert c._client.writes == [writes[4], writes[5]]
    assert c._mass2_usb_schedules[C1]["repeat"] == 0xBF


def test_set_schedule_repeat():
    """The set_schedule action: any day combination, bit 7 kept or set."""
    assert mask_from_days(["tuesday", "wednesday", "thursday", "friday", "saturday"]) == 0x3E
    # keep on/off when "enabled" is left out
    assert build_repeat(0xFE, ["monday", "sunday"], None) == 0xC1
    assert build_repeat(0x7E, ["monday", "sunday"], None) == 0x41
    # explicit on/off
    assert build_repeat(0x00, ["friday"], True) == 0x90
    assert build_repeat(0xFF, ["friday"], False) == 0x10
    with pytest.raises(ValueError):
        build_repeat(0xFF, [], True)
    # the captured quiet hours change (Sunday out) through the action path
    assert build_repeat(
        0xFE, ["tuesday", "wednesday", "thursday", "friday", "saturday"], None
    ) == 0xBE
