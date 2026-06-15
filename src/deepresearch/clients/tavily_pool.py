"""Tavily API key pool with automatic quota-exhaustion failover.

When one key runs out of quota (HTTP 429 or quota error), the pool
automatically rotates to the next key with remaining capacity.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from deepresearch.clients.tavily import SearchClient
from deepresearch.errors import SearchError


@dataclass
class KeyState:
    key: str
    remaining: int  # estimated remaining calls (pessimistic)
    exhausted: bool = False
    error_count: int = 0
    last_error: str = ""


class TavilyKeyPool:
    """Pool of Tavily API keys with automatic failover."""

    def __init__(self, keys: list[tuple[str, int]]):
        """
        Parameters
        ----------
        keys:
            List of (api_key, estimated_remaining_calls) tuples.
            Keys are tried in order; the first non-exhausted key is used.
        """
        self._states: list[KeyState] = []
        for key, remaining in keys:
            self._states.append(KeyState(key=key, remaining=remaining))
        self._lock = threading.Lock()
        self._current_index = 0

    @property
    def active_key(self) -> str:
        with self._lock:
            state = self._get_active()
            return state.key

    @property
    def remaining_total(self) -> int:
        with self._lock:
            return sum(s.remaining for s in self._states if not s.exhausted)

    @property
    def pool_status(self) -> str:
        with self._lock:
            parts = []
            for i, s in enumerate(self._states):
                marker = "← active" if i == self._current_index and not s.exhausted else ""
                status = "EXHAUSTED" if s.exhausted else f"~{s.remaining} calls"
                parts.append(f"  Key[{i}]: {status} {marker}")
            return "\n".join(parts)

    def _get_active(self) -> KeyState:
        """Find the first non-exhausted key. Must be called under lock."""
        for i in range(len(self._states)):
            idx = (self._current_index + i) % len(self._states)
            state = self._states[idx]
            if not state.exhausted:
                self._current_index = idx
                return state
        raise SearchError("All Tavily API keys are exhausted")

    def _mark_exhausted(self, state: KeyState) -> None:
        """Mark a key as exhausted and rotate. Must be called under lock."""
        state.exhausted = True
        # Try the next key
        for s in self._states:
            if not s.exhausted:
                self._current_index = self._states.index(s)
                return

    def record_success(self, count: int = 1) -> None:
        """Record successful API calls against the active key."""
        with self._lock:
            state = self._states[self._current_index]
            state.remaining = max(0, state.remaining - count)

    def record_error(self, is_quota_error: bool = False) -> None:
        """Record an error. If quota-related, mark the key as exhausted."""
        with self._lock:
            state = self._states[self._current_index]
            state.error_count += 1
            if is_quota_error:
                self._mark_exhausted(state)


class PooledTavilyClient:
    """Tavily search client that routes through a key pool.

    Wraps the raw Tavily API, creating ephemeral SearchClient instances
    with the currently-active key.  On quota errors (429), it rotates
    keys and retries.
    """

    def __init__(self, pool: TavilyKeyPool, max_retries: int = 2):
        self._pool = pool
        self._max_retries = max_retries

    def _is_quota_error(self, exc: Exception) -> bool:
        msg = str(exc).lower()
        return any(marker in msg for marker in (
            "429", "too many requests", "rate limit",
            "quota", "exceeded", "insufficient", "usage limit",
            "monthly limit", "daily limit",
        ))

    def search(self, query: str, *, subquestion_id: str, max_results: int):
        """Search with automatic key rotation on quota errors."""
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                from deepresearch.clients.tavily import TavilySearchClient
                client = TavilySearchClient(api_key=self._pool.active_key)
                result = client.search(query, subquestion_id=subquestion_id, max_results=max_results)
                self._pool.record_success(1)
                return result
            except Exception as exc:
                last_error = exc
                is_quota = self._is_quota_error(exc)
                self._pool.record_error(is_quota_error=is_quota)
                if is_quota:
                    continue  # Rotate and retry
                raise  # Non-quota error — don't retry

        raise SearchError(f"Search failed after {self._max_retries} key rotations: {last_error}")

    def extract(self, urls: list[str], *, subquestion_id: str):
        """Extract with automatic key rotation on quota errors."""
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                from deepresearch.clients.tavily import TavilySearchClient
                client = TavilySearchClient(api_key=self._pool.active_key)
                result = client.extract(urls, subquestion_id=subquestion_id)
                self._pool.record_success(1)
                return result
            except Exception as exc:
                last_error = exc
                is_quota = self._is_quota_error(exc)
                self._pool.record_error(is_quota_error=is_quota)
                if is_quota:
                    continue
                raise

        raise SearchError(f"Extract failed after {self._max_retries} key rotations: {last_error}")
