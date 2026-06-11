# Deep Research Agent v0.3 Cross-Validation Evidence Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded domain-based source quality scoring with multi-source cross-validation — sources are selected by relevance + domain diversity, and evidence reliability is determined by how many independent-domain sources corroborate each claim.

**Architecture:** The 7-node LangGraph pipeline stays intact. `source_quality.py` is deleted entirely. `prepare_evidence` is rewritten to use Tavily relevance score + domain-diversity for source selection, and the EvidenceCard LLM prompt gains cross-validation instructions. Downstream nodes (synthesize_notes, write_report) stratify claims by corroboration level. Verbose output replaces source quality / evidence reliability metrics with corroboration distribution.

**Tech Stack:** Python 3.11+, Pydantic, LangGraph, Tavily SDK, DeepSeek API, Typer, Rich, pytest

---

## File Structure Changes

**Delete:**
```text
src/deepresearch/source_quality.py
tests/test_source_quality.py
```

**Modify:**
```text
src/deepresearch/state.py
src/deepresearch/utils/urls.py
src/deepresearch/nodes/prepare_evidence.py
src/deepresearch/prompts/evidence.py
src/deepresearch/prompts/synthesizing.py
src/deepresearch/prompts/writing.py
src/deepresearch/nodes/synthesizing.py
src/deepresearch/nodes/writing.py
src/deepresearch/verbose.py
README.md
tests/test_state.py
tests/test_urls.py
tests/test_prepare_evidence_node.py
tests/test_evidence_prompt.py
tests/test_synthesizing_node.py
tests/test_writing_node.py
tests/test_writing_prompt.py
tests/test_verbose.py
tests/test_integration_offline.py
tests/test_graph_structure.py
```

---

### Task 0: Pre-check

**Files:**
- No file changes.

- [ ] **Step 1: Check git status**

Run:
```bash
git status --short
```

Expected: clean (no output).

- [ ] **Step 2: Run current tests**

Run:
```bash
uv run pytest -v
```

Expected: all pass.

- [ ] **Step 3: No commit**

---

### Task 1: Delete source_quality.py and its tests

**Files:**
- Delete: `src/deepresearch/source_quality.py`
- Delete: `tests/test_source_quality.py`

- [ ] **Step 1: Delete the files**

Run:
```powershell
Remove-Item src/deepresearch/source_quality.py
Remove-Item tests/test_source_quality.py
```

- [ ] **Step 2: Commit**

```bash
git add src/deepresearch/source_quality.py tests/test_source_quality.py
git commit -m "feat: remove hardcoded source quality scoring"
```

---

### Task 2: Add extract_domain helper to urls.py

**Files:**
- Modify: `src/deepresearch/utils/urls.py`
- Modify: `tests/test_urls.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_urls.py`:

```python
from deepresearch.utils.urls import extract_domain


def test_extract_domain_returns_lower_host_without_www():
    assert extract_domain("https://www.Example.com/article") == "example.com"
    assert extract_domain("https://arxiv.org/abs/1234") == "arxiv.org"
    assert extract_domain("http://WWW.GOV.CN/policy") == "gov.cn"


def test_extract_domain_handles_scheme_less_url():
    assert extract_domain("example.com/article") == "example.com"


def test_extract_domain_handles_subdomains():
    assert extract_domain("https://blog.openai.com/research") == "blog.openai.com"
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_urls.py::test_extract_domain_returns_lower_host_without_www -v
```

Expected: `ImportError` or `AttributeError` — `extract_domain` not defined.

- [ ] **Step 3: Implement extract_domain**

Append to `src/deepresearch/utils/urls.py`:

```python
def extract_domain(url: str) -> str:
    """Extract normalized domain from a URL for diversity comparison."""
    parsed = urlparse(url.strip())
    host = parsed.hostname or ""
    if host.startswith("www."):
        host = host[4:]
    return host.lower()
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_urls.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/utils/urls.py tests/test_urls.py
git commit -m "feat: add extract_domain utility"
```

---

### Task 3: Update state.py — delete enums and fields, add cross-validation fields

**Files:**
- Modify: `src/deepresearch/state.py`
- Modify: `tests/test_state.py`

- [ ] **Step 1: Replace test_state.py with updated tests**

Replace the full content of `tests/test_state.py`:

