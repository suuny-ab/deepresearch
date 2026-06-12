from tests.conftest import FakeLLMClient

from deepresearch.nodes.writing import make_write_report_node
from deepresearch.state import EvidenceCard, SearchResult, SubQuestion


VALID_NUMBERED_REPORT = "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com"


def _state() -> dict:
    return {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "errors": [],
    }


def test_write_report_uses_llm_markdown_with_numbered_citations():
    llm = FakeLLMClient([VALID_NUMBERED_REPORT])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_markdown"] == VALID_NUMBERED_REPORT
    assert result["report_status"] == "success"


def test_write_report_accepts_numbered_citations_with_sources_mapping():
    llm = FakeLLMClient(["# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com"])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "success"
    assert result["rewrite_attempted"] is False
    assert result["validation_attempts"] == 1
    assert result["validation_failures"] == []


def test_write_report_allows_url_only_in_sources_when_body_uses_numbered_citation():
    llm = FakeLLMClient([
        "# AI Search\n\n"
        "AI search systems combine retrieval and synthesis into user-facing answers.[1]\n\n"
        "## Sources\n\n"
        "[1] https://example.com"
    ])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "success"
    assert "AI search systems combine retrieval" in result["report_markdown"]
    assert "https://example.com" in result["report_markdown"]


def test_write_report_prefers_evidence_card_urls_over_raw_search_result_urls():
    llm = FakeLLMClient([
        "# AI Search\n\nAI search cites normalized evidence.[1]\n\n## Sources\n\n[1] https://example.com/report"
    ])
    node = make_write_report_node(llm)
    state = {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [
            SearchResult(
                subquestion_id="q1",
                title="Raw source",
                url="https://www.example.com/report?utm_source=x",
                content="Content",
            )
        ],
        "evidence_cards": [
            EvidenceCard(
                id="e1",
                subquestion_id="q1",
                claim="AI search cites normalized evidence.",
                source_url="https://example.com/report",
                source_title="Normalized source",
                supporting_snippet="AI search cites normalized evidence.",
                content_type="extracted_content",
                corroboration_level="single_source",
                corroborating_sources=[],
                confidence="high",
            )
        ],
        "errors": [],
    }

    result = node(state)
    llm = FakeLLMClient([
        "# AI Search\n\nAI search cites normalized evidence.[1]\n\n## Sources\n\n[1] https://example.com/report"
    ])
    node = make_write_report_node(llm)
    state = {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [
            SearchResult(
                subquestion_id="q1",
                title="Raw source",
                url="https://www.example.com/report?utm_source=x",
                content="Content",
            )
        ],
        "evidence_cards": [
            EvidenceCard(
                id="e1",
                subquestion_id="q1",
                claim="AI search cites normalized evidence.",
                source_url="https://example.com/report",
                source_title="Normalized source",
                supporting_snippet="AI search cites normalized evidence.",
                content_type="extracted_content",
                corroboration_level="single_source",
                corroborating_sources=[],
                confidence="high",
            )
        ],
        "errors": [],
    }

    node(state)

    assert "https://example.com/report" in llm.prompts[0]
    assert "https://www.example.com/report?utm_source=x" not in llm.prompts[0]


def test_write_report_replaces_report_when_sources_section_missing():
    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery.[1]",
        "# AI Search\n\nAI search is changing discovery.[1]",
    ])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "failed_validation"
    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "报告缺少 ## Sources 来源部分" in result["report_markdown"]
    assert "AI search is changing discovery" not in result["report_markdown"]
    assert "https://example.com" in result["report_markdown"]
    assert any("missing_sources_section" in error for error in result["errors"])


def test_write_report_replaces_report_when_body_has_no_numbered_citations():
    llm = FakeLLMClient([
        "# AI Search\n\nThis report makes unsupported claims without citations.\n\n## Sources\n\n[1] https://example.com",
        "# AI Search\n\nThis report still makes unsupported claims without citations.\n\n## Sources\n\n[1] https://example.com",
    ])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "failed_validation"
    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "正文没有使用编号引用" in result["report_markdown"]
    assert "This report makes unsupported claims" not in result["report_markdown"]
    assert "https://example.com" in result["report_markdown"]
    assert any("missing_body_citations" in error for error in result["errors"])


def test_write_report_replaces_report_when_source_url_is_not_allowed():
    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://invented.example/source",
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://invented.example/source",
    ])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "failed_validation"
    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "Sources 中存在未被搜索结果支持的 URL" in result["report_markdown"]
    assert "https://invented.example/source" in result["report_markdown"]
    assert "https://example.com" in result["report_markdown"]
    assert any("invalid_source_urls" in error for error in result["errors"])
    assert any("https://invented.example/source" in error for error in result["errors"])


def test_write_report_replaces_report_when_sources_are_unused():
    llm = FakeLLMClient([
        "# AI Search\n\n"
        "AI search is changing discovery.[1]\n\n"
        "## Sources\n\n"
        "[1] https://example.com\n"
        "[2] https://example.com/unused",
        "# AI Search\n\n"
        "AI search is changing discovery.[1]\n\n"
        "## Sources\n\n"
        "[1] https://example.com\n"
        "[2] https://example.com/unused",
    ])
    node = make_write_report_node(llm)
    state = _state()
    state["search_results"].append(
        SearchResult(subquestion_id="q1", title="Unused", url="https://example.com/unused", content="Unused content")
    )

    result = node(state)

    assert result["report_status"] == "failed_validation"
    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "Sources 中存在未被正文引用的编号" in result["report_markdown"]
    assert "https://example.com/unused" in result["report_markdown"]
    assert any("unused_sources" in error for error in result["errors"])


