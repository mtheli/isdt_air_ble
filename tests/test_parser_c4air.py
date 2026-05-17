"""C4 Air parser regression tests.

These tests run real captures from the round-cell C4 Air through the
shared parser and assert that the C4-Air-specific code path still works
after the Air 8 / K2 Air refactor — in particular that:

  * Every requested channel decodes (no drops, no warnings).
  * The C4-Air ``BATTERY_TYPE_MAP`` (1 → "LiIon") is selected, not the
    Air 8 one (1 → "LiPo").
  * Input voltage / current and work-state strings carry their normal
    C4-Air semantics ("idle" for ``work_state == 0``).
"""

from __future__ import annotations

import json
from pathlib import Path

from isdt_air_ble.parser import parse_charger_responses

FIXTURES = Path(__file__).parent / "fixtures" / "c4air"


def _replay(fixture: str):
    raw_notifies: list[bytes] = []
    for line in (FIXTURES / fixture).read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("kind") != "notify":
            continue
        if event.get("char") != "AF01":
            continue
        raw_notifies.append(bytes.fromhex(event["hex"].replace(" ", "")))

    parsed, alarm = parse_charger_responses(raw_notifies, num_channels=6, model="C4 Air")
    return parsed, alarm


def test_c4air_empty_all_six_channels_decoded():
    """The 6-channel C4 Air must populate every channel slot in parsed."""
    parsed, _ = _replay("empty.jsonl")
    assert set(parsed.keys()) == {0, 1, 2, 3, 4, 5}
    # Each channel must have decoded WorkState (work_state key present)
    for ch in range(6):
        assert "work_state" in parsed[ch], f"channel {ch} missing work_state"


def test_c4air_all_slots_idle():
    """Without batteries, every slot should report ``work_state == idle``.

    The slot still remembers its last configured ``battery_type`` (e.g.
    LiHv = 4 if previously used for a LiHv pack), so we don't pin a
    specific chemistry — only the C4-Air ``WORK_STATE_MAP`` membership.
    """
    parsed, _ = _replay("empty.jsonl")
    for ch in range(6):
        assert parsed[ch]["work_state"] == 0
        assert parsed[ch]["work_state_str"] == "idle"


def test_c4air_input_voltage_realistic():
    """Input voltage from the DC supply should be roughly 12 V."""
    parsed, _ = _replay("empty.jsonl")
    # Channel 0 ElectricResp: input_v ≈ 0x2ec5 mV = 11.973 V
    assert 11.0 < parsed[0]["input_voltage"] < 13.0


def test_c4air_empty_slots_have_negligible_pack_voltage():
    """Empty slots report at most a few-hundred-millivolt residue on the
    output rail (no real pack voltage). A clearly empty pack would be
    under 0.5 V; a connected cell would be well above 2.5 V."""
    parsed, _ = _replay("empty.jsonl")
    for ch in range(6):
        assert parsed[ch]["output_voltage"] < 0.5, (
            f"channel {ch} reports output_voltage={parsed[ch]['output_voltage']} "
            f"V — looks like a real battery is connected"
        )


def test_c4air_explicit_battery_type_mapping():
    """Synthetic check: feed a WorkStateResp with battery_type=1 through
    the parser with model="C4 Air" and confirm the C4-Air map fires."""
    # 38-byte WorkStateResp, channel 0, work_state=2 (CC charging),
    # battery_type=1 at offset 17, everything else zero.
    frame = bytearray(38)
    frame[0] = 0x31
    frame[1] = 0xE7
    frame[2] = 0x00
    frame[3] = 0x02  # work_state = charging
    frame[17] = 0x01  # battery_type = 1
    parsed, _ = parse_charger_responses(
        [bytes(frame)], num_channels=1, model="C4 Air"
    )
    assert parsed[0]["work_state_str"] == "charging"
    # C4-Air map: 1 → "LiIon"; Air 8 map would say "LiPo"
    assert parsed[0]["battery_type_str"] == "LiIon"


