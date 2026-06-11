from tests.conftest import FakeLLMClient

from deepresearch.nodes.writing import make_write_report_node
from deepresearch.state import ResearchNote, SearchResult, SubQuestion


VALID_NUMBERED_REPORT = "# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://example.com"


def _state() -> dict:
    return {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
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


def test_write_report_replaces_report_when_sources_section_missing():
    llm = FakeLLMClient(["# AI Search\n\nAI search is changing discovery.[1]"])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "failed_validation"
    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "报告缺少 ## Sources 来源部分" in result["report_markdown"]
    assert "AI search is changing discovery" not in result["report_markdown"]
    assert "https://example.com" in result["report_markdown"]
    assert any("missing_sources_section" in error for error in result["errors"])


def test_write_report_replaces_report_when_body_has_no_numbered_citations():
    llm = FakeLLMClient(["# AI Search\n\nThis report makes unsupported claims without citations.\n\n## Sources\n\n[1] https://example.com"])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "failed_validation"
    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "正文没有使用编号引用" in result["report_markdown"]
    assert "This report makes unsupported claims" not in result["report_markdown"]
    assert "https://example.com" in result["report_markdown"]
    assert any("missing_body_citations" in error for error in result["errors"])


def test_write_report_replaces_report_when_source_url_is_not_allowed():
    llm = FakeLLMClient(["# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://invented.example/source"])
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
        "[2] https://example.com/unused"
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


def test_write_report_rejects_unused_source_number_without_retry_yet():
    llm = FakeLLMClient([
        "# AI Search\n\n"
        "AI search is changing discovery.[1]\n\n"
        "## Sources\n\n"
        "[1] https://example.com\n"
        "[2] https://example.com/extra"
    ])
    node = make_write_report_node(llm)
    state = _state()
    state["search_results"].append(
        SearchResult(subquestion_id="q1", title="Extra", url="https://example.com/extra", content="Content")
    )

    result = node(state)

    assert result["report_status"] == "failed_validation"
    assert result["rewrite_attempted"] is False
    assert result["validation_attempts"] == 1
    assert result["validation_failures"][0]["reason"] == "unused_sources"


def test_write_report_replaces_report_when_body_contains_bare_url():
    llm = FakeLLMClient(["# AI Search\n\nAI search is changing discovery https://example.com [1]\n\n## Sources\n\n[1] https://example.com"])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "failed_validation"
    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "正文中出现裸 URL" in result["report_markdown"]
    assert any("bare_urls_in_body" in error for error in result["errors"])


def test_write_report_does_not_retry_after_validation_failure_yet():
    llm = FakeLLMClient([
        "# AI Search\n\nThis report makes unsupported claims without citations.\n\n## Sources\n\n[1] https://example.com",
        VALID_NUMBERED_REPORT,
    ])
    node = make_write_report_node(llm)

    result = node(_state())

    assert result["report_status"] == "failed_validation"
    assert len(llm.prompts) == 1


def test_write_report_sets_failed_validation_status_when_inputs_are_missing():
    llm = FakeLLMClient([])
    node = make_write_report_node(llm)

    result = node({"question": "AI search", "search_results": [], "notes": [], "errors": []})

    assert result["report_status"] == "failed_validation"
    assert "Insufficient search results or notes" in result["report_markdown"]


def test_invalid_source_failure_report_is_chinese_and_lists_invalid_and_allowed_urls():
    llm = FakeLLMClient(["# AI Search\n\nAI search is changing discovery.[1]\n\n## Sources\n\n[1] https://invented.example/source"])
    node = make_write_report_node(llm)

    result = node({**_state(), "question": "AI 搜索"})

    report = result["report_markdown"]
    assert "# 研究报告生成失败" in report
    assert "## 失败原因" in report
    assert "Sources 中存在未被搜索结果支持的 URL" in report
    assert "## 非法来源 URL" in report
    assert "https://invented.example/source" in report
    assert "## 可用来源 URL" in report
    assert "https://example.com" in report
    assert "## 你可以怎么做" in report
    assert "--results-per-query" in report