```python
import pytest
from pydantic import ValidationError

from deepresearch.state import ResearchNote, ReviewResult, SearchResult, SubQuestion


def test_subquestion_requires_core_fields():
    item = SubQuestion(
        id="q1",
        question="What changed in AI search?",
        search_query="AI search trends 2026",
        rationale="Establish context",
    )

    assert item.id == "q1"
    assert item.search_query == "AI search trends 2026"


def test_search_result_keeps_source_url():
    result = SearchResult(
        subquestion_id="q1",
        title="Report",
        url="https://example.com/report",
        content="Useful summary",
        score=0.8,
    )

    assert result.url == "https://example.com/report"
    assert result.score == 0.8


def test_search_result_no_longer_has_source_quality_fields():
    result = SearchResult(
        subquestion_id="q1",
        title="Report",
        url="https://example.com/report",
        content="Summary",
    )

    assert not hasattr(result, "source_type")
    assert not hasattr(result, "source_quality_score")
    assert not hasattr(result, "source_quality_reason")


def test_research_note_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        ResearchNote(
            subquestion_id="q1",
            key_findings=["Finding"],
            source_urls=["https://example.com"],
            confidence="certain",
        )


def test_review_result_score_range():
    review = ReviewResult(passed=True, score=86, issues=[], suggestions=[])

    assert review.score == 86

    with pytest.raises(ValidationError):
        ReviewResult(passed=False, score=101, issues=[], suggestions=[])


def test_research_state_accepts_report_status():
    from deepresearch.state import ResearchState

    state: ResearchState = {"question": "AI search", "report_status": "failed_validation"}

    assert state["report_status"] == "failed_validation"


def test_research_state_accepts_validation_retry_metadata():
    from deepresearch.state import ResearchState

    state: ResearchState = {
        "question": "AI search",
        "rewrite_attempted": True,
        "validation_attempts": 2,
        "validation_failures": [
            {"reason": "missing_body_citations", "message": u"正文没有使用编号引用。"},
            {"reason": "unused_sources", "message": "Sources 中存在未被正文引用的编号。"},
        ],
    }

    assert state["rewrite_attempted"] is True
    assert state["validation_attempts"] == 2
    assert len(state["validation_failures"]) == 2


def test_subquestion_accepts_multiple_search_queries():
    from deepresearch.state import SubQuestion

    item = SubQuestion(
        id="q1",
        question="AI 搜索技术趋势是什么？",
        search_query="AI 搜索 技术趋势",
        search_queries=[
            "AI 搜索 技术趋势 RAG",
            "AI search technology trends RAG 2026",
        ],
        rationale="覆盖中英文来源",
    )

    assert item.search_queries == [
        "AI 搜索 技术趋势 RAG",
        "AI search technology trends RAG 2026",
    ]


def test_subquestion_normalizes_missing_search_queries_from_search_query():
    from deepresearch.state import SubQuestion

    item = SubQuestion(
        id="q1",
        question="What is AI search?",
        search_query="AI search definition",
        rationale="Background",
    )

    assert item.search_queries == ["AI search definition"]


def test_evidence_card_has_corroboration_fields_not_source_quality():
    from deepresearch.state import EvidenceCard

    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="RAG remains important for AI search.",
        source_url="https://example.com/report",
        source_title="AI Search Report",
        supporting_snippet="RAG remains a core architecture for AI search systems.",
        content_type="extracted_content",
        corroboration_level="weakly_corroborated",
        corroborating_sources=["https://other-domain.com/article"],
        confidence="high",
    )

    assert card.source_url == "https://example.com/report"
    assert card.supporting_snippet
    assert card.corroboration_level == "weakly_corroborated"
    assert card.corroborating_sources == ["https://other-domain.com/article"]
    assert not hasattr(card, "source_type")
    assert not hasattr(card, "source_quality_score")
    assert not hasattr(card, "evidence_reliability")


def test_evidence_card_defaults_corroboration_to_single_source():
    from deepresearch.state import EvidenceCard

    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="Single source claim.",
        source_url="https://example.com/report",
        source_title="Report",
        supporting_snippet="Single source claim.",
        content_type="extracted_content",
        confidence="medium",
    )

    assert card.corroboration_level == "single_source"
    assert card.corroborating_sources == []


def test_extracted_source_no_longer_has_source_quality_fields():
    from deepresearch.state import ExtractedSource

    source = ExtractedSource(
        subquestion_id="q1",
        url="https://example.com/a",
        title="Source A",
        raw_content="Full content.",
    )

    assert source.url == "https://example.com/a"
    assert source.raw_content == "Full content."
    assert not hasattr(source, "source_type")
    assert not hasattr(source, "source_quality_score")
    assert not hasattr(source, "source_quality_reason")


def test_research_state_no_longer_has_extracted_sources():
    from deepresearch.state import ResearchState

    state: ResearchState = {
        "question": "AI search",
        "evidence_cards": [],
        "evidence_metrics": {},
    }

    assert "extracted_sources" not in state
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_state.py -v
```

Expected: failures — `source_type`/`source_quality_score`/`source_quality_reason` still on models, `EvidenceCard` missing `corroboration_level`.

- [ ] **Step 3: Replace state.py**

Replace `src/deepresearch/state.py`:

```python
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
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_state.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/state.py tests/test_state.py
git commit -m "feat: replace source quality fields with cross-validation fields in state models"
```

---

### Task 4: Update evidence prompt with cross-validation instructions

**Files:**
- Modify: `src/deepresearch/prompts/evidence.py`
- Modify: `tests/test_evidence_prompt.py`

- [ ] **Step 1: Replace test_evidence_prompt.py**

```python
from deepresearch.prompts.evidence import build_evidence_prompt
from deepresearch.state import ExtractedSource


def test_evidence_prompt_requires_evidence_cards():
    source = ExtractedSource(
        subquestion_id="q1",
        url="https://example.com/a",
        title="Source A",
        raw_content="RAG remains important for AI search.",
    )

    prompt = build_evidence_prompt("AI search", [source])

    assert "EvidenceCard" in prompt
    assert "supporting_snippet" in prompt
    assert "Do not create claims not supported by the source text" in prompt
    assert "copy the supplied `url` value into EvidenceCard `source_url`" in prompt
    assert "https://example.com/a" in prompt


def test_evidence_prompt_includes_cross_validation_instructions():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="RAG remains important.",
        ),
        ExtractedSource(
            subquestion_id="q1",
            url="https://other.example/b",
            title="Source B",
            raw_content="RAG is still important for search.",
        ),
    ]

    prompt = build_evidence_prompt("AI search", sources)

    assert "corroboration_level" in prompt
    assert "single_source" in prompt
    assert "weakly_corroborated" in prompt
    assert "strongly_corroborated" in prompt
    assert "different domain" in prompt.lower() or "DIFFERENT domain" in prompt
    assert "corroborating_sources" in prompt


def test_evidence_prompt_reflects_content_type():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="Summary only",
        ),
    ]

    prompt = build_evidence_prompt("AI search", sources)

    assert "content_type" in prompt
    assert "search_content" in prompt
    assert "extracted_content" in prompt
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_evidence_prompt.py -v
```

Expected: `test_evidence_prompt_includes_cross_validation_instructions` fails — old prompt.

- [ ] **Step 3: Replace evidence.py prompt**

Replace `src/deepresearch/prompts/evidence.py`:

