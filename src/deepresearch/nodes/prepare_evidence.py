from collections import Counter, defaultdict

from pydantic import BaseModel

from deepresearch.clients.llm import LLMClient
from deepresearch.clients.tavily import SearchClient
from deepresearch.prompts.evidence import build_validation_prompt
from deepresearch.prompts.extraction import build_extraction_prompt
from deepresearch.state import (
    EvidenceCard, ExtractedClaim, ExtractedSource, ResearchState, SearchResult,
)
from deepresearch.utils.json import JSONParseError, parse_json_object
from deepresearch.utils.urls import extract_domain, normalize_url


class ClaimsResponse(BaseModel):
    claims: list[ExtractedClaim]


class EvidenceResponse(BaseModel):
    evidence_cards: list[EvidenceCard]


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


def _is_english_domain(url: str) -> bool:
    domain = extract_domain(url)
    if not domain:
        return False
    return not any(domain.endswith(tld) for tld in [".cn", ".com.cn", ".org.cn"])


def _select_sources(results, max_sources, has_english_query=False):
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
    if has_english_query and selected and not any(_is_english_domain(s.url) for s in selected):
        for candidate in candidates:
            if candidate not in selected and _is_english_domain(candidate.url):
                if len(selected) >= max_sources:
                    selected.pop()
                selected.append(candidate)
                break
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
        return fallback, fallback
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
        return parse_json_object(llm.complete(prompt), ClaimsResponse).claims
    except JSONParseError as exc:
        errors.append(f"Phase 1 extraction failed: {exc}")
        return []


def _phase2_validate(llm, sq_id, sq_question, claims, sources, errors):
    if not claims:
        return []
    prompt = build_validation_prompt(sq_id, sq_question, claims, sources)
    try:
        return list(parse_json_object(llm.complete(prompt), EvidenceResponse).evidence_cards)
    except JSONParseError as exc:
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


def _build_metrics(raw, deduped, extracted_sources, evidence_cards):
    return {
        "raw_search_results": len(raw),
        "deduped_sources": len(deduped),
        "duplicates_removed": len(raw) - len(deduped),
        "extracted_sources": len(extracted_sources),
        "evidence_cards": len(evidence_cards),
        "corroboration": dict(Counter(c.corroboration_level for c in evidence_cards)),
    }


def _run_assertions(claims, sources, cards):
    results = []
    for source in sources:
        count = len([c for c in claims if c.source_url == source.url])
        if count == 0:
            results.append(f"[FAIL] Source {source.url} contributed 0 claims")
    if cards:
        strong_weak = sum(1 for c in cards if c.corroboration_level in ("strongly_corroborated", "weakly_corroborated"))
        rate = strong_weak / len(cards)
        if rate < 0.6:
            results.append(f"[FAIL] Corroboration rate {rate:.0%} below 60% threshold")
    if claims:
        sq_counts = defaultdict(int)
        for c in claims:
            sq_counts[c.subquestion_id] += 1
        if sq_counts:
            mx, mn = max(sq_counts.values()), min(sq_counts.values())
            if mn > 0 and mx > mn * 3:
                results.append(f"[FAIL] Claims distribution skewed: {dict(sq_counts)}")
    return results


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

        assertion_results = _run_assertions(claims, extracted_sources, all_cards)
        errors.extend(assertion_results)

        evidence_metrics = _build_metrics(raw_results, deduped, extracted_sources, all_cards)
        return {
            **state,
            "search_results": deduped,
            "extracted_claims": claims,
            "evidence_cards": all_cards,
            "evidence_metrics": evidence_metrics,
            "errors": errors,
        }

    return prepare_evidence
