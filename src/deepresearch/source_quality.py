from pydantic import BaseModel, Field

from deepresearch.state import SearchResult, SourceType


class SourceQuality(BaseModel):
    source_type: SourceType
    score: int = Field(ge=0, le=100)
    reason: str


def classify_source(result: SearchResult) -> SourceQuality:
    url = result.url.lower()
    title = result.title.lower()

    if ".gov" in url or "gov.cn" in url:
        return SourceQuality(source_type="official", score=95, reason="Government or official domain")
    if "doi.org" in url or "arxiv.org" in url or "sciengine.com" in url:
        return SourceQuality(source_type="academic", score=90, reason="Academic or DOI-like source")
    if url.endswith(".pdf") or any(term in title for term in ["report", "whitepaper", "research", "报告", "白皮书"]):
        return SourceQuality(source_type="industry_report", score=85, reason="Report-like source")
    if any(domain in url for domain in ["reuters.com", "bloomberg.com", "news.cn", "stcn.com", "21jingji.com", "36kr.com"]):
        return SourceQuality(source_type="reputable_media", score=75, reason="Recognized media domain")
    if any(domain in url for domain in ["seo.com", "semrush.com", "hubspot.com"]):
        return SourceQuality(source_type="seo_content", score=20, reason="SEO/marketing content domain")
    if any(domain in url for domain in ["zhihu.com", "csdn.net", "cnblogs.com"]):
        return SourceQuality(source_type="blog", score=45, reason="Blog/forum-like domain")
    if "/blog" in url:
        return SourceQuality(source_type="blog", score=45, reason="Blog path")
    if any(domain in url for domain in ["openai.com", "anthropic.com", "google.com", "microsoft.com", "aws.amazon.com", "aliyun.com", "volcengine.com"]):
        return SourceQuality(source_type="company_blog", score=65, reason="Company or vendor domain")
    return SourceQuality(source_type="unknown", score=50, reason="No strong quality signal")