def test_c4air_1cell_charging_slot0_active():
    """Slot 0 holds a 1-cell NiMH battery being charged; slots 1-5 idle.

    The C4 Air also exposes ``unit_serials_num == 1`` for the single cell
    and a non-zero charging current on the active slot.
    """
    parsed, _ = _replay("1cell_charging.jsonl")

    # Slot 0: charging
    assert parsed[0]["work_state_str"] == "charging"
    assert parsed[0]["unit_serials_num"] == 1  # one cell detected
    assert parsed[0]["charging_current"] > 0.1  # > 100 mA
    assert parsed[0]["capacity_percentage"] >= 0  # SOC field present
    # battery_type = 4 → "NiMH/Cd" in the C4-Air chemistry map
    assert parsed[0]["battery_type"] == 4
    assert parsed[0]["battery_type_str"] == "NiMH/Cd"

    # Slots 1-5: still idle (no batteries inserted)
    for ch in range(1, 6):
        assert parsed[ch]["work_state_str"] == "idle", (
            f"channel {ch} unexpectedly active: state={parsed[ch]['work_state_str']}"
        )


def test_c4air_1cell_charging_draws_more_supply_current():
    """An active charge slot pulls noticeably more current from the DC
    supply than an empty one — we expect at least 50 mA on slot 0."""
    parsed, _ = _replay("1cell_charging.jsonl")
    assert parsed[0]["input_current"] > 0.05  # > 50 mA on the charging slot


def test_c4air_1cell_done_slot0_settled():
    """After charge complete, the C4 Air reports stable per-cell readings
    on the formerly-active slot — the protocol only surfaces a usable cell
    voltage and IR once the duty-cycle pulsing stops."""
    parsed, _ = _replay("1cell_done.jsonl")

    # Slot 0: charge complete
    assert parsed[0]["work_state"] == 6
    assert parsed[0]["work_state_str"] == "done"
    assert parsed[0]["capacity_percentage"] == 100
    assert parsed[0]["capacity_done"] >= 100  # at least 0.1 Ah of NiMH input
    assert parsed[0]["charging_current"] == 0.0  # no more current flowing
    # Cell voltage of a freshly-charged NiMH/Cd sits around 1.4 V
    assert 1.0 < parsed[0]["output_voltage"] < 1.6
    # IR is now reported — a sane NiMH AA reads tens of mΩ
    assert parsed[0]["ir_mohm"] is not None
    assert 5.0 < parsed[0]["ir_mohm"] < 200.0
    # Single-cell config preserved
    assert parsed[0]["unit_serials_num"] == 1
    assert parsed[0]["battery_type_str"] == "NiMH/Cd"

    # Slots 1-5: still idle
    for ch in range(1, 6):
        assert parsed[ch]["work_state_str"] == "idle"


def test_c4air_4cell_four_slots_charging_in_parallel():
    """Four NiMH cells charging simultaneously — exercises the per-slot
    polling path and confirms each slot gets distinct, plausible data
    rather than the device-wide fields being smeared across slots."""
    parsed, _ = _replay("4cell_charging.jsonl")

    # Slots 0-3 active
    for ch in range(4):
        slot = parsed[ch]
        assert slot["work_state_str"] == "charging", (
            f"slot {ch} expected to be charging, got {slot['work_state_str']}"
        )
        assert slot["battery_type"] == 4
        assert slot["battery_type_str"] == "NiMH/Cd"
        assert slot["unit_serials_num"] == 1
        # Cell voltage in the active-NiMH-charge band (1.0-1.5 V)
        assert 1.0 < slot["output_voltage"] < 1.5
        # Real charging current (~0.7-1.0 A in this capture)
        assert 0.3 < slot["charging_current"] < 2.0

    # Slots 4-5 stay empty
    for ch in range(4, 6):
        assert parsed[ch]["work_state_str"] == "idle"
        assert parsed[ch]["output_voltage"] == 0.0
        assert parsed[ch]["charging_current"] == 0.0


def test_c4air_4cell_per_slot_voltages_are_distinct():
    """Each charging slot should report its own cell voltage — if the
    parser accidentally shared state across channels they would collapse
    to identical values."""
    parsed, _ = _replay("4cell_charging.jsonl")
    voltages = [parsed[ch]["output_voltage"] for ch in range(4)]
    # At least two slots must report visibly different cell voltages
    # (mV-level granularity from the device).
    assert len(set(voltages)) >= 2, (
        f"all 4 slots reported the same voltage: {voltages}"
    )


