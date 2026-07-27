"""Tests for stale entity-registry detection (issue #4).

Before the A8 Air was a known model, setup fell back to a generic
6-channel charger profile and registered cell-voltage sensors for
channels 0-5. Those disabled-by-default registry entries survived every
update and showed up as ghost "Cell voltage" entities on slots 1-6.
"""

from isdt_air_ble.const import (
    get_channel_count,
    is_stale_charger_unique_id,
    supports_cell_voltages,
)

ADDRESS = "50:54:7B:EB:D2:3A"
A8 = "A8 Air"
A8_CHANNELS = get_channel_count(A8)


def _stale(unique_id, model=A8, channel_count=None):
    if channel_count is None:
        channel_count = get_channel_count(model)
    return is_stale_charger_unique_id(unique_id, ADDRESS, model, channel_count)


def test_supports_cell_voltages():
    assert not supports_cell_voltages("A8 Air")
    assert supports_cell_voltages("C4 Air")
    assert supports_cell_voltages("Air 8")
    assert supports_cell_voltages("K2 Air")


def test_a8_ghost_cell_sensors_are_stale():
    # The exact issue-#4 pattern: cells on channels 0-5 from the
    # 6-channel fallback profile.
    for ch in range(6):
        for cell in range(16):
            assert _stale(f"{ADDRESS}_ch{ch}_cell{cell}")


def test_a8_valid_entities_are_kept():
    for ch in range(A8_CHANNELS):
        assert not _stale(f"{ADDRESS}_ch{ch}_output_voltage")
        assert not _stale(f"{ADDRESS}_ch{ch}_ir_mohm")
        assert not _stale(f"{ADDRESS}_slot{ch + 1}_active")
    assert not _stale(f"{ADDRESS}_ch0_input_voltage")
    # Device-level entities don't match the channel/slot schemes.
    assert not _stale(f"{ADDRESS}_connected")
    assert not _stale(f"{ADDRESS}_alarm_tone")
    assert not _stale(f"{ADDRESS}_firmware_update")


def test_a8_beta_input_channel_leftover_is_stale():
    # The first A8 beta read input voltage/current from channel 8.
    assert _stale(f"{ADDRESS}_ch8_input_voltage")
    assert _stale(f"{ADDRESS}_ch8_input_current")


def test_channels_beyond_model_count_are_stale():
    assert _stale(f"{ADDRESS}_ch1_output_voltage", model="Air 8")
    assert _stale(f"{ADDRESS}_slot2_active", model="Air 8")
    assert not _stale(f"{ADDRESS}_ch0_output_voltage", model="Air 8")
    assert not _stale(f"{ADDRESS}_slot1_active", model="Air 8")


def test_cell_sensors_kept_on_models_with_cell_data():
    assert not _stale(f"{ADDRESS}_ch0_cell0", model="C4 Air")
    assert not _stale(f"{ADDRESS}_ch0_cell15", model="Air 8")


def test_other_device_unique_ids_untouched():
    assert not _stale("AA:BB:CC:DD:EE:FF_ch0_cell0")


def test_similar_keys_not_mistaken_for_cells():
    # A hypothetical key merely starting with "cell" must not be pruned.
    assert not _stale(f"{ADDRESS}_ch0_cell_balance_state")
