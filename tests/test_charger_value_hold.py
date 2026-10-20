"""Tests for holding charger values through missing responses.

The charger does not answer every command of a cycle. Each gap used to
blank the slot for one cycle: status unknown, current 0, and back again
with the next cycle.
"""

from __future__ import annotations

from isdt_air_ble.parser import ChargerValueHold

CHARGING = {"work_state_str": "charging", "capacity_percentage": 88}
ELECTRIC = {"output_voltage": 1.5, "charging_current": 0.965}


def test_missing_response_keeps_last_values():
    hold = ChargerValueHold()
    hold.apply({0: {**CHARGING, **ELECTRIC}})

    # WorkState for channel 0 did not arrive this cycle
    merged = hold.apply({0: dict(ELECTRIC)})

    assert merged[0]["work_state_str"] == "charging"
    assert merged[0]["capacity_percentage"] == 88
    assert merged[0]["charging_current"] == 0.965


def test_new_values_replace_held_ones():
    hold = ChargerValueHold()
    hold.apply({0: {**CHARGING, **ELECTRIC}})

    # Battery taken out: the charger reports it, nothing is held over it
    merged = hold.apply({0: {"work_state_str": "empty", "capacity_percentage": 0}})

    assert merged[0]["work_state_str"] == "empty"
    assert merged[0]["capacity_percentage"] == 0


def test_value_dropped_after_max_missed_cycles():
    hold = ChargerValueHold(max_missed=3)
    hold.apply({0: dict(CHARGING)})

    for _ in range(3):
        assert hold.apply({0: {}})[0]["work_state_str"] == "charging"

    assert "work_state_str" not in hold.apply({0: {}})[0]


def test_received_value_resets_the_count():
    hold = ChargerValueHold(max_missed=2)
    hold.apply({0: dict(CHARGING)})
    hold.apply({0: {}})
    hold.apply({0: {}})
    hold.apply({0: dict(CHARGING)})
    hold.apply({0: {}})

    assert hold.apply({0: {}})[0]["work_state_str"] == "charging"


def test_channels_are_held_independently():
    hold = ChargerValueHold()
    hold.apply({0: dict(CHARGING), 1: {"work_state_str": "done"}})

    merged = hold.apply({0: {}, 1: {"work_state_str": "empty"}})

    assert merged[0]["work_state_str"] == "charging"
    assert merged[1]["work_state_str"] == "empty"


def test_reset_forgets_held_values():
    hold = ChargerValueHold()
    hold.apply({0: dict(CHARGING)})
    hold.reset()

    assert hold.apply({0: {}}) == {0: {}}


def test_result_is_a_copy():
    hold = ChargerValueHold()
    merged = hold.apply({0: dict(CHARGING)})
    merged[0]["work_state_str"] = "changed"

    assert hold.apply({0: {}})[0]["work_state_str"] == "charging"
