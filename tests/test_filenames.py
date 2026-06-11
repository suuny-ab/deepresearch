from datetime import datetime

from deepresearch.utils.filenames import make_report_filename, slugify_question


def test_slugify_ascii_question():
    assert slugify_question("AI Search Trends 2026") == "ai-search-trends-2026"


def test_slugify_removes_punctuation():
    assert slugify_question("LangGraph vs. CrewAI: which one?") == "langgraph-vs-crewai-which-one"


def test_slugify_non_ascii_falls_back_to_report():
    assert slugify_question("分析 2026 年 AI 搜索趋势") == "2026-ai"


def test_slugify_empty_falls_back_to_report():
    assert slugify_question("!!!") == "report"


def test_make_report_filename_contains_timestamp_and_slug():
    now = datetime(2026, 6, 10, 15, 30, 0)

    filename = make_report_filename("AI Search Trends", now=now)

    assert filename == "2026-06-10-153000-ai-search-trends.md"


def test_make_failed_report_filename_contains_failed_suffix():
    now = datetime(2026, 6, 11, 9, 26, 27)

    filename = make_report_filename("AI Search", failed=True, now=now)

    assert filename == "2026-06-11-092627-ai-search-failed.md"
