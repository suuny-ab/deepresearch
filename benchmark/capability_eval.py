"""Capability-ceiling evaluation: measures what each architecture *can* achieve.

All quality metrics are derived from the **final report text** plus its
``## Sources`` section — never from architecture-specific intermediate state
(evidence_cards, search_results, etc.).  This makes the comparison fair
across Pipeline, Multi-Agent, and ReAct.

Five quality dimensions:
1. Factual Depth      — claim count, source-per-claim, corroboration depth
2. Exploration Breadth — unique domains cited, domain diversity
3. Corroboration Strength — strong/weak/single-source ratios
4. Structural Completeness — LLM-as-Judge coverage scoring
5. Uncertainty Honesty     — LLM-as-Judge 1-5 scale

Process metrics are recorded separately (not scored).
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from deepresearch.utils.urls import extract_domain


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ExtractedClaim:
    """One claim extracted from a report, with citation mapping resolved."""
    text: str
    citation_ids: list[int]
    confidence: str  # high | medium | low
    unique_domains: int = 0
    corroboration_level: str = "unverifiable"  # strongly | weakly | single | unverifiable
    corroboration_weight: float = 0.5


@dataclass
class ProcessMetrics:
    """Per-run process metrics — recorded, not scored."""
    architecture: str = ""
    wall_time_seconds: float = 0.0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    llm_call_count: int = 0
    search_query_count: int = 0
    pages_fetched: int | None = None       # None = N/A for this architecture
    iterations: int = 0
    dead_searches: int | None = None       # None = N/A
    error_count: int = 0
    # Flags for reporting
    fulltext_ratio_na: bool = False
    dead_end_rate_na: bool = False


@dataclass
class CapabilityScores:
    """Five-dimension quality scores for one run."""
    architecture: str = ""
    question_id: str = ""
    round_num: int = 0

    # Dimension 1: Factual Depth
    distinct_claims: int = 0
    quality_weighted_claims: float = 0.0
    avg_sources_per_claim: float = 0.0
    single_source_ratio: float = 0.0
    max_corroboration_depth: int = 0

    # Dimension 2: Exploration Breadth
    unique_domains_cited: int = 0
    fulltext_ratio: float | None = None     # None = N/A

    # Dimension 3: Corroboration Strength
    strong_corroboration_pct: float = 0.0
    weak_corroboration_pct: float = 0.0
    cross_perspective_pct: float | None = None  # None = N/A (only Multi-Agent)
    contradictions_acknowledged: bool = False

    # Dimension 4: Structural Completeness
    coverage_score: float = 0.0
    sections_present: list[str] = field(default_factory=list)

    # Dimension 5: Uncertainty Honesty
    honesty_score: float = 0.0
    hedge_word_count: int = 0
    contradiction_presented: bool = False

    # Composite (architecture-agnostic)
    composite_score: float = 0.0

    errors: list[str] = field(default_factory=list)


@dataclass
class RunResult:
    """Complete result from one evaluation run."""
    question_id: str
    architecture: str
    round_num: int
    report: str = ""
    capability: CapabilityScores = field(default_factory=CapabilityScores)
    process: ProcessMetrics = field(default_factory=ProcessMetrics)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Citation parsing (deterministic, zero LLM)
# ---------------------------------------------------------------------------

_CITATION_MAP_RE = re.compile(r"^\[(\d+)\]\s+(https?://\S+)", re.MULTILINE)


def _parse_citation_map(report: str) -> dict[int, str]:
    """Parse ``## Sources`` (or equivalent) section → {citation_number: url}.

    Handles multiple header formats (English ``## Sources``, Chinese ``## 来源``,
    ``## 参考来源``, etc.) and multiple citation formats:
    1. ``[N] https://...``  (Pipeline / Multi-Agent)
    2. ``N. [Title](https://...)``  (React Markdown numbered list)
    3. ``N. https://...``  (Bare URL numbered list)
    """
    # Try multiple source-section header patterns
    _SOURCE_HEADERS = [
        r"##\s+Sources",
        r"##\s+来源",
        r"##\s+参考来源",
        r"##\s+参考资料",
        r"##\s+参考文献",
        r"##\s+引用",
        r"##\s+Reference",
    ]

    sources_text = ""
    for pattern in _SOURCE_HEADERS:
        match = re.search(
            rf"(?:^|\n){pattern}\s*\n(.*?)(?:\n##\s|\n---|\Z)",
            report, re.DOTALL | re.IGNORECASE,
        )
        if match:
            sources_text = match.group(1).strip()
            break

    # Fallback: try the standard split_sources (handles ## Sources only)
    if not sources_text:
        from deepresearch.citations import split_sources
        _body, sources_text = split_sources(report)
        if sources_text:
            sources_text = sources_text.strip()

    if not sources_text:
        return {}

    citation_map: dict[int, str] = {}

    # Format 1: [N] URL  (standard DeepResearch format)
    bracket_matches = re.findall(r"\[(\d+)\]\s*(https?://\S+)", sources_text)
    for num_str, url in bracket_matches:
        citation_map[int(num_str)] = url.rstrip(".,;:)")

    # Format 2: N. [Title](URL)  (Markdown numbered list — React output)
    md_link_matches = re.findall(
        r"^(\d+)\.\s*\[.*?\]\((https?://[^)]+)\)",
        sources_text,
        re.MULTILINE,
    )
    for num_str, url in md_link_matches:
        num = int(num_str)
        if num not in citation_map:
            citation_map[num] = url

    # Format 3: Bare URL in a numbered list: "1. https://..."
    bare_url_matches = re.findall(
        r"^(\d+)\.\s*(https?://\S+)",
        sources_text,
        re.MULTILINE,
    )
    for num_str, url in bare_url_matches:
        num = int(num_str)
        if num not in citation_map:
            citation_map[num] = url.rstrip(".,;:)")

    # Format 4: Fallback — extract all markdown links [text](url) and number sequentially
    if not citation_map:
        all_links = re.findall(r"\[.*?\]\((https?://[^)]+)\)", sources_text)
        for i, url in enumerate(all_links, 1):
            citation_map[i] = url

    return citation_map


def _resolve_claim_citations(
    citation_ids: list[int],
    citation_map: dict[int, str],
) -> tuple[list[str], int]:
    """Map citation [N] → URL → domain → count unique domains.

    Returns (valid_urls, unique_domain_count).
    """
    urls = []
    domains = set()
    for cid in citation_ids:
        url = citation_map.get(cid)
        if url:
            urls.append(url)
            domain = extract_domain(url)
            if domain:
                domains.add(domain)
    return urls, len(domains)


# ---------------------------------------------------------------------------
# Claim extraction from report (LLM-based, architecture-agnostic)
# ---------------------------------------------------------------------------

_CLAIM_EXTRACTION_PROMPT = """Extract every distinct factual claim from this research report.
A claim is a single verifiable statement — not a paragraph summary.

## Rules
- Split to the smallest verifiable unit (one fact per claim)
- For each claim, list ALL [N] citation numbers that support it
- If a claim has no citation support, use empty citation_ids array
- Do NOT invent citation numbers that don't appear in the text
- Assign confidence: "high" (explicitly stated), "medium" (reasonably inferred), "low" (vague/hinted)

## Available Citations (from ## Sources section)
{source_mapping}

## Report Body
{report_body}

Return ONLY this JSON (no markdown, no explanation):
{{"claims": [{{"text": "...", "citation_ids": [1, 2], "confidence": "high|medium|low"}}]}}"""


def _extract_claims_from_report(
    llm,
    report: str,
    errors: list[str],
) -> tuple[list[ExtractedClaim], dict[int, str]]:
    """LLM extracts claims from report; deterministic post-processing resolves citations.

    Returns (claims, citation_map).
    """
    citation_map = _parse_citation_map(report)

    # Split report body from Sources
    from deepresearch.citations import split_sources
    body, _sources_text = split_sources(report)

    if not body.strip():
        return [], citation_map

    # Format source mapping for the prompt
    if citation_map:
        source_lines = "\n".join(f"  [{n}] {url}" for n, url in sorted(citation_map.items()))
    else:
        source_lines = "  (no citations found in ## Sources section)"

    prompt = _CLAIM_EXTRACTION_PROMPT.format(
        source_mapping=source_lines,
        report_body=body[:8000],
    )

    try:
        text, _ = llm.complete(prompt)
    except Exception as exc:
        errors.append(f"Claim extraction LLM call failed: {exc}")
        return [], citation_map

    raw_claims = _extract_json(text).get("claims", [])
    if not isinstance(raw_claims, list):
        errors.append(f"Claim extraction returned non-list: {type(raw_claims)}")
        return [], citation_map

    # Post-process: validate citation_ids, compute corroboration
    claims: list[ExtractedClaim] = []
    for rc in raw_claims:
        if not isinstance(rc, dict) or not rc.get("text"):
            continue
        raw_ids = rc.get("citation_ids", [])
        if not isinstance(raw_ids, list):
            raw_ids = []

        # Filter: only keep citation_ids that exist in the Sources map
        valid_ids = [cid for cid in raw_ids if isinstance(cid, int) and cid in citation_map]

        confidence = rc.get("confidence", "medium")
        if confidence not in ("high", "medium", "low"):
            confidence = "medium"

        claim = ExtractedClaim(
            text=rc["text"].strip(),
            citation_ids=valid_ids,
            confidence=confidence,
        )

        # Resolve citations → domains → corroboration
        _urls, domain_count = _resolve_claim_citations(valid_ids, citation_map)
        claim.unique_domains = domain_count

        # Corroboration level (deterministic from citation structure)
        # Weight choices (documented in design):
        #   single_source = 0.5 — one domain, no independent verification
        #   weakly_corroborated = 0.75 — two independent domains
        #   strongly_corroborated = 1.0 — three+ independent domains; collusion highly improbable
        #   unverifiable = 0.5 — no valid citations; treated same as single_source (conservative)
        if domain_count >= 3:
            claim.corroboration_level = "strongly_corroborated"
            claim.corroboration_weight = 1.0
        elif domain_count == 2:
            claim.corroboration_level = "weakly_corroborated"
            claim.corroboration_weight = 0.75
        elif domain_count == 1:
            claim.corroboration_level = "single_source"
            claim.corroboration_weight = 0.5
        else:
            claim.corroboration_level = "unverifiable"
            claim.corroboration_weight = 0.5

        claims.append(claim)

    return claims, citation_map


# ---------------------------------------------------------------------------
# Contradiction detection from report text (architecture-agnostic)
# ---------------------------------------------------------------------------

_CONTRADICTION_SIGNALS = re.compile(
    r"另一方面|然而|但是|不过|相反|与之相对|相比之下|存在争议|观点分歧|不同看法",
    re.IGNORECASE,
)


def _detect_contradictions_in_report(report: str, citation_map: dict[int, str]) -> bool:
    """Check if the report acknowledges conflicting views.

    Strategy: report must (a) cite ≥3 unique domains (condition for having
    diverse enough sources to even detect contradictions) AND (b) contain
    explicit contradiction/contrast language.
    """
    domains = {extract_domain(url) for url in citation_map.values() if extract_domain(url)}
    has_diversity = len(domains) >= 3
    has_language = bool(_CONTRADICTION_SIGNALS.search(report))
    return has_diversity and has_language


# ---------------------------------------------------------------------------
# Process metrics extraction (pure computation, no LLM)
# ---------------------------------------------------------------------------

def extract_process_metrics(
    state: dict,
    architecture: str,
    elapsed: float,
    react_steps: list | None = None,
) -> ProcessMetrics:
    """Extract process metrics from a research state after completion.

    Parameters
    ----------
    react_steps:
        List of ReActStep objects (only for ReAct architecture).  Used to
        extract search/fetch counts that would otherwise come from state.
    """
    token_usage = state.get("token_usage", [])

    total_tokens = sum(u.prompt_tokens + u.completion_tokens for u in token_usage)
    total_cost = sum(u.estimated_cost for u in token_usage)

    if architecture == "react" and react_steps is not None:
        search_count = sum(1 for s in react_steps if getattr(s, "action", "") == "search")
        fetch_count = sum(1 for s in react_steps if getattr(s, "action", "") == "fetch")
        dead = sum(1 for s in react_steps
                   if getattr(s, "action", "") == "search"
                   and "Already searched" in getattr(s, "observation", ""))
        return ProcessMetrics(
            architecture=architecture,
            wall_time_seconds=round(elapsed, 1),
            total_tokens=total_tokens,
            total_cost_usd=round(total_cost, 6),
            llm_call_count=len(token_usage),
            search_query_count=search_count,
            pages_fetched=fetch_count,
            iterations=len(react_steps),
            dead_searches=dead,
            error_count=len(state.get("errors", [])),
            fulltext_ratio_na=True,
            dead_end_rate_na=True,
        )

    if architecture == "multi-agent":
        # Multi-agent: searches happen inside subquestion agents.
        # Aggregate from _agent_results and mark extraction metrics as N/A.
        agent_results = state.get("_agent_results", [])
        agent_search_count = sum(
            len(getattr(ar, "search_results", [])) for ar in agent_results
        )
        return ProcessMetrics(
            architecture=architecture,
            wall_time_seconds=round(elapsed, 1),
            total_tokens=total_tokens,
            total_cost_usd=round(total_cost, 6),
            llm_call_count=len(token_usage),
            search_query_count=agent_search_count if agent_search_count > 0 else None,
            pages_fetched=None,
            error_count=len(state.get("errors", [])),
            fulltext_ratio_na=True,
            dead_end_rate_na=True,
        )

    else:
        # Pipeline / Multi-Agent: extract from state
        search_results = state.get("search_results", [])
        fulltext_count = sum(
            1 for r in search_results
            if getattr(r, "content_type", None) == "extracted_content"
        )
        dead_count = sum(1 for r in search_results if not r.content)

        return ProcessMetrics(
            architecture=architecture,
            wall_time_seconds=round(elapsed, 1),
            total_tokens=total_tokens,
            total_cost_usd=round(total_cost, 6),
            llm_call_count=len(token_usage),
            search_query_count=len(search_results),
            pages_fetched=fulltext_count,
            error_count=len(state.get("errors", [])),
            dead_searches=dead_count,
            fulltext_ratio_na=False,
            dead_end_rate_na=False,
        )


# ---------------------------------------------------------------------------
# Dimension computation (all from report + claims only)
# ---------------------------------------------------------------------------

def compute_capability_scores(
    report: str,
    question: str,
    architecture: str,
    question_id: str,
    round_num: int,
    llm_judge,
    claims: list[ExtractedClaim] | None = None,
    citation_map: dict[int, str] | None = None,
) -> CapabilityScores:
    """Compute all five capability dimensions.

    All quality metrics are derived from *claims* (extracted from report text)
    and *citation_map* (parsed from ``## Sources``).  No architecture-specific
    intermediate state is consulted.

    Parameters
    ----------
    claims:
        Pre-extracted claims.  If None, dimensions 1-3 will be zero.
    citation_map:
        Pre-parsed citation map.  If None, parsed from *report*.
    """
    errors: list[str] = []
    if claims is None:
        claims = []
    if citation_map is None:
        citation_map = _parse_citation_map(report)

    # --- Dimension 1: Factual Depth ---
    distinct_claims = len(claims)
    if claims:
        # quality_weighted_claims: penalize single-source, reward corroboration
        quality_weighted = sum(c.corroboration_weight for c in claims)
        avg_sources = sum(c.unique_domains for c in claims) / len(claims)
        single_source_count = sum(1 for c in claims if c.corroboration_level in ("single_source", "unverifiable"))
        single_source_ratio_val = single_source_count / len(claims)
        max_depth = max((c.unique_domains for c in claims), default=0)
    else:
        quality_weighted = 0.0
        avg_sources = 0.0
        single_source_ratio_val = 0.0
        max_depth = 0

    # --- Dimension 2: Exploration Breadth ---
    cited_domains = {extract_domain(url) for url in citation_map.values() if extract_domain(url)}

    # fulltext_ratio: only applicable to Pipeline/Multi-Agent (ReAct = N/A).
    # Handled at the CapabilityScores level — caller sets None for ReAct.

    # --- Dimension 3: Corroboration Strength ---
    if claims:
        strong = sum(1 for c in claims if c.corroboration_level == "strongly_corroborated")
        weak = sum(1 for c in claims if c.corroboration_level == "weakly_corroborated")
        strong_pct = strong / len(claims)
        weak_pct = weak / len(claims)
    else:
        strong_pct = 0.0
        weak_pct = 0.0

    # Cross-perspective: only Multi-Agent has this architectural capability.
    # Pipeline and ReAct get None (displayed as "N/A").
    cross_perspective_pct_val: float | None = None

    # Contradictions acknowledged: architecture-agnostic, detected from report
    contradictions_ack = _detect_contradictions_in_report(report, citation_map)

    # --- Dimension 4 & 5: LLM-as-Judge ---
    coverage_score = 0.0
    honesty_score = 0.0
    sections_present: list[str] = []
    hedge_count = 0
    contradiction_presented = False

    if llm_judge is not None:
        try:
            coverage_score, sections_present = _judge_coverage(llm_judge, question, report, errors)
            honesty_score, hedge_count, contradiction_presented = _judge_honesty(llm_judge, report, errors)
        except Exception as exc:
            errors.append(f"LLM-as-Judge failed: {exc}")

    # --- Composite (architecture-agnostic) ---
    # quality_weighted_claims normalized to [0,1] assuming max ~30 quality-weighted claims
    # domains normalized to [0,1] assuming max ~30 unique domains cited
    # corroboration: strong + weak ratio
    # Composite (Option A, regulator-approved 2026-06-16):
    # 100% from declarative quality — no LLM judge, no citation structure.
    # Four terms: quantity (dc), quality (qw), breadth (1-sr), depth (sp).
    composite = compute_composite(
        claims=claims,
        cited_urls=len(citation_map),
        unique_domains=len(cited_domains),
        architecture=architecture,
    )
    if composite is None:
        composite = 0.0  # Gate failed or architecture excluded

    return CapabilityScores(
        architecture=architecture,
        question_id=question_id,
        round_num=round_num,
        distinct_claims=distinct_claims,
        quality_weighted_claims=round(quality_weighted, 1),
        avg_sources_per_claim=round(avg_sources, 2),
        single_source_ratio=round(single_source_ratio_val, 3),
        max_corroboration_depth=max_depth,
        unique_domains_cited=len(cited_domains),
        fulltext_ratio=None,  # Set by caller if applicable
        strong_corroboration_pct=round(strong_pct, 3),
        weak_corroboration_pct=round(weak_pct, 3),
        cross_perspective_pct=cross_perspective_pct_val,
        contradictions_acknowledged=contradictions_ack,
        coverage_score=round(coverage_score, 3),
        sections_present=sections_present,
        honesty_score=round(honesty_score, 1),
        hedge_word_count=hedge_count,
        contradiction_presented=contradiction_presented,
        composite_score=round(composite, 3),
        errors=errors,
    )


def _normalize(value: float, floor: float, ceiling: float) -> float:
    if ceiling <= floor:
        return 0.0
    return max(0.0, min(1.0, (value - floor) / (ceiling - floor)))


def compute_composite(
    claims: list,
    cited_urls: int = 0,
    unique_domains: int = 0,
    architecture: str = "",
) -> float | None:
    """Compute the architecture-agnostic composite quality score.

    Gate: cited_urls ≥ 1 AND unique_domains ≥ 1 (catches crashes + parse failures).
    React excluded until evidence formatting aligns with Pipeline/Multi-Agent.

    Formula (Option A, regulator-approved 2026-06-16):
        composite = 0.30 × norm(distinct_claims, 0, 100)
                  + 0.30 × norm(quality_weighted, 0, 65)
                  + 0.25 × (1 - single_source_ratio)
                  + 0.15 × strong_corroboration_pct

    Four terms measure four distinct concepts:
      dc   — quantity (how many claims extracted)
      qw   — quality (claims weighted by corroboration)
      (1-sr) — breadth (fraction with ≥1 corroborating source)
      sp   — depth (fraction with ≥3 independent domains)

    Returns None if gate fails or architecture is excluded.
    """
    if architecture == "react":
        return None  # ⓘ Evidence formatting path not aligned

    if cited_urls < 1 or unique_domains < 1:
        return None  # Gate: crash or parse failure

    if not claims:
        return 0.0

    n = len(claims)
    dc = n
    qw = sum(getattr(c, "corroboration_weight", 0.5) for c in claims)
    single_and_unverifiable = sum(
        1 for c in claims
        if getattr(c, "corroboration_level", "single_source")
        in ("single_source", "unverifiable")
    )
    sr = single_and_unverifiable / n
    strong = sum(
        1 for c in claims
        if getattr(c, "corroboration_level", "") == "strongly_corroborated"
    )
    sp = strong / n

    return (
        0.30 * _normalize(dc, 0, 100)
        + 0.30 * _normalize(qw, 0, 65)
        + 0.25 * (1 - sr)
        + 0.15 * sp
    )


# ---------------------------------------------------------------------------
# LLM-as-Judge prompts (no truncation — uses full report)
# ---------------------------------------------------------------------------

def _judge_coverage(llm, question: str, report: str, errors: list[str]) -> tuple[float, list[str]]:
    prompt = f"""You are evaluating a research report for structural completeness.

## Research Question
{question}

## Report
{report}

## Task
1. List 5-8 information dimensions that a COMPLETE answer to this question MUST cover.
2. For each dimension, judge whether the report covers it:
   - 0.0 = not mentioned at all
   - 0.5 = briefly mentioned but not substantively discussed
   - 1.0 = covered with specific evidence or analysis

Return ONLY this JSON:
{{"dimensions": [{{"name": "...", "score": 0.X}}]}}"""

    try:
        text, _ = llm.complete(prompt)
        data = _extract_json(text)
        dims = data.get("dimensions", [])
        if dims:
            scores = [d.get("score", 0) for d in dims]
            coverage = sum(scores) / len(scores)
            sections = [d.get("name", "") for d in dims if d.get("score", 0) > 0]
            return coverage, sections
    except Exception as exc:
        errors.append(f"Coverage judge error: {exc}")
    return 0.0, []


def _judge_honesty(llm, report: str, errors: list[str]) -> tuple[float, int, bool]:
    prompt = f"""You are evaluating a research report for uncertainty honesty.

## Report
{report}

## Task
Rate the report's honesty about uncertainty on a 1-5 scale:

1 = All claims are stated as absolute facts with no caveats, no source limitations mentioned
2 = A few minor hedges but mostly presents claims as certain
3 = Some claims are qualified; source limitations occasionally noted
4 = Most key claims include confidence qualifiers; conflicting views noted
5 = Clearly distinguishes consensus from speculation; actively flags evidence gaps;
    presents conflicting views without forcing resolution; acknowledges what is UNKNOWN

Also count:
- hedge_word_count: number of hedging words/phrases (可能, perhaps, unclear, etc.)
- contradiction_presented: whether the report explicitly discusses conflicting viewpoints (true/false)

Return ONLY this JSON:
{{"honesty_score": <1-5 integer>, "hedge_word_count": <int>, "contradiction_presented": <bool>}}"""

    try:
        text, _ = llm.complete(prompt)
        data = _extract_json(text)
        honesty = float(data.get("honesty_score", 3))
        hedge_count = int(data.get("hedge_word_count", 0))
        contradiction = bool(data.get("contradiction_presented", False))
        return honesty, hedge_count, contradiction
    except Exception as exc:
        errors.append(f"Honesty judge error: {exc}")
    return 3.0, 0, False


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------
# Run evaluation for one architecture × question
# ---------------------------------------------------------------------------

def run_capability_eval(
    agent_fn,
    question: str,
    question_id: str,
    architecture: str,
    round_num: int,
    llm_judge,
) -> RunResult:
    """Run one capability evaluation: invoke agent → extract claims from report → score."""
    t0 = time.perf_counter()
    try:
        state = agent_fn(question)
    except Exception as exc:
        return RunResult(
            question_id=question_id,
            architecture=architecture,
            round_num=round_num,
            errors=[f"Agent crashed: {exc}"],
        )
    elapsed = time.perf_counter() - t0

    report = state.get("report_markdown", "")
    react_steps = state.get("_react_steps", None)

    # Architecture-agnostic: extract claims from the report text
    errors: list[str] = []
    claims, citation_map = _extract_claims_from_report(llm_judge, report, errors)

    # Process metrics
    process = extract_process_metrics(state, architecture, elapsed, react_steps=react_steps)

    # Capability scores (all from claims + report)
    capability = compute_capability_scores(
        report=report,
        question=question,
        architecture=architecture,
        question_id=question_id,
        round_num=round_num,
        llm_judge=llm_judge,
        claims=claims,
        citation_map=citation_map,
    )

    # Set architecture-specific fields
    if architecture == "multi-agent":
        cross_count = state.get("_cross_agent_corroborations", 0)
        capability.cross_perspective_pct = round(
            cross_count / len(claims) if claims else 0.0, 3
        )
    if architecture != "react":
        # fulltext_ratio only meaningful for Pipeline/Multi-Agent
        search_results = state.get("search_results", [])
        if search_results:
            fulltext_count = sum(
                1 for r in search_results
                if getattr(r, "content_type", None) == "extracted_content"
            )
            capability.fulltext_ratio = round(fulltext_count / len(search_results), 3)

    capability.errors.extend(errors)

    return RunResult(
        question_id=question_id,
        architecture=architecture,
        round_num=round_num,
        report=report,
        capability=capability,
        process=process,
        errors=capability.errors,
    )