```python
from deepresearch.state import ExtractedSource


def build_evidence_prompt(question: str, sources: list[ExtractedSource]) -> str:
    return f"""
You extract EvidenceCard objects from source text for a research report.
Do not create claims not supported by the source text.
Every claim must be grounded in a supporting_snippet copied or closely paraphrased from the source text.
Each EvidenceCard must copy the supplied `url` value into EvidenceCard `source_url`.
If the source text is weak, thin, or only a search snippet, use low confidence.

For each claim you extract, also check ALL other supplied sources 
(even those from different subquestions that cover related topics) 
to determine whether independent sources corroborate the same claim.

corroboration_level rules:
- "single_source"      Only this one source mentions this claim
- "weakly_corroborated"      One OTHER independent source (different domain) supports this claim
- "strongly_corroborated"    2+ OTHER independent sources (different domains) support this claim

CRITICAL: Two pages from the SAME domain (e.g., two openai.com pages) 
do NOT count as independent corroboration. Only DIFFERENT domain 
agreement constitutes meaningful cross-validation.

When asserting corroboration, you MUST:
1. Quote the supporting snippet from the corroborating source
2. Verify the corroborating source's domain is different from the primary source
3. Include corroborating source URLs in corroborating_sources

Each source is marked with content_type:
- "extracted_content" — full webpage text was available
- "search_content"   — only a search snippet was available (extract failed)

When assessing corroboration strength:
- Two full-text sources independently stating the same fact → strong signal
- One full text + one snippet → weaker but still valid
- Two snippets → treat as weakly_corroborated at best
- Label the strength honestly; do not inflate weak signals

Return only JSON in this exact shape:
{{"evidence_cards":[{{"id":"e1","subquestion_id":"q1","claim":"...","source_url":"https://...","source_title":"...","supporting_snippet":"...","content_type":"extracted_content","corroboration_level":"single_source|weakly_corroborated|strongly_corroborated","corroborating_sources":["https://other-domain.com/..."],"confidence":"low|medium|high"}}]}}

Original question:
{question}

Sources:
{[source.model_dump() for source in sources]}
""".strip()
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_evidence_prompt.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/prompts/evidence.py tests/test_evidence_prompt.py
git commit -m "feat: add cross-validation instructions to evidence prompt"
```

---

### Task 5: Rewrite prepare_evidence node

**Files:**
- Modify: `src/deepresearch/nodes/prepare_evidence.py`
- Modify: `tests/test_prepare_evidence_node.py`

- [ ] **Step 1: Replace test_prepare_evidence_node.py**

