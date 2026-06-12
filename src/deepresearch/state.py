from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field, model_validator


ContentType = Literal["search_content", "extracted_content"]
Confidence = Literal["low", "medium", "high"]
CorroborationLevel = Literal["single_source", "weakly_corroborated", "strongly_corroborated"]


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


class ExtractedClaim(BaseModel):
    """Phase 1 output -- raw claims extracted from sources, no cross-validation."""
    id: str
    subquestion_id: str
    claim: str
    source_url: str
    source_title: str
    supporting_snippet: str
    content_type: Literal["search_content", "extracted_content"]
    confidence: Confidence


class ExtractedSource(BaseModel):
    subquestion_id: str
    url: str
    title: str
    raw_content: str
    extract_depth: Literal["basic", "advanced"] = "basic"
    format: Literal["markdown", "text"] = "markdown"


class EvidenceCard(BaseModel):
    id: str
    subquestion_id: str
    claim: str
    source_url: str
    source_title: str
    supporting_snippet: str
    content_type: Literal["search_content", "extracted_content"]
    corroboration_level: CorroborationLevel = "single_source"
    corroborating_sources: list[str] = Field(default_factory=list)
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
    extracted_claims: list[ExtractedClaim]
    evidence_cards: list[EvidenceCard]
    evidence_metrics: dict[str, Any]
    report_markdown: str
    report_status: Literal["success", "failed_validation"]
    rewrite_attempted: bool
    validation_attempts: int
    validation_failures: list[dict[str, Any]]
    review: ReviewResult
    review_feedback: str | None
    review_rewritten: bool
    output_path: str
    errors: list[str]
