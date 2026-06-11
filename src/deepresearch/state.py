from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, model_validator


SourceType = Literal[
    "official",
    "academic",
    "industry_report",
    "reputable_media",
    "company_blog",
    "blog",
    "forum",
    "seo_content",
    "unknown",
]
ContentType = Literal["search_content", "raw_content", "extracted_content"]
EvidenceReliability = Literal["low", "medium", "high"]
Confidence = Literal["low", "medium", "high"]


class SubQuestion(BaseModel):
    id: str
    question: str
    search_query: str
    search_queries: list[str] = Field(default_factory=list)
    rationale: str

    @model_validator(mode="after")
    def normalize_search_queries(self) -> "SubQuestion":
        if not self.search_queries:
            self.search_queries = [self.search_query]
        return self


class SearchResult(BaseModel):
    subquestion_id: str
    title: str
    url: str
    content: str
    query: str | None = None
    raw_content: str | None = None
    content_type: ContentType = "search_content"
    score: float | None = None
    published_date: str | None = None
    source_type: SourceType = "unknown"
    source_quality_score: int = Field(default=50, ge=0, le=100)
    source_quality_reason: str = ""


class ExtractedSource(BaseModel):
    subquestion_id: str
    url: str
    title: str
    raw_content: str
    extract_depth: Literal["basic", "advanced"] = "basic"
    format: Literal["markdown", "text"] = "markdown"
    source_type: SourceType = "unknown"
    source_quality_score: int = Field(default=50, ge=0, le=100)
    source_quality_reason: str = ""


class EvidenceCard(BaseModel):
    id: str
    subquestion_id: str
    claim: str
    source_url: str
    source_title: str
    supporting_snippet: str
    content_type: Literal["search_content", "extracted_content"]
    source_type: SourceType
    source_quality_score: int = Field(ge=0, le=100)
    evidence_reliability: EvidenceReliability
    confidence: Confidence


class ResearchNote(BaseModel):
    subquestion_id: str
    key_findings: list[str]
    source_urls: list[str]
    confidence: Confidence


class ReviewResult(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[str]
    suggestions: list[str]


class ResearchState(TypedDict, total=False):
    question: str
    subquestions: list[SubQuestion]
    search_results: list[SearchResult]
    extracted_sources: list[ExtractedSource]
    evidence_cards: list[EvidenceCard]
    evidence_metrics: dict[str, Any]
    notes: list[ResearchNote]
    report_markdown: str
    report_status: Literal["success", "failed_validation"]
    rewrite_attempted: bool
    validation_attempts: int
    validation_failures: list[dict[str, Any]]
    review: ReviewResult
    output_path: str
    errors: list[str]
