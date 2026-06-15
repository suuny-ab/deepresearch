"""Run the capability-ceiling evaluation: 3 architectures × 3 questions × 3 rounds.

Usage::

    uv run python benchmark/run_capability_eval.py --rounds 3

Produces ``benchmark/capability_results/*.json`` files, one per run.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily import TavilySearchClient
from deepresearch.clients.tavily_pool import PooledTavilyClient, TavilyKeyPool
from deepresearch.config import AppConfig
from deepresearch.runner import build_agent

from capability_eval import run_capability_eval

BENCHMARK_DIR = Path(__file__).resolve().parent
RESULTS_DIR = BENCHMARK_DIR / "capability_results"

# Three questions designed to test different capability ceilings:
# Q1: Fact-dense — tests extraction precision and cross-validation
# Q2: Comparison — tests perspective diversity and balance
# Q3: Open exploration — tests search strategy and self-correction
QUESTIONS = [
    {
        "id": "Q1-solid-state-battery",
        "question": "固态电池 2026 年商业化量产的真实进展：哪些公司的哪些技术路线已经进入或接近量产阶段？具体的产能规划和时间节点是什么？目前面临的最大技术瓶颈和成本挑战是什么？",
    },
    {
        "id": "Q2-agent-framework",
        "question": "LangGraph 与 CrewAI 在构建 AI Agent 系统时的真实技术差异是什么？各自的架构设计哲学、适用场景和局限性是什么？请基于实际文档和社区案例进行客观对比，不要偏向任何一方。",
    },
    {
        "id": "Q3-agent-challenges",
        "question": "2026 年 AI Agent 开发面临的核心工程挑战是什么？从可靠性、安全性、成本控制、工具集成、评估体系五个维度分析当前的主要瓶颈和社区共识。",
    },
]

ARCHITECTURES = ["pipeline", "multi-agent", "react"]


def load_config() -> AppConfig:
    config = AppConfig.from_env()
    config.validate_required()
    return config


def build_search_client(config: AppConfig):
    if len(config.tavily_api_keys) > 1:
        pool = TavilyKeyPool(config.tavily_api_keys)
        return PooledTavilyClient(pool)
    return TavilySearchClient(api_key=config.tavily_api_key)  # type: ignore[arg-type]


def build_llm_client(config: AppConfig):
    return DeepSeekLLMClient(
        api_key=config.deepseek_api_key,  # type: ignore[arg-type]
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run capability ceiling evaluation")
    parser.add_argument("--rounds", type=int, default=3, help="Rounds per question × architecture")
    parser.add_argument("--questions", type=str, nargs="*", help="Question IDs to run (default: all)")
    parser.add_argument("--architectures", type=str, nargs="*", help="Architectures to test (default: all)")
    parser.add_argument("--results-dir", type=str, default=str(RESULTS_DIR),
                        help=f"Output directory (default: {RESULTS_DIR})")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan without executing")
    args = parser.parse_args()

    config = load_config()
    llm = build_llm_client(config)
    search = build_search_client(config)

    # Filter
    qs = QUESTIONS
    if args.questions:
        qs = [q for q in QUESTIONS if q["id"] in args.questions]
    archs = ARCHITECTURES
    if args.architectures:
        valid = set(args.architectures) & set(ARCHITECTURES)
        archs = [a for a in ARCHITECTURES if a in valid]

    results_dir = Path(args.results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)

    total_runs = len(qs) * len(archs) * args.rounds
    print(f"Capability Ceiling Evaluation")
    print(f"  Questions:    {len(qs)} ({', '.join(q['id'] for q in qs)})")
    print(f"  Architectures: {archs}")
    print(f"  Rounds:        {args.rounds}")
    print(f"  Total runs:    {total_runs}")
    print(f"  Results dir:   {results_dir}")
    print()

    if args.dry_run:
        print("[DRY RUN] Would execute the following runs:")
        run_num = 1
        for round_num in range(1, args.rounds + 1):
            for q in qs:
                for arch in archs:
                    print(f"  {run_num:2d}. {q['id']} × {arch} (round {round_num})")
                    run_num += 1
        return

    # Use the same LLM for judging (DeepSeek is fine for structural evaluation)
    judge_llm = llm

    run_num = 1
    total_time_start = time.perf_counter()

    for round_num in range(1, args.rounds + 1):
        for q in qs:
            for arch in archs:
                print(f"[{run_num}/{total_runs}] {q['id']} × {arch} (round {round_num})...", end=" ", flush=True)

                # Build agent for this architecture
                agent = build_agent(
                    llm=llm,
                    search=search,
                    max_subquestions=3,
                    results_per_query=4,
                    output_dir=config.output_dir,
                    architecture=arch,  # type: ignore[arg-type]
                )

                result = run_capability_eval(
                    agent_fn=agent,
                    question=q["question"],
                    question_id=q["id"],
                    architecture=arch,
                    round_num=round_num,
                    llm_judge=judge_llm,
                )

                # Serialize
                output = {
                    "question_id": result.question_id,
                    "architecture": result.architecture,
                    "round_num": result.round_num,
                    "report": result.report,
                    "capability": {
                        "architecture": result.capability.architecture,
                        "question_id": result.capability.question_id,
                        "round_num": result.capability.round_num,
                        "distinct_claims": result.capability.distinct_claims,
                        "quality_weighted_claims": result.capability.quality_weighted_claims,
                        "avg_sources_per_claim": result.capability.avg_sources_per_claim,
                        "single_source_ratio": result.capability.single_source_ratio,
                        "max_corroboration_depth": result.capability.max_corroboration_depth,
                        "unique_domains_cited": result.capability.unique_domains_cited,
                        "fulltext_ratio": result.capability.fulltext_ratio,
                        "strong_corroboration_pct": result.capability.strong_corroboration_pct,
                        "weak_corroboration_pct": result.capability.weak_corroboration_pct,
                        "cross_perspective_pct": result.capability.cross_perspective_pct,
                        "contradictions_acknowledged": result.capability.contradictions_acknowledged,
                        "coverage_score": result.capability.coverage_score,
                        "sections_present": result.capability.sections_present,
                        "honesty_score": result.capability.honesty_score,
                        "hedge_word_count": result.capability.hedge_word_count,
                        "contradiction_presented": result.capability.contradiction_presented,
                        "composite_score": result.capability.composite_score,
                        "errors": result.capability.errors,
                    },
                    "process": {
                        "architecture": result.process.architecture,
                        "wall_time_seconds": result.process.wall_time_seconds,
                        "total_tokens": result.process.total_tokens,
                        "total_cost_usd": result.process.total_cost_usd,
                        "llm_call_count": result.process.llm_call_count,
                        "search_query_count": result.process.search_query_count,
                        "pages_fetched": result.process.pages_fetched,
                        "iterations": result.process.iterations,
                        "dead_searches": result.process.dead_searches,
                        "error_count": result.process.error_count,
                        "fulltext_ratio_na": result.process.fulltext_ratio_na,
                        "dead_end_rate_na": result.process.dead_end_rate_na,
                    },
                    "errors": result.errors,
                }

                filename = f"{q['id']}_{arch}_r{round_num}.json"
                output_path = results_dir / filename
                output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

                elapsed = time.perf_counter() - total_time_start
                print(f"✓ ({result.process.wall_time_seconds:.0f}s, "
                      f"{result.process.total_tokens} tokens, "
                      f"composite={result.capability.composite_score:.3f}) "
                      f"[elapsed: {elapsed:.0f}s]")

                run_num += 1

                # Small delay between runs to avoid rate limiting
                time.sleep(0.5)

    total_elapsed = time.perf_counter() - total_time_start
    print(f"\nDone. {total_runs} runs in {total_elapsed:.0f}s.")
    print(f"Results saved to {results_dir}/")
    print(f"\nTo compare: uv run python benchmark/capability_compare.py {results_dir}/")


if __name__ == "__main__":
    main()
