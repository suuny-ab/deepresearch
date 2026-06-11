from collections import Counter, defaultdict

from pydantic import BaseModel

from deepresearch.clients.llm import LLMClient
from deepresearch.clients.tavily import SearchClient
from deepresearch.prompts.evidence import build_evidence_prompt
from deepresearch.source_quality import classify_source
from deepresearch.state import EvidenceCard, ExtractedSource, ResearchState, SearchResult
from deepresearch.utils.json import JSONParseError, parse_json_object
from deepresearch.utils.urls import normalize_url


class EvidenceResponse(BaseModel):
    evidence_cards: list[EvidenceCard]


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[str] = set()
    deduped: list[SearchResult] = []
    for result in results:
        key = normalize_url(result.url)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _apply_quality(results: list[SearchResult]) -> list[SearchResult]:
    for result in results:
        quality = classify_source(result)
        result.source_type = quality.source_type
        result.source_quality_score = quality.score
        result.source_quality_reason = quality.reason
    return results


def _select_by_subquestion(results: list[SearchResult], max_sources_per_subquestion: int) -> dict[str, list[SearchResult]]:
    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    for result in results:
        grouped[result.subquestion_id].append(result)

    selected: dict[str, list[SearchResult]] = {}
    for subquestion_id, items in grouped.items():
        ranked = sorted(items, key=lambda item: item.source_quality_score, reverse=True)
        selected[subquestion_id] = ranked[:max_sources_per_subquestion]
    return selected


def _copy_quality(source: ExtractedSource, selected_by_url: dict[str, SearchResult]) -> ExtractedSource:
    result = selected_by_url.get(normalize_url(source.url))
    if result is None:
        return source
    source.source_type = result.source_type
    source.source_quality_score = result.source_quality_score
    source.source_quality_reason = result.source_quality_reason
    if not source.title:
        source.title = result.title
    return source


def _fallback_extracted_sources(selected: list[SearchResult]) -> list[ExtractedSource]:
    return [
        ExtractedSource(
            subquestion_id=result.subquestion_id,
            url=result.url,
            title=result.title,
            raw_content=result.content,
            source_type=result.source_type,
            source_quality_score=result.source_quality_score,
            source_quality_reason=result.source_quality_reason,
        )
        for result in selected
        if result.url and result.content
    ]


def _extract_sources_for_subquestion(search_client: SearchClient, subquestion_id: str, selected: list[SearchResult], errors: list[str]) -> list[ExtractedSource]:
    selected_by_url = {normalize_url(result.url): result for result in selected}
    urls = [result.url for result in selected]
    try:
        extracted = search_client.extract(urls, subquestion_id=subquestion_id)
    except Exception as exc:
        errors.append(f"Evidence extract failed for {subquestion_id}: {exc}")
        return _fallback_extracted_sources(selected)

    copied = [_copy_quality(source, selected_by_url) for source in extracted]
    extracted_keys = {normalize_url(source.url) for source in copied}
    missing = [result for result in selected if normalize_url(result.url) not in extracted_keys]
    if missing:
        copied.extend(_fallback_extracted_sources(missing))
    return copied


def _valid_source_urls(sources: list[ExtractedSource]) -> set[str]:
    urls = set()
    for source in sources:
        urls.add(source.url)
        urls.add(normalize_url(source.url))
    return urls


def _drop_invalid_cards(cards: list[EvidenceCard], sources: list[ExtractedSource], errors: list[str]) -> list[EvidenceCard]:
    valid_urls = _valid_source_urls(sources)
    valid_cards: list[EvidenceCard] = []
    for card in cards:
        if card.source_url not in valid_urls and normalize_url(card.source_url) not in valid_urls:
            errors.append(f"EvidenceCard {card.id} has invalid source_url: {card.source_url}")
            continue
        valid_cards.append(card)
    return valid_cards


def _build_metrics(raw: list[SearchResult], deduped: list[SearchResult], extracted_sources: list[ExtractedSource], evidence_cards: list[EvidenceCard]) -> dict[str, object]:
    return {
        "raw_search_results": len(raw),
        "deduped_sources": len(deduped),
        "duplicates_removed": len(raw) - len(deduped),
        "extracted_sources": len(extracted_sources),
        "evidence_cards": len(evidence_cards),
        "source_quality": dict(Counter(result.source_type for result in deduped)),
        "evidence_reliability": dict(Counter(card.evidence_reliability for card in evidence_cards)),
    }


def make_prepare_evidence_node(search_client: SearchClient, llm: LLMClient, max_sources_per_subquestion: int):
    def prepare_evidence(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        raw_results = list(state.get("search_results", []))
        deduped = _apply_quality(_dedupe_results(raw_results))
        selected_by_subquestion = _select_by_subquestion(deduped, max_sources_per_subquestion)

        extracted_sources: list[ExtractedSource] = []
        for subquestion_id, selected in selected_by_subquestion.items():
            extracted_sources.extend(_extract_sources_for_subquestion(search_client, subquestion_id, selected, errors))

        prompt = build_evidence_prompt(state.get("question", ""), extracted_sources)
        try:
            parsed = parse_json_object(llm.complete(prompt), EvidenceResponse)
            evidence_cards = _drop_invalid_cards(parsed.evidence_cards, extracted_sources, errors)
        except JSONParseError as exc:
            errors.append(f"Evidence JSON parse failed: {exc}")
            evidence_cards = []

        evidence_metrics = _build_metrics(raw_results, deduped, extracted_sources, evidence_cards)
        return {
            **state,
            "search_results": deduped,
            "extracted_sources": extracted_sources,
            "evidence_cards": evidence_cards,
            "evidence_metrics": evidence_metrics,
            "errors": errors,
        }

    return prepare_evidence