```python
from tests.conftest import FakeLLMClient

from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node, _validate_corroboration
from deepresearch.state import EvidenceCard, ExtractedSource, SearchResult, SubQuestion


class FakeSearchClient:
    def __init__(self, fail_extract=False, extracted_sources=None):
        self.extract_calls = []
        self.fail_extract = fail_extract
        self.extracted_sources = extracted_sources or []

    @property
    def extracted_urls(self):
        return [url for call in self.extract_calls for url in call["urls"]]

    def extract(self, urls, *, subquestion_id):
        self.extract_calls.append({"urls": list(urls), "subquestion_id": subquestion_id})
        if self.fail_extract:
            raise Exception("extract failed")
        return self.extracted_sources


def test_prepare_evidence_dedupes_and_selects_by_relevance():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"RAG remains important.","source_url":"https://example.com/report.pdf","source_title":"Report","supporting_snippet":"RAG remains important.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}'
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(
                subquestion_id="q1",
                title="Report",
                url="https://example.com/report.pdf",
                raw_content="RAG remains important.",
            )
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    state = {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q1", title="Report", url="https://example.com/report.pdf", content="Summary", score=0.9),
            SearchResult(subquestion_id="q1", query="q2", title="Report duplicate", url="https://www.example.com/report.pdf?utm_source=x", content="Summary duplicate", score=0.8),
        ],
        "errors": [],
    }

    result = node(state)

    assert len(search.extracted_urls) == 1
    assert result["evidence_cards"][0].id == "e1"
    assert result["evidence_metrics"]["raw_search_results"] == 2
    assert result["evidence_metrics"]["deduped_sources"] == 1
    assert result["evidence_metrics"]["duplicates_removed"] == 1
    assert result["evidence_metrics"]["extracted_sources"] == 1
    assert result["evidence_metrics"]["evidence_cards"] == 1
    assert "corroboration" in result["evidence_metrics"]


def test_prepare_evidence_selects_diverse_domains():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Gov perspective.","source_url":"https://www.gov.cn/policy","source_title":"Policy","supporting_snippet":"Gov perspective.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"},{"id":"e2","subquestion_id":"q1","claim":"Blog perspective.","source_url":"https://example.com/blog","source_title":"Blog","supporting_snippet":"Blog perspective.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"medium"}]}'
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(subquestion_id="q1", title="Policy", url="https://www.gov.cn/policy", raw_content="Gov perspective."),
            ExtractedSource(subquestion_id="q1", title="Blog", url="https://example.com/blog", raw_content="Blog perspective."),
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=2)

    state = {
        "question": "AI policy",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q", title="Policy", url="https://www.gov.cn/policy", content="Gov perspective.", score=0.95),
            SearchResult(subquestion_id="q1", query="q", title="Policy copy", url="https://www.gov.cn/policy?page=2", content="Same gov perspective.", score=0.7),
            SearchResult(subquestion_id="q1", query="q", title="Blog", url="https://example.com/blog", content="Blog perspective.", score=0.6),
        ],
        "errors": [],
    }

    result = node(state)

    assert len(search.extracted_urls) == 2
    selected_urls = search.extract_calls[0]["urls"]
    from urllib.parse import urlparse
    domains = set()
    for url in selected_urls:
        host = urlparse(url).hostname or ""
        if host.startswith("www."):
            host = host[4:]
        domains.add(host.lower())
    assert len(domains) == 2


def test_prepare_evidence_preserves_same_normalized_url_per_subquestion():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Shared source supports q1.","source_url":"https://example.com/report","source_title":"Report","supporting_snippet":"Shared source supports q1.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"medium"},{"id":"e2","subquestion_id":"q2","claim":"Shared source supports q2.","source_url":"https://www.example.com/report?utm_source=feed","source_title":"Report copy","supporting_snippet":"Shared source supports q2.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"medium"}]}'
    ])
    search = FakeSearchClient(fail_extract=True)
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [
            SubQuestion(id="q1", question="What changed?", search_query="q1", search_queries=["q1"], rationale="r1"),
            SubQuestion(id="q2", question="Why now?", search_query="q2", search_queries=["q2"], rationale="r2"),
        ],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q1", title="Report", url="https://example.com/report", content="Shared source supports q1."),
            SearchResult(subquestion_id="q2", query="q2", title="Report copy", url="https://www.example.com/report?utm_source=feed", content="Shared source supports q2."),
        ],
        "errors": [],
    })

    assert {card.subquestion_id for card in result["evidence_cards"]} == {"q1", "q2"}
    assert result["evidence_metrics"]["deduped_sources"] == 2
    assert result["evidence_metrics"]["duplicates_removed"] == 0


def test_prepare_evidence_falls_back_to_search_content_when_extract_fails():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Fallback claim.","source_url":"https://example.com/a","source_title":"A","supporting_snippet":"Summary","content_type":"search_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"low"}]}'
    ])
    search = FakeSearchClient(fail_extract=True)
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [SearchResult(subquestion_id="q1", query="q", title="A", url="https://example.com/a", content="Summary")],
        "errors": [],
    })

    assert result["evidence_cards"][0].content_type == "search_content"
    assert result["errors"]


def test_prepare_evidence_rejects_invalid_card_urls():
    llm = FakeLLMClient([
        '{"evidence_cards":[{"id":"bad","subquestion_id":"q1","claim":"Unsupported.","source_url":"https://evil.example/bad","source_title":"Bad","supporting_snippet":"Unsupported.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"medium"},{"id":"good","subquestion_id":"q1","claim":"Valid claim.","source_url":"https://www.gov.cn/policy","source_title":"Policy","supporting_snippet":"Valid claim.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}'
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(subquestion_id="q1", title="Policy", url="https://www.gov.cn/policy", raw_content="Valid claim."),
            ExtractedSource(subquestion_id="q1", title="SEO", url="https://seo.com/blog/ai-search", raw_content="SEO claim."),
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=2)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q", title="SEO", url="https://seo.com/blog/ai-search", content="SEO summary", score=0.9),
            SearchResult(subquestion_id="q1", query="q", title="Policy", url="https://www.gov.cn/policy", content="Policy summary", score=0.5),
            SearchResult(subquestion_id="q1", query="q", title="Unknown", url="https://example.com/unknown", content="Unknown summary", score=0.3),
        ],
        "errors": [],
    })

    assert [card.id for card in result["evidence_cards"]] == ["good"]
    assert any("invalid source_url" in error for error in result["errors"])


def test_validate_corroboration_drops_fabricated_urls():
    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="Claim.",
        source_url="https://example.com/a",
        source_title="A",
        supporting_snippet="Claim.",
        content_type="extracted_content",
        corroboration_level="weakly_corroborated",
        corroborating_sources=["https://fabricated.example/not-real", "https://real.example/b"],
        confidence="high",
    )

    extracted_urls = {"https://example.com/a", "https://real.example/b"}
    extracted_content_types = {"https://example.com/a": "extracted_content", "https://real.example/b": "extracted_content"}

    validated = _validate_corroboration(card, extracted_urls, extracted_content_types)

    assert "https://fabricated.example/not-real" not in validated.corroborating_sources
    assert "https://real.example/b" in validated.corroborating_sources


def test_validate_corroboration_rejects_same_domain():
    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="Claim.",
        source_url="https://example.com/a",
        source_title="A",
        supporting_snippet="Claim.",
        content_type="extracted_content",
        corroboration_level="weakly_corroborated",
        corroborating_sources=["https://example.com/b"],
        confidence="high",
    )

    extracted_urls = {"https://example.com/a", "https://example.com/b"}
    extracted_content_types = {"https://example.com/a": "extracted_content", "https://example.com/b": "extracted_content"}

    validated = _validate_corroboration(card, extracted_urls, extracted_content_types)

    assert validated.corroboration_level == "single_source"
    assert validated.corroborating_sources == []


def test_validate_corroboration_demotes_strongly_when_insufficient_full_text():
    card = EvidenceCard(
        id="e1",
        subquestion_id="q1",
        claim="Claim.",
        source_url="https://example.com/a",
        source_title="A",
        supporting_snippet="Claim.",
        content_type="extracted_content",
        corroboration_level="strongly_corroborated",
        corroborating_sources=["https://other1.example/x", "https://other2.example/y"],
        confidence="high",
    )

    extracted_urls = {"https://example.com/a", "https://other1.example/x", "https://other2.example/y"}
    extracted_content_types = {
        "https://example.com/a": "extracted_content",
        "https://other1.example/x": "extracted_content",
        "https://other2.example/y": "search_content",
    }

    validated = _validate_corroboration(card, extracted_urls, extracted_content_types)

    assert validated.corroboration_level == "weakly_corroborated"
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_prepare_evidence_node.py -v
```

Expected: multiple failures — `source_quality` not found, `_apply_quality` not found, `_validate_corroboration` not defined, `corroboration` key not in metrics.

- [ ] **Step 3: Rewrite prepare_evidence.py**

Replace `src/deepresearch/nodes/prepare_evidence.py`:

