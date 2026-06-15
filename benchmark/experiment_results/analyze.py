"""Experiment analysis: metric stability + cross-architecture discrimination."""
import json, re, sys
from pathlib import Path
from statistics import mean, stdev

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from benchmark.capability_eval import _parse_citation_map, _detect_contradictions_in_report
from deepresearch.utils.urls import extract_domain

# === Part A: Pipeline R1-R4 metric stability ===
rounds = []
for r in range(1, 5):
    f = Path(__file__).resolve().parent / f'exp2_Q1_pipeline_r{r}.json'
    d = json.loads(f.read_text())
    rounds.append(d)

HEDGE_PAT = re.compile(r'可能|或许|尚不|有待|似乎|推测|估计|大概|也许|不确定|未确认|未经证实|存在争议|有待验证|尚无定论')
PSEUDO_CONSENSUS = re.compile(r'研究表明|学界认为|业界公认|普遍认为|众所周知|数据显示|事实证明|大量研究证实|多项研究表明|一致认为|广泛认可|主流观点认为|多方视为|行业观察人士指出|普遍预期|从目前公开信息看')

meta = {
    'wall_time': [], 'tokens': [], 'cited_urls': [], 'unique_domains': [],
    'report_len': [],
    'has_insufficient_info': [], 'has_contradiction_section': [],
    'has_corroboration_language': [], 'hedge_count': [], 'pseudo_consensus_count': [],
    'contradictions_acknowledged': [],
}

for d in rounds:
    report = d['report']
    cmap = _parse_citation_map(report)
    domains = {extract_domain(url) for url in cmap.values() if extract_domain(url)}
    meta['wall_time'].append(d['wall_time'])
    meta['tokens'].append(d['total_tokens'])
    meta['cited_urls'].append(len(cmap))
    meta['unique_domains'].append(len(domains))
    meta['report_len'].append(len(report))
    meta['has_insufficient_info'].append(1 if re.search(r'信息不足|信息有限|未找到充分|当前搜索未能|尚无足够', report) else 0)
    meta['has_contradiction_section'].append(1 if re.search(r'##\s*(风险|不确定性|不同观点|争议|矛盾|分歧|相反)', report) else 0)
    meta['has_corroboration_language'].append(1 if re.search(r'多个独立来源|多家[^的]*证实|多方[^的]*印证|独立.*[证实|印证]', report) else 0)
    meta['hedge_count'].append(len(HEDGE_PAT.findall(report)))
    meta['pseudo_consensus_count'].append(len(PSEUDO_CONSENSUS.findall(report)))
    meta['contradictions_acknowledged'].append(1 if _detect_contradictions_in_report(report, cmap) else 0)

print('=== Exp 2: Pipeline Q1 R1-R4 — Metric Stability ===')
print(f'{"Metric":<35} {"R1":>8} {"R2":>8} {"R3":>8} {"R4":>8} {"Mean":>8} {"σ":>8} {"CV":>8}')
print('-' * 100)
for key, vals in meta.items():
    m, s = mean(vals), stdev(vals) if len(vals) >= 2 else 0
    cv = (s / m) if m > 0 else 0
    vs = ''.join(f'{v:>8.1f}' if isinstance(v, float) else f'{v:>8}' for v in vals)
    print(f'{key:<35} {vs} {m:>8.2f} {s:>8.2f} {cv:>8.3f}')

# === Part B: Cross-architecture discrimination ===
print('\n=== Cross-Architecture Discrimination (from 27 rounds, R1 only) ===')
cap_results = Path(__file__).resolve().parent.parent / 'capability_results'
arch_data = {'pipeline': [], 'multi-agent': [], 'react': []}
for qid in ['Q1-solid-state-battery', 'Q2-agent-framework', 'Q3-agent-challenges']:
    for arch in ['pipeline', 'multi-agent', 'react']:
        files = sorted(cap_results.glob(f'{qid}_{arch}_r*.json'))
        if not files: continue
        d = json.loads(files[0].read_text())
        cap = d.get('capability', {})
        if not cap: continue
        arch_data[arch].append({
            'distinct_claims': cap.get('distinct_claims', 0),
            'quality_weighted_claims': cap.get('quality_weighted_claims', 0),
            'strong_corroboration_pct': cap.get('strong_corroboration_pct', 0),
            'weak_corroboration_pct': cap.get('weak_corroboration_pct', 0),
            'single_source_ratio': cap.get('single_source_ratio', 0),
            'unique_domains_cited': cap.get('unique_domains_cited', 0),
            'coverage_score': cap.get('coverage_score', 0),
            'honesty_score': cap.get('honesty_score', 0),
            'composite_score': cap.get('composite_score', 0),
        })

print(f'{"Metric":<35} {"Pipeline":>10} {"Multi-Agent":>10} {"React":>10} {"Max-Min":>10} {"Effect Size":>12}')
print('-' * 92)
for key in arch_data['pipeline'][0].keys():
    pv = [d[key] for d in arch_data['pipeline'] if d[key] is not None]
    mv = [d[key] for d in arch_data['multi-agent'] if d[key] is not None]
    rv = [d[key] for d in arch_data['react'] if d[key] is not None]
    if not pv or not mv or not rv: continue
    pm, mm, rm = mean(pv), mean(mv), mean(rv)
    gm = mean(pv + mv + rv)
    mxmn = max(pm, mm, rm) - min(pm, mm, rm)
    es = mxmn / gm if gm > 0 else 0
    print(f'{key:<35} {pm:>10.3f} {mm:>10.3f} {rm:>10.3f} {mxmn:>10.3f} {es:>12.3f}')

# === Part C: Four-Quadrant Classification ===
print('\n=== Four-Quadrant Classification ===')
print('Key: σ=stability (Pipeline R1-R4 CV), Δ=discrimination (cross-arch effect size)')
print(f'{"Metric":<35} {"Stability(CV)":>15} {"Discrim(ES)":>15} {"Quadrant":>20}')
print('-' * 90)

# Stability data from Part A (use CVs)
stability = {
    'cited_urls': 0.061, 'unique_domains': 0.065, 'report_len': 0.100,
    'has_insufficient_info': 0.0, 'has_contradiction_section': 0.0,
    'has_corroboration_language': 0.0, 'hedge_count': 0.259,
    'pseudo_consensus_count': 1.155, 'contradictions_acknowledged': 0.0,
}

for key in ['distinct_claims', 'quality_weighted_claims', 'strong_corroboration_pct',
             'weak_corroboration_pct', 'single_source_ratio', 'unique_domains_cited',
             'coverage_score', 'honesty_score', 'composite_score']:
    if key not in arch_data['pipeline'][0]: continue
    pv = [d[key] for d in arch_data['pipeline'] if d[key] is not None]
    mv = [d[key] for d in arch_data['multi-agent'] if d[key] is not None]
    rv = [d[key] for d in arch_data['react'] if d[key] is not None]
    if not pv or not mv or not rv: continue
    pm, mm, rm = mean(pv), mean(mv), mean(rv)
    gm = mean(pv + mv + rv)
    mxmn = max(pm, mm, rm) - min(pm, mm, rm)
    es = mxmn / gm if gm > 0 else 0

    cv_val = stability.get(key, 0.3)  # default if not in Part A
    quadrant = 'Ideal' if cv_val < 0.15 and es > 0.15 else \
               'Stable-NoDiscrim' if cv_val < 0.15 else \
               'Discrim-Noisy' if es > 0.15 else 'Junk'
    print(f'{key:<35} {cv_val:>15.3f} {es:>15.3f} {quadrant:>20}')
