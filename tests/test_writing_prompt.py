from deepresearch.prompts.writing import build_writing_prompt
from deepresearch.state import SearchResult


def test_writing_prompt_requires_numbered_citations_and_lists_allowed_urls():
    results = [
        SearchResult(subquestion_id="q1", title="Source A", url="https://example.com/a", content="Content A"),
        SearchResult(subquestion_id="q1", title="Source B", url="https://example.com/b", content="Content B"),
    ]

    prompt = build_writing_prompt("AI search", [], [], results)

    assert "Use numbered citations in the body" in prompt
    assert "Do not put raw URLs in the body" in prompt
    assert "URLs may only appear in the ## Sources section" in prompt
    assert "Every citation number used in the body must be defined in ## Sources" in prompt
    assert "Every source listed in ## Sources must be cited in the body" in prompt
    assert "Only use URLs from the allowed source URL list" in prompt
    assert "Allowed source URLs" in prompt
    assert "https://example.com/a" in prompt
    assert "https://example.com/b" in prompt
