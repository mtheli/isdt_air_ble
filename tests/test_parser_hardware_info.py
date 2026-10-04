"""Tests for HardwareInfoResp parsing, in particular the serial number."""

from __future__ import annotations

import pytest

from isdt_air_ble.parser import parse_hardware_info


def _resp(device_id: bytes, framed: bool = False) -> bytes:
    body = bytes([0xE1, 0x01, 0x02, 0x01, 0x06]) + device_id
    return (b"\x31" + body) if framed else body


@pytest.mark.parametrize("framed", [False, True])
def test_versions(framed):
    hw, sw, _ = parse_hardware_info(_resp(bytes(8), framed))
    assert hw == "1.2"
    assert sw == "1.6"


@pytest.mark.parametrize(
    "device_id",
    [
        b"C4Air   ",  # C4 Air: padded model name
        b"MASS2   ",  # MASS2: padded model name
        b"CENTPERI",  # K4
        b"\x00" * 8,
        b"\xff" * 8,
    ],
)
def test_placeholder_device_id_gives_no_serial(device_id):
    assert parse_hardware_info(_resp(device_id))[2] is None


def test_binary_device_id_is_serial():
    device_id = bytes.fromhex("123456789abcdef0")
    assert parse_hardware_info(_resp(device_id))[2] == "F0DEBC9A78563412"


def test_too_short_or_wrong_command():
    assert parse_hardware_info(b"") is None
    assert parse_hardware_info(_resp(b"C4Air")) is None
    assert parse_hardware_info(bytes.fromhex("31 e7 00 03 4f 09 00")) is None
