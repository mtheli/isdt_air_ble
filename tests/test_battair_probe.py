"""Decode the BattAir captures from issue #15 with the probe script.

The expected values are the reference values posted for the same packs
at the time of the capture (screenshots in issue #15).
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "battair"

if "bleak" not in sys.modules:
    try:
        import bleak  # noqa: F401
    except ImportError:
        stub = types.ModuleType("bleak")
        stub.BleakClient = stub.BleakScanner = object
        sys.modules["bleak"] = stub

_spec = importlib.util.spec_from_file_location(
    "battair_probe", REPO_ROOT / "scripts" / "battair_probe.py")
probe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe)


def _records(name: str) -> list[dict]:
    with open(FIXTURES / name, encoding="utf-8") as f:
        return [json.loads(line) for line in f]


def _responses() -> dict[str, dict]:
    return {
        r["purpose"]: probe.decode_response(bytes.fromhex(r["plain"]))
        for r in _records("connect_4s_1300mah.jsonl")
        if r["kind"] == "response"
    }


def test_advert_4s_pack() -> None:
    advert = next(
        r for r in _records("scan_storage_11_packs.jsonl")
        if r["kind"] == "advert" and r["address"] == "54:14:A7:EF:88:AD"
    )
    decoded = probe.decode_advert(bytes.fromhex(advert["manufacturer_data"]["0xabba"]))
    assert decoded["battery_type"] == "LiPo"
    assert decoded["cells"] == 4
    assert decoded["capacity_mah"] == 1300
    assert decoded["voltage_v"] == 15.23
    assert decoded["cycles"] == 1
    assert decoded["filter"] == ""


def test_advert_capacity_matches_pack_names() -> None:
    """Pack names like 'BattAir-2s-900-30002' carry the capacity."""
    seen = 0
    for r in _records("scan_storage_11_packs.jsonl"):
        if r["kind"] != "advert" or "-" not in r["name"] or not r["name"].startswith("BATAIR"):
            continue
        _, cells, capacity, _ = r["name"].split("-")
        decoded = probe.decode_advert(bytes.fromhex(r["manufacturer_data"]["0xabba"]))
        assert decoded["capacity_mah"] == int(capacity)
        assert decoded["cells"] == int(cells[0])
        assert decoded["filter"].lower() == cells.lower()
        seen += 1
    assert seen > 5


def test_connect_4s_pack_matches_reference() -> None:
    resp = _responses()
    assert resp["CellVoltages"]["cells_mv"] == [3815, 3804, 3816, 3807]
    assert resp["HardwareInfo"]["hardware"] == "2.0"
    assert resp["HardwareInfo"]["software"] == "1.34"
    assert resp["HardwareInfo"]["cells"] == 4
    assert resp["RealTime"]["temperature_c"] == 23
    assert resp["RealTime"]["level"] == 34
    assert resp["AbnormalStatistics"]["cycles"] == 1
    assert resp["AbnormalStatistics"]["error_log"] == 0
    assert resp["UserParameter"]["full_charge_mv"] == 4200
    assert resp["UserParameter"]["storage_mv"] == 3900
    assert resp["UserParameter"]["charge_current_ma"] == 1300
    assert resp["UserParameter"]["auto_storage_timer"] == "disabled"
    assert resp["OEMParameter"]["charge_rate_c"] == 5
    assert resp["OEMParameter"]["discharge_rate_c"] == 80
    assert resp["ActivationDays"]["activation_days"] == 169
    assert resp["BleName"]["text"] == "BattAir"
    assert resp["OEMName"]["text"] == "BattAir"
    assert resp["Filter"]["filter"] == ""