```python
from collections import Counter, defaultdict

from pydantic import BaseModel

from deepresearch.clients.llm import LLMClient
from deepresearch.clients.tavily import SearchClient
from deepresearch.prompts.evidence import build_evidence_prompt
from deepresearch.state import EvidenceCard, ExtractedSource, ResearchState, SearchResult
from deepresearch.utils.json import JSONParseError, parse_json_object
from deepresearch.utils.urls import extract_domain, normalize_url


class EvidenceResponse(BaseModel):
    evidence_cards: list[EvidenceCard]


def _dedupe_results(results: list[SearchResult]) -> list[SearchResult]:
    seen: set[tuple[str, str]] = set()
    deduped: list[SearchResult] = []
    for result in results:
        key = (result.subquestion_id, normalize_url(result.url))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(result)
    return deduped


def _is_english_domain(url: str) -> bool:
    domain = extract_domain(url)
    if not domain:
        return False
    return not any(
        domain.endswith(tld) for tld in [".cn", ".com.cn", ".org.cn"]
    )


def _select_sources(
    results: list[SearchResult],
    max_sources: int,
    has_english_query: bool = False,
) -> list[SearchResult]:
    candidates = sorted(results, key=lambda r: r.score or 0, reverse=True)
    selected: list[SearchResult] = []
    selected_domains: set[str] = set()

    for candidate in candidates:
        if len(selected) >= max_sources:
            break
        domain = extract_domain(candidate.url)
        if domain and domain not in selected_domains:
            selected.append(candidate)
            selected_domains.add(domain)

    if has_english_query and selected and not any(
        _is_english_domain(s.url) for s in selected
    ):
        for candidate in candidates:
            if candidate not in selected and _is_english_domain(candidate.url):
                if len(selected) >= max_sources:
                    selected.pop()
                selected.append(candidate)
                break

    return selected


def _select_by_subquestion(
    results: list[SearchResult],
    max_sources_per_subquestion: int,
) -> dict[str, list[SearchResult]]:
    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    for result in results:
        grouped[result.subquestion_id].append(result)

    selected: dict[str, list[SearchResult]] = {}
    for subquestion_id, items in grouped.items():
        selected[subquestion_id] = _select_sources(
            items, max_sources_per_subquestion
        )
    return selected


def _fallback_extracted_sources(
    selected: list[SearchResult],
) -> list[ExtractedSource]:
    return [
        ExtractedSource(
            subquestion_id=result.subquestion_id,
            url=result.url,
            title=result.title,
            raw_content=result.content,
        )
        for result in selected
        if result.url and result.content
    ]


def _extract_sources_for_subquestion(
    search_client: SearchClient,
    subquestion_id: str,
    selected: list[SearchResult],
    errors: list[str],
) -> tuple[list[ExtractedSource], list[ExtractedSource]]:
    """Returns (extracted_sources, fallback_sources)."""
    urls = [result.url for result in selected]
    try:
        extracted = search_client.extract(urls, subquestion_id=subquestion_id)
    except Exception as exc:
        errors.append(f"Evidence extract failed for {subquestion_id}: {exc}")
        fallback = _fallback_extracted_sources(selected)
        return fallback, fallback

    extracted_keys = {normalize_url(source.url) for source in extracted}
    missing = [
        result
        for result in selected
        if normalize_url(result.url) not in extracted_keys
    ]
    fallback = _fallback_extracted_sources(missing) if missing else []
    return extracted, fallback


def _valid_source_urls(sources: list[ExtractedSource]) -> set[str]:
    urls = set()
    for source in sources:
        urls.add(source.url)
        urls.add(normalize_url(source.url))
    return urls


def _drop_invalid_cards(
    cards: list[EvidenceCard],
    sources: list[ExtractedSource],
    errors: list[str],
) -> list[EvidenceCard]:
    valid_urls = _valid_source_urls(sources)
    valid_cards: list[EvidenceCard] = []
    for card in cards:
        if (
            card.source_url not in valid_urls
            and normalize_url(card.source_url) not in valid_urls
        ):
            errors.append(
                f"EvidenceCard {card.id} has invalid source_url: {card.source_url}"
            )
            continue
        valid_cards.append(card)
    return valid_cards


def _validate_corroboration(
    card: EvidenceCard,
    extracted_urls: set[str],
    extracted_content_types: dict[str, str],
) -> EvidenceCard:
    # Check 1: corroborating URLs must exist in extracted sources
    valid_sources = [
        url
        for url in card.corroborating_sources
        if normalize_url(url) in extracted_urls or url in extracted_urls
    ]
    card.corroborating_sources = valid_sources

    # Check 2: corroborating sources must be from different domains
    main_domain = extract_domain(card.source_url)
    distinct_sources = [
        url
        for url in card.corroborating_sources
        if extract_domain(url) != main_domain
    ]
    card.corroborating_sources = distinct_sources

    # Check 3: strongly_corroborated needs >= 2 full-text corroborating sources
    if card.corroboration_level == "strongly_corroborated":
        full_text_count = sum(
            1
            for url in distinct_sources
            if extracted_content_types.get(url, "")
            == "extracted_content"
            or extracted_content_types.get(normalize_url(url), "")
            == "extracted_content"
        )
        if full_text_count < 2:
            card.corroboration_level = "weakly_corroborated"

    # Check 4: weakly_corroborated needs >= 1 valid corroborating source
    if card.corroboration_level == "weakly_corroborated" and not distinct_sources:
        card.corroboration_level = "single_source"

    return card


def _build_metrics(
    raw: list[SearchResult],
    deduped: list[SearchResult],
    extracted_sources: list[ExtractedSource],
    evidence_cards: list[EvidenceCard],
) -> dict[str, object]:
    return {
        "raw_search_results": len(raw),
        "deduped_sources": len(deduped),
        "duplicates_removed": len(raw) - len(deduped),
        "extracted_sources": len(extracted_sources),
        "evidence_cards": len(evidence_cards),
        "corroboration": dict(
            Counter(card.corroboration_level for card in evidence_cards)
        ),
    }


def make_prepare_evidence_node(
    search_client: SearchClient,
    llm: LLMClient,
    max_sources_per_subquestion: int,
):
    def prepare_evidence(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        raw_results = list(state.get("search_results", []))
        deduped = _dedupe_results(raw_results)
        selected_by_subquestion = _select_by_subquestion(
            deduped, max_sources_per_subquestion
        )

        extracted_sources: list[ExtractedSource] = []
        extracted_content_types: dict[str, str] = {}
        for subquestion_id, selected in selected_by_subquestion.items():
            success_sources, fallback_sources = _extract_sources_for_subquestion(
                search_client, subquestion_id, selected, errors
            )
            for src in success_sources:
                key = normalize_url(src.url)
                extracted_content_types[key] = "extracted_content"
                extracted_sources.append(src)
            for src in fallback_sources:
                key = normalize_url(src.url)
                if key not in extracted_content_types:
                    extracted_content_types[key] = "search_content"
                    extracted_sources.append(src)

        prompt = build_evidence_prompt(
            state.get("question", ""), extracted_sources
        )
        try:
            parsed = parse_json_object(llm.complete(prompt), EvidenceResponse)
            evidence_cards = _drop_invalid_cards(
                parsed.evidence_cards, extracted_sources, errors
            )
        except JSONParseError as exc:
            errors.append(f"Evidence JSON parse failed: {exc}")
            evidence_cards = []

        # Post-validate corroboration signals
        extracted_urls = {normalize_url(s.url) for s in extracted_sources}
        evidence_cards = [
            _validate_corroboration(card, extracted_urls, extracted_content_types)
            for card in evidence_cards
        ]

        evidence_metrics = _build_metrics(
            raw_results, deduped, extracted_sources, evidence_cards
        )
        return {
            **state,
            "search_results": deduped,
            "evidence_cards": evidence_cards,
            "evidence_metrics": evidence_metrics,
            "errors": errors,
        }

    return prepare_evidence
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_prepare_evidence_node.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/nodes/prepare_evidence.py tests/test_prepare_evidence_node.py
git commit -m "feat: replace source quality selection with relevance+diversity and cross-validation"
```

