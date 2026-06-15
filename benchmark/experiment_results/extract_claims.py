"""Extract claims from experiment reports to complete metric analysis."""
import json, sys
from pathlib import Path
from statistics import mean, stdev

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from deepresearch.clients.llm import DeepSeekLLMClient
from deepresearch.config import AppConfig
from benchmark.capability_eval import _extract_claims_from_report, _parse_citation_map

config = AppConfig.from_env()
llm = DeepSeekLLMClient(
    api_key=config.deepseek_api_key,
    base_url=config.deepseek_base_url,
    model=config.deepseek_model,
)

results_dir = Path(__file__).resolve().parent

# -- Pipeline R1-R5 claims --
print("=== Pipeline R1-R5 Claim Extraction ===")
pipe_metrics = []
for r in [1, 2, 3, 4]:
    f = results_dir / f'exp2_Q1_pipeline_r{r}.json'
    d = json.loads(f.read_text())
    report = d['report']
    errors = []
    claims, cmap = _extract_claims_from_report(llm, report, errors)
    if claims:
        n = len(claims)
        strong = sum(1 for c in claims if c.corroboration_level == 'strongly_corroborated')
        weak = sum(1 for c in claims if c.corroboration_level == 'weakly_corroborated')
        single = sum(1 for c in claims if c.corroboration_level in ('single_source', 'unverifiable'))
        qw = sum(c.corroboration_weight for c in claims)
        domains = len({c.unique_domains for c in claims if c.unique_domains > 0})
        pipe_metrics.append({
            'round': r, 'claims': n, 'qw_claims': qw,
            'strong_pct': strong/n, 'weak_pct': weak/n, 'single_ratio': single/n,
            'unique_domains': domains, 'errors': errors,
        })
        print(f'  R{r}: {n} claims, strong={strong/n:.3f}, weak={weak/n:.3f}, single={single/n:.3f}, qw={qw:.1f}, domains={domains}')

# R5 (fixed)
f = results_dir / 'exp2_Q1_pipeline_r5_fixed.json'
d = json.loads(f.read_text())
report = d['report']
errors = []
claims, cmap = _extract_claims_from_report(llm, report, errors)
if claims:
    n = len(claims)
    strong = sum(1 for c in claims if c.corroboration_level == 'strongly_corroborated')
    weak = sum(1 for c in claims if c.corroboration_level == 'weakly_corroborated')
    single = sum(1 for c in claims if c.corroboration_level in ('single_source', 'unverifiable'))
    qw = sum(c.corroboration_weight for c in claims)
    domains = len({c.unique_domains for c in claims if c.unique_domains > 0})
    pipe_metrics.append({
        'round': 5, 'claims': n, 'qw_claims': qw,
        'strong_pct': strong/n, 'weak_pct': weak/n, 'single_ratio': single/n,
        'unique_domains': domains, 'errors': errors,
    })
    print(f'  R5(fixed): {n} claims, strong={strong/n:.3f}, weak={weak/n:.3f}, single={single/n:.3f}, qw={qw:.1f}, domains={domains}')

# Stability CVs for capability metrics
print('\n--- Stability CVs ---')
keys = ['claims', 'qw_claims', 'strong_pct', 'weak_pct', 'single_ratio', 'unique_domains']
for key in keys:
    vals = [m[key] for m in pipe_metrics]
    m, s = mean(vals), stdev(vals)
    cv = s/m if m > 0 else 0
    print(f'  {key}: mean={m:.3f}, σ={s:.3f}, CV={cv:.3f}')

# -- React Option C claims --
print('\n=== React Option C Claim Extraction ===')
react_metrics = []
for qid in ['Q1-solid-state-battery', 'Q2-agent-framework', 'Q3-agent-challenges']:
    f = results_dir / f'exp1_{qid}.json'
    d = json.loads(f.read_text())
    report = d['report']
    errors = []
    claims, cmap = _extract_claims_from_report(llm, report, errors)
    if claims:
        n = len(claims)
        strong = sum(1 for c in claims if c.corroboration_level == 'strongly_corroborated')
        weak = sum(1 for c in claims if c.corroboration_level == 'weakly_corroborated')
        single = sum(1 for c in claims if c.corroboration_level in ('single_source', 'unverifiable'))
        qw = sum(c.corroboration_weight for c in claims)
        cited = len(cmap)
        domains = len({c.unique_domains for c in claims if c.unique_domains > 0})
        react_metrics.append({
            'qid': qid, 'claims': n, 'qw_claims': qw,
            'strong_pct': strong/n, 'weak_pct': weak/n, 'single_ratio': single/n,
            'cited_urls': cited, 'domains': domains, 'errors': errors,
        })
        print(f'  {qid}: {n} claims, strong={strong/n:.3f}, weak={weak/n:.3f}, single={single/n:.3f}, cited={cited}, domains={domains}')

# Save results
out = {
    'pipeline_stability': pipe_metrics,
    'react_option_c': react_metrics,
}
(results_dir / 'claim_analysis.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
print('\nSaved to claim_analysis.json')
