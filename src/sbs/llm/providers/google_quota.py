"""Quota-aware throttling utilities for Google provider calls."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from time import monotonic


class GoogleQuotaLimiter:
    """Enforce rolling RPM/TPM/RPD quotas with async backpressure."""

    _RPM_WINDOW_SECONDS = 60.0
    _TPM_WINDOW_SECONDS = 60.0
    _RPD_WINDOW_SECONDS = 86_400.0

    def __init__(
        self,
        *,
        rpm_limit: int,
        tpm_limit: int,
        rpd_limit: int,
        time_fn: Callable[[], float] = monotonic,
    ) -> None:
        self._rpm_limit = max(1, int(rpm_limit))
        self._tpm_limit = max(1, int(tpm_limit))
        self._rpd_limit = max(1, int(rpd_limit))
        self._time_fn = time_fn

        self._request_events: deque[float] = deque()
        self._token_events: deque[tuple[float, int]] = deque()
        self._daily_events: deque[float] = deque()
        self._total_wait_seconds = 0.0

        self._lock = asyncio.Lock()

    async def acquire(self, estimated_tokens: int) -> int:
        """Reserve quota capacity for a request before dispatch."""
        reserved_tokens = self._clamp_tokens(estimated_tokens)

        while True:
            async with self._lock:
                now = self._time_fn()
                self._prune(now)
                wait_seconds = self._compute_wait_seconds(now, reserved_tokens)
                if wait_seconds <= 0:
                    self._request_events.append(now)
                    self._token_events.append((now, reserved_tokens))
                    self._daily_events.append(now)
                    return reserved_tokens

            await asyncio.sleep(wait_seconds)
            async with self._lock:
                self._total_wait_seconds += wait_seconds

    async def reconcile(self, *, reserved_tokens: int, actual_tokens: int) -> None:
        """Add extra token usage if actual output exceeded reservation."""
        extra_tokens = max(0, int(actual_tokens) - int(reserved_tokens))
        if extra_tokens <= 0:
            return

        async with self._lock:
            now = self._time_fn()
            self._prune(now)
            self._token_events.append((now, extra_tokens))

    async def snapshot(self) -> dict[str, float | int]:
        """Return current usage stats for logging/observability."""
        async with self._lock:
            now = self._time_fn()
            self._prune(now)
            return {
                "rpm_used": len(self._request_events),
                "rpm_limit": self._rpm_limit,
                "tpm_used": self._current_tpm(),
                "tpm_limit": self._tpm_limit,
                "rpd_used": len(self._daily_events),
                "rpd_limit": self._rpd_limit,
                "total_wait_seconds": self._total_wait_seconds,
            }

    def _compute_wait_seconds(self, now: float, reserved_tokens: int) -> float:
        wait_candidates = [0.0]

        if len(self._request_events) >= self._rpm_limit:
            wait_candidates.append(self._request_events[0] + self._RPM_WINDOW_SECONDS - now)

        if len(self._daily_events) >= self._rpd_limit:
            wait_candidates.append(self._daily_events[0] + self._RPD_WINDOW_SECONDS - now)

        tpm_used = self._current_tpm()
        projected_tpm = tpm_used + reserved_tokens
        if projected_tpm > self._tpm_limit:
            need_to_free = projected_tpm - self._tpm_limit
            reclaimed = 0
            for ts, tokens in self._token_events:
                reclaimed += tokens
                if reclaimed >= need_to_free:
                    wait_candidates.append(ts + self._TPM_WINDOW_SECONDS - now)
                    break

        wait = max(wait_candidates)
        # A tiny floor avoids busy loops when many workers wake simultaneously.
        return max(0.0, wait) if wait <= 0 else max(0.01, wait)

    def _prune(self, now: float) -> None:
        rpm_cutoff = now - self._RPM_WINDOW_SECONDS
        while self._request_events and self._request_events[0] <= rpm_cutoff:
            self._request_events.popleft()

        tpm_cutoff = now - self._TPM_WINDOW_SECONDS
        while self._token_events and self._token_events[0][0] <= tpm_cutoff:
            self._token_events.popleft()

        rpd_cutoff = now - self._RPD_WINDOW_SECONDS
        while self._daily_events and self._daily_events[0] <= rpd_cutoff:
            self._daily_events.popleft()

    def _current_tpm(self) -> int:
        return sum(tokens for _ts, tokens in self._token_events)

    def _clamp_tokens(self, estimated_tokens: int) -> int:
        # If a request estimate exceeds TPM limit, reserving full limit avoids deadlocks.
        return max(1, min(int(estimated_tokens), self._tpm_limit))
