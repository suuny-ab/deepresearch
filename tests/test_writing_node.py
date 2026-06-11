from tests.conftest import FakeLLMClient

from deepresearch.nodes.writing import make_write_report_node
from deepresearch.state import ResearchNote, SearchResult, SubQuestion


def test_write_report_uses_llm_markdown():
    llm = FakeLLMClient(["# AI Search\n\nCited claim: https://example.com\n\n## Sources\n\n- https://example.com"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_markdown"].startswith("# AI Search")


def test_write_report_replaces_report_when_llm_invents_source_url():
    llm = FakeLLMClient(["# AI Search\n\nInvented citation: https://invented.example/source"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "模型生成的报告包含未被搜索结果支持的来源 URL" in result["report_markdown"]
    assert "https://invented.example/source" in result["report_markdown"]
    assert any("invalid source URL" in error for error in result["errors"])
    assert any("https://invented.example/source" in error for error in result["errors"])


def test_write_report_replaces_report_when_llm_omits_source_urls():
    llm = FakeLLMClient(["# AI Search\n\nThis report makes unsupported claims without citations."])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "模型生成的报告没有在正文中引用任何可用来源" in result["report_markdown"]
    assert "This report makes unsupported claims" not in result["report_markdown"]
    assert "https://example.com" in result["report_markdown"]
    assert any("citation" in error.lower() or "source" in error.lower() for error in result["errors"])


def test_write_report_replaces_report_when_llm_omits_sources_section():
    llm = FakeLLMClient(["# AI Search\n\nCited claim: https://example.com"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "模型生成的报告缺少 ## Sources 来源部分" in result["report_markdown"]
    assert "Cited claim" not in result["report_markdown"]
    assert "https://example.com" in result["report_markdown"]
    assert any("Sources section" in error for error in result["errors"])


def test_write_report_replaces_report_when_allowed_urls_only_appear_in_sources_section():
    llm = FakeLLMClient([
        "# AI Search\n\n"
        "AI search systems combine retrieval and synthesis into user-facing answers.\n\n"
        "## Sources\n\n"
        "- https://example.com"
    ])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert "# 研究报告生成失败" in result["report_markdown"]
    assert "模型生成的报告只在 Sources 部分列出来源" in result["report_markdown"]
    assert "AI search systems combine retrieval" not in result["report_markdown"]
    assert "https://example.com" in result["report_markdown"]
    assert any(
        "body citation" in error.lower() or "no citations before sources" in error.lower()
        for error in result["errors"]
    )


def test_write_report_sets_success_status_for_valid_report():
    llm = FakeLLMClient(["# AI Search\n\nCited claim: https://example.com\n\n## Sources\n\n- https://example.com"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_status"] == "success"


def test_write_report_sets_failed_validation_status_for_invalid_url():
    llm = FakeLLMClient(["# AI Search\n\nInvented citation: https://invented.example/source"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert result["report_status"] == "failed_validation"


def test_invalid_url_failure_report_is_chinese_and_lists_invalid_url():
    llm = FakeLLMClient(["# AI Search\n\nInvented citation: https://invented.example/source"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI 搜索",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    report = result["report_markdown"]
    assert "# 研究报告生成失败" in report
    assert "## 失败原因" in report
    assert "模型生成的报告包含未被搜索结果支持的来源 URL" in report
    assert "## 非法来源 URL" in report
    assert "https://invented.example/source" in report
    assert "## 可用来源 URL" in report
    assert "https://example.com" in report
    assert "## 你可以怎么做" in report
    assert "--results-per-query" in report


def test_missing_sources_failure_report_uses_specific_reason():
    llm = FakeLLMClient(["# AI Search\n\nCited claim: https://example.com"])
    node = make_write_report_node(llm)

    result = node({
        "question": "AI 搜索",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="AI search", rationale="Background")],
        "search_results": [SearchResult(subquestion_id="q1", title="Source", url="https://example.com", content="Content")],
        "notes": [ResearchNote(subquestion_id="q1", key_findings=["Finding"], source_urls=["https://example.com"], confidence="high")],
        "errors": [],
    })

    assert "模型生成的报告缺少 ## Sources 来源部分" in result["report_markdown"]
