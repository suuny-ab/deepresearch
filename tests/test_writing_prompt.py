from deepresearch.prompts.writing import build_writing_prompt
from deepresearch.state import EvidenceCard, SearchResult


def test_writing_prompt_requires_numbered_citations_and_lists_allowed_urls():
    results = [
        SearchResult(subquestion_id="q1", title="Source A", url="https://example.com/a", content="Content A"),
        SearchResult(subquestion_id="q1", title="Source B", url="https://example.com/b", content="Content B"),
    ]

    prompt = build_writing_prompt("AI search", [], results)

    assert "Use numbered citations in the body" in prompt
    assert "Do not put raw URLs in the body" in prompt
    assert "URLs may only appear in the ## Sources section" in prompt
    assert "Every citation number used in the body must be defined in ## Sources" in prompt
    assert "Every source listed in ## Sources must be cited in the body" in prompt
    assert "Only use URLs from the allowed source URL list" in prompt
    assert "Allowed source URLs" in prompt
    assert "https://example.com/a" in prompt
    assert "https://example.com/b" in prompt


def test_writing_prompt_uses_evidence_card_urls_when_provided():
    results = [
        SearchResult(
            subquestion_id="q1",
            title="Raw source",
            url="https://www.example.com/report?utm_source=x",
            content="Content",
        )
    ]
    evidence_cards = [
        EvidenceCard(
            id="e1",
            subquestion_id="q1",
            claim="Claim from normalized evidence.",
            source_url="https://example.com/report",
            source_title="Normalized source",
            supporting_snippet="Claim from normalized evidence.",
            content_type="extracted_content",
            corroboration_level="single_source",
            corroborating_sources=[],
            confidence="high",
        )
    ]

    prompt = build_writing_prompt("AI search", [], results, evidence_cards=evidence_cards)

    assert "https://example.com/report" in prompt
    assert "https://www.example.com/report?utm_source=x" not in prompt


def test_writing_prompt_includes_corroboration_guidance():
    results = [SearchResult(subquestion_id="q1", title="A", url="https://example.com/a", content="Content")]
    evidence_cards = [
        EvidenceCard(
            id="e1",
            subquestion_id="q1",
            claim="Claim.",
            source_url="https://example.com/a",
            source_title="A",
            supporting_snippet="Claim.",
            content_type="extracted_content",
            corroboration_level="single_source",
            corroborating_sources=[],
            confidence="medium",
        )
    ]

    prompt = build_writing_prompt("AI search", [], results, evidence_cards=evidence_cards)

    assert "supported by multiple independent sources" in prompt
    assert "single source" in prompt
