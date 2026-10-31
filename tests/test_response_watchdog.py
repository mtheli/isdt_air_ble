"""Tests for request/response pacing and the response watchdog.

The device sends at most one notification per connection event. Writing
ahead of its answers only queues packets in the host controller; when the
device stops answering, the connection has to be dropped before the
kernel kills it after 45 s.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from isdt_air_ble.watchdog import ResponseStall, ResponseWatchdog


def test_watchdog_quiet_while_responses_arrive():
    wd = ResponseWatchdog(max_consecutive_misses=3, max_silence=10.0)
    wd.reset(0.0)
    for t in range(1, 30):
        wd.on_response(float(t))
        assert wd.check(float(t)) is None


def test_watchdog_trips_on_consecutive_misses():
    wd = ResponseWatchdog(max_consecutive_misses=3, max_silence=10.0)
    wd.reset(0.0)
    wd.on_miss()
    wd.on_miss()
    assert wd.check(4.0) is None
    wd.on_miss()
    assert "3 commands in a row" in wd.check(6.0)


def test_watchdog_response_resets_miss_count():
    wd = ResponseWatchdog(max_consecutive_misses=3, max_silence=10.0)
    wd.reset(0.0)
    wd.on_miss()
    wd.on_miss()
    wd.on_response(4.0)
    wd.on_miss()
    assert wd.consecutive_misses == 1
    assert wd.check(6.0) is None


def test_watchdog_trips_on_silence():
    wd = ResponseWatchdog(max_consecutive_misses=100, max_silence=10.0)
    wd.reset(0.0)
    assert wd.check(9.9) is None
    assert "no response for 10.0s" in wd.check(10.0)


def test_watchdog_reset_starts_fresh():
    wd = ResponseWatchdog(max_consecutive_misses=3, max_silence=10.0)
    wd.reset(0.0)
    for _ in range(3):
        wd.on_miss()
    wd.reset(100.0)
    assert wd.consecutive_misses == 0
    assert wd.check(105.0) is None


# ---------------------------------------------------------------------------
# Coordinator pacing (needs Home Assistant installed)
# ---------------------------------------------------------------------------


def _make_coordinator(answer: bool, adapter: bool = True):
    pytest.importorskip("homeassistant")
    from isdt_air_ble import coordinator as coord
    from isdt_air_ble.const import DeviceType

    c = object.__new__(coord.ISDTDataUpdateCoordinator)
    c.device_type = DeviceType.ADAPTER if adapter else DeviceType.CHARGER
    c.command_interval = 0.0
    c._commands = [b"\x00"]
    c._response_event = asyncio.Event()
    c._response_timeout = 0.05
    c._watchdog = ResponseWatchdog(max_consecutive_misses=3, max_silence=10.0)
    writes: list[bytes] = []

    async def write_gatt_char(char, data, response):
        assert response is False
        writes.append(bytes(data))
        if answer:
            # The device answers asynchronously via a notification.
            asyncio.get_running_loop().call_soon(c._on_response)

    c._client = SimpleNamespace(write_gatt_char=write_gatt_char)
    return c, coord, writes


def test_send_and_wait_returns_on_response():
    async def run():
        c, coord, writes = _make_coordinator(answer=True)
        c._watchdog.reset(coord.time.monotonic())
        for _ in range(5):
            await c._send_and_wait(b"\x01")
        assert len(writes) == 5
        assert c._watchdog.consecutive_misses == 0

    asyncio.run(run())


def test_send_and_wait_raises_stall_after_misses():
    async def run():
        c, coord, writes = _make_coordinator(answer=False)
        c._watchdog.reset(coord.time.monotonic())
        await c._send_and_wait(b"\x01")
        await c._send_and_wait(b"\x01")
        with pytest.raises(ResponseStall):
            await c._send_and_wait(b"\x01")
        # No write goes out while the previous one is unanswered: exactly
        # one write per call, and the third call stops the cycle.
        assert len(writes) == 3

    asyncio.run(run())


def test_send_and_wait_keeps_adapter_cycle_pause(monkeypatch):
    async def run():
        c, coord, _ = _make_coordinator(answer=True)
        monkeypatch.setattr(coord, "_ADAPTER_CYCLE_MIN", 0.2)
        c._watchdog.reset(coord.time.monotonic())
        start = coord.time.monotonic()
        await c._send_and_wait(b"\x01", cycle_end=False)
        assert coord.time.monotonic() - start < 0.15
        start = coord.time.monotonic()
        await c._send_and_wait(b"\x01", cycle_end=True)
        assert coord.time.monotonic() - start >= 0.19

    asyncio.run(run())
