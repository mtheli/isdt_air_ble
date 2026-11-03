"""Tests for what the coordinator pushes after a reconnect, and for the
warning when a device stays silent.

The entities follow the connection, so they go unavailable on disconnect
and come back only with the next push. Pushes are skipped while the data
is unchanged, which left a reconnected MASS2 with all ports at 0 W
unavailable until Home Assistant restarted.
"""

from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from isdt_air_ble import coordinator as coord  # noqa: E402
from isdt_air_ble.const import DeviceType  # noqa: E402
from isdt_air_ble.parser import ChargerValueHold  # noqa: E402
from isdt_air_ble.watchdog import ResponseWatchdog  # noqa: E402

ADDRESS = "AA:BB:CC:DD:EE:FF"
PORTS = {0: {"power": 0.0, "status": 0}}


def _make_coordinator():
    c = object.__new__(coord.ISDTDataUpdateCoordinator)
    c.address = ADDRESS
    c.model = "MASS2"
    c.device_type = DeviceType.ADAPTER
    c.adapter_protocol = None  # skip the MASS2 settings/time writes
    c._client = None
    c._connected = False
    c._notification_started = False
    c._connect_time = None
    c._hw_info_fetched = True
    c._device_registry_updated = True
    c._charger_hold = ChargerValueHold()
    c._watchdog = ResponseWatchdog(max_consecutive_misses=3, max_silence=10.0)
    c._last_pushed_data = dict(PORTS)
    c._silent_since = None
    c._silent_warned = False
    return c


def test_connect_resets_change_detection(monkeypatch):
    """A connect must lead to a push even when nothing changed meanwhile."""

    async def run():
        c = _make_coordinator()
        client = SimpleNamespace(
            services=SimpleNamespace(services={}), mtu_size=23, is_connected=True
        )

        async def fake_establish(*args, **kwargs):
            return client

        async def noop(*args, **kwargs):
            return None

        monkeypatch.setattr(coord, "establish_connection", fake_establish)
        monkeypatch.setattr(coord.asyncio, "sleep", noop)
        monkeypatch.setattr(c, "_setup_notifications", noop, raising=False)
        monkeypatch.setattr(c, "_send_bind_request", noop, raising=False)

        assert c._sensor_data_changed(dict(PORTS)) is False
        await c._connect(object())
        assert c._connected is True
        assert c._sensor_data_changed(dict(PORTS)) is True

    asyncio.run(run())


def test_silence_warns_once_and_reports_the_end(monkeypatch, caplog):
    c = _make_coordinator()
    now = [1000.0]
    monkeypatch.setattr(coord.time, "monotonic", lambda: now[0])

    with caplog.at_level(logging.WARNING, logger=coord.__name__):
        c._note_silence()
        now[0] += coord._SILENT_WARN_AFTER - 1
        c._note_silence()
        assert not caplog.records

        now[0] += 1
        c._note_silence()
        now[0] += 300
        c._note_silence()
        warnings = [r.getMessage() for r in caplog.records]
        assert len(warnings) == 1
        assert "has not advertised for 10 minutes" in warnings[0]

        now[0] += 60
        c._note_advertising()
        assert "advertising again after 16 minutes" in caplog.records[-1].getMessage()

    # A new silent period starts from scratch.
    assert c._silent_since is None
    assert c._silent_warned is False


def test_short_silence_stays_quiet(monkeypatch, caplog):
    c = _make_coordinator()
    now = [1000.0]
    monkeypatch.setattr(coord.time, "monotonic", lambda: now[0])

    with caplog.at_level(logging.WARNING, logger=coord.__name__):
        c._note_silence()
        now[0] += 120
        c._note_silence()
        c._note_advertising()
    assert not caplog.records
