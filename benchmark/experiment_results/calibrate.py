"""Calibrate composite: gate thresholds, norm bounds, weight sensitivity."""
import json, sys
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from benchmark.capability_eval import _parse_citation_map
from deepresearch.utils.urls import extract_domain

# Collect ALL reports with their metric data
cap_dir = Path(__file__).resolve().parent.parent / 'capability_results'
exp_dir = Path(__file__).resolve().parent
claim_file = exp_dir / 'claim_analysis.json'
claims_data = json.loads(claim_file.read_text()) if claim_file.exists() else {}

all_reports = []

# 27 rounds + Pipeline 5 rounds + React OC 3 rounds
for ddir in [cap_dir, exp_dir]:
    for f in sorted(ddir.glob('*.json')):
        if '_run' in f.name or 'claim' in f.name or 'gaps' in f.name or 'judge' in f.name:
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        report = d.get('report', '')
        if not report: continue
        cmap = _parse_citation_map(report)
        domains = [extract_domain(url) for url in cmap.values() if extract_domain(url)]

        arch = d.get('architecture', '')
        if not arch:
            # Infer from filename
            fn = f.stem
            for a in ['pipeline', 'multi-agent', 'react']:
                if a in fn: arch = a; break

        all_reports.append({
            'file': f.name,
            'arch': arch,
            'cited_urls': len(cmap),
            'unique_domains': len(set(domains)),
            'report_len': len(report),
        })

print(f'Total reports analyzed: {len(all_reports)}')
print()

# === Question 1: Gate thresholds ===
print('=== Q1: Gate Threshold Calibration ===')
print(f'{"Arch":<15} {"N":>4} {"cited_urls(min/med/max)":>30} {"domains(min/med/max)":>30}')
for arch in ['pipeline', 'multi-agent', 'react']:
    arch_reports = [r for r in all_reports if arch in r['arch']]
    if not arch_reports: continue
    cited = sorted([r['cited_urls'] for r in arch_reports])
    doms = sorted([r['unique_domains'] for r in arch_reports])
    print(f'{arch:<15} {len(arch_reports):>4}   {cited[0]:>3}/{int(median(cited)):>3}/{cited[-1]:>3}                  {doms[0]:>3}/{int(median(doms)):>3}/{doms[-1]:>3}')

# Overall distribution
all_cited = sorted([r['cited_urls'] for r in all_reports])
all_doms = sorted([r['unique_domains'] for r in all_reports])
print(f'\nOverall (n={len(all_reports)}):')
print(f'  cited_urls: p0={all_cited[0]}, p5={all_cited[max(0,len(all_cited)//20)]}, p25={all_cited[len(all_cited)//4]}, p50={int(median(all_cited))}, p75={all_cited[3*len(all_cited)//4]}')
print(f'  domains:    p0={all_doms[0]}, p5={all_doms[max(0,len(all_doms)//20)]}, p25={all_doms[len(all_doms)//4]}, p50={int(median(all_doms))}, p75={all_doms[3*len(all_doms)//4]}')

# Find borderline cases
print(f'\nReports with cited_urls <= 3:')
for r in all_reports:
    if r['cited_urls'] <= 3:
        print(f'  {r["file"]}: cited={r["cited_urls"]}, domains={r["unique_domains"]}, arch={r["arch"]}')
print(f'Reports with unique_domains <= 2:')
for r in all_reports:
    if r['unique_domains'] <= 2:
        print(f'  {r["file"]}: cited={r["cited_urls"]}, domains={r["unique_domains"]}, arch={r["arch"]}')

# === Question 3: Norm upper bounds ===
print()
print('=== Q3: Norm Upper Bound Calibration ===')
# From claim analysis (Pipeline R1-R5 + React OC 3 rounds)
pipe_claims = [c['claims'] for c in claims_data.get('pipeline_stability', [])]
react_claims = [c['claims'] for c in claims_data.get('react_option_c', [])]
all_claims_data = pipe_claims + react_claims

# Also from 27 rounds (R1 only, capability scores)
from pathlib import Path as P
disc_claims = []
disc_qw = []
for f in sorted(cap_dir.glob('*_r1.json')):
    d = json.loads(f.read_text())
    cap = d.get('capability', {})
    dc = cap.get('distinct_claims', 0)
    qw = cap.get('quality_weighted_claims', 0)
    if dc > 0: disc_claims.append(dc)
    if qw > 0: disc_qw.append(qw)

print(f'Pipeline R1-R5 claims: {pipe_claims}')
print(f'React OC 3 claims: {react_claims}')
print(f'27-round R1 distinct_claims: p50={int(median(disc_claims))}, p95={sorted(disc_claims)[int(len(disc_claims)*0.95)] if len(disc_claims)>=20 else "n/a"}, max={max(disc_claims)}')
print(f'27-round R1 quality_weighted: p50={median(disc_qw):.1f}, p95={sorted(disc_qw)[int(len(disc_qw)*0.95)] if len(disc_qw)>=20 else "n/a"}, max={max(disc_qw)}')

if all_claims_data:
    print(f'Combined claims data: max={max(all_claims_data)}, p95≈{sorted(all_claims_data)[int(len(all_claims_data)*0.95)] if len(all_claims_data)>=20 else max(all_claims_data)}')

# === Question 4: Weight sensitivity ===
print()
print('=== Q4: Weight Sensitivity ===')

# Load 27-round R1 capability data
arch_scores = {'pipeline': [], 'multi-agent': [], 'react': []}
for f in sorted(cap_dir.glob('*_r1.json')):
    d = json.loads(f.read_text())
    cap = d.get('capability', {})
    arch = d.get('architecture', '')
    if not arch: continue
    dc = cap.get('distinct_claims', 0)
    qw = cap.get('quality_weighted_claims', 0)
    sr = cap.get('single_source_ratio', 0)
    sp = cap.get('strong_corroboration_pct', 0)
    wp = cap.get('weak_corroboration_pct', 0)
    if dc <= 0: continue
    arch_scores[arch].append({
        'dc': dc, 'qw': qw, 'sr': sr, 'sp': sp, 'wp': wp,
    })

# Compute composite with 3 weight sets
def norm(v, lo, hi):
    return max(0.0, min(1.0, (v - lo) / (hi - lo))) if hi > lo else 0.0

weight_sets = [
    ('W1: 30/30/25/15', 0.30, 0.30, 0.25, 0.15),
    ('W2: 25/25/30/20', 0.25, 0.25, 0.30, 0.20),
    ('W3: 35/35/15/15', 0.35, 0.35, 0.15, 0.15),
]

for label, w_dc, w_qw, w_sr, w_corr in weight_sets:
    arch_means = {}
    for arch in ['pipeline', 'multi-agent', 'react']:
        comps = []
        for s in arch_scores[arch]:
            c = (w_dc * norm(s['dc'], 0, 100) +
                 w_qw * norm(s['qw'], 0, 60) +
                 w_sr * (1 - s['sr']) +
                 w_corr * (s['sp'] + s['wp']))
            comps.append(c)
        arch_means[arch] = mean(comps)

    # Ranking
    ranking = sorted(arch_means.items(), key=lambda x: x[1], reverse=True)
    rank_str = ' > '.join(f'{a} ({v:.3f})' for a, v in ranking)
    spread = ranking[0][1] - ranking[-1][1]
    print(f'{label}: {rank_str}  (spread={spread:.3f})')
