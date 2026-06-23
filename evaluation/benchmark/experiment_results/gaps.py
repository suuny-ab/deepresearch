"""Fill remaining gaps: honesty checks + source authority on all reports."""
import json, re
from pathlib import Path
from statistics import mean

# Import classification function inline
def classify_domain(domain):
    d = domain.lower().strip()
    if any(d.endswith(t) for t in ['.edu','.gov','.ac.cn','.gov.cn','.mil']): return '学术/政府'
    for a in ['nature.com','sciencedirect.com','arxiv.org','ieee.org','pubs.acs.org','nejm.org',
              'springer.com','wiley.com','cell.com','pnas.org','thelancet.com','jstor.org']:
        if a in d: return '学术/政府'
    for p in ['globenewswire.com','prnewswire.com','businesswire.com','newswire.ca']:
        if p in d: return '企业官方'
    for s in ['medium.com','zhuanlan.zhihu.com','caifuhao.eastmoney.com','mp.weixin.qq.com',
              'toutiao.com','jianshu.com','xiaohongshu.com']:
        if s in d: return '自媒体'
    for s in ['reddit.com','x.com','twitter.com','facebook.com','youtube.com','tiktok.com',
              'instagram.com','weibo.com','douyin.com']:
        if s in d: return '社交媒体'
    for e in ['toyota.com','samsung.com','tesla.com','bmw.com','vw.com','ford.com','gm.com',
              'hyundai.com','nio.com','byd.com','catl.com','panasonic.com','lg.com','sk.com',
              'bosch.com','continental.com']:
        if e in d: return '企业官方'
    for r in ['gartner.com','mckinsey.com','idtechex.com','imarcgroup.com','interactanalysis.com',
              'futuremarketsinc.com','bcg.com','deloitte.com','pwc.com','accenture.com','kpmg.com']:
        if r in d: return '行业媒体'
    for t in ['reuters.com','bloomberg.com','autonews.gasgoo.com','auto.ifeng.com',
              'news.metal.com','to7motor.com','eepower.com','36kr.com','kr-asia.com',
              'techcrunch.com','theverge.com','wired.com','arstechnica.com',
              'tech.sina.com.cn','finance.qq.com','news.qq.com','cls.cn','stcn.com',
              'ce.cn','sina.cn','tmtpost.com','eastmoney.com']:
        if t in d: return '行业媒体'
    for b in ['wordpress.com','blogspot.com','substack.com','hashnode.dev','dev.to',
              'ner.jgvogel.cn','hirohida.com','ideesz.com','nxebattery.com']:
        if b in d: return '自媒体'
    return '不可分类'

# Honesty check patterns
INSUFFICIENT_INFO = re.compile(r'信息不足|信息有限|未找到充分|当前搜索未能|尚无足够|尚不明确|有待进一步|仍需更多|数据有限|公开信息有限')
CONTRADICTION_SECTION = re.compile(r'##\s*(风险|不确定性|不同观点|争议|矛盾|分歧|相反|Uncertainties|Risks)')
CORROBORATION_LANGUAGE = re.compile(r'多个独立来源|多家[^的]*证实|多方[^的]*印证|独立.*[证实|印证]|单一来源|仅一家|仅.*来源|未找到其他.*来源|尚无其他')
PSEUDO_CONSENSUS = re.compile(r'研究表明|学界认为|业界公认|普遍认为|众所周知|数据显示|事实证明|大量研究证实|多项研究表明|一致认为|广泛认可|主流观点认为|多方视为|行业观察人士指出|普遍预期|从目前公开信息看')

# Collect all reports
cap_dir = Path(__file__).resolve().parent.parent / 'capability_results'
exp_dir = Path(__file__).resolve().parent

reports = []
# 27 archived rounds (all R1 — representative)
for qid in ['Q1-solid-state-battery', 'Q2-agent-framework', 'Q3-agent-challenges']:
    for arch in ['pipeline', 'multi-agent', 'react']:
        files = sorted(cap_dir.glob(f'{qid}_{arch}_r*.json'))
        if files:
            d = json.loads(files[0].read_text())
            reports.append({'id': f'{qid}/{arch}', 'report': d.get('report',''), 'arch': arch, 'qid': qid})

# Pipeline Q1 R1-R5
for r in range(1, 6):
    f = exp_dir / (f'exp2_Q1_pipeline_r{r}.json' if r < 5 else 'exp2_Q1_pipeline_r5_fixed.json')
    if f.exists():
        d = json.loads(f.read_text())
        reports.append({'id': f'pipe_Q1_R{r}', 'report': d.get('report',''), 'arch': 'pipeline', 'qid': 'Q1'})

# React Option C
for qid in ['Q1-solid-state-battery', 'Q2-agent-framework', 'Q3-agent-challenges']:
    f = exp_dir / f'exp1_{qid}.json'
    if f.exists():
        d = json.loads(f.read_text())
        reports.append({'id': f'ReactOC/{qid}', 'report': d.get('report',''), 'arch': 'react_oc', 'qid': qid})

print(f'Analyzing {len(reports)} reports...')
print()

