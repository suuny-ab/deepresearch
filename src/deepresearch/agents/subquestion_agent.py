"""Independent subquestion agent: search → extract → validate for one subquestion.

Each agent owns its own search and evidence pipeline, producing evidence cards
that are later merged by the coordinator.  Agents are isolated — a crash in one
does not affect others.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from deepresearch.prompts.evidence import build_validation_prompt
from deepresearch.prompts.extraction import build_extraction_prompt
from deepresearch.state import (
    EvidenceCard, ExtractedClaim, ExtractedSource, SearchResult,
    SubQuestion, TokenUsage, UsageInfo,
)
from deepresearch.utils.json import JSONParseError, _extract_json_text, parse_json_object
from deepresearch.utils.urls import extract_domain, normalize_url

if TYPE_CHECKING:
    from deepresearch.clients.llm import LLMClient
    from deepresearch.clients.tavily import SearchClient


@dataclass
class AgentResult:
    """Output from a single subquestion agent run."""
    subquestion_id: str
    evidence_cards: list[EvidenceCard] = field(default_factory=list)
    extracted_claims: list[ExtractedClaim] = field(default_factory=list)
    search_results: list[SearchResult] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    token_usage: list[TokenUsage] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers — mirrors prepare_evidence.py logic but scoped to one agent
# ---------------------------------------------------------------------------

def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[tuple[str, str]] = set()
    deduped: list[SearchResult] = []
    for result in results:
        key = (result.subquestion_id, normalize_url(result.url))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _select_sources(results: list[SearchResult], max_sources: int) -> list[SearchResult]:
    candidates = sorted(results, key=lambda r: r.score or 0, reverse=True)
    selected: list[SearchResult] = []
    selected_domains: set[str] = set()
    for candidate in candidates:
        if len(selected) >= max_sources:
            break
        domain = extract_domain(candidate.url)
        if domain and domain not in selected_domains:
            selected.append(candidate)
            selected_domains.add(domain)
    return selected


def _fallback_sources(selected: list[SearchResult]) -> list[ExtractedSource]:
    return [
        ExtractedSource(
            subquestion_id=r.subquestion_id, url=r.url, title=r.title,
            raw_content=r.content,
        )
        for r in selected if r.url and r.content
    ]


def _extract_sources(search_client: SearchClient, subquestion_id: str,
                     selected: list[SearchResult], errors: list[str],
                     ) -> tuple[list[ExtractedSource], dict[str, str]]:
    """Return (extracted_sources, content_type_map)."""
    urls = [r.url for r in selected]
    content_types: dict[str, str] = {}
    try:
        extracted = search_client.extract(urls, subquestion_id=subquestion_id)
    except Exception as exc:
        errors.append(f"Evidence extract failed for {subquestion_id}: {exc}")
        fallback = _fallback_sources(selected)
        for src in fallback:
            content_types[normalize_url(src.url)] = "search_content"
        return fallback, content_types

    for src in extracted:
        content_types[normalize_url(src.url)] = "extracted_content"
    extracted_keys = {normalize_url(s.url) for s in extracted}
    missing = [r for r in selected if normalize_url(r.url) not in extracted_keys]
    fallback = _fallback_sources(missing) if missing else []
    for src in fallback:
        key = normalize_url(src.url)
        if key not in content_types:
            content_types[key] = "search_content"
    return list(extracted) + fallback, content_types


# Reuse the pydantic wrappers from prepare_evidence for JSON parsing
from pydantic import BaseModel, model_validator
from typing import Any as _Any


def _filter_valid(items: list[dict], model_cls: type) -> list[dict]:
    return [item for item in items if _is_valid(item, model_cls)]


def _is_valid(data: dict, model_cls: type) -> bool:
    try:
        model_cls.model_validate(data)
        return True
    except Exception:
        return False


class _ClaimsResponse(BaseModel):
    claims: list[ExtractedClaim]

    @model_validator(mode="before")
    @classmethod
    def skip_invalid(cls, data: _Any) -> _Any:
        if isinstance(data, dict) and "claims" in data:
            data["claims"] = _filter_valid(data["claims"], ExtractedClaim)
        return data


class _EvidenceResponse(BaseModel):
    evidence_cards: list[EvidenceCard]

    @model_validator(mode="before")
    @classmethod
    def skip_invalid(cls, data: _Any) -> _Any:
        if isinstance(data, dict) and "evidence_cards" in data:
            data["evidence_cards"] = _filter_valid(data["evidence_cards"], EvidenceCard)
        return data


# ---------------------------------------------------------------------------
# Phase functions — scoped to one subquestion
# ---------------------------------------------------------------------------

def _extract_claims(llm: LLMClient, question: str, sources: list[ExtractedSource],
                    subquestion: SubQuestion, errors: list[str],
                    ) -> tuple[list[ExtractedClaim], UsageInfo]:
    """Phase 1: extract claims from this agent's sources."""
    prompt = build_extraction_prompt(question, sources, [subquestion])
    try:
        text, usage = llm.complete(prompt)
    except Exception as exc:
        errors.append(f"LLM call failed in agent[{subquestion.id}] phase1: {exc}")
        return [], UsageInfo()
    try:
        raw = _extract_json_text(text)
        raw_claims = json.loads(raw).get("claims", [])
        raw_count = len(raw_claims) if isinstance(raw_claims, list) else 0
        parsed = parse_json_object(text, _ClaimsResponse)
        valid_count = len(parsed.claims)
        if valid_count < raw_count:
            errors.append(
                f"Agent[{subquestion.id}] phase1: {raw_count - valid_count}/{raw_count} claims dropped"
            )
        return parsed.claims, usage
    except (JSONParseError, json.JSONDecodeError) as exc:
        errors.append(f"Agent[{subquestion.id}] phase1 extraction failed: {exc}")
        return [], UsageInfo()


