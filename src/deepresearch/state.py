from typing import Literal, TypedDict

from pydantic import BaseModel, Field


class SubQuestion(BaseModel):
    id: str
    question: str
    search_query: str
    rationale: str


class SearchResult(BaseModel):
    subquestion_id: str
    title: str
    url: str
    content: str
    score: float | None = None
    published_date: str | None = None


class ResearchNote(BaseModel):
    subquestion_id: str
    key_findings: list[str]
    source_urls: list[str]
    confidence: Literal["low", "medium", "high"]


class ReviewResult(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[str]
    suggestions: list[str]


class ResearchState(TypedDict, total=False):
    question: str
    subquestions: list[SubQuestion]
    search_results: list[SearchResult]
    notes: list[ResearchNote]
    report_markdown: str
    review: ReviewResult
    output_path: str
    errors: list[str]
