"""Dump full state dict from a replay run. Works on v0.4+.

Usage: uv run python benchmark/scripts/dump_state.py <frozen.json> <output.json>
"""

import json
import sys

from deepresearch.cli import _build_app
from deepresearch.config import AppConfig

config = AppConfig.from_env()
with open(sys.argv[1], encoding="utf-8") as f:
    saved = json.load(f)

# Convert to Pydantic models if available (v0.5.2+), else pass dicts
try:
    from deepresearch.state import SearchResult, SubQuestion

    subquestions = [SubQuestion(**sq) for sq in saved["subquestions"]]
    search_results = [SearchResult(**sr) for sr in saved["search_results"]]
except Exception:
    subquestions = saved["subquestions"]
    search_results = saved["search_results"]

app = _build_app(config, dry_run=False, replay_search=True)
result = app.invoke(
    {
        "question": saved["question"],
        "subquestions": subquestions,
        "search_results": search_results,
        "errors": [],
    }
)


def serialize(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, list):
        return [serialize(v) for v in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items()}
    return obj


with open(sys.argv[2], "w", encoding="utf-8") as f:
    json.dump(serialize(result), f, indent=2, default=str)

print(f"State dumped to {sys.argv[2]}")
