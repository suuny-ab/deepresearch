from collections import Counter, defaultdict

from pydantic import BaseModel

from deepresearch.clients.llm import LLMClient
from deepresearch.clients.tavily import SearchClient
from deepresearch.prompts.evidence import build_evidence_prompt
from deepresearch.state import EvidenceCard, ExtractedSource, ResearchState, SearchResult
from deepresearch.utils.json import JSONParseError, parse_json_object
from deepresearch.utils.urls import extract_domain, normalize_url


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
    return not any(
        domain.endswith(tld) for tld in [".cn", ".com.cn", ".org.cn"]
    )


def _select_sources(
    results: list[SearchResult],
    max_sources: int,
    has_english_query: bool = False,
) -> list[SearchResult]:
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

    if has_english_query and selected and not any(
        _is_english_domain(s.url) for s in selected
    ):
        for candidate in candidates:
            if candidate not in selected and _is_english_domain(candidate.url):
                if len(selected) >= max_sources:
                    selected.pop()
                selected.append(candidate)
                break

    return selected


def _select_by_subquestion(
    results: list[SearchResult],
    max_sources_per_subquestion: int,
) -> dict[str, list[SearchResult]]:
    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    for result in results:
        grouped[result.subquestion_id].append(result)

    selected: dict[str, list[SearchResult]] = {}
    for subquestion_id, items in grouped.items():
        selected[subquestion_id] = _select_sources(
            items, max_sources_per_subquestion
        )
    return selected


def _fallback_extracted_sources(
    selected: list[SearchResult],
) -> list[ExtractedSource]:
    return [
        ExtractedSource(
            subquestion_id=result.subquestion_id,
            url=result.url,
            title=result.title,
            raw_content=result.content,
        )
        for result in selected
        if result.url and result.content
    ]


def _extract_sources_for_subquestion(
    search_client: SearchClient,
    subquestion_id: str,
    selected: list[SearchResult],
    errors: list[str],
) -> tuple[list[ExtractedSource], list[ExtractedSource]]:
    """Returns (extracted_sources, fallback_sources)."""
    urls = [result.url for result in selected]
    try:
        extracted = search_client.extract(urls, subquestion_id=subquestion_id)
    except Exception as exc:
        errors.append(f"Evidence extract failed for {subquestion_id}: {exc}")
        fallback = _fallback_extracted_sources(selected)
        return fallback, fallback

    extracted_keys = {normalize_url(source.url) for source in extracted}
    missing = [
        result
        for result in selected
        if normalize_url(result.url) not in extracted_keys
    ]
    fallback = _fallback_extracted_sources(missing) if missing else []
    return extracted, fallback


def _valid_source_urls(sources: list[ExtractedSource]) -> set[str]:
    urls = set()
    for source in sources:
        urls.add(source.url)
        urls.add(normalize_url(source.url))
    return urls


def _drop_invalid_cards(
    cards: list[EvidenceCard],
    sources: list[ExtractedSource],
    errors: list[str],
) -> list[EvidenceCard]:
    valid_urls = _valid_source_urls(sources)
    valid_cards: list[EvidenceCard] = []
    for card in cards:
        if (
            card.source_url not in valid_urls
            and normalize_url(card.source_url) not in valid_urls
        ):
            errors.append(
                f"EvidenceCard {card.id} has invalid source_url: {card.source_url}"
            )
            continue
        valid_cards.append(card)
    return valid_cards


def _validate_corroboration(
    card: EvidenceCard,
    extracted_urls: set[str],
    extracted_content_types: dict[str, str],
) -> EvidenceCard:
    # Check 1: corroborating URLs must exist in extracted sources
    valid_sources = [
        url
        for url in card.corroborating_sources
        if normalize_url(url) in extracted_urls or url in extracted_urls
    ]
    card.corroborating_sources = valid_sources

    # Check 2: corroborating sources must be from different domains
    main_domain = extract_domain(card.source_url)
    distinct_sources = [
        url
        for url in card.corroborating_sources
        if extract_domain(url) != main_domain
    ]
    card.corroborating_sources = distinct_sources

    # Check 3: strongly_corroborated needs >= 2 full-text corroborating sources
    if card.corroboration_level == "strongly_corroborated":
        full_text_count = sum(
            1
            for url in distinct_sources
            if extracted_content_types.get(url, "")
            == "extracted_content"
            or extracted_content_types.get(normalize_url(url), "")
            == "extracted_content"
        )
        if full_text_count < 2:
            card.corroboration_level = "weakly_corroborated"

    # Check 4: weakly_corroborated needs >= 1 valid corroborating source
    if card.corroboration_level == "weakly_corroborated" and not distinct_sources:
        card.corroboration_level = "single_source"

    return card


def _build_metrics(
    raw: list[SearchResult],
    deduped: list[SearchResult],
    extracted_sources: list[ExtractedSource],
    evidence_cards: list[EvidenceCard],
) -> dict[str, object]:
    return {
        "raw_search_results": len(raw),
        "deduped_sources": len(deduped),
        "duplicates_removed": len(raw) - len(deduped),
        "extracted_sources": len(extracted_sources),
        "evidence_cards": len(evidence_cards),
        "corroboration": dict(
            Counter(card.corroboration_level for card in evidence_cards)
        ),
    }


def make_prepare_evidence_node(
    search_client: SearchClient,
    llm: LLMClient,
    max_sources_per_subquestion: int,
):
    def prepare_evidence(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        raw_results = list(state.get("search_results", []))
        deduped = _dedupe_results(raw_results)
        selected_by_subquestion = _select_by_subquestion(
            deduped, max_sources_per_subquestion
        )

        extracted_sources: list[ExtractedSource] = []
        extracted_content_types: dict[str, str] = {}
        for subquestion_id, selected in selected_by_subquestion.items():
            success_sources, fallback_sources = _extract_sources_for_subquestion(
                search_client, subquestion_id, selected, errors
            )
            for src in success_sources:
                key = normalize_url(src.url)
                extracted_content_types[key] = "extracted_content"
                extracted_sources.append(src)
            for src in fallback_sources:
                key = normalize_url(src.url)
                if key not in extracted_content_types:
                    extracted_content_types[key] = "search_content"
                    extracted_sources.append(src)

        prompt = build_evidence_prompt(
            state.get("question", ""), extracted_sources
        )
        try:
            parsed = parse_json_object(llm.complete(prompt), EvidenceResponse)
            evidence_cards = _drop_invalid_cards(
                parsed.evidence_cards, extracted_sources, errors
            )
        except JSONParseError as exc:
            errors.append(f"Evidence JSON parse failed: {exc}")
            evidence_cards = []

        # Post-validate corroboration signals
        extracted_urls = {normalize_url(s.url) for s in extracted_sources}
        evidence_cards = [
            _validate_corroboration(card, extracted_urls, extracted_content_types)
            for card in evidence_cards
        ]

        evidence_metrics = _build_metrics(
            raw_results, deduped, extracted_sources, evidence_cards
        )
        return {
            **state,
            "search_results": deduped,
            "evidence_cards": evidence_cards,
            "evidence_metrics": evidence_metrics,
            "errors": errors,
        }

    return prepare_evidence
