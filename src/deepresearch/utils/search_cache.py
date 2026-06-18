"""Persistent search cache with TTL-based expiry.

Caches Tavily search results to disk (JSON) so repeated queries in
development, benchmarking, and overlapping research runs don't
burn API quota.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from pathlib import Path
from typing import Any


def _cache_dir() -> Path:
    """User-level cache directory."""
    return Path.home() / ".deepresearch" / "cache"


class SearchCache:
    """JSON-file cache for search results with TTL.

    Uses a simple on-disk JSON store keyed by ``(query_hash, max_results)``.
    Entries older than *ttl_seconds* are treated as stale and evicted on read.

    Parameters
    ----------
    cache_path:
        Path to the JSON cache file.  Defaults to the platform cache
        directory (``~/.cache/deepresearch/`` on Linux, etc.).
    ttl_seconds:
        Time-to-live in seconds.  Default 86 400 (24 hours).
    """

    def __init__(
        self,
        cache_path: str | Path | None = None,
        ttl_seconds: int = 86_400,
    ):
        if cache_path is None:
            cache_path = _cache_dir() / "search_cache.json"
        self._path = Path(cache_path)
        self._ttl = ttl_seconds
        self._lock = threading.Lock()
        self._entries: dict[str, dict[str, Any]] = {}
        self._loaded = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(
        self, query: str, max_results: int = 5,
    ) -> list[dict[str, Any]] | None:
        """Return cached results, or ``None`` on miss / expiry."""
        self._ensure_loaded()
        key = self._make_key(query, max_results)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            age = time.time() - entry.get("cached_at", 0)
            if age > self._ttl:
                # Stale — remove and return miss
                del self._entries[key]
                return None
            return list(entry.get("results", []))

    def put(
        self,
        query: str,
        max_results: int,
        results: list[dict[str, Any]],
    ) -> None:
        """Store results in the cache."""
        self._ensure_loaded()
        key = self._make_key(query, max_results)
        with self._lock:
            self._entries[key] = {
                "query": query,
                "max_results": max_results,
                "cached_at": time.time(),
                "results": results,
            }
            self._save()

    def get_stale(
        self, query: str, max_results: int = 5,
    ) -> list[dict[str, Any]] | None:
        """Return cached results even if expired (API-failure fallback)."""
        self._ensure_loaded()
        key = self._make_key(query, max_results)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            return list(entry.get("results", []))

    def clear(self) -> None:
        """Remove all cached entries."""
        self._ensure_loaded()
        with self._lock:
            self._entries.clear()
            self._save()

    @property
    def entry_count(self) -> int:
        """Number of entries currently in cache (including stale)."""
        self._ensure_loaded()
        with self._lock:
            return len(self._entries)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _make_key(query: str, max_results: int) -> str:
        raw = f"{query.strip().lower()}|{max_results}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            self._load()
            self._loaded = True

    def _load(self) -> None:
        if not self._path.exists():
            self._entries = {}
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._entries = data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, OSError):
            self._entries = {}

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._path.write_text(
                json.dumps(self._entries, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass  # Non-critical — cache write failures are silent


# Module-level singleton for convenient import
_default_cache: SearchCache | None = None


def get_cache(ttl_seconds: int = 86_400) -> SearchCache:
    """Return a module-level :class:`SearchCache` singleton."""
    global _default_cache
    if _default_cache is None:
        _default_cache = SearchCache(ttl_seconds=ttl_seconds)
    return _default_cache