def test_c4air_4cell_at_least_one_slot_reports_ir():
    """During active charging the C4 Air populates IR on at least one
    slot (50 mΩ on slot 0 in the matching app screenshot)."""
    parsed, _ = _replay("4cell_charging.jsonl")
    ir_values = [parsed[ch].get("ir_mohm") for ch in range(4)]
    assert any(v is not None and v > 0 for v in ir_values), (
        f"no slot reported a usable IR value: {ir_values}"
    )


def test_c4air_2cell_only_slots_3_and_4_active():
    """Cells in slots 3-4 only (channels 2 and 3 zero-indexed); slots 1-2
    were just emptied so they still carry the previous session's mAh
    counter but report ``work_state == idle``."""
    parsed, _ = _replay("2cell_charging_slots_3_4.jsonl")

    # Active slots
    for ch in (2, 3):
        slot = parsed[ch]
        assert slot["work_state_str"] == "charging"
        assert slot["unit_serials_num"] == 1
        assert slot["battery_type_str"] == "NiMH/Cd"
        assert 1.3 < slot["output_voltage"] < 1.55  # NiMH on CC charge
        assert 0.5 < slot["charging_current"] < 1.5

    # Idle slots with historical capacity counter (just removed)
    for ch in (0, 1):
        slot = parsed[ch]
        assert slot["work_state_str"] == "idle"
        assert slot["charging_current"] == 0.0
        # Historical mAh from the previous session is preserved by the
        # device even after the cell is pulled — confirm it doesn't get
        # zeroed by the parser.
        assert slot["capacity_done"] > 50, (
            f"slot {ch} lost its historical capacity counter "
            f"({slot['capacity_done']} mAh)"
        )

    # Truly empty slots
    for ch in (4, 5):
        slot = parsed[ch]
        assert slot["work_state_str"] == "idle"
        assert slot["capacity_done"] == 0
        assert slot["output_voltage"] == 0.0


def test_c4air_2cell_only_slots_1_and_2_active():
    """Same scenario, batteries moved to slots 1-2 (channels 0-1) — the
    parser must drive the right per-channel routing regardless of which
    physical slots carry cells. Slots 3-4 then show idle with low
    residual voltage on the energised rail."""
    parsed, _ = _replay("2cell_charging_slots_1_2.jsonl")

    for ch in (0, 1):
        slot = parsed[ch]
        assert slot["work_state_str"] == "charging"
        assert slot["unit_serials_num"] == 1
        assert slot["battery_type_str"] == "NiMH/Cd"
        # 84-85 % charged in this capture
        assert 50 < slot["capacity_percentage"] <= 100
        assert 1.3 < slot["output_voltage"] < 1.55
        assert 0.5 < slot["charging_current"] < 1.5

    for ch in (2, 3, 4, 5):
        slot = parsed[ch]
        assert slot["work_state_str"] == "idle"
        assert slot["charging_current"] == 0.0


def test_c4air_done_session_recorded_work_period():
    """``work_period`` (charge duration in seconds) is non-zero for a
    completed session and roughly matches the 21-22 minute charge time
    observed in TRES9000-style captures (≈1300 s)."""
    parsed, _ = _replay("1cell_done.jsonl")
    # 21:40 in the capture → 1300 s ± headroom
    assert 60 < parsed[0]["work_period"] < 7200


def test_air8_explicit_battery_type_mapping_distinct():
    """Same frame, model="Air 8" must yield the Air 8 chemistry name."""
    frame = bytearray(38)
    frame[0] = 0x31
    frame[1] = 0xE7
    frame[2] = 0x00
    frame[3] = 0x03  # work_state = Air 8 CC fast-charge
    frame[17] = 0x01  # battery_type = 1
    parsed, _ = parse_charger_responses(
        [bytes(frame)], num_channels=1, model="Air 8"
    )
    # Air 8 map: 1 → "LiPo"
    assert parsed[0]["battery_type_str"] == "LiPo"
    # Air 8 map: 3 → "charging"
    assert parsed[0]["work_state_str"] == "charging"
