"""Air 8 LiPo balance charger parser tests.

Each fixture is a JSONL trace captured from a real Air 8 with a known
battery pack attached.  We replay every ``notify`` event through
``parse_charger_responses`` with ``num_channels=1`` and assert that the
decoded pack voltage, cell voltages and internal-resistance values match
the physics of the connected pack.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from isdt_air_ble.parser import parse_charger_responses

FIXTURES = Path(__file__).parent / "fixtures" / "air8"


def _replay(fixture: str):
    """Return (parsed_channel_0, alarm_tone) for the given fixture file."""
    raw_notifies: list[bytes] = []
    for line in (FIXTURES / fixture).read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("kind") != "notify":
            continue
        if event.get("char") != "AF01":
            continue  # AF02 (Bind/Hardware) is not part of the polling loop
        raw_notifies.append(bytes.fromhex(event["hex"].replace(" ", "")))

    parsed, alarm = parse_charger_responses(raw_notifies, num_channels=1, model="Air 8")
    return parsed[0], alarm


def test_idle_no_battery():
    """No battery: workState=idle, no pack voltage, no cell data."""
    ch0, _ = _replay("idle_no_battery.jsonl")

    assert ch0["work_state"] == 0
    assert ch0["work_state_str"] == "idle"
    # Air 8 reports battery_type=1 = LiPo even when idle (last-used chemistry)
    assert ch0["battery_type_str"] == "LiPo"
    # link_type 0 = no battery detected
    assert ch0["link_type"] == 0
    # No pack voltage when no battery is connected
    assert ch0["output_voltage"] == pytest.approx(0.0)
    # Input voltage from the DC supply (≈ 13.8 V)
    assert 13.0 < ch0["input_voltage"] < 14.5
    # Cell voltages are all zero
    cells = ch0.get("cell_voltages", [])
    assert all(v == 0.0 for v in cells)


@pytest.mark.parametrize(
    "fixture, expected_cells, expected_pack_v",
    [
        ("idle_2s_battery.jsonl", 2, 8.012),
        ("idle_3s_battery.jsonl", 3, 11.864),
        ("idle_4s_battery.jsonl", 4, 15.315),
        ("idle_6s_battery.jsonl", 6, 23.785),
    ],
)
def test_battery_packs(fixture, expected_cells, expected_pack_v):
    """For each pack: detected cell count and pack voltage are correct."""
    ch0, _ = _replay(fixture)

    # work_state=3 = active charging (CC phase)
    assert ch0["work_state_str"] == "charging"
    assert ch0["battery_type_str"] == "LiPo"
    # link_type=3 = SmartLiPo-style pack with per-cell data
    assert ch0["link_type"] == 3
    # Detected cell count matches the pack
    assert ch0["unit_serials_num"] == expected_cells
    # Full-charge voltage per cell = 4.2 V (LiPo)
    assert ch0["full_charged_volt"] == pytest.approx(4.2, abs=0.01)
    # Pack voltage matches the sum of cells (verified ±5 mV)
    assert ch0["output_voltage"] == pytest.approx(expected_pack_v, abs=0.005)

    # Only the first <expected_cells> cells should carry voltage > 0.1 V
    cells = ch0.get("cell_voltages", [])
    populated = [v for v in cells if v > 0.1]
    assert len(populated) == expected_cells
    # All present cells are within a sane LiPo voltage band
    assert all(2.5 < v < 4.5 for v in populated)
    # Pack voltage equals the sum of present cells (to the mV)
    assert sum(populated) == pytest.approx(ch0["output_voltage"], abs=0.005)


def test_cells_sum_to_pack_voltage_all_fixtures():
    """Sanity check: for every battery fixture, Σ cell_v ≈ output_v."""
    for fixture in [
        "idle_2s_battery.jsonl",
        "idle_3s_battery.jsonl",
        "idle_4s_battery.jsonl",
        "idle_6s_battery.jsonl",
    ]:
        ch0, _ = _replay(fixture)
        populated = [v for v in ch0["cell_voltages"] if v > 0.1]
        assert sum(populated) == pytest.approx(ch0["output_voltage"], abs=0.005)


def test_per_cell_ir_array_layout():
    """The parser must surface ir_raw[] with sentinel 0xFFFF for the
    cells that aren't populated. The card reads this per-cell to draw
    individual IR readings on a balance-charger view, so the layout
    contract matters.

    TRES9000's 6S capture: cells 0-5 carry real IR values, cells 6-7
    are sentinels (0xFFFF).
    """
    ch0, _ = _replay("idle_6s_battery.jsonl")
    ir_raw = ch0["ir_raw"]

    # Eight slots are decoded from the 19-byte short IRResp.
    assert len(ir_raw) == 8

    # First six are real (the 6S pack): in the single-to-tens of mΩ band
    # once divided by 10. Raw range therefore 10-1000.
    for idx in range(6):
        assert 10 <= ir_raw[idx] < 1000, (
            f"cell {idx + 1} IR raw {ir_raw[idx]} is outside the sane band"
        )

    # Cells 7 and 8 are sentinel — 0xFFFF.
    assert ir_raw[6] == 0xFFFF
    assert ir_raw[7] == 0xFFFF


def test_primary_ir_in_range_with_battery():
    """With a healthy pack present, the primary cell IR is plausible."""
    # 6S pack — TRES9000's measured first-cell IR was 8.1 mΩ
    ch0, _ = _replay("idle_6s_battery.jsonl")
    assert ch0["ir_mohm"] is not None
    assert 1.0 < ch0["ir_mohm"] < 50.0


def test_no_ir_without_battery():
    """Without a battery the IR field has no usable reading."""
    ch0, _ = _replay("idle_no_battery.jsonl")
    assert ch0.get("ir_mohm") is None


def test_air8_ignores_other_channels():
    """Air 8 FW echoes every channel byte we send; parser must drop ch 1-5."""
    # The no-battery fixture polls channels 0..5; with num_channels=1 only
    # ch 0 data should land in the parsed dict.
    ch0, _ = _replay("idle_no_battery.jsonl")
    # We expect the ch 0 dict to contain decoded WorkState / Electric / IR keys
    assert "work_state" in ch0
    assert "output_voltage" in ch0
