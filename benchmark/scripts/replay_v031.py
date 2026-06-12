#!/usr/bin/env python3
"""Replay benchmark queries on v0.3.1 using frozen search results.

v0.3.1 does not have --replay-search, and its graph cannot skip plan+search.
Instead of using the full graph, this script directly calls prepare_evidence
with frozen search data for dry-run tests (Test A).
For full-flow tests, v0.3.1 is not supported -- use v0.4+.

Usage:
  git checkout v0.3.1
  python benchmark/scripts/replay_v031.py benchmark/frozen/q1.json --output results.json
"""

import json
import sys
from argparse import ArgumentParser
from pathlib import Path

# Add v0.3.1 source to path -- assumes we're at repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.config import AppConfig
from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node


def main():
    parser = ArgumentParser(description="v0.3.1 benchmark dry-run replay adapter")
    parser.add_argument("frozen", type=Path, help="Path to frozen search JSON")
    parser.add_argument("--output", type=Path, default=None, help="Save output as JSON")
    parser.add_argument("--max-sources", type=int, default=3,
                        help="Max sources per subquestion for evidence selection")
    args = parser.parse_args()

    with open(args.frozen) as f:
        frozen = json.load(f)

    config = AppConfig.from_env()
    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )
    search = TavilySearchClient(api_key=config.tavily_api_key)

    # v0.3.1 doesn't support --replay-search -- directly call prepare_evidence
    prepare_evidence = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=args.max_sources)

    result = prepare_evidence({
        "question": frozen["question"],
        "subquestions": frozen["subquestions"],
        "search_results": frozen["search_results"],
        "errors": [],
    })

    if args.output:
        output_data = {
            "evidence_cards": [c.model_dump() for c in result.get("evidence_cards", [])],
            "extracted_claims": [c.model_dump() for c in result.get("extracted_claims", [])],
            "evidence_metrics": result.get("evidence_metrics", {}),
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"Output saved to {args.output}")

    print(f"Evidence cards: {len(result.get('evidence_cards', []))}")
    print(f"Extracted claims: {len(result.get('extracted_claims', []))}")


if __name__ == "__main__":
    main()
