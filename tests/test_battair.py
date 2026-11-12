"""BattAir advertisement decoding against the captures from issue #15."""

from __future__ import annotations

import json
from pathlib import Path

from isdt_air_ble.battair import (
    BATTAIR_MANUFACTURER_ID,
    decode_advert,
    default_title,
    is_battair,
    legacy_title,
    pack_name,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "battair"


def _adverts(name: str = "scan_storage_11_packs.jsonl") -> list[dict]:
    with open(FIXTURES / name, encoding="utf-8") as f:
        records = [json.loads(line) for line in f]
    return [r for r in records if r["kind"] == "advert"]


def _payload(record: dict) -> bytes:
    return bytes.fromhex(record["manufacturer_data"][f"0x{BATTAIR_MANUFACTURER_ID:04x}"])


def test_all_scan_adverts_decode():
    adverts = _adverts()
    assert {r["address"] for r in adverts} and len({r["address"] for r in adverts}) == 11
    for record in adverts:
        advert = decode_advert(_payload(record))
        assert advert is not None
        assert advert.cells in (2, 3, 4)
        assert advert.capacity_mah in (900, 1300, 2200, 5200)
        assert advert.battery_type == "lipo"


def test_4s_1300_pack_matches_reference():
    """Pack 88:AD, the one that was also read over a connection."""
    record = next(r for r in _adverts() if r["address"] == "54:14:A7:EF:88:AD")
    advert = decode_advert(_payload(record))
    assert advert.voltage == 15.23
    assert advert.cells == 4
    assert advert.capacity_mah == 1300
    assert advert.percentage == 33
    assert advert.cycles == 1
    assert advert.filter_text is None  # empty filter is sent as FF FF FF FF
    assert advert.cell_voltage_avg == round(15.23 / 4, 3)
    assert advert.cell_voltage_low is False


def test_2s_pack_fields():
    payload = bytes.fromhex("10 00 00 01 fb 02 27 14 01 00 02 dc 00 00 32 73 00 00")
    advert = decode_advert(payload)
    assert advert.voltage == 7.63
    assert advert.percentage == 39
    assert advert.temperature == 20
    assert advert.cycles == 1
    assert advert.cells == 2
    assert advert.capacity_mah == 2200
    assert advert.filter_text == "2s"
    assert advert.status == 0x01


def test_shake_bit_is_not_a_value_change():
    still = decode_advert(bytes.fromhex("10 00 00 00 fb 02 27 14 01 00 02 dc 00 00 32 73 00 00"))
    shaken = decode_advert(bytes.fromhex("10 00 00 01 fb 02 27 14 01 00 02 dc 00 00 32 73 00 00"))
    assert still.values_key() == shaken.values_key()


def test_status_bits():
    # Byte 3 = 0x1a: storage discharge, error log, transport mode
    advert = decode_advert(bytes.fromhex("10 00 00 1a dd 05 13 19 0c 00 04 bc 02 01 42 61 74 36"))
    assert advert.storage_discharge
    assert advert.error_log
    assert advert.transport_mode
    assert advert.voltage == 15.01
    assert advert.capacity_mah == 7000
    assert advert.assembly == 1
    assert advert.filter_text == "Bat6"
    assert advert.is_plugin


def test_negative_temperature():
    advert = decode_advert(bytes.fromhex("10 00 00 00 fb 02 27 fb 01 00 02 dc 00"))
    assert advert.temperature == -5
    assert advert.filter_text is None


def test_low_cell_voltage():
    # 2S at 5.80 V = 2.90 V per cell
    advert = decode_advert(bytes.fromhex("10 00 00 00 44 02 00 14 01 00 02 dc 00"))
    assert advert.cell_voltage_avg == 2.9
    assert advert.cell_voltage_low is True


def test_unknown_chemistry_has_no_low_voltage_threshold():
    # Battery type 3 (LiFe) in the high nibble
    advert = decode_advert(bytes.fromhex("30 00 00 00 44 02 00 14 01 00 02 dc 00"))
    assert advert.battery_type == "life"
    assert advert.cell_voltage_low is None


def test_rejects_short_and_charger_payloads():
    assert decode_advert(None) is None
    assert decode_advert(bytes.fromhex("10 00 00 00 fb 02")) is None
    assert decode_advert(bytes.fromhex("af fa 01 03 00 00 4b 32 41 69 72 00")) is None


def test_is_battair():
    assert is_battair(["0000ba00-0000-1000-8000-00805f9b34fb"], None, None)
    assert is_battair([], "BATAIRmike", None)
    assert not is_battair(["0000af00-0000-1000-8000-00805f9b34fb"], "K2Air", None)


def test_6s_plugin_matches_reference():
    """Plugin 5F:B1 on a 6S 1550 mAh pack, second capture in issue #15.

    Reference values from the issue: LiPo 6S 1550 mAh, 55 %, 23.271 V (sum of cells),
    0 cycles, filter '6s', name 'ovonic1550'.
    """
    record = next(
        r for r in _adverts("scan_storage_12_devices_with_6s_plugin.jsonl")
        if r["address"] == "54:14:A7:02:5F:B1"
    )
    advert = decode_advert(_payload(record))
    assert advert.is_plugin
    assert advert.model == "BattAir Plugin"
    assert advert.battery_type == "lipo"
    assert advert.cells == 6
    assert advert.capacity_mah == 1550
    assert advert.percentage == 55
    assert advert.voltage == 23.28
    assert advert.cycles == 0
    assert advert.temperature == 25
    assert advert.filter_text == "6s"
    assert pack_name(record["name"]) == "ovonic1550"
    assert default_title(advert, record["address"], record["name"]) == "BattAir Plugin ovonic1550"


def test_second_scan_packs_are_not_plugins():
    adverts = _adverts("scan_storage_12_devices_with_6s_plugin.jsonl")
    packs = [r for r in adverts if r["address"] != "54:14:A7:02:5F:B1"]
    assert len({r["address"] for r in packs}) == 11
    for record in packs:
        advert = decode_advert(_payload(record))
        assert not advert.is_plugin
        assert advert.model == "BattAir"


def test_pack_name():
    # 16-byte name field, then four characters that are not part of the name.
    assert pack_name("BATAIRBattAi-2s-2200-20001") == "BattAi-2s-2200-2"
    assert pack_name("BATAIRBattAir-2s-900-50002") == "BattAir-2s-900-5"
    assert pack_name("BATAIRovonic1550      0000") == "ovonic1550"
    assert pack_name("BATAIRBattAir") is None
    assert pack_name("BATAIRBattAir         0001") is None
    assert pack_name("BATAIRshort\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00") == "short"
    assert pack_name("54-14-A7-EF-34-CA") is None
    assert pack_name(None) is None


def test_default_title():
    advert = decode_advert(bytes.fromhex("10 00 00 00 f3 05 21 14 01 00 04 82 00 00 ff ff ff ff"))
    assert default_title(advert, "54:14:A7:EF:88:AD") == "BattAir 4S 1300 mAh 88AD"
    assert default_title(advert, "54:14:A7:EF:88:AD", "BATAIRBattAir") == "BattAir 4S 1300 mAh 88AD"
    assert default_title(None, "54:14:A7:EF:88:AD") == "BattAir 88AD"
    assert default_title(advert, "54:14:A7:EF:88:AD", "BATAIRBattAir         0001") == "BattAir 4S 1300 mAh 88AD"
    assert default_title(advert, "54:14:A7:EF:66:E3", "BATAIRBattAir-2s-900-20002") == "BattAir-2s-900-2"
    assert default_title(advert, "54:14:A7:EF:65:5D", "BATAIRBattAi-2s-2200-20001") == "BattAi-2s-2200-2"


def test_legacy_title_matches_beta1_names():
    """The titles v0.15.0-beta.1 created, so setup can rename those entries."""
    advert = decode_advert(bytes.fromhex("10 00 00 00 f3 05 21 14 01 00 04 82 00 00 ff ff ff ff"))
    assert legacy_title(advert, "54:14:A7:EF:66:E3", "BATAIRBattAir-2s-900-20002") == "BattAir-2s-900-20002"
    assert legacy_title(advert, "54:14:A7:EF:88:AD", "BATAIRBattAir         0001") == "BattAir         0001"
    assert legacy_title(advert, "54:14:A7:02:5F:B1", "BATAIRovonic1550      0000") == default_title(
        advert, "54:14:A7:02:5F:B1", "BATAIRovonic1550      0000"
    )
