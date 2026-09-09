"""Local analysis preferences and conservative durable provider-use reservations."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class AnalysisLimitError(ValueError):
    """No provider request may start when the local safe allowance is exhausted."""


@dataclass(frozen=True)
class AnalysisPolicy:
    enabled: bool = True
    daily_attempt_limit: int = 10
    daily_token_limit: int = 200_000
    analysis_mode: str = "auto"
    personal_instructions: str = ""


class AnalysisPolicyStore:
    """Store preferences and usage without prompts, source content, keys, or provider IDs."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS analysis_policy (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    settings_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_usage (
                    day TEXT PRIMARY KEY,
                    reserved_attempts INTEGER NOT NULL,
                    reserved_tokens INTEGER NOT NULL
                );
            """)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=15)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get(self) -> AnalysisPolicy:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT settings_json FROM analysis_policy WHERE singleton=1"
            ).fetchone()
        return AnalysisPolicy(**json.loads(row[0])) if row else AnalysisPolicy()

    def save(self, policy: AnalysisPolicy) -> AnalysisPolicy:
        if not 1 <= policy.daily_attempt_limit <= 1000:
            raise ValueError("Daily provider-attempt limit must be between 1 and 1000.")
        if not 1000 <= policy.daily_token_limit <= 10_000_000:
            raise ValueError("Daily token allowance must be between 1000 and 10000000.")
        if policy.analysis_mode not in {
            "auto",
            "project",
            "learning",
            "research_writing",
            "context_handoff",
        }:
            raise ValueError("Unsupported analysis mode.")
        if len(policy.personal_instructions) > 4000:
            raise ValueError("Personal instructions must be at most 4000 characters.")
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO analysis_policy VALUES (1, ?)",
                (json.dumps(asdict(policy)),),
            )
        return policy

    def usage(self) -> dict[str, Any]:
        day = datetime.now(UTC).date().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT reserved_attempts, reserved_tokens FROM analysis_usage WHERE day=?", (day,)
            ).fetchone()
        policy = self.get()
        attempts, tokens = row or (0, 0)
        return {
            "day": day,
            "reserved_attempts": attempts,
            "reserved_tokens": tokens,
            "remaining_attempts": max(0, policy.daily_attempt_limit - attempts),
            "remaining_tokens": max(0, policy.daily_token_limit - tokens),
            "currency_cost": None,
            "explanation": (
                "Conservative reservations include all possible key attempts and maximum output. "
                "They are not billed usage or a currency-cost estimate. Reset: 00:00 UTC."
            ),
        }

    def reserve(self, *, attempts: int, tokens: int) -> None:
        """Atomically reserve a worst-case allowance before any remote request can start."""
        if attempts < 1 or tokens < 1:
            raise ValueError("A reservation must be positive.")
        day = datetime.now(UTC).date().isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT settings_json FROM analysis_policy WHERE singleton=1"
            ).fetchone()
            policy = AnalysisPolicy(**json.loads(row[0])) if row else AnalysisPolicy()
            if not policy.enabled:
                raise AnalysisLimitError("Analysis is paused. Your sources remain saved.")
            row = conn.execute(
                "SELECT reserved_attempts, reserved_tokens FROM analysis_usage WHERE day=?", (day,)
            ).fetchone()
            used_attempts, used_tokens = row or (0, 0)
            if (
                used_attempts + attempts > policy.daily_attempt_limit
                or used_tokens + tokens > policy.daily_token_limit
            ):
                raise AnalysisLimitError(
                    "Daily analysis allowance reached. Your sources and queued work remain saved. "
                    "Wait for 00:00 UTC or change the limits in Analysis settings."
                )
            conn.execute(
                "INSERT OR REPLACE INTO analysis_usage VALUES (?, ?, ?)",
                (day, used_attempts + attempts, used_tokens + tokens),
            )


class BudgetedProvider:
    """Wrap the real provider without replacing generation or persisting request content."""

    def __init__(self, provider: Any, policy_store: AnalysisPolicyStore):
        self.provider = provider
        self.policy_store = policy_store
        if isinstance(provider, InterruptibleProvider):
            provider.call_guards.append(self._check_enabled)

    def _check_enabled(self):
        if not self.policy_store.get().enabled:
            raise AnalysisLimitError("Analysis is paused. Your sources remain saved.")

    def generate_json(self, **kwargs):
        before_attempt = getattr(self.provider, "before_attempt", None)
        if before_attempt is not None:
            before_attempt()
        # UTF-8 bytes plus framing are a deliberately conservative tokenizer-independent bound.
        attempts = max(1, len(getattr(self.provider, "credentials", ())))
        tokens = (
            len(kwargs["system"].encode("utf-8"))
            + len(kwargs["user"].encode("utf-8"))
            + 1024
            + int(kwargs.get("max_tokens", 4096))
        ) * attempts
        self.policy_store.reserve(attempts=attempts, tokens=tokens)
        return self.provider.generate_json(**kwargs)


class InterruptibleProvider:
    """Stop future calls on shutdown while letting an already sent response settle safely."""

    def __init__(self, provider, should_stop):
        self.provider = provider
        self.should_stop = should_stop
        self.credentials = getattr(provider, "credentials", ())
        self.call_guards = []
        self._previous_guard = getattr(provider, "before_attempt", None)
        if hasattr(provider, "before_attempt"):
            provider.before_attempt = self.before_attempt

    def before_attempt(self):
        from reweave.llm import ProviderConnectionChangedError

        if self.should_stop():
            raise ProviderConnectionChangedError(
                "Reweave is closing. Unsent analysis remains saved."
            )
        for guard in self.call_guards:
            guard()
        if self._previous_guard is not None:
            self._previous_guard()

    def generate_json(self, **kwargs):
        self.before_attempt()
        return self.provider.generate_json(**kwargs)

    def generate_text(self, **kwargs):
        self.before_attempt()
        return self.provider.generate_text(**kwargs)
