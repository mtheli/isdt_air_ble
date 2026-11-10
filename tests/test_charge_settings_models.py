"""Which models expose their per-slot charge settings."""

from isdt_air_ble.const import supports_charge_settings


def test_only_c4_air_reports_charge_settings():
    assert supports_charge_settings("C4 Air")
    for model in ("A8 Air", "Air 8", "K2 Air", "NP2 Air", "MASS2"):
        assert not supports_charge_settings(model)


def test_charge_setting_entities_pruned_on_other_models():
    from isdt_air_ble.const import is_stale_charger_unique_id

    addr = "AA:BB:CC:DD:EE:FF"
    for key in ("work_current", "cutoff_mv", "capacity_limit_mah"):
        uid = f"{addr}_ch0_{key}"
        assert not is_stale_charger_unique_id(uid, addr, "C4 Air", 6)
        assert is_stale_charger_unique_id(uid, addr, "A8 Air", 8)