def _validate_claims(llm: LLMClient, sq_id: str, sq_question: str,
                     claims: list[ExtractedClaim], sources: list[ExtractedSource],
                     errors: list[str],
                     ) -> tuple[list[EvidenceCard], UsageInfo]:
    """Phase 2: cross-validate claims within this agent's sources."""
    if not claims:
        return [], UsageInfo()
    prompt = build_validation_prompt(sq_id, sq_question, claims, sources)
    try:
        text, usage = llm.complete(prompt)
    except Exception as exc:
        errors.append(f"Agent[{sq_id}] phase2 LLM failed: {exc}")
        fallback = [
            EvidenceCard(
                id=c.id, subquestion_id=c.subquestion_id,
                claim=c.claim, source_url=c.source_url,
                source_title=c.source_title, supporting_snippet=c.supporting_snippet,
                content_type=c.content_type,
                corroboration_level="single_source", corroborating_sources=[],
                confidence="low",
            ) for c in claims
        ]
        return fallback, UsageInfo()
    try:
        raw = _extract_json_text(text)
        raw_cards = json.loads(raw).get("evidence_cards", [])
        raw_count = len(raw_cards) if isinstance(raw_cards, list) else 0
        parsed = parse_json_object(text, _EvidenceResponse)
        valid_count = len(parsed.evidence_cards)
        if valid_count < raw_count:
            errors.append(
                f"Agent[{sq_id}] phase2: {raw_count - valid_count}/{raw_count} cards dropped"
            )
        return list(parsed.evidence_cards), usage
    except (JSONParseError, json.JSONDecodeError) as exc:
        errors.append(f"Agent[{sq_id}] phase2 validation failed: {exc}")
        fallback = [
            EvidenceCard(
                id=c.id, subquestion_id=c.subquestion_id,
                claim=c.claim, source_url=c.source_url,
                source_title=c.source_title, supporting_snippet=c.supporting_snippet,
                content_type=c.content_type,
                corroboration_level="single_source", corroborating_sources=[],
                confidence="low",
            ) for c in claims
        ]
        return fallback, UsageInfo()


