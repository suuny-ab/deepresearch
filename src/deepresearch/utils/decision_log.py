"""Decision log — records every LLM call the agent makes for post-hoc review.

Each entry captures: timestamp, phase, the full prompt sent, and the full
response received.  Saved as JSON Lines alongside the report so you can
trace exactly what the agent saw and how it decided.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class DecisionLogger:
    """Records agent decisions to a JSON Lines file.

    Parameters
    ----------
    path:
        Path to the log file (``.jsonl``).
    """

    def __init__(self, path: str | Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[dict[str, Any]] = []
        self._start_time = time.time()

    def log(
        self,
        phase: str,
        prompt: str,
        response: str,
        *,
        iteration: int = 0,
        action: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Record one LLM interaction."""
        entry = {
            "timestamp": time.time() - self._start_time,
            "phase": phase,
            "iteration": iteration,
            "action": action,
            "prompt": prompt,
            "response": response,
        }
        if extra:
            entry["extra"] = extra
        self._entries.append(entry)
        # Append to file immediately so partial runs are visible
        self._flush_one(entry)

    def _flush_one(self, entry: dict) -> None:
        try:
            with open(self._path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except OSError:
            pass

    @property
    def entry_count(self) -> int:
        return len(self._entries)
