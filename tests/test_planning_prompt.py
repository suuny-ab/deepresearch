from deepresearch.prompts.planning import build_planning_prompt


def test_planning_prompt_requests_multiple_search_queries():
    prompt = build_planning_prompt("AI 搜索趋势", max_subquestions=5)

    assert "search_queries" in prompt
    assert "2" in prompt
    assert "3" in prompt
    assert "中文" in prompt or "Chinese" in prompt
    assert "English" in prompt or "英文" in prompt


def test_planning_prompt_uses_valid_range_for_small_max_subquestions():
    prompt_one = build_planning_prompt("AI 搜索趋势", max_subquestions=1)
    prompt_two = build_planning_prompt("AI 搜索趋势", max_subquestions=2)

    assert "3 to 1" not in prompt_one
    assert "3 to 2" not in prompt_two
    assert "up to 1" in prompt_one
    assert "up to 2" in prompt_two