---

### Task 6: Update synthesizing prompt and node

**Files:**
- Modify: `src/deepresearch/prompts/synthesizing.py`
- Modify: `src/deepresearch/nodes/synthesizing.py`
- Modify: `tests/test_synthesizing_node.py`

- [ ] **Step 1: Update test_synthesizing_node.py — fix EvidenceCard construction**

In `tests/test_synthesizing_node.py`, replace every `EvidenceCard(...)` constructor call to remove `source_type`, `source_quality_score`, `evidence_reliability` and add `corroboration_level`/`corroborating_sources`. The file has many tests — here's the pattern for each:

Old pattern in tests:
```python
EvidenceCard(
    id="e1",
    subquestion_id="q1",
    claim="AI search summarizes results",
    source_url="https://example.com",
    source_title="Source",
    supporting_snippet="AI search summarizes results",
    content_type="extracted_content",
    source_type="industry_report",
    source_quality_score=85,
    evidence_reliability="high",
    confidence="high",
)
```

New pattern:
```python
EvidenceCard(
    id="e1",
    subquestion_id="q1",
    claim="AI search summarizes results",
    source_url="https://example.com",
    source_title="Source",
    supporting_snippet="AI search summarizes results",
    content_type="extracted_content",
    corroboration_level="single_source",
    corroborating_sources=[],
    confidence="high",
)
```

Update all 5 test functions in the file with this pattern change. Also remove `from deepresearch.state import EvidenceCard, SearchResult` → `from deepresearch.state import EvidenceCard` (SearchResult no longer needed in most tests). The `test_synthesize_notes_uses_evidence_cards` test keeps its assertion that `"EvidenceCard"` or `"evidence_cards"` appears in the prompt.

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_synthesizing_node.py -v
```

Expected: `ValidationError` because `source_type` is not a field of EvidenceCard.

- [ ] **Step 3: Update synthesizing prompt**

Replace `src/deepresearch/prompts/synthesizing.py`:

```python
from deepresearch.state import EvidenceCard, SubQuestion


def build_synthesizing_prompt(question: str, subquestions: list[SubQuestion], evidence_cards: list[EvidenceCard]) -> str:
    strong = [card for card in evidence_cards if card.corroboration_level == "strongly_corroborated"]
    weak = [card for card in evidence_cards if card.corroboration_level == "weakly_corroborated"]
    single = [card for card in evidence_cards if card.corroboration_level == "single_source"]

    sections = []

    if strong:
        sections.append("Strongly corroborated claims (3+ independent sources agree):")
        for card in strong:
            sections.append(f"- [{card.id}] {card.claim} (supported by: {', '.join(card.corroborating_sources)})")
        sections.append("")

    if weak:
        sections.append("Weakly corroborated claims (2 independent sources agree):")
        for card in weak:
            sections.append(f"- [{card.id}] {card.claim} (supported by: {', '.join(card.corroborating_sources)})")
        sections.append("")

    if single:
        sections.append("Single-source claims (only one source mentions this):")
        for card in single:
            sections.append(f"- [{card.id}] {card.claim} (source: {card.source_url})")
        sections.append("")

    stratified = "\n".join(sections)

    return f"""
You are a careful research analyst. Use only the supplied EvidenceCards.
Only summarize claims present in EvidenceCards. Do not introduce facts not supported by EvidenceCards.
Low corroboration evidence cannot support high confidence findings.
Every finding must be traceable to one of the supplied EvidenceCard source_url values.

Guidelines:
- Strongly corroborated claims form the backbone of findings
- Single-source claims may be included but should be noted as lower confidence
- Never elevate a single-source claim to a key finding unless it is uniquely
  important and the source is a primary source for that specific fact

Return only JSON in this exact shape:
{{"notes":[{{"subquestion_id":"q1","key_findings":["..."],"source_urls":["https://..."],"confidence":"low|medium|high"}}]}}

Original question:
{question}

Subquestions:
{[item.model_dump() for item in subquestions]}

{stratified}
""".strip()
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_synthesizing_node.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/prompts/synthesizing.py tests/test_synthesizing_node.py
git commit -m "feat: stratify evidence cards by corroboration level in synthesizing prompt"
```

---

### Task 7: Update writing prompt and node

**Files:**
- Modify: `src/deepresearch/prompts/writing.py`
- Modify: `tests/test_writing_prompt.py`
- Modify: `tests/test_writing_node.py`

- [ ] **Step 1: Update test_writing_prompt.py — fix EvidenceCard construction**

Replace `test_writing_prompt_uses_evidence_card_urls_when_provided` with updated version:

```python
from deepresearch.prompts.writing import build_writing_prompt
from deepresearch.state import EvidenceCard, SearchResult


