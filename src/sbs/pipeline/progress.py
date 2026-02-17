"""Lightweight progress tracker for pipeline stages."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from time import perf_counter


@dataclass
class StageProgress:
    """Pure-Python progress tracker with optional Rich callback.

    Tracks completed items, throughput, and ETA for a pipeline stage.
    No Rich dependency — the callback is wired externally by the runner.
    """

    total: int | None = None
    completed: int = 0
    _start_time: float = field(default_factory=perf_counter, repr=False)
    _on_advance: Callable[[int], None] | None = field(default=None, repr=False)

    def advance(self, n: int = 1) -> None:
        """Increment completed count and fire the Rich callback."""
        self.completed += n
        if self._on_advance is not None:
            self._on_advance(n)

    def elapsed(self) -> float:
        """Seconds since tracking started."""
        return perf_counter() - self._start_time

    def throughput(self) -> float:
        """Items per second (0.0 if no time elapsed)."""
        elapsed = self.elapsed()
        if elapsed <= 0:
            return 0.0
        return self.completed / elapsed

    def eta_seconds(self) -> float | None:
        """Estimated remaining seconds, or None if total is unknown."""
        if self.total is None or self.total <= 0:
            return None
        remaining = self.total - self.completed
        if remaining <= 0:
            return 0.0
        tput = self.throughput()
        if tput <= 0:
            return None
        return remaining / tput
