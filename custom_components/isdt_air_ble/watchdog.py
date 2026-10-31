"""Response watchdog for the persistent BLE connection.

Kept free of Home Assistant imports so it can be unit-tested directly.

The device sends at most one notification per connection event and has
only a few transmit buffers. When it stops answering while the link stays
up, every further write piles up unacknowledged in the host controller
until the kernel kills the connection after 45 s — and on some adapters
the controller does not recover from that. The watchdog notices the
silence early so the connection can be dropped cleanly instead.
"""

from __future__ import annotations


class ResponseStall(Exception):
    """Raised when the device has stopped answering commands."""


class ResponseWatchdog:
    """Track command responses and decide when the link has stalled.

    A stall is reported when either
    - ``max_consecutive_misses`` commands in a row got no response, or
    - no response at all arrived for ``max_silence`` seconds.
    """

    def __init__(self, max_consecutive_misses: int, max_silence: float) -> None:
        self.max_consecutive_misses = max_consecutive_misses
        self.max_silence = max_silence
        self._consecutive_misses = 0
        self._last_response: float = 0.0

    def reset(self, now: float) -> None:
        """Start a fresh watch period, e.g. after (re)connecting."""
        self._consecutive_misses = 0
        self._last_response = now

    def on_response(self, now: float) -> None:
        """Record that a response arrived."""
        self._consecutive_misses = 0
        self._last_response = now

    def on_miss(self) -> None:
        """Record that a command got no response in time."""
        self._consecutive_misses += 1

    @property
    def consecutive_misses(self) -> int:
        """Number of commands in a row without a response."""
        return self._consecutive_misses

    def silence(self, now: float) -> float:
        """Seconds since the last response (or since the last reset)."""
        return now - self._last_response

    def check(self, now: float) -> str | None:
        """Return a reason string if the link is considered stalled."""
        if self._consecutive_misses >= self.max_consecutive_misses:
            return f"{self._consecutive_misses} commands in a row without response"
        silence = self.silence(now)
        if silence >= self.max_silence:
            return f"no response for {silence:.1f}s"
        return None
