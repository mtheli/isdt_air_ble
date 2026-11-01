"""NP2 Air / LP2 Air (camera battery chargers) work-state tests.

The frames are built from the values of a real NP2 Air debug log (#13):
an empty slot, a Sony NP-FZ100 charging in slot 2, and the same slot right
after the battery was removed. After removal the charger reports work
state 0 again but keeps the last capacity, voltage, current, duration and
battery type, which used to keep the slot showing as occupied.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from isdt_air_ble.parser import (
    ChargerValueHold,
    clear_empty_slots,
    parse_charger_responses,
)


def _workstate(
    ch: int,
    state: int,
    cap_pct: int = 0,
    mah: int = 0,
    ms: int = 0,
    btype: int = 100,
    error: int = 0,
) -> bytes:
    frame = bytearray(38)
    frame[0:3] = bytes([0x31, 0xE7, ch])
    frame[3] = state
    frame[4] = cap_pct
    frame[5:9] = mah.to_bytes(4, "little")
    frame[13:17] = ms.to_bytes(4, "little")
    frame[17] = btype
    frame[36:38] = error.to_bytes(2, "little")
    return bytes(frame)


def _electric(ch: int, in_v: float, in_a: float, out_v: float, charge_a: float) -> bytes:
    frame = bytearray(31)
    frame[0:3] = bytes([0x31, 0xE5, ch])
    frame[3:5] = round(in_v * 1000).to_bytes(2, "little")
    frame[5:9] = round(in_a * 1000).to_bytes(4, "little")
    frame[9:11] = round(out_v * 1000).to_bytes(2, "little")
    frame[11:15] = round(charge_a * 1000).to_bytes(4, "little")
    return bytes(frame)


def _ir(ch: int, mohm_x10: int) -> bytes:
    frame = bytearray(19)
    frame[0:3] = bytes([0x31, 0xFB, ch])
    frame[3:5] = mohm_x10.to_bytes(2, "little")
    return bytes(frame)


def _cycle(frames: list[bytes], model: str = "NP2 Air", hold=None) -> dict:
    """Run one poll cycle the way the coordinator does."""
    parsed, _ = parse_charger_responses(frames, num_channels=2, model=model)
    hold = hold or ChargerValueHold()
    return clear_empty_slots(hold.apply(parsed))


EMPTY = [_workstate(1, 0), _electric(1, 8.94, 0.0, 0.0, 0.0), _ir(1, 0)]
CHARGING = [
    _workstate(1, 19, cap_pct=51, mah=6, ms=27200, btype=7),
    _electric(1, 8.69, 1.028, 7.71, 1.0),
    _ir(1, 123),
]
REMOVED = [
    _workstate(1, 0, cap_pct=51, mah=6, ms=27900, btype=7),
    _electric(1, 8.93, 1.0, 7.71, 1.0),
    _ir(1, 123),
]


def test_empty_slot():
    ch = _cycle(EMPTY)[1]
    assert ch["work_state_str"] == "empty"
    assert ch["battery_type_str"] is None


def test_charging_normal_mode():
    ch = _cycle(CHARGING)[1]
    assert ch["work_state_str"] == "charging"
    assert ch["battery_type_str"] == "NP-FZ100"
    assert ch["capacity_percentage"] == 51
    assert ch["output_voltage"] == pytest.approx(7.71)
    assert ch["ir_mohm"] == pytest.approx(12.3)


def test_removed_battery_blanks_stale_values():
    """State 0 with leftover values from the removed battery is empty."""
    ch = _cycle(REMOVED)[1]
    assert ch["work_state_str"] == "empty"
    assert ch["battery_type_str"] is None
    assert ch["capacity_percentage"] == 0
    assert ch["capacity_done"] == 0
    assert ch["work_period"] == 0
    assert ch["output_voltage"] == 0.0
    assert ch["charging_current"] == 0.0
    assert ch["ir_mohm"] is None
    # Input values are device-wide and stay.
    assert ch["input_voltage"] == pytest.approx(8.93)


def test_held_values_do_not_return_after_removal():
    """A missing ElectricResp right after removal must not revive 7.71 V."""
    hold = ChargerValueHold()
    _cycle(CHARGING, hold=hold)
    ch = _cycle([REMOVED[0]], hold=hold)[1]
    assert ch["work_state_str"] == "empty"
    assert ch["output_voltage"] == 0.0
    assert ch["charging_current"] == 0.0


@pytest.mark.parametrize(
    "state, expected",
    [(19, "charging"), (20, "charging"), (5, "charging"), (21, "done"), (22, "done")],
)
def test_work_state_map(state, expected):
    ch = _cycle([_workstate(1, state, btype=8)])[1]
    assert ch["work_state_str"] == expected
    assert ch["battery_type_str"] == "NP-FW50"


@pytest.mark.parametrize("state", [0, 19, 21])
def test_error_code_overrides_state(state):
    ch = _cycle([_workstate(1, state, btype=7, error=0x0040)])[1]
    assert ch["work_state_str"] == "error"
    assert ch["error_code"] == 0x0040


def test_lp2_air_battery_types():
    ch = _cycle([_workstate(0, 19, btype=10)], model="LP2 Air")[0]
    assert ch["work_state_str"] == "charging"
    assert ch["battery_type_str"] == "LP-E6"


def test_round_cell_charger_unchanged():
    """C4 Air keeps its own map and its values are never blanked."""
    frames = [
        _workstate(1, 0, cap_pct=51, mah=6, btype=1),
        _electric(1, 8.93, 0.0, 4.1, 0.0),
    ]
    ch = _cycle(frames, model="C4 Air")[1]
    assert ch["work_state_str"] == "idle"
    assert ch["battery_type_str"] == "LiIon"
    assert ch["capacity_percentage"] == 51
    assert ch["output_voltage"] == pytest.approx(4.1)


def _status_sensor(model: str, data: dict):
    pytest.importorskip("homeassistant")
    from isdt_air_ble.sensor import ISDTC4StatusSensor

    coordinator = SimpleNamespace(
        address="AA:BB:CC:DD:EE:FF", model=model, connected=True,
        last_update_success=True, data=data,
    )
    return ISDTC4StatusSensor(coordinator, "slot_status", "work_state_str", 1, 2)


def test_status_sensor_unmapped_state_is_unknown(caplog):
    """An unknown code used to raise on every update (ENUM options check)."""
    sensor = _status_sensor("C4 Air", {1: {"work_state": 19, "work_state_str": "unknown_19"}})
    assert sensor.native_value is None
    assert sensor.native_value is None
    assert caplog.text.count("unmapped work state 19") == 1


def test_status_sensor_camera_charger_after_removal():
    data = _cycle(REMOVED)
    assert _status_sensor("NP2 Air", data).native_value == "empty"