def test_write_report_retries_unused_source_number_once_then_fails():
    llm = FakeLLMClient([
        "# AI Search\n\n"
        "AI search is changing discovery.[1]\n\n"
        "## Sources\n\n"
        "[1] https://example.com\n"
        "[2] https://example.com/extra",
        "# AI Search\n\n"
        "AI search is changing discovery.[1]\n\n"
        "## Sources\n\n"
        "[1] https://example.com\n"
        "[2] https://example.com/extra",
    ])
    node = make_write_report_node(llm)
    state = _state()
    state["search_results"].append(
        SearchResult(subquestion_id="q1", title="Extra", url="https://example.com/extra", content="Content")
    )

    result = node(state)

    assert result["report_status"] == "failed_validation"
    assert result["rewrite_attempted"] is True
    assert result["validation_attempts"] == 2
    assert result["validation_failures"][0]["reason"] == "unused_sources"


def test_write_report_replaces_report_when_body_contains_bare_url():
    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery https://example.com [1]\n\n## Sources\n\n[1] https://example.com",
        "# AI Search\n\nAI search is changing discovery https://example.com [1]\n\n## Sources\n\n[1] https://example.com",
    ])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "failed_validation"
    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "正文中出现裸 URL" in result["report_markdown"]
    assert any("bare_urls_in_body" in error for error in result["errors"])


def test_write_report_retries_after_validation_failure():
    llm = FakeLLMClient([
        "# AI Search\n\nThis report makes unsupported claims without citations.\n\n## Sources\n\n[1] https://example.com",
        VALID_NUMBERED_REPORT,
    ])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "success"
    assert result["rewrite_attempted"] is True
    assert result["validation_attempts"] == 2
    assert len(llm.prompts) == 2


def test_write_report_sets_failed_validation_status_when_inputs_are_missing():
    llm = FakeLLMClient([])
    node = make_write_report_node(llm)

    result = node({"question": "AI search", "search_results": [], "errors": []})

    assert result["report_status"] == "failed_validation"
    assert "Insufficient search results" in result["report_markdown"]
    assert "notes" not in result["report_markdown"]


def test_invalid_source_failure_report_is_chinese_and_lists_invalid_and_allowed_urls():
    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://invented.example/source",
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://invented.example/source",
    ])
    node = make_write_report_node(llm)

    result = node({**_state(), "question": "AI 搜索"})

    report = result["report_markdown"]
    assert "# 研究报告生成失败" in report
    assert "## 第一次失败原因" in report
    assert "## 第二次失败原因" in report
    assert "Sources 中存在未被搜索结果支持的 URL" in report
    assert "## 非法来源 URL" in report
    assert "https://invented.example/source" in report
    assert "## 可用来源 URL" in report
    assert "https://example.com" in report
    assert "## 你可以怎么做" in report
    assert "--results-per-query" in report


def test_write_report_retries_once_after_validation_failure_and_succeeds():
    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery without citation.\n\n## Sources\n\n[1] https://example.com",
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com",
    ])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "errors": [],
    })

    assert result["report_status"] == "success"
    assert result["rewrite_attempted"] is True
    assert result["validation_attempts"] == 2
    assert result["validation_failures"][0]["reason"] == "missing_body_citations"
    assert len(llm.prompts) == 2
    assert "未通过引用校验" in llm.prompts[1]
    assert "missing_body_citations" in llm.prompts[1]
    assert "https://example.com" in llm.prompts[1]


def test_write_report_retries_once_then_saves_full_failure_report():
    llm = FakeLLMClient([
        "# AI Search\n\nNo citation.\n\n## Sources\n\n[1] https://example.com",
        "# AI Search\n\nStill no citation.\n\n## Sources\n\n[1] https://example.com",
    ])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "errors": [],
    })

    assert result["report_status"] == "failed_validation"
    assert result["rewrite_attempted"] is True
    assert result["validation_attempts"] == 2
    assert len(result["validation_failures"]) == 2
    report = result["report_markdown"]
    assert "## 第一次失败原因" in report
    assert "## 第二次失败原因" in report
    assert "## 详细诊断" in report
    assert "### 第 1 次诊断" in report
    assert "reason: missing_body_citations" in report
    assert "body citations:" in report
    assert "source citations:" in report
    assert "undefined citations:" in report
    assert "unused sources:" in report
    assert "invalid source URLs:" in report
    assert "bare body URLs:" in report
    assert "available source URLs:" in report
    assert "### 第 2 次诊断" in report


def test_write_report_includes_review_feedback_in_rewrite_prompt():
    """When review_feedback is provided, it should appear in the LLM prompt."""
    from tests.conftest import FakeLLMClient

    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com"
    ])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "evidence_cards": [],
        "review_feedback": "Issues: The report lacks sufficient citations.\nSuggestions: Add more numbered references.",
        "errors": [],
    })

    prompt = llm.prompts[0]
    assert "lacks sufficient citations" in prompt
    assert result["report_status"] == "success"


def test_write_report_clears_review_feedback_after_consumption():
    """After write_report consumes review_feedback, it should be cleared from state."""
    llm = FakeLLMClient([
        "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com"
    ])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "evidence_cards": [],
        "review_feedback": "Issues: Not enough citations.",
        "errors": [],
    })

    assert result.get("review_feedback") is None
    assert result.get("review_rewritten") is True
