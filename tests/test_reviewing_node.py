from tests.conftest import FakeLLMClient

from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.state import EvidenceCard, SubQuestion


class _FailingLLMClient:
    """LLM client that raises on every call, simulating a network or API error."""

    def complete(self, prompt: str) -> str:
        raise RuntimeError("Simulated LLM failure")


def test_review_report_uses_evidence_cards():
    llm = FakeLLMClient([
        '{"passed":true,"score":86,"issues":[],"suggestions":[]}'
    ])
    node = make_review_report_node(llm)

    evidence_cards = [
        EvidenceCard(
            id="e1", subquestion_id="q1",
            claim="RAG is important.",
            source_url="https://example.com/report",
            source_title="Report",
            supporting_snippet="RAG is important.",
            content_type="extracted_content",
            corroboration_level="strongly_corroborated",
            corroborating_sources=["https://other1.example/a", "https://other2.example/b"],
            confidence="high",
        ),
    ]

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "report_markdown": "# AI Search\n\nRAG is important.[1]\n\n## Sources\n\n[1] https://example.com/report",
        "search_results": [],
        "evidence_cards": evidence_cards,
        "errors": [],
    })

    assert result["review"].score == 86
    assert result["review"].passed is True


def test_review_prompt_contains_rubric():
    from deepresearch.prompts.reviewing import build_reviewing_prompt
    from deepresearch.state import EvidenceCard

    cards = [
        EvidenceCard(
            id="e1", subquestion_id="q1", claim="Claim.",
            source_url="https://example.com/a", source_title="A",
            supporting_snippet="Claim.", content_type="extracted_content",
            corroboration_level="weakly_corroborated",
            corroborating_sources=["https://example.com/b"],
            confidence="high",
        ),
    ]

    prompt = build_reviewing_prompt("AI search", "# Report", cards)

    assert ("rubric" in prompt.lower() or "来源支撑" in prompt or "source support" in prompt.lower() or "Source Support" in prompt)
    assert ("30%" in prompt)
    assert ("20%" in prompt)
    assert "https://example.com/a" in prompt


def test_review_report_does_not_set_feedback_on_llm_error():
    """When the LLM call fails, return score=0 but do not set review_feedback."""
    llm = _FailingLLMClient()
    node = make_review_report_node(llm)

    result = node({
        "question": "AI search",
        "report_markdown": "# Report\n\nContent.[1]\n\n## Sources\n\n[1] https://example.com",
        "evidence_cards": [],
        "errors": [],
    })

    assert result["review"].score == 0
    assert result["review"].issues == ["LLM call failed"]
    assert result.get("review_feedback") is None
    assert any("LLM call failed" in e for e in result["errors"])


def test_review_report_does_not_set_feedback_on_json_parse_error():
    """When JSON parsing fails, return score=0 but do not set review_feedback."""
    llm = FakeLLMClient(["not valid json {{{"])
    node = make_review_report_node(llm)

    result = node({
        "question": "AI search",
        "report_markdown": "# Report\n\nContent.[1]\n\n## Sources\n\n[1] https://example.com",
        "evidence_cards": [],
        "errors": [],
    })

    assert result["review"].score == 0
    assert result["review"].issues == ["Review parsing failed"]
    assert result.get("review_feedback") is None
    assert any("Review JSON parse failed" in e for e in result["errors"])


def test_review_report_does_not_set_feedback_when_already_rewritten():
    """When score < 70 but review_rewritten=True, do not set review_feedback."""
    llm = FakeLLMClient([
        '{"passed":false,"score":50,"issues":["Too brief"],"suggestions":["Add details"]}',
    ])
    node = make_review_report_node(llm)

    result = node({
        "question": "AI search",
        "report_markdown": "# Report\n\nContent.[1]\n\n## Sources\n\n[1] https://example.com",
        "evidence_cards": [],
        "errors": [],
        "review_rewritten": True,
    })

    assert result["review"].score == 50
    assert result["review"].issues == ["Too brief"]
    assert result.get("review_feedback") is None
