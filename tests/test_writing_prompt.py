from deepresearch.prompts.writing import build_writing_prompt


def test_writing_prompt_requires_numbered_citations():
    prompt = build_writing_prompt("AI search", [], [], [])

    assert "Use numbered citations in the body" in prompt
    assert "[1]" in prompt
    assert "Do not put raw URLs in the body" in prompt
    assert "URLs may only appear in the ## Sources section" in prompt
    assert "Every citation number used in the body must be defined in ## Sources" in prompt
    assert "Every source listed in ## Sources must be cited in the body" in prompt
    assert "Only use URLs from the allowed source URL list" in prompt
