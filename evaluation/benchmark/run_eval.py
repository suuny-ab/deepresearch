"""Run a LangSmith evaluation experiment across the benchmark question set.

Usage::

    uv run python benchmark/run_eval.py --experiment v0.5.3-baseline
    uv run python benchmark/run_eval.py --experiment v0.5.3-new-prompt \\
        --max-subquestions 3 --results-per-query 3
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.compare import evaluate_all
from deepresearch.config import AppConfig
from deepresearch.eval_target import make_target
from deepresearch.evaluators import (
    citation_compliance,
    cross_validation_usage,
    source_utilization,
)
from deepresearch.runner import build_agent

BENCHMARK_DIR = Path(__file__).resolve().parent
QUESTIONS_PATH = BENCHMARK_DIR / "questions.json"


def load_questions() -> list[dict]:
    """Load the benchmark question set."""
    with open(QUESTIONS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _parse_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes"}


def main() -> None:
    import argparse

    config = AppConfig.from_env()

    parser = argparse.ArgumentParser(description="Run LangSmith eval experiment")
    parser.add_argument(
        "--experiment",
        required=True,
        help="Experiment name prefix (e.g. v0.5.3-renew-prompt)",
    )
    parser.add_argument(
        "--max-subquestions",
        type=int,
        default=config.max_subquestions,
        help=f"Max subquestions (default: {config.max_subquestions})",
    )
    parser.add_argument(
        "--results-per-query",
        type=int,
        default=config.results_per_query,
        help=f"Tavily results per query (default: {config.results_per_query})",
    )
    parser.add_argument(
        "--dry-run",
        default=False,
        const=True,
        nargs="?",
        type=_parse_bool,
        help="Run without registering to LangSmith",
    )
    parser.add_argument(
        "--results-dir",
        default=str(BENCHMARK_DIR / "results"),
        help="Directory for local result JSON files (default: benchmark/results)",
    )
    args = parser.parse_args()

    config.validate_required()

    # Build agent with real clients
    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,  # type: ignore[arg-type]
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )
    search = TavilySearchClient(api_key=config.tavily_api_key)  # type: ignore[arg-type]

    agent = build_agent(
        llm=llm,
        search=search,
        max_subquestions=args.max_subquestions,
        results_per_query=args.results_per_query,
        output_dir=config.output_dir,
    )
    target = make_target(agent)
    questions = load_questions()

    print(f"Running experiment '{args.experiment}' on {len(questions)} questions...")

    # ---- local evaluation (always run) ----
    print("Computing local evaluation scores...")
    summary = evaluate_all(target, questions, version=args.experiment)
    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / f"{args.experiment}.json"
    results_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Local results saved to {results_path}")

    if args.dry_run:
        for i, q in enumerate(questions, 1):
            entry = summary["questions"][i - 1]
            print(f"  [{i}/{len(questions)}] {q['id']}: {q['question'][:50]}")
            print(f"      引用={entry['citation_passed']} 自评={entry['review_score']} "
                  f"子问题={entry['subquestion_count']} 搜索词={entry['search_query_count']} "
                  f"搜索={entry['search_result_count']}")
            print(f"      Claim={entry['extracted_claim_count']} 每源={entry['claims_per_source']:.1f} "
                  f"证据卡={entry['evidence_card_count']} 保留率={entry['extraction_retention']:.1%} "
                  f"强印证={entry['corroboration_strong_ratio']:.1%}")
            errs = entry.get("errors", [])
            print(f"      来源利用={entry['source_utilization']:.1%} "
                  f"长度={entry['report_length']}字 密度={entry['citation_density']:.1f}/千字"
                  f"{'  ⚠ errors=' + str(len(errs)) if errs else ''}")
        print("Dry-run complete.")
        return

    # ---- LangSmith experiment (optional) ----
    try:
        from langsmith.evaluation import evaluate

        evaluate(
            target,
            data=[{"question": q["question"]} for q in questions],
            evaluators=[citation_compliance, source_utilization, cross_validation_usage],
            experiment_prefix=args.experiment,
            max_concurrency=1,
        )
        print("LangSmith experiment complete. View at https://smith.langchain.com/")
    except ImportError:
        print("langsmith not installed — local results already saved.", file=sys.stderr)


if __name__ == "__main__":
    main()
