"""Run LLM judge on 5 Pipeline rounds to get actual coverage/honesty CV."""
import json, sys, re
from pathlib import Path
from statistics import mean, stdev

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.config import AppConfig
from benchmark.capability_eval import _parse_citation_map, _extract_json

config = AppConfig.from_env()
llm = DeepSeekLLMClient(
    api_key=config.deepseek_api_key,
    base_url=config.deepseek_base_url,
    model=config.deepseek_model,
)
results_dir = Path(__file__).resolve().parent

# Judge all 5 Pipeline rounds for coverage + honesty
scores = {'coverage': [], 'honesty': [], 'contradiction_presented': [], 'hedge_count': []}

for r in range(1, 6):
    if r == 5:
        f = results_dir / 'exp2_Q1_pipeline_r5_fixed.json'
    else:
        f = results_dir / f'exp2_Q1_pipeline_r{r}.json'
    d = json.loads(f.read_text())
    report = d['report']
    question = '固态电池 2026 年商业化量产的真实进展'

    # Coverage judge
    coverage_prompt = f"""You are evaluating a research report for structural completeness.

## Research Question
{question}

## Report
{report[:8000]}

## Task
1. List 5-8 information dimensions that a COMPLETE answer to this question MUST cover.
2. For each dimension, judge whether the report covers it:
   - 0.0 = not mentioned at all
   - 0.5 = briefly mentioned but not substantively discussed
   - 1.0 = covered with specific evidence or analysis

Return ONLY this JSON:
{{"dimensions": [{{"name": "...", "score": 0.X}}]}}"""

    try:
        text, _ = llm.complete(coverage_prompt)
        data = _extract_json(text)
        dims = data.get("dimensions", [])
        if dims:
            cov = sum(d.get("score", 0) for d in dims) / len(dims)
        else:
            cov = 0.0
    except Exception:
        cov = 0.0
    scores['coverage'].append(cov)

    # Honesty judge
    honesty_prompt = f"""You are evaluating a research report for uncertainty honesty.

## Report
{report[:8000]}

## Task
Rate the report's honesty about uncertainty on a 1-5 scale:

1 = All claims are stated as absolute facts with no caveats
5 = Clearly distinguishes consensus from speculation; acknowledges what is UNKNOWN

Also count:
- hedge_word_count: number of hedging words/phrases
- contradiction_presented: whether the report explicitly discusses conflicting viewpoints (true/false)

Return ONLY this JSON:
{{"honesty_score": <1-5 integer>, "hedge_word_count": <int>, "contradiction_presented": <bool>}}"""

    try:
        text, _ = llm.complete(honesty_prompt)
        data = _extract_json(text)
        scores['honesty'].append(float(data.get("honesty_score", 3)))
        scores['contradiction_presented'].append(1 if data.get("contradiction_presented", False) else 0)
        scores['hedge_count'].append(int(data.get("hedge_word_count", 0)))
    except Exception:
        scores['honesty'].append(3.0)
        scores['contradiction_presented'].append(0)
        scores['hedge_count'].append(0)

    print(f'R{r}: coverage={cov:.2f}, honesty={scores["honesty"][-1]:.0f}, '
          f'contrad_present={scores["contradiction_presented"][-1]}, '
          f'hedge={scores["hedge_count"][-1]}')

# Compute CVs
print('\n--- Judge metric stability ---')
for key in ['coverage', 'honesty', 'contradiction_presented', 'hedge_count']:
    vals = scores[key]
    m, s = mean(vals), stdev(vals)
    cv = s/m if m > 0 else 0
    print(f'{key}: values={[round(v,2) for v in vals]}, mean={m:.3f}, σ={s:.3f}, CV={cv:.3f}')

# Cross-architecture discrimination for these (from existing data)
print('\n--- Cross-arch discrimination (from R1 only) ---')
print('coverage: pipeline=1.00, multi=1.00, react=0.91, max-min=0.09, ES=0.09')
print('honesty:  pipeline=5.0,  multi=4.3,  react=5.0,  max-min=0.67, ES=0.14')

# Save
(results_dir / 'judge_cv.json').write_text(json.dumps(scores, ensure_ascii=False))
print('Saved.')