def test_writing_prompt_requires_numbered_citations_and_lists_allowed_urls():
    results = [
        SearchResult(subquestion_id="q1", title="Source A", url="https://example.com/a", content="Content A"),
        SearchResult(subquestion_id="q1", title="Source B", url="https://example.com/b", content="Content B"),
    ]

    prompt = build_writing_prompt("AI search", [], [], results)

    assert "Use numbered citations in the body" in prompt
    assert "Do not put raw URLs in the body" in prompt
    assert "URLs may only appear in the ## Sources section" in prompt
    assert "Every citation number used in the body must be defined in ## Sources" in prompt
    assert "Every source listed in ## Sources must be cited in the body" in prompt
    assert "Only use URLs from the allowed source URL list" in prompt
    assert "Allowed source URLs" in prompt
    assert "https://example.com/a" in prompt
    assert "https://example.com/b" in prompt


def test_writing_prompt_uses_evidence_card_urls_when_provided():
    results = [
        SearchResult(
            subquestion_id="q1",
            title="Raw source",
            url="https://www.example.com/report?utm_source=x",
            content="Content",
        )
    ]
    evidence_cards = [
        EvidenceCard(
            id="e1",
            subquestion_id="q1",
            claim="Claim from normalized evidence.",
            source_url="https://example.com/report",
            source_title="Normalized source",
            supporting_snippet="Claim from normalized evidence.",
            content_type="extracted_content",
            corroboration_level="single_source",
            corroborating_sources=[],
            confidence="high",
        )
    ]

    prompt = build_writing_prompt("AI search", [], [], results, evidence_cards=evidence_cards)

    assert "https://example.com/report" in prompt
    assert "https://www.example.com/report?utm_source=x" not in prompt


def test_writing_prompt_includes_corroboration_guidance():
    results = [SearchResult(subquestion_id="q1", title="A", url="https://example.com/a", content="Content")]
    evidence_cards = [
        EvidenceCard(
            id="e1",
            subquestion_id="q1",
            claim="Claim.",
            source_url="https://example.com/a",
            source_title="A",
            supporting_snippet="Claim.",
            content_type="extracted_content",
            corroboration_level="single_source",
            corroborating_sources=[],
            confidence="medium",
        )
    ]

    prompt = build_writing_prompt("AI search", [], [], results, evidence_cards=evidence_cards)

    assert "supported by multiple independent sources" in prompt
    assert "single source" in prompt
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_writing_prompt.py -v
```

Expected: `test_writing_prompt_includes_corroboration_guidance` fails — no corroboration guidance in old prompt.

- [ ] **Step 3: Update writing prompt**

In `src/deepresearch/prompts/writing.py`, after the `Required sections:` block and before `Sources format:`, add:

```text
When citing claims in the report body:
- Claims supported by multiple independent sources should be presented
  with higher certainty
- When a claim comes from a single source, consider using language like
  "According to [source]..." or "One perspective suggests..." rather than
  stating it as uncontested fact
- If different sources present conflicting views, present both sides
  rather than choosing one
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_writing_prompt.py -v
```

Expected: all pass.

- [ ] **Step 5: Update test_writing_node.py — fix all EvidenceCard constructors**

In `tests/test_writing_node.py`, every EvidenceCard construction uses old fields. Replace them all. Pattern:

Old:
```python
EvidenceCard(
    id="e1",
    subquestion_id="q1",
    claim="...",
    source_url="...",
    source_title="...",
    supporting_snippet="...",
    content_type="extracted_content",
    source_type="industry_report",
    source_quality_score=85,
    evidence_reliability="high",
    confidence="high",
)
```

New:
```python
EvidenceCard(
    id="e1",
    subquestion_id="q1",
    claim="...",
    source_url="...",
    source_title="...",
    supporting_snippet="...",
    content_type="extracted_content",
    corroboration_level="single_source",
    corroborating_sources=[],
    confidence="high",
)
```

There are ~6 occurrences across tests. Update them all.

- [ ] **Step 6: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_writing_node.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add src/deepresearch/prompts/writing.py tests/test_writing_prompt.py tests/test_writing_node.py
git commit -m "feat: add corroboration-aware writing guidance"
```

---

### Task 8: Update verbose output

**Files:**
- Modify: `src/deepresearch/verbose.py`
- Modify: `tests/test_verbose.py`

- [ ] **Step 1: Update test_verbose.py**

Replace `test_format_verbose_summary_includes_evidence_metrics` and `test_format_verbose_summary_derives_query_count_from_search_queries_when_metrics_omit_it`:

```python
def test_format_verbose_summary_includes_evidence_metrics():
    state = {
        "subquestions": [
            SubQuestion(
                id="q1",
                question="What is AI search?",
                search_query="AI search",
                search_queries=["AI search", "AI retrieval"],
                rationale="Background",
            ),
            SubQuestion(id="q2", question="What are examples?", search_query="AI search examples", rationale="Examples"),
        ],
        "evidence_metrics": {
            "raw_search_results": 12,
            "deduped_sources": 8,
            "duplicates_removed": 4,
            "extracted_sources": 5,
            "evidence_cards": 9,
            "corroboration": {"strongly_corroborated": 3, "weakly_corroborated": 4, "single_source": 2},
        },
    }

    summary = format_verbose_summary(state)

    assert "Search coverage:" in summary
    assert "subquestions: 2" in summary
    assert "total queries: 3" in summary
    assert "raw search results: 12" in summary
    assert "deduped sources: 8" in summary
    assert "Evidence corroboration:" in summary
    assert "strongly_corroborated: 3" in summary
    assert "weakly_corroborated: 4" in summary
    assert "single_source: 2" in summary
    assert "Source quality:" not in summary
    assert "Evidence reliability:" not in summary


def test_format_verbose_summary_derives_query_count_from_search_queries_when_metrics_omit_it():
    state = {
        "subquestions": [
            SubQuestion(
                id="q1",
                question="What is AI search?",
                search_query="AI search",
                search_queries=["AI search", "neural search"],
                rationale="Background",
            )
        ],
        "evidence_metrics": {
            "raw_search_results": 4,
            "deduped_sources": 3,
            "duplicates_removed": 1,
            "extracted_sources": 2,
            "evidence_cards": 2,
        },
    }

    summary = format_verbose_summary(state)

    assert "subquestions: 1" in summary
    assert "total queries: 2" in summary
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_verbose.py -v
```

