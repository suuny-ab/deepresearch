from urllib.parse import urlparse

from pydantic import BaseModel, Field

from deepresearch.state import SearchResult, SourceType


class SourceQuality(BaseModel):
    source_type: SourceType
    score: int = Field(ge=0, le=100)
    reason: str


def host_matches(host: str, domains: list[str]) -> bool:
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def classify_source(result: SearchResult) -> SourceQuality:
    parsed = urlparse(result.url.lower())
    host = parsed.hostname or ""
    path = parsed.path
    title = result.title.lower()

    if host_matches(host, ["gov.cn"]) or host.endswith(".gov"):
        return SourceQuality(source_type="official", score=95, reason="Government or official domain")
    if host_matches(host, ["doi.org", "arxiv.org", "sciengine.com"]):
        return SourceQuality(source_type="academic", score=90, reason="Academic or DOI-like source")
    if host_matches(host, ["seo.com", "semrush.com", "hubspot.com"]):
        return SourceQuality(source_type="seo_content", score=20, reason="SEO/marketing content domain")
    if host_matches(host, ["reuters.com", "bloomberg.com", "news.cn", "stcn.com", "21jingji.com", "36kr.com"]):
        return SourceQuality(source_type="reputable_media", score=75, reason="Recognized media domain")
    if host_matches(host, ["openai.com", "anthropic.com", "google.com", "microsoft.com", "aws.amazon.com", "aliyun.com", "volcengine.com"]):
        return SourceQuality(source_type="company_blog", score=65, reason="Company or vendor domain")
    if host_matches(host, ["zhihu.com", "csdn.net", "cnblogs.com"]):
        return SourceQuality(source_type="blog", score=45, reason="Blog/forum-like domain")
    if "/blog" in path:
        return SourceQuality(source_type="blog", score=45, reason="Blog path")
    if path.endswith(".pdf") or any(term in title for term in ["report", "whitepaper", "research", "报告", "白皮书"]):
        return SourceQuality(source_type="industry_report", score=85, reason="Report-like source")
    return SourceQuality(source_type="unknown", score=50, reason="No strong quality signal")