def _validate_corroboration(card: EvidenceCard, extracted_urls: set[str],
                            content_types: dict[str, str]) -> EvidenceCard:
    """Post-validate: ensure corroboration claims are genuine."""
    valid_sources = [
        url for url in card.corroborating_sources
        if normalize_url(url) in extracted_urls or url in extracted_urls
    ]
    card.corroborating_sources = valid_sources
    if card.corroboration_level == "strongly_corroborated":
        full_text_count = sum(
            1 for url in valid_sources
            if content_types.get(url, "") == "extracted_content"
            or content_types.get(normalize_url(url), "") == "extracted_content"
        )
        if full_text_count < 2:
            card.corroboration_level = "weakly_corroborated"
    if card.corroboration_level == "weakly_corroborated" and not valid_sources:
        card.corroboration_level = "single_source"
    return card


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_subquestion_agent(
    *,
    question: str,
    subquestion: SubQuestion,
    search_client: SearchClient,
    llm: LLMClient,
    results_per_query: int = 5,
    max_sources: int = 3,
) -> AgentResult:
    """Execute search → extract → validate for a single subquestion.

    This is the independent agent unit.  It handles its own search and
    evidence pipeline and returns a self-contained result.  Failures are
    captured in ``result.errors`` rather than propagating.
    """
    errors: list[str] = []
    usage: list[TokenUsage] = []

    # 1. Search
    search_results: list[SearchResult] = []
    queries = subquestion.search_queries or [subquestion.search_query]
    for query in queries:
        try:
            search_results.extend(
                search_client.search(query, subquestion_id=subquestion.id, max_results=results_per_query)
            )
        except Exception as exc:
            errors.append(f"Agent[{subquestion.id}] search failed for '{query}': {exc}")

    if not search_results:
        return AgentResult(subquestion_id=subquestion.id, errors=errors)

    # 2. Deduplicate + select sources
    deduped = _dedupe_results(search_results)
    selected = _select_sources(deduped, max_sources)

    # 3. Extract full text
    sources, content_types = _extract_sources(search_client, subquestion.id, selected, errors)

    # 4. Phase 1: Extract claims
    claims, p1_usage = _extract_claims(llm, question, sources, subquestion, errors)
    usage.append(TokenUsage(
        node=f"agent_{subquestion.id}",
        prompt_tokens=p1_usage.prompt_tokens,
        completion_tokens=p1_usage.completion_tokens,
        estimated_cost=p1_usage.estimated_cost,
    ))

    if not claims:
        return AgentResult(
            subquestion_id=subquestion.id,
            search_results=deduped,
            errors=errors,
            token_usage=usage,
        )

    # 5. Phase 2: Cross-validate
    cards, p2_usage = _validate_claims(
        llm, subquestion.id, subquestion.question, claims, sources, errors,
    )
    usage.append(TokenUsage(
        node=f"agent_{subquestion.id}",
        prompt_tokens=p2_usage.prompt_tokens,
        completion_tokens=p2_usage.completion_tokens,
        estimated_cost=p2_usage.estimated_cost,
    ))

    # 6. Post-validate
    extracted_urls = {normalize_url(s.url) for s in sources}
    valid_urls = {s.url for s in sources} | {normalize_url(s.url) for s in sources}
    cards = [
        c for c in cards
        if c.source_url in valid_urls or normalize_url(c.source_url) in valid_urls
    ]
    cards = [_validate_corroboration(c, extracted_urls, content_types) for c in cards]

    return AgentResult(
        subquestion_id=subquestion.id,
        evidence_cards=cards,
        extracted_claims=claims,
        search_results=deduped,
        errors=errors,
        token_usage=usage,
    )
