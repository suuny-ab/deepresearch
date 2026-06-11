from deepresearch.source_quality import classify_source
from deepresearch.state import SearchResult


def result(url: str, title: str = "Title", content: str = "Content") -> SearchResult:
    return SearchResult(subquestion_id="q1", title=title, url=url, content=content)


def test_classify_official_source():
    quality = classify_source(result("https://www.gov.cn/zhengce/example.html", title="政策文件"))

    assert quality.source_type == "official"
    assert quality.score >= 90


def test_classify_academic_source():
    quality = classify_source(result("https://doi.org/10.1234/example", title="Academic Paper"))

    assert quality.source_type == "academic"
    assert quality.score >= 85


def test_classify_industry_report_pdf():
    quality = classify_source(result("https://example.com/report.pdf", title="AI Search Industry Report 2026"))

    assert quality.source_type == "industry_report"
    assert quality.score >= 80


def test_classify_seo_content():
    quality = classify_source(result("https://www.seo.com/blog/ai-search-trends", title="AI Search Trends"))

    assert quality.source_type == "seo_content"
    assert quality.score <= 40


def test_quality_score_is_not_tavily_score():
    item = result("https://www.seo.com/blog/ai-search-trends")
    item.score = 0.95

    quality = classify_source(item)

    assert quality.score <= 40


def test_seo_domain_overrides_report_pdf_signals():
    quality = classify_source(result("https://seo.com/report.pdf", title="AI Search Report"))

    assert quality.source_type == "seo_content"
    assert quality.score <= 40


def test_seo_domain_overrides_report_title_signals():
    quality = classify_source(result("https://seo.com/article", title="AI Search Research Report"))

    assert quality.source_type == "seo_content"


def test_company_domain_overrides_blog_path():
    quality = classify_source(result("https://openai.com/blog/ai-search"))

    assert quality.source_type == "company_blog"
    assert quality.score == 65


def test_official_classification_requires_matching_host():
    quality = classify_source(result("https://example.com?next=gov.cn"))

    assert quality.source_type != "official"


def test_reputable_media_classification_requires_matching_host():
    quality = classify_source(result("https://notreuters.com/article"))

    assert quality.source_type != "reputable_media"


def test_academic_classification_requires_matching_host():
    quality = classify_source(result("https://foo.com/path/doi.org/article"))

    assert quality.source_type != "academic"


def test_pdf_detection_uses_path_before_query_string():
    quality = classify_source(result("https://example.com/file.pdf?download=1"))

    assert quality.source_type == "industry_report"
