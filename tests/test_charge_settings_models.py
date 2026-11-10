"""Which models expose their per-slot charge settings."""

from isdt_air_ble.const import supports_charge_settings


def test_only_c4_air_reports_charge_settings():
    assert supports_charge_settings("C4 Air")
    for model in ("A8 Air", "Air 8", "K2 Air", "NP2 Air", "MASS2"):
        assert not supports_charge_settings(model)
