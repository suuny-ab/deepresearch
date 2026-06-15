import json
from collections import defaultdict

from typing import Any
from pydantic import BaseModel, model_validator

from deepresearch.prompts.evidence import build_validation_prompt
from deepresearch.prompts.extraction import build_extraction_prompt
from deepresearch.state import (
    EvidenceCard, ExtractedClaim, ExtractedSource, ResearchState, SearchResult,
)
from deepresearch.utils.json import JSONParseError, _extract_json_text, parse_json_object
from deepresearch.utils.urls import extract_domain, normalize_url


def _filter_valid_items(items: list[dict], model_cls: type) -> list[dict]:
    """Return only items that pass *model_cls.model_validate()*."""
    return [item for item in items if _is_valid(item, model_cls)]


def _is_valid(data: dict, model_cls: type) -> bool:
    try:
        model_cls.model_validate(data)
        return True
    except Exception:
        return False


class ClaimsResponse(BaseModel):
    claims: list[ExtractedClaim]

    @model_validator(mode="before")
    @classmethod
    def skip_invalid_claims(cls, data: Any) -> Any:
        if isinstance(data, dict) and "claims" in data:
            data["claims"] = _filter_valid_items(data["claims"], ExtractedClaim)
        return data


class EvidenceResponse(BaseModel):
    evidence_cards: list[EvidenceCard]

    @model_validator(mode="before")
    @classmethod
    def skip_invalid_cards(cls, data: Any) -> Any:
        if isinstance(data, dict) and "evidence_cards" in data:
            data["evidence_cards"] = _filter_valid_items(data["evidence_cards"], EvidenceCard)
        return data


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


def _select_sources(results, max_sources):
    candidates = sorted(results, key=lambda r: r.score or 0, reverse=True)
    selected = []
    selected_domains = set()
    for candidate in candidates:
        if len(selected) >= max_sources:
            break
        domain = extract_domain(candidate.url)
        if domain and domain not in selected_domains:
            selected.append(candidate)
            selected_domains.add(domain)
    return selected


def _select_by_subquestion(results, max_sources_per_subquestion):
    grouped = defaultdict(list)
    for result in results:
        grouped[result.subquestion_id].append(result)
    selected = {}
    for sq_id, items in grouped.items():
        selected[sq_id] = _select_sources(items, max_sources_per_subquestion)
    return selected


def _fallback_extracted_sources(selected):
    return [
        ExtractedSource(subquestion_id=r.subquestion_id, url=r.url, title=r.title, raw_content=r.content)
        for r in selected if r.url and r.content
    ]


def _extract_sources_for_subquestion(search_client, subquestion_id, selected, errors):
    urls = [r.url for r in selected]
    try:
        extracted = search_client.extract(urls, subquestion_id=subquestion_id)
    except Exception as exc:
        errors.append(f"Evidence extract failed for {subquestion_id}: {exc}")
        fallback = _fallback_extracted_sources(selected)
        return [], fallback
    extracted_keys = {normalize_url(s.url) for s in extracted}
    missing = [r for r in selected if normalize_url(r.url) not in extracted_keys]
    fallback = _fallback_extracted_sources(missing) if missing else []
    return extracted, fallback


def _valid_source_urls(sources):
    urls = set()
    for s in sources:
        urls.add(s.url)
        urls.add(normalize_url(s.url))
    return urls


def _drop_invalid_cards(cards, sources, errors):
    valid_urls = _valid_source_urls(sources)
    valid = []
    for card in cards:
        if card.source_url not in valid_urls and normalize_url(card.source_url) not in valid_urls:
            errors.append(f"EvidenceCard {card.id} has invalid source_url: {card.source_url}")
            continue
        valid.append(card)
    return valid


def _validate_corroboration(card, extracted_urls, extracted_content_types):
    valid_sources = [url for url in card.corroborating_sources if normalize_url(url) in extracted_urls or url in extracted_urls]
    card.corroborating_sources = valid_sources
    if card.corroboration_level == "strongly_corroborated":
        full_text_count = sum(1 for url in valid_sources
            if extracted_content_types.get(url, "") == "extracted_content"
            or extracted_content_types.get(normalize_url(url), "") == "extracted_content")
        if full_text_count < 2:
            card.corroboration_level = "weakly_corroborated"
    if card.corroboration_level == "weakly_corroborated" and not valid_sources:
        card.corroboration_level = "single_source"
    return card


