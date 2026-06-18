"""Agent decision-quality evaluators — zero-LLM, reads decision logs.

Each evaluator takes a decision log file path and returns
``{"key": str, "score": float, "comment": str}``, matching the
existing evaluator convention in ``evaluators.py``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_entries(path: str | Path) -> list[dict[str, Any]]:
    entries = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            entries.append(json.loads(line))
    return entries


def _parse_response(response: str) -> dict[str, Any] | None:
    """Parse an LLM response that may be wrapped in markdown code fences."""
    text = response.strip()
    # Raw JSON object
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    # Raw JSON array — take the first object
    if text.startswith("["):
        try:
            arr = json.loads(text)
            if isinstance(arr, list) and len(arr) > 0:
                return arr[0]
        except json.JSONDecodeError:
            pass
    # Fenced code block — find any { or [ after the fence
    m = re.search(r"```(?:json)?\s*([\{\[])", text)
    if m:
        start = m.start(1)
        is_array = text[start] == '['
        depth = 0
        for i in range(start, len(text)):
            if text[i] in '{[':
                depth += 1
            elif text[i] in '}]':
                depth -= 1
                if depth == 0:
                    try:
                        result = json.loads(text[start:i + 1])
                        if is_array and isinstance(result, list) and len(result) > 0:
                            return result[0]
                        return result
                    except json.JSONDecodeError:
                        break
    return None


def _plan_topics(entries: list[dict]) -> list[str]:
    for e in entries:
        if e["phase"] == "plan":
            plan = json.loads(e["response"])
            return [t["id"] for t in plan.get("topics", [])]
    return []


def _search_actions(entries: list[dict]) -> list[dict]:
    """Return search action entries that have an observation."""
    out = []
    for e in entries:
        if e["phase"] != "action":
            continue
        extra = e.get("extra", {})
        if not extra.get("observation"):
            continue
        d = _parse_response(e.get("response", ""))
        if d and d.get("action") == "search":
            out.append({"entry": e, "parsed": d})
    return out


# ---------------------------------------------------------------------------
# Search coverage
# ---------------------------------------------------------------------------


def topic_coverage(path: str | Path) -> dict[str, Any]:
    """Fraction of planned topics that received at least 1 search."""
    entries = _load_entries(path)
    planned = set(_plan_topics(entries))
    if not planned:
        return {"key": "topic_coverage", "score": 0.0, "comment": "No plan found"}

    searched = set()
    for sa in _search_actions(entries):
        tid = sa["parsed"].get("topic_id", "")
        if tid:
            searched.add(tid)

    ratio = len(searched & planned) / len(planned)
    return {
        "key": "topic_coverage",
        "score": ratio,
        "comment": f"{len(searched & planned)}/{len(planned)} topics searched",
    }


def topic_depth(path: str | Path) -> dict[str, Any]:
    """Average number of searches per topic."""
    entries = _load_entries(path)
    planned = _plan_topics(entries)
    if not planned:
        return {"key": "topic_depth", "score": 0.0, "comment": "No plan found"}

    counts: dict[str, int] = {t: 0 for t in planned}
    for sa in _search_actions(entries):
        tid = sa["parsed"].get("topic_id", "")
        if tid in counts:
            counts[tid] += 1

    avg = sum(counts.values()) / len(counts)
    detail = ", ".join(f"{t}:{c}" for t, c in counts.items())
    return {
        "key": "topic_depth",
        "score": avg,
        "comment": f"avg {avg:.1f} searches/topic [{detail}]",
    }


def topic_balance(path: str | Path) -> dict[str, Any]:
    """How evenly distributed are searches across topics? 1.0 = perfectly even."""
    entries = _load_entries(path)
    planned = _plan_topics(entries)
    if not planned or len(planned) < 2:
        return {"key": "topic_balance", "score": 1.0, "comment": "Single topic"}

    counts = {t: 0 for t in planned}
    for sa in _search_actions(entries):
        tid = sa["parsed"].get("topic_id", "")
        if tid in counts:
            counts[tid] += 1

    total = sum(counts.values())
    if total == 0:
        return {"key": "topic_balance", "score": 0.0, "comment": "No searches"}

    # Gini-like: ratio of min/max
    vals = list(counts.values())
    balance = min(vals) / max(vals) if max(vals) > 0 else 0
    return {
        "key": "topic_balance",
        "score": balance,
        "comment": f"min={min(vals)} max={max(vals)} ratio={balance:.2f}",
    }


# ---------------------------------------------------------------------------
# Query diversity
# ---------------------------------------------------------------------------


def query_uniqueness(path: str | Path) -> dict[str, Any]:
    """Ratio of unique search queries to total searches."""
    searches = _search_actions(_load_entries(path))
    if not searches:
        return {"key": "query_uniqueness", "score": 1.0, "comment": "No searches"}

    queries = [sa["parsed"].get("input", {}).get("query", "").strip().lower()
               for sa in searches]
    ratio = len(set(queries)) / len(queries)
    return {
        "key": "query_uniqueness",
        "score": ratio,
        "comment": f"{len(set(queries))}/{len(queries)} unique",
    }


def query_overlap(path: str | Path) -> dict[str, Any]:
    """Average word overlap between consecutive searches (lower = more diverse)."""
    searches = _search_actions(_load_entries(path))
    if len(searches) < 2:
        return {"key": "query_overlap", "score": 0.0, "comment": "Not enough searches"}

    overlaps = []
    for i in range(len(searches) - 1):
        q1 = set(searches[i]["parsed"].get("input", {}).get("query", "").lower().split())
        q2 = set(searches[i + 1]["parsed"].get("input", {}).get("query", "").lower().split())
        union = q1 | q2
        if union:
            overlaps.append(len(q1 & q2) / len(union))

    avg = sum(overlaps) / len(overlaps)
    return {
        "key": "query_overlap",
        "score": avg,
        "comment": f"avg overlap {avg:.0%} between consecutive queries (lower = more diverse)",
    }


# ---------------------------------------------------------------------------
# Information acquisition
# ---------------------------------------------------------------------------


def unique_sources(path: str | Path) -> dict[str, Any]:
    """Total unique source URLs discovered across all searches."""
    entries = _load_entries(path)
    urls: set[str] = set()
    for e in entries:
        extra = e.get("extra", {})
        obs = extra.get("observation", "")
        if not obs:
            continue
        # Extract URLs from formatted observation
        import re
        found = re.findall(r"URL: (https?://[^\s]+)", obs)
        urls.update(found)

    return {
        "key": "unique_sources",
        "score": len(urls),
        "comment": f"{len(urls)} unique source URLs",
    }


def content_volume(path: str | Path) -> dict[str, Any]:
    """Total characters of search result content accumulated."""
    entries = _load_entries(path)
    total = 0
    for e in entries:
        extra = e.get("extra", {})
        obs = extra.get("observation", "")
        total += len(obs)
    return {
        "key": "content_volume",
        "score": total,
        "comment": f"{total:,} chars of search content",
    }


# ---------------------------------------------------------------------------
# Decision efficiency
# ---------------------------------------------------------------------------


def productive_ratio(path: str | Path) -> dict[str, Any]:
    """Fraction of action iterations that were productive (new searches, not dupes/errors)."""
    entries = _load_entries(path)
    actions = [e for e in entries if e["phase"] == "action"]
    if not actions:
        return {"key": "productive_ratio", "score": 1.0, "comment": "No actions"}

    productive = 0
    for e in actions:
        d = _parse_response(e.get("response", ""))
        if d and d.get("action") in ("search", "synthesize"):
            productive += 1

    ratio = productive / len(actions)
    return {
        "key": "productive_ratio",
        "score": ratio,
        "comment": f"{productive}/{len(actions)} productive",
    }


def duplicate_query_rate(path: str | Path) -> dict[str, Any]:
    """Fraction of searches that repeated a previous query."""
    searches = _search_actions(_load_entries(path))
    if not searches:
        return {"key": "duplicate_query_rate", "score": 0.0, "comment": "No searches"}

    queries = [sa["parsed"].get("input", {}).get("query", "").strip().lower()
               for sa in searches]
    seen = set()
    dupes = 0
    for q in queries:
        if q in seen:
            dupes += 1
        seen.add(q)

    ratio = dupes / len(queries)
    return {
        "key": "duplicate_query_rate",
        "score": ratio,
        "comment": f"{dupes}/{len(queries)} duplicates ({ratio:.0%})",
    }


# ---------------------------------------------------------------------------
# Stop behavior
# ---------------------------------------------------------------------------


def stop_reason(path: str | Path) -> dict[str, Any]:
    """How did the agent stop?  Coded as: 1.0=synthesize, 0.5=max_iters, 0.0=error."""
    entries = _load_entries(path)
    done_entry = None
    for e in reversed(entries):
        if e["phase"] == "done":
            done_entry = e
        if e["phase"] == "action":
            d = _parse_response(e.get("response", ""))
            if d and d.get("action") == "synthesize":
                return {
                    "key": "stop_reason",
                    "score": 1.0,
                    "comment": f"Synthesized at iter {e['iteration']}",
                }

    if done_entry:
        d = json.loads(done_entry["response"])
        iters = d.get("iterations", 0)
        if iters >= 15:
            return {
                "key": "stop_reason",
                "score": 0.5,
                "comment": f"Hit max_iterations ({iters})",
            }

    return {"key": "stop_reason", "score": 0.0, "comment": "Unknown/unclear stop"}


def saturation_at_stop(path: str | Path) -> dict[str, Any]:
    """Fraction of topics saturated when research ended."""
    entries = _load_entries(path)
    for e in reversed(entries):
        if e["phase"] == "done":
            d = json.loads(e["response"])
            topics = d.get("topics_final", [])
            if not topics:
                continue
            saturated = sum(1 for t in topics if t["status"] == "saturated")
            ratio = saturated / len(topics)
            return {
                "key": "saturation_at_stop",
                "score": ratio,
                "comment": f"{saturated}/{len(topics)} saturated",
            }
    return {"key": "saturation_at_stop", "score": 0.0, "comment": "No done entry"}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

ALL_AGENT_EVALUATORS: list[tuple[str, callable]] = [
    # Search coverage
    ("topic_coverage", topic_coverage),
    ("topic_depth", topic_depth),
    ("topic_balance", topic_balance),
    # Query diversity
    ("query_uniqueness", query_uniqueness),
    ("query_overlap", query_overlap),
    # Information acquisition
    ("unique_sources", unique_sources),
    ("content_volume", content_volume),
    # Decision efficiency
    ("productive_ratio", productive_ratio),
    ("duplicate_query_rate", duplicate_query_rate),
    # Stop behavior
    ("stop_reason", stop_reason),
    ("saturation_at_stop", saturation_at_stop),
]


def evaluate_log(log_path: str | Path) -> dict[str, Any]:
    """Run all agent evaluators on a single decision log."""
    results = {}
    for key, fn in ALL_AGENT_EVALUATORS:
        result = fn(log_path)
        results[result["key"]] = result
    return results
