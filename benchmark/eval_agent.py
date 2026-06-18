"""Batch evaluate agent decision quality across multiple questions.

Usage::

    uv run python benchmark/eval_agent.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from deepresearch.agent_evaluators import ALL_AGENT_EVALUATORS, evaluate_log
from deepresearch.config import AppConfig
from deepresearch.runner import build_agent
from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.clients.tavily_pool import TavilyKeyPool, PooledTavilyClient
from deepresearch.tools import TavilySearchTool, ToolRegistry


def load_questions(path: str = "benchmark/questions.json") -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def run_one(question: dict, config: AppConfig, output_dir: str) -> dict | None:
    """Run the agent on one question and return evaluation results."""
    qid = question["id"]
    qtext = question["question"]
    print(f"\n{'='*60}")
    print(f"Evaluating: {qid} — {qtext[:60]}...")
    print(f"{'='*60}")

    llm = DeepSeekLLMClient(
        api_key=config.deepseek_api_key,  # type: ignore[arg-type]
        base_url=config.deepseek_base_url,
        model=config.deepseek_model,
    )

    if len(config.tavily_api_keys) > 1:
        pool = TavilyKeyPool(config.tavily_api_keys)
        search = PooledTavilyClient(pool)
    else:
        from deepresearch.clients.tavily import TavilySearchClient
        search = TavilySearchClient(api_key=config.tavily_api_keys[0])

    # Build agent with decision logging
    from deepresearch.utils.decision_log import DecisionLogger
    log_dir = Path(output_dir) / "decisions"
    log_path = log_dir / f"{time.strftime('%Y-%m-%d-%H%M%S')}_{qid}.jsonl"
    log = DecisionLogger(log_path)

    tools = ToolRegistry([TavilySearchTool(search)])
    from deepresearch.agents.react_workspace import ReActV2Agent
    agent = ReActV2Agent(llm=llm, tools=tools, decision_log=log)

    print(f"  Running agent...")
    t0 = time.time()
    result = agent.run(qtext)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.0f}s — {result.iterations} iterations, "
          f"report {len(result.report)} chars, {len(result.errors)} errors")

    # Evaluate
    results = evaluate_log(str(log_path))
    results["question_id"] = qid
    results["question_text"] = qtext
    results["elapsed_seconds"] = elapsed
    return results


def main():
    config = AppConfig.from_env()
    config.validate_required()

    questions = load_questions()
    print(f"Loaded {len(questions)} questions")

    output_dir = "benchmark/agent_results"
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    all_results = []
    for q in questions:
        result = run_one(q, config, output_dir)
        if result:
            all_results.append(result)

    # Print summary table
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}")

    # Columns: metric names + question IDs
    metric_keys = [key for key, _ in ALL_AGENT_EVALUATORS]
    header = f"{'Metric':<30}"
    for r in all_results:
        header += f" {r['question_id']:<20}"
    print(header)
    print("-" * len(header))

    for key in metric_keys:
        row = f"{key:<30}"
        for r in all_results:
            m = r.get(key, {})
            score = m.get("score", 0)
            row += f" {score:<20.2f}"
        print(row)

    # Save
    out_path = Path(output_dir) / f"summary_{time.strftime('%Y%m%d-%H%M%S')}.json"
    out_path.write_text(json.dumps(all_results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved to {out_path}")


if __name__ == "__main__":
    main()
