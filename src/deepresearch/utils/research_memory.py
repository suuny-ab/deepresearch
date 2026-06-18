"""Cross-run research memory — persists learnings across sessions.

Stores a lightweight JSON file that tracks past questions, high-value
sources, and query patterns so the planner can benefit from prior research.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path


class ResearchMemory:
    """Lightweight cross-run memory backed by a JSON file.

    Tracks:
    - Past research questions (for dedup and context)
    - High-value source domains (frequently cited, high corroboration)
    - Successful query patterns

    Parameters
    ----------
    path:
        Path to the memory JSON file. Defaults to
        ``~/.deepresearch/research_memory.json``.
    max_history:
        Maximum number of past questions to remember (default 50).
    """

    def __init__(
        self,
        path: str | Path | None = None,
        max_history: int = 50,
    ):
        if path is None:
            path = Path.home() / ".deepresearch" / "research_memory.json"
        self._path = Path(path)
        self._max_history = max_history
        self._lock = threading.Lock()

        # In-memory state
        self.past_questions: list[dict] = []     # [{question, timestamp, topics}]
        self.source_scores: dict[str, float] = {}  # domain -> score (0-1)
        self.query_patterns: list[str] = []       # Successful query templates

        self._load()

    # ------------------------------------------------------------------
    # Read API
    # ------------------------------------------------------------------

    def get_relevant_context(self, question: str, max_items: int = 3) -> str:
        """Return a string of relevant past research context for the planner."""
        with self._lock:
            if not self.past_questions:
                return ""

            # Simple relevance: check for keyword overlap
            q_words = set(question.lower().split())
            relevant = []
            for pq in self.past_questions[-20:]:
                pq_words = set(pq.get("question", "").lower().split())
                overlap = q_words & pq_words
                if len(overlap) >= 3:
                    relevant.append(pq)

            if not relevant:
                return ""

            lines = [
                "",
                "## Past Research Context",
                "You have previously researched these related topics:",
                "",
            ]
            for r in relevant[-max_items:]:
                lines.append(f"- {r.get('question', '')}")

            if self.source_scores:
                high_value = sorted(
                    self.source_scores.items(),
                    key=lambda x: x[1], reverse=True,
                )[:5]
                lines.append("")
                lines.append("High-value sources from past research:")
                for domain, score in high_value:
                    lines.append(f"- {domain} (score: {score:.2f})")

            return "\n".join(lines)

    # ------------------------------------------------------------------
    # Write API
    # ------------------------------------------------------------------

    def record_question(self, question: str, topics: list[str] | None = None) -> None:
        """Record a successfully-researched question."""
        import time
        with self._lock:
            self.past_questions.append({
                "question": question,
                "timestamp": time.time(),
                "topics": topics or [],
            })
            # Trim
            if len(self.past_questions) > self._max_history:
                self.past_questions = self.past_questions[-self._max_history:]
            self._save()

    def record_source_quality(self, domain: str, score: float) -> None:
        """Update a domain's quality score (exponential moving average)."""
        with self._lock:
            old = self.source_scores.get(domain, 0.5)
            alpha = 0.3  # EMA smoothing factor
            self.source_scores[domain] = round(alpha * score + (1 - alpha) * old, 2)
            self._save()

    def record_query_pattern(self, pattern: str) -> None:
        """Record a successful query pattern for future reference."""
        with self._lock:
            if pattern not in self.query_patterns:
                self.query_patterns.append(pattern)
                if len(self.query_patterns) > 100:
                    self.query_patterns = self.query_patterns[-100:]
            self._save()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self.past_questions = data.get("past_questions", [])
            self.source_scores = data.get("source_scores", {})
            self.query_patterns = data.get("query_patterns", [])
        except (json.JSONDecodeError, OSError):
            pass

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._path.write_text(
                json.dumps({
                    "past_questions": self.past_questions,
                    "source_scores": self.source_scores,
                    "query_patterns": self.query_patterns,
                }, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        except OSError:
            pass


# Module-level singleton
_default_memory: ResearchMemory | None = None


def get_memory() -> ResearchMemory:
    """Return a module-level :class:`ResearchMemory` singleton."""
    global _default_memory
    if _default_memory is None:
        _default_memory = ResearchMemory()
    return _default_memory
