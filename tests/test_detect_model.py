"""Unit tests for ``detect_model_from_mfg_data``.

Covers:
  * Known ``DeviceModelID`` lookup wins over any embedded name.
  * Unknown ``DeviceModelID`` falls back to the ASCII name embedded in
    the advertisement (issue #3: K2 Air announces itself as "K2Air").
  * Degenerate payloads (empty / too short / non-ASCII) return ``None``
    instead of inventing a model name.
"""

from __future__ import annotations

from isdt_air_ble.const import detect_model_from_mfg_data


# --- Known device IDs ---------------------------------------------------------


def test_air8_id_maps_to_air8():
    """TRES9000's Air 8 advertisement (issue #2)."""
    mfg = bytes.fromhex("affa01030000200000000000000000000000ff")
    assert detect_model_from_mfg_data(mfg) == "Air 8"


def test_k2air_id_maps_to_k2air():
    """Mngnt's K2 Air advertisement (issue #3)."""
    mfg = bytes.fromhex("affa010400004b32416972000000000000000000")
    assert detect_model_from_mfg_data(mfg) == "K2 Air"


def test_c4air_id_still_maps_to_c4air():
    """Regression: the real C4 Air (01070000) must keep its mapping."""
    mfg = bytes.fromhex("affa01070000000000000000000000000000")
    assert detect_model_from_mfg_data(mfg) == "C4 Air"


# --- Fallback: ASCII name from advertisement ----------------------------------


def test_unknown_id_falls_back_to_embedded_name():
    """A hypothetical future device whose ID we don't know yet still
    resolves if it embeds its name (ISDT's wire convention)."""
    # 99999999 is not in DEVICE_MODEL_MAP; payload says "X9 Air"
    mfg = bytes.fromhex("affa999999995839416972000000")  # "X9Air\x00"
    assert detect_model_from_mfg_data(mfg) == "X9 Air"


def test_embedded_name_is_space_normalised():
    """`K2Air` (no space, wire form) → `K2 Air` (integration form)."""
    mfg = b"\xaf\xfa\x55\x55\x55\x55" + b"K2Air\x00"
    assert detect_model_from_mfg_data(mfg) == "K2 Air"


def test_embedded_name_without_digit_letter_boundary_kept_as_is():
    """Names without a `digit→letter` run are passed through unchanged."""
    mfg = b"\xaf\xfa\x55\x55\x55\x55" + b"EDGE\x00"
    assert detect_model_from_mfg_data(mfg) == "EDGE"


# --- Degenerate inputs --------------------------------------------------------


def test_none_returns_none():
    assert detect_model_from_mfg_data(None) is None


def test_too_short_returns_none():
    """5 bytes is shorter than the magic prefix + DeviceModelID."""
    assert detect_model_from_mfg_data(b"\xaf\xfa\x01\x02\x03") is None


def test_unknown_id_with_no_embedded_name_returns_none():
    """Unknown ID + no usable ASCII name → caller should keep stored model."""
    mfg = b"\xaf\xfa\xde\xad\xbe\xef\x00\x00\x00\x00"
    assert detect_model_from_mfg_data(mfg) is None


def test_unknown_id_with_non_ascii_name_returns_none():
    mfg = b"\xaf\xfa\xde\xad\xbe\xef\xff\xfe\xfd"
    assert detect_model_from_mfg_data(mfg) is None
