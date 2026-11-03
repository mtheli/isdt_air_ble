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


# ---------------------------------------------------------------------------
# MASS2 clock on a long-running connection
# ---------------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402

from homeassistant.util import dt as dt_util  # noqa: E402

from isdt_air_ble.const import AdapterProtocol  # noqa: E402

CET = timezone(timedelta(hours=1))
CEST = timezone(timedelta(hours=2))


def _clock_coordinator(monkeypatch, tz, protocol=AdapterProtocol.MASS2):
    c = _make_coordinator()
    c.adapter_protocol = protocol
    c._rtc_synced_at = None
    c._rtc_offset = None
    now = [5000.0]
    wall = [datetime(2026, 10, 25, 1, 30, tzinfo=tz)]
    monkeypatch.setattr(coord.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(dt_util, "now", lambda: wall[0])
    writes: list[bytes] = []

    async def write_gatt_char(char, data, response):
        writes.append(bytes(data))

    c._client = SimpleNamespace(write_gatt_char=write_gatt_char)
    return c, now, wall, writes


def test_clock_not_resent_without_a_first_sync(monkeypatch):
    c, _, _, _ = _clock_coordinator(monkeypatch, CEST)
    assert c._rtc_resync_due() is False


def test_clock_resent_when_daylight_saving_ends(monkeypatch):
    async def run():
        c, now, wall, writes = _clock_coordinator(monkeypatch, CEST)
        await c._send_mass2_set_time()
        assert writes[-1][-1] == 2  # UTC+2 sent
        assert c._rtc_resync_due() is False

        now[0] += 3600
        wall[0] = datetime(2026, 10, 25, 2, 30, tzinfo=CET)
        assert c._rtc_resync_due() is True
        await c._send_mass2_set_time()
        assert writes[-1][-1] == 1  # UTC+1 sent
        assert writes[-1][3] == 2  # hour on the device: 02:30
        assert c._rtc_resync_due() is False

    asyncio.run(run())


def test_clock_resent_once_a_day(monkeypatch):
    async def run():
        c, now, _, _ = _clock_coordinator(monkeypatch, CET)
        await c._send_mass2_set_time()
        now[0] += coord._RTC_RESYNC_INTERVAL - 1
        assert c._rtc_resync_due() is False
        now[0] += 1
        assert c._rtc_resync_due() is True

    asyncio.run(run())


def test_clock_only_for_mass2(monkeypatch):
    async def run():
        c, now, _, _ = _clock_coordinator(monkeypatch, CET, AdapterProtocol.PS200)
        c._rtc_synced_at = now[0]
        c._rtc_offset = timedelta(hours=2)
        assert c._rtc_resync_due() is False

    asyncio.run(run())


def test_clock_resync_leaves_no_answer_for_the_next_command(monkeypatch):
    async def run():
        c, _, _, writes = _clock_coordinator(monkeypatch, CET)
        c._response_queue = asyncio.Queue()
        c._response_event = asyncio.Event()

        async def write_and_answer(char, data, response):
            writes.append(bytes(data))
            c._response_queue.put_nowait(b"\x31\xcf")
            c._response_event.set()

        c._client = SimpleNamespace(write_gatt_char=write_and_answer)
        real_sleep = asyncio.sleep
        monkeypatch.setattr(coord.asyncio, "sleep", lambda s: real_sleep(0))
        await c._resync_mass2_clock()
        assert writes and writes[-1][:2] == b"\x12\xce"
        assert c._response_queue.empty()
        assert not c._response_event.is_set()

    asyncio.run(run())