def _phase1_extract(llm, question, sources, subquestions, errors):
    prompt = build_extraction_prompt(question, sources, subquestions)
    try:
        text = llm.complete(prompt)
    except Exception as exc:
        errors.append(f"LLM call failed in phase1_extract: {exc}")
        return []
    try:
        raw = _extract_json_text(text)
        raw_claims = json.loads(raw).get("claims", [])
        raw_count = len(raw_claims) if isinstance(raw_claims, list) else 0
        parsed = parse_json_object(text, ClaimsResponse)
        valid_count = len(parsed.claims)
        if valid_count < raw_count:
            errors.append(
                f"Phase 1 extraction: {raw_count - valid_count}/{raw_count} claims "
                f"dropped due to validation errors (e.g. missing or misspelled fields)"
            )
        return parsed.claims
    except (JSONParseError, json.JSONDecodeError) as exc:
        errors.append(f"Phase 1 extraction failed: {exc}")
        return []


def _phase2_validate(llm, sq_id, sq_question, claims, sources, errors):
    if not claims:
        return []
    prompt = build_validation_prompt(sq_id, sq_question, claims, sources)
    try:
        text = llm.complete(prompt)
    except Exception as exc:
        errors.append(f"LLM call failed in phase2_validate for {sq_id}: {exc}")
        return [
            EvidenceCard(
                id=c.id, subquestion_id=c.subquestion_id,
                claim=c.claim, source_url=c.source_url,
                source_title=c.source_title, supporting_snippet=c.supporting_snippet,
                content_type=c.content_type,
                corroboration_level="single_source", corroborating_sources=[],
                confidence="low",
            ) for c in claims
        ]
    try:
        raw = _extract_json_text(text)
        raw_cards = json.loads(raw).get("evidence_cards", [])
        raw_count = len(raw_cards) if isinstance(raw_cards, list) else 0
        parsed = parse_json_object(text, EvidenceResponse)
        valid_count = len(parsed.evidence_cards)
        if valid_count < raw_count:
            errors.append(
                f"Phase 2 validation [{sq_id}]: {raw_count - valid_count}/{raw_count} cards "
                f"dropped due to validation errors"
            )
        return list(parsed.evidence_cards)
    except (JSONParseError, json.JSONDecodeError) as exc:
        errors.append(f"Phase 2 validation failed for {sq_id}: {exc}")
        return [
            EvidenceCard(
                id=c.id, subquestion_id=c.subquestion_id,
                claim=c.claim, source_url=c.source_url,
                source_title=c.source_title, supporting_snippet=c.supporting_snippet,
                content_type=c.content_type,
                corroboration_level="single_source", corroborating_sources=[],
                confidence="low",
            ) for c in claims
        ]


def make_prepare_evidence_node(search_client, llm, max_sources_per_subquestion):
    def prepare_evidence(state):
        errors = list(state.get("errors", []))
        raw_results = list(state.get("search_results", []))
        subquestions = state.get("subquestions", [])
        question = state.get("question", "")

        deduped = _dedupe_results(raw_results)
        selected_by_sq = _select_by_subquestion(deduped, max_sources_per_subquestion)

        extracted_sources = []
        extracted_content_types = {}
        for sq_id, selected in selected_by_sq.items():
            success, fallback = _extract_sources_for_subquestion(search_client, sq_id, selected, errors)
            for src in success:
                extracted_content_types[normalize_url(src.url)] = "extracted_content"
                extracted_sources.append(src)
            for src in fallback:
                key = normalize_url(src.url)
                if key not in extracted_content_types:
                    extracted_content_types[key] = "search_content"
                    extracted_sources.append(src)

        # Phase 1: Extract claims (1 LLM call)
        claims = _phase1_extract(llm, question, extracted_sources, subquestions, errors)

        # Phase 2: Validate per subquestion (N LLM calls)
        sq_map = {sq.id: sq.question for sq in subquestions}
        sources_by_sq = defaultdict(list)
        for src in extracted_sources:
            sources_by_sq[src.subquestion_id].append(src)

        all_cards = []
        for sq_id, sq_sources in sources_by_sq.items():
            sq_claims = [c for c in claims if c.subquestion_id == sq_id]
            sq_question = sq_map.get(sq_id, sq_id)
            sq_cards = _phase2_validate(llm, sq_id, sq_question, sq_claims, sq_sources, errors)
            all_cards.extend(sq_cards)

        # Post-validate
        extracted_urls = {normalize_url(s.url) for s in extracted_sources}
        all_cards = _drop_invalid_cards(all_cards, extracted_sources, errors)
        all_cards = [_validate_corroboration(c, extracted_urls, extracted_content_types) for c in all_cards]

        return {
            **state,
            "search_results": deduped,
            "extracted_claims": claims,
            "evidence_cards": all_cards,
            "errors": errors,
        }

    return prepare_evidence