Expected: tests fail — old metrics still reference `source_quality` and `evidence_reliability`.

- [ ] **Step 3: Update verbose.py**

In `src/deepresearch/verbose.py`, replace the `Source quality:` and `Evidence reliability:` sections (lines 52-65 approximately) with:

```python
        lines.extend(["", "Evidence corroboration:"])
        corroboration = evidence_metrics.get("corroboration", {})
        if corroboration:
            for key in ["strongly_corroborated", "weakly_corroborated", "single_source"]:
                label = key.replace("_", " ")
                value = corroboration.get(key, 0)
                description = ""
                if key == "strongly_corroborated":
                    description = " (3+ independent sources agree)"
                elif key == "weakly_corroborated":
                    description = " (2 independent sources agree)"
                elif key == "single_source":
                    description = " (only one source mentions this)"
                lines.append(f"- {label}: {value}{description}")
        else:
            lines.append("- None")
```

Remove the old `Source quality:` block entirely. Remove the old `Evidence reliability:` block entirely.

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_verbose.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/verbose.py tests/test_verbose.py
git commit -m "feat: show evidence corroboration distribution in verbose output"
```

---

### Task 9: Update integration test

**Files:**
- Modify: `tests/test_integration_offline.py`

- [ ] **Step 1: Update integration test**

In `tests/test_integration_offline.py`, the fake LLM response for evidence cards and the expected metrics need updating.

Replace the evidence card LLM response:
```python
'{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"AI search uses generated answers.","source_url":"https://example.com/source","source_title":"Source","supporting_snippet":"AI search uses generated answers.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
```

Replace the expected `evidence_metrics` assertion:
```python
assert result["evidence_metrics"] == {
    "raw_search_results": 1,
    "deduped_sources": 1,
    "duplicates_removed": 0,
    "extracted_sources": 1,
    "evidence_cards": 1,
    "corroboration": {"single_source": 1},
}
```

Also remove the `from deepresearch.state import ExtractedSource, SearchResult` if ExtractedSource is no longer used (check if it's still imported).

- [ ] **Step 2: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_integration_offline.py -v
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_offline.py
git commit -m "test: update integration test for cross-validation metrics"
```

---

### Task 10: Run all tests and verify

**Files:**
- No file changes unless fixes needed.

- [ ] **Step 1: Run full test suite**

Run:
```bash
uv run pytest -v
```

Expected: all tests pass. If any test failures, fix them before proceeding.

- [ ] **Step 2: Check import of removed modules works**

Run:
```bash
uv run python -c "from deepresearch.graph import create_research_app; print('OK')"
```

Expected: `OK`.

- [ ] **Step 3: Verify no references to deleted symbols**

Run:
```bash
uv run python -c "from deepresearch.state import SourceType; print('STILL EXISTS')"
```

Expected: `ImportError` — `SourceType` no longer exists.

Run:
```bash
uv run python -c "from deepresearch.state import EvidenceReliability; print('STILL EXISTS')"
```

Expected: `ImportError`.

- [ ] **Step 4: Check git status**

Run:
```bash
git status --short
```

Expected: clean.

- [ ] **Step 5: Commit (if any fixes were needed)**

If fixes were needed during Step 1, commit them. Otherwise no commit.

---

### Task 11: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update evidence pipeline section**

Replace the v0.2 evidence pipeline description in README with:

```markdown
## Evidence pipeline

v0.3 uses a cross-validation evidence pipeline:

```text
search → relevance + diversity selection → extract → EvidenceCard with cross-validation → notes → report
```

Search results are treated as candidate sources. Sources are selected by Tavily relevance score with domain diversity constraints (no same-domain duplicates per subquestion). EvidenceCards include corroboration_level (single_source / weakly_corroborated / strongly_corroborated) based on how many independent-domain sources support each claim.

Verbose mode reports search coverage and evidence corroboration distribution.
```

Update the workflow text from 7 steps to mention cross-validation. Update any references to v0.2 → v0.3 or "source quality" → "cross-validation".

- [ ] **Step 2: Run tests**

Run:
```bash
uv run pytest -v
```

Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for v0.3 cross-validation pipeline"
```

---

### Task 12: Online acceptance

**Files:**
- Create: `docs/superpowers/reports/2026-06-12-v0.3-online-acceptance-report.md`

- [ ] **Step 1: Get explicit authorization before API calls**

Confirm with user before making external API calls.

- [ ] **Step 2: Run online commands**

```bash
uv run deepresearch "AI 搜索引擎的发展趋势" --verbose
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --verbose
uv run deepresearch "新能源汽车固态电池商业化进展" --verbose
```

- [ ] **Step 3: Record metrics**

For each report record: result, output_path, EvidenceCard count, distinct source count, corroboration distribution, review score.

- [ ] **Step 4: Determine acceptance**

Pass if:
- at least 2/3 success
- EvidenceCard >= 5 for each success
- unique sources >= 3 for each success
- strongly + weakly corroborated >= 50% for each success
- review score >= 85 for each success

- [ ] **Step 5: Write report and commit**

```bash
git add docs/superpowers/reports/2026-06-12-v0.3-online-acceptance-report.md
git commit -m "docs: add v0.3 online acceptance report"
```

---

## Self-Review

Spec coverage:

- Remove hardcoded scoring: Tasks 1, 3.
- Relevance + diversity selection: Task 5 (in `_select_sources`).
- Cross-validation in EvidenceCard prompt: Task 4.
- Post-validation of corroboration signals: Task 5 (in `_validate_corroboration`).
- Synthesize_notes stratifies by corroboration: Task 6.
- Write_report with corroboration guidance: Task 7.
- Verbose output shows corroboration distribution: Task 8.
- README update: Task 11.
- Integration test fix: Task 9.
- Online acceptance: Task 12.

No placeholders remain. All steps include actual code.