# ---- Gap 1: Honesty checks ----
print('=== GAP 1: Honesty Checks ===')
honesty_results = {}
for r in reports:
    report = r['report']
    hid = r['id']
    honesty_results[hid] = {
        'arch': r['arch'],
        'insufficient_info': 1 if INSUFFICIENT_INFO.search(report) else 0,
        'contradiction_section': 1 if CONTRADICTION_SECTION.search(report) else 0,
        'corroboration_language': 1 if CORROBORATION_LANGUAGE.search(report) else 0,
        'pseudo_consensus': len(PSEUDO_CONSENSUS.findall(report)),
    }

# Aggregate by architecture
for arch in ['pipeline', 'multi-agent', 'react', 'react_oc']:
    arch_reports = {k: v for k, v in honesty_results.items() if v['arch'] == arch}
    if not arch_reports: continue
    n = len(arch_reports)
    info = mean(v['insufficient_info'] for v in arch_reports.values())
    contra = mean(v['contradiction_section'] for v in arch_reports.values())
    corrob = mean(v['corroboration_language'] for v in arch_reports.values())
    pseudo = mean(v['pseudo_consensus'] for v in arch_reports.values())
    print(f'{arch} (n={n}): insufficient_info={info:.2f}, contradiction_sect={contra:.2f}, '
          f'corroboration_lang={corrob:.2f}, pseudo_consensus={pseudo:.1f}')

# Cross-architecture discrimination (ES)
print()
for check, key in [('insufficient_info','insufficient_info'), ('contradiction_sect','contradiction_section'),
                    ('corroboration_lang','corroboration_language'), ('pseudo_consensus','pseudo_consensus')]:
    arch_means = {}
    for arch in ['pipeline', 'multi-agent', 'react']:
        vals = [v[key] for k, v in honesty_results.items() if v['arch'] == arch]
        if vals: arch_means[arch] = mean(vals)
    if len(arch_means) >= 2:
        mxmn = max(arch_means.values()) - min(arch_means.values())
        gm = mean(arch_means.values())
        es = mxmn / gm if gm > 0 else 0
        print(f'{check}: pipeline={arch_means.get("pipeline",0):.2f}, multi={arch_means.get("multi-agent",0):.2f}, '
              f'react={arch_means.get("react",0):.2f}, max-min={mxmn:.2f}, ES={es:.3f}')

# ---- Gap 2: Source authority ----
print()
print('=== GAP 2: Source Authority ===')
from benchmark.capability_eval import _parse_citation_map
from deepresearch.utils.urls import extract_domain

sa_results = {}
for r in reports:
    cmap = _parse_citation_map(r['report'])
    domains = [extract_domain(url) for url in cmap.values() if extract_domain(url)]
    cats = [classify_domain(d) for d in domains]
    n = len(domains)
    if n == 0:
        sa_results[r['id']] = {'arch': r['arch'], 'total': 0, 'social': 0, 'self_media': 0, 'academic': 0, 'industry': 0, 'enterprise': 0, 'unclass': 0}
        continue
    sa_results[r['id']] = {
        'arch': r['arch'],
        'total': n,
        'social': cats.count('社交媒体') / n,
        'self_media': cats.count('自媒体') / n,
        'academic': cats.count('学术/政府') / n,
        'industry': cats.count('行业媒体') / n,
        'enterprise': cats.count('企业官方') / n,
        'unclass': cats.count('不可分类') / n,
    }

for arch in ['pipeline', 'multi-agent', 'react', 'react_oc']:
    arch_reports = {k: v for k, v in sa_results.items() if v['arch'] == arch}
    if not arch_reports: continue
    n = len(arch_reports)
    social = mean(v['social'] for v in arch_reports.values())
    self_m = mean(v['self_media'] for v in arch_reports.values())
    ind = mean(v['industry'] for v in arch_reports.values())
    ent = mean(v['enterprise'] for v in arch_reports.values())
    uncl = mean(v['unclass'] for v in arch_reports.values())
    total = mean(v['total'] for v in arch_reports.values())
    print(f'{arch} (n={n}): domains={total:.1f}, social={social:.1%}, self_media={self_m:.1%}, '
          f'industry={ind:.1%}, enterprise={ent:.1%}, unclass={uncl:.1%}')

# Cross-architecture ES for social media ratio
print()
for cat in ['social', 'self_media', 'industry', 'unclass']:
    arch_means = {}
    for arch in ['pipeline', 'multi-agent', 'react']:
        vals = [v[cat] for v in sa_results.values() if v['arch'] == arch]
        if vals: arch_means[arch] = mean(vals)
    if len(arch_means) >= 2:
        mxmn = max(arch_means.values()) - min(arch_means.values())
        gm = mean(arch_means.values())
        es = mxmn / gm if gm > 0 else 0
        print(f'{cat}_ratio: pipe={arch_means.get("pipeline",0):.1%}, multi={arch_means.get("multi-agent",0):.1%}, '
              f'react={arch_means.get("react",0):.1%}, max-min={mxmn:.1%}, ES={es:.3f}')

# Save
out = {'honesty_checks': honesty_results, 'source_authority': sa_results}
(Path(__file__).resolve().parent / 'gaps.json').write_text(json.dumps(out, ensure_ascii=False, indent=2))
print('\nSaved.')
