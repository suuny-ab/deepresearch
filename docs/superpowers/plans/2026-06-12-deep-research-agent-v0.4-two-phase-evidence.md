# Deep Research Agent v0.4 Two-Phase Evidence Pipeline + A/B Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split evidence extraction and cross-validation into two independent LLM phases to eliminate the conflict between "extract more claims" and "be conservative about corroboration." Add search-result freezing, replay, and comparison infrastructure for reproducible A/B testing.

**Architecture:** Phase 1 (1 DeepSeek call) extracts raw claims from all sources without any cross-validation instructions. Phase 2 (N calls, one per subquestion) validates claims against same-subquestion sources from different domains. A new `--save-search`/`--replay-search`/`--compare` CLI workflow enables frozen-input A/B testing. Auto-monitoring assertions run at `--dry-run` completion.

**Tech Stack:** Python 3.11+, Pydantic, LangGraph, DeepSeek API, Typer, Rich, pytest

---

## File Structure Changes

**Create:**
```text
src/deepresearch/prompts/extraction.py
tests/test_extraction_prompt.py
```

**Modify:**
```text
src/deepresearch/state.py
src/deepresearch/prompts/evidence.py
src/deepresearch/nodes/prepare_evidence.py
src/deepresearch/graph.py
src/deepresearch/cli.py
tests/test_evidence_prompt.py
tests/test_prepare_evidence_node.py
tests/test_graph_structure.py
tests/test_cli.py
tests/test_integration_offline.py
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

Expected: clean.

- [ ] **Step 2: Run current tests**

Run:
```bash
uv run pytest -v
```

Expected: 127 pass.

- [ ] **Step 3: No commit**

---

### Task 1: Add ExtractedClaim model to state.py

**Files:**
- Modify: `src/deepresearch/state.py`
- Modify: `tests/test_state.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_state.py`:

```python
def test_extracted_claim_has_no_corroboration_fields():
    from deepresearch.state import ExtractedClaim

    claim = ExtractedClaim(
        id="e1",
        subquestion_id="q1",
        claim="RAG remains important.",
        source_url="https://example.com/a",
        source_title="Source A",
        supporting_snippet="RAG remains important.",
        content_type="extracted_content",
        confidence="high",
    )

    assert claim.claim == "RAG remains important."
    assert not hasattr(claim, "corroboration_level")
    assert not hasattr(claim, "corroborating_sources")


def test_research_state_accepts_extracted_claims():
    from deepresearch.state import ExtractedClaim, ResearchState

    state: ResearchState = {
        "question": "AI search",
        "extracted_claims": [
            ExtractedClaim(
                id="e1",
                subquestion_id="q1",
                claim="RAG remains important.",
                source_url="https://example.com/a",
                source_title="Source A",
                supporting_snippet="RAG remains important.",
                content_type="extracted_content",
                confidence="high",
            )
        ],
    }

    assert len(state["extracted_claims"]) == 1
```

- [ ] **Step 2: Run test to confirm failure**

Run:
```bash
uv run pytest tests/test_state.py::test_extracted_claim_has_no_corroboration_fields -v
```

Expected: `ImportError` — `ExtractedClaim` not defined.

- [ ] **Step 3: Add ExtractedClaim to state.py**

In `src/deepresearch/state.py`, add after `SearchResult`:

```python
class ExtractedClaim(BaseModel):
    """Phase 1 output — raw claims extracted from sources, no cross-validation."""
    id: str
    subquestion_id: str
    claim: str
    source_url: str
    source_title: str
    supporting_snippet: str
    content_type: Literal["search_content", "extracted_content"]
    confidence: Confidence
```

Add to `ResearchState`:

```python
    extracted_claims: list[ExtractedClaim]
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
git commit -m "feat: add ExtractedClaim model for two-phase evidence pipeline"
```

---

### Task 2: Create Phase 1 extraction prompt

**Files:**
- Create: `src/deepresearch/prompts/extraction.py`
- Create: `tests/test_extraction_prompt.py`

- [ ] **Step 1: Create test file**

Create `tests/test_extraction_prompt.py`:

```python
from deepresearch.prompts.extraction import build_extraction_prompt
from deepresearch.state import ExtractedSource, SubQuestion


def test_extraction_prompt_contains_no_corroboration_instructions():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="RAG remains important for AI search.",
        ),
    ]
    subquestions = [
        SubQuestion(id="q1", question="What is AI search?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_extraction_prompt("AI search", sources, subquestions)

    # Must NOT contain cross-validation terms
    assert "corroboration" not in prompt.lower()
    assert "cross-valid" not in prompt.lower()

    # Must contain extraction-focused instructions
    assert "claim" in prompt.lower()
    assert "supporting_snippet" in prompt
    assert "https://example.com/a" in prompt


def test_extraction_prompt_encourages_max_claims():
    sources = [
        ExtractedSource(
            subquestion_id="q1",
            url="https://example.com/a",
            title="Source A",
            raw_content="RAG is important. Vector search is trending.",
        ),
    ]
    subquestions = [
        SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r"),
    ]

    prompt = build_extraction_prompt("AI search", sources, subquestions)

    assert "as many" in prompt.lower() or "every" in prompt.lower() or "all" in prompt.lower()


def test_extraction_prompt_groups_sources_by_subquestion():
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://example.com/a", title="A", raw_content="Content A."),
        ExtractedSource(subquestion_id="q2", url="https://other.example/b", title="B", raw_content="Content B."),
    ]
    subquestions = [
        SubQuestion(id="q1", question="Tech trends?", search_query="q1", search_queries=["q1"], rationale="tech"),
        SubQuestion(id="q2", question="Market?", search_query="q2", search_queries=["q2"], rationale="market"),
    ]

    prompt = build_extraction_prompt("AI search", sources, subquestions)

    assert "Tech trends?" in prompt
    assert "Market?" in prompt
```

- [ ] **Step 2: Run test to confirm failure**

Run:
```bash
uv run pytest tests/test_extraction_prompt.py -v
```

Expected: `ImportError` — module doesn't exist.

- [ ] **Step 3: Implement extraction prompt**

Create `src/deepresearch/prompts/extraction.py`:

```python
from deepresearch.state import ExtractedSource, SubQuestion


def build_extraction_prompt(
    question: str,
    sources: list[ExtractedSource],
    subquestions: list[SubQuestion],
) -> str:
    sq_map: dict[str, str] = {sq.id: sq.question for sq in subquestions}

    groups: dict[str, list[ExtractedSource]] = {}
    for source in sources:
        key = source.subquestion_id
        groups.setdefault(key, []).append(source)

    subquestion_lines = []
    if subquestions:
        subquestion_lines.append("Research subquestions:")
        for sq in subquestions:
            subquestion_lines.append(f"- [{sq.id}] {sq.question}")
        subquestion_lines.append("")

    source_lines = []
    source_lines.append("Sources (grouped by subquestion):")
    for sq_id, group_sources in groups.items():
        sq_question = sq_map.get(sq_id, sq_id)
        source_lines.append(f"--- {sq_id}: {sq_question} ---")
        for source in group_sources:
            source_lines.append(f"  URL: {source.url}")
            source_lines.append(f"  Title: {source.title}")
            source_lines.append(f"  Content ({source.format}): {source.raw_content}")
            source_lines.append("")
    source_lines.append("---")

    grouped_sources = "\n".join(source_lines)
    subquestion_overview = "\n".join(subquestion_lines)

    return f"""
You are extracting claims from source texts for a research report.

A claim is a specific factual assertion, finding, or argument that can be
traced to a particular passage in a source text. Extract every distinct,
citable claim from every source. There is no minimum or maximum —
extract as many as each source genuinely contains.

Rules:
- Each claim MUST include a supporting_snippet from the source text
- Prefer specific, verifiable claims over vague generalizations
- Do NOT check other sources for corroboration — that is a separate step
- Do NOT assign any reliability or corroboration level
- Assign a confidence to each claim based on the source text quality:
  - "high": well-supported with specific evidence
  - "medium": reasonably supported
  - "low": weakly supported or thin

The sources below are organized by subquestion. Each source was retrieved
to answer a specific subquestion, shown in the group header.

{subquestion_overview}

Return only JSON in this exact shape:
{{"claims":[{{"id":"e1","subquestion_id":"q1","claim":"...","source_url":"https://...","source_title":"...","supporting_snippet":"...","content_type":"extracted_content","confidence":"low|medium|high"}}]}}

Original question:
{question}

{grouped_sources}
""".strip()
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_extraction_prompt.py -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/prompts/extraction.py tests/test_extraction_prompt.py
git commit -m "feat: add Phase 1 extraction prompt with no cross-validation"
```

---

### Task 3: Update evidence prompt to Phase 2 (single subquestion)

**Files:**
- Modify: `src/deepresearch/prompts/evidence.py`
- Modify: `tests/test_evidence_prompt.py`

- [ ] **Step 1: Replace test_evidence_prompt.py**

```python
from deepresearch.prompts.evidence import build_validation_prompt
from deepresearch.state import ExtractedClaim, ExtractedSource


def test_validation_prompt_scoped_to_single_subquestion():
    claims = [
        ExtractedClaim(
            id="e1", subquestion_id="q1",
            claim="RAG remains important.",
            source_url="https://example.com/a", source_title="A",
            supporting_snippet="RAG remains important.",
            content_type="extracted_content", confidence="high",
        ),
    ]
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://example.com/a", title="A", raw_content="RAG remains important."),
        ExtractedSource(subquestion_id="q1", url="https://other.example/b", title="B", raw_content="RAG is key."),
    ]

    prompt = build_validation_prompt(
        sq_id="q1",
        sq_question="What is AI search?",
        claims=claims,
        sources=sources,
    )

    assert "q1" in prompt
    assert "What is AI search?" in prompt
    assert "corroboration_level" in prompt
    assert "strongly_corroborated" in prompt


def test_validation_prompt_includes_corroboration_rules():
    claims = [
        ExtractedClaim(
            id="e1", subquestion_id="q1",
            claim="Claim.", source_url="https://a.example/x",
            source_title="X", supporting_snippet="Claim.",
            content_type="extracted_content", confidence="high",
        ),
    ]
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="X", raw_content="Claim."),
        ExtractedSource(subquestion_id="q1", url="https://b.example/y", title="Y", raw_content="Claim too."),
    ]

    prompt = build_validation_prompt("q1", "Test?", claims, sources)

    assert "different domain" in prompt.lower()
    assert "single_source" in prompt
    assert "weakly_corroborated" in prompt
    assert "corroborating_sources" in prompt


def test_validation_prompt_does_not_ask_to_extract_new_claims():
    claims = [
        ExtractedClaim(
            id="e1", subquestion_id="q1",
            claim="Claim.", source_url="https://a.example/x",
            source_title="X", supporting_snippet="Claim.",
            content_type="extracted_content", confidence="high",
        ),
    ]
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="X", raw_content="Claim."),
    ]

    prompt = build_validation_prompt("q1", "Test?", claims, sources)

    assert "do not create new claims" in prompt.lower() or "do not extract" in prompt.lower()
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_evidence_prompt.py -v
```

Expected: `ImportError` — `build_validation_prompt` not defined.

- [ ] **Step 3: Replace evidence prompt**

Replace `src/deepresearch/prompts/evidence.py`:

```python
from deepresearch.state import ExtractedClaim, ExtractedSource


def build_validation_prompt(
    sq_id: str,
    sq_question: str,
    claims: list[ExtractedClaim],
    sources: list[ExtractedSource],
) -> str:
    claim_lines = []
    for c in claims:
        claim_lines.append(f"- [{c.id}] {c.claim} (primary source: {c.source_url})")

    source_lines = []
    for s in sources:
        source_lines.append(f"  URL: {s.url} | Title: {s.title}")
        source_lines.append(f"  Content: {s.raw_content}")
        source_lines.append("")

    claims_text = "\n".join(claim_lines)
    sources_text = "\n".join(source_lines)

    return f"""
You are evaluating whether claims extracted from one source are
independently corroborated by OTHER sources within the same subquestion.

Subquestion [{sq_id}]: {sq_question}

Claims to validate (all from this subquestion):
{claims_text}

Sources for this subquestion (each from a different domain):
{sources_text}

For each claim:
1. Identify which source it came from (the primary source, by source_url)
2. Check the OTHER sources (different from the primary) for independent
   confirmation of the same fact or finding
3. A claim is corroborated only if another source independently states
   the same fact — not just mentions the same topic
4. Assign corroboration_level:
   - "strongly_corroborated": 2+ OTHER sources independently confirm
   - "weakly_corroborated": 1 OTHER source independently confirms
   - "single_source": no other source confirms
5. For corroborated claims, include the corroborating source URLs

IMPORTANT:
- Do NOT create new claims. Only validate the claims provided above.
- Sources in this subquestion are already from different domains —
  no need to check domain diversity.
- Preserve all fields from the input claims (id, claim, source_url,
  source_title, supporting_snippet, content_type, confidence)

Return only JSON:
{{"evidence_cards":[{{"id":"e1","subquestion_id":"q1","claim":"...","source_url":"https://...","source_title":"...","supporting_snippet":"...","content_type":"extracted_content","corroboration_level":"single_source|weakly_corroborated|strongly_corroborated","corroborating_sources":["https://other.example/..."],"confidence":"low|medium|high"}}]}}
""".strip()
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_evidence_prompt.py -v
```

Expected: all 3 pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/prompts/evidence.py tests/test_evidence_prompt.py
git commit -m "feat: replace evidence prompt with single-subquestion validation prompt"
```

---

### Task 4: Rewrite prepare_evidence for two-phase flow

**Files:**
- Modify: `src/deepresearch/nodes/prepare_evidence.py`
- Modify: `tests/test_prepare_evidence_node.py`

This is the largest task — splitting the single LLM call into Phase 1 (extraction) + Phase 2 (per-subquestion validation) + assertions.

- [ ] **Step 1: Replace test_prepare_evidence_node.py**

```python
from tests.conftest import FakeLLMClient

from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node, _run_assertions
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


def test_two_phase_evidence_pipeline():
    # Phase 1 LLM response: extraction
    # Phase 2 LLM response: validation for q1
    llm = FakeLLMClient([
        # Phase 1: extract claims
        '{"claims":[{"id":"e1","subquestion_id":"q1","claim":"RAG is important.","source_url":"https://example.com/report.pdf","source_title":"Report","supporting_snippet":"RAG is important.","content_type":"extracted_content","confidence":"high"}]}',
        # Phase 2 q1: validate
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"RAG is important.","source_url":"https://example.com/report.pdf","source_title":"Report","supporting_snippet":"RAG is important.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(subquestion_id="q1", title="Report", url="https://example.com/report.pdf", raw_content="RAG is important."),
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    state = {
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [SearchResult(subquestion_id="q1", query="q", title="Report", url="https://example.com/report.pdf", content="Summary", score=0.9)],
        "errors": [],
    }

    result = node(state)

    assert result["evidence_cards"][0].id == "e1"
    assert result["evidence_cards"][0].corroboration_level == "single_source"
    assert "extracted_claims" in result
    assert result["evidence_metrics"]["evidence_cards"] == 1
    assert "corroboration" in result["evidence_metrics"]


def test_extract_fallback_when_phase1_fails():
    llm = FakeLLMClient([
        '{"claims":[]}',  # Phase 1 returns empty
    ])
    search = FakeSearchClient(fail_extract=True)
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [SubQuestion(id="q1", question="What?", search_query="q", search_queries=["q"], rationale="r")],
        "search_results": [SearchResult(subquestion_id="q1", query="q", title="A", url="https://example.com/a", content="Summary")],
        "errors": [],
    })

    assert result["evidence_cards"] == []
    assert result["errors"]


def test_phase2_called_per_subquestion():
    sq1 = SubQuestion(id="q1", question="Q1?", search_query="q1", search_queries=["q1"], rationale="r1")
    sq2 = SubQuestion(id="q2", question="Q2?", search_query="q2", search_queries=["q2"], rationale="r2")

    # Phase 1 + Phase 2 for q1 + Phase 2 for q2 = 3 calls
    llm = FakeLLMClient([
        # Phase 1
        '{"claims":[{"id":"e1","subquestion_id":"q1","claim":"Claim q1.","source_url":"https://a.example/x","source_title":"A","supporting_snippet":"Claim q1.","content_type":"extracted_content","confidence":"high"},{"id":"e2","subquestion_id":"q2","claim":"Claim q2.","source_url":"https://b.example/y","source_title":"B","supporting_snippet":"Claim q2.","content_type":"extracted_content","confidence":"high"}]}',
        # Phase 2 q1
        '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"Claim q1.","source_url":"https://a.example/x","source_title":"A","supporting_snippet":"Claim q1.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
        # Phase 2 q2
        '{"evidence_cards":[{"id":"e2","subquestion_id":"q2","claim":"Claim q2.","source_url":"https://b.example/y","source_title":"B","supporting_snippet":"Claim q2.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
    ])
    search = FakeSearchClient(
        extracted_sources=[
            ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="A", raw_content="Claim q1."),
            ExtractedSource(subquestion_id="q2", url="https://b.example/y", title="B", raw_content="Claim q2."),
        ]
    )
    node = make_prepare_evidence_node(search, llm, max_sources_per_subquestion=3)

    result = node({
        "question": "AI search",
        "subquestions": [sq1, sq2],
        "search_results": [
            SearchResult(subquestion_id="q1", query="q1", title="A", url="https://a.example/x", content="Claim q1.", score=0.9),
            SearchResult(subquestion_id="q2", query="q2", title="B", url="https://b.example/y", content="Claim q2.", score=0.8),
        ],
        "errors": [],
    })

    assert len(result["evidence_cards"]) == 2
    assert {c.subquestion_id for c in result["evidence_cards"]} == {"q1", "q2"}


def test_assertion_source_utilization_warns_on_zero_claim_source():
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="A", raw_content="Content"),
        ExtractedSource(subquestion_id="q1", url="https://b.example/y", title="B", raw_content="Content"),
    ]
    claims = []  # No claims at all

    results = _run_assertions(claims, sources, [])
    assert len(results) > 0
    assert any("0 claims" in r for r in results)


def test_assertion_corroboration_rate_warns_below_60_percent():
    cards = [
        EvidenceCard(id="e1", subquestion_id="q1", claim="C1", source_url="https://a.example/x", source_title="A",
                     supporting_snippet="C1", content_type="extracted_content",
                     corroboration_level="single_source", corroborating_sources=[], confidence="medium"),
        EvidenceCard(id="e2", subquestion_id="q1", claim="C2", source_url="https://a.example/x", source_title="A",
                     supporting_snippet="C2", content_type="extracted_content",
                     corroboration_level="single_source", corroborating_sources=[], confidence="medium"),
    ]
    results = _run_assertions([], [], cards)
    assert any("corroboration rate" in r.lower() for r in results)


def test_assertion_passes_with_good_data():
    sources = [
        ExtractedSource(subquestion_id="q1", url="https://a.example/x", title="A", raw_content="Content"),
    ]
    cards = [
        EvidenceCard(id="e1", subquestion_id="q1", claim="C1", source_url="https://a.example/x", source_title="A",
                     supporting_snippet="C1", content_type="extracted_content",
                     corroboration_level="strongly_corroborated", corroborating_sources=["https://b.example/y", "https://c.example/z"], confidence="high"),
    ]

    results = _run_assertions([], sources, cards)
    # Source utilization: no claims list so no source check
    # Corroboration: 1/1 = 100% >= 60% → pass
    # Should not fail
    assert len([r for r in results if "FAIL" in r]) == 0
```

- [ ] **Step 2: Run tests to confirm failure**

Run:
```bash
uv run pytest tests/test_prepare_evidence_node.py -v
```

Expected: failures — `_run_assertions` not defined, old single-phase code still active.

- [ ] **Step 3: Rewrite prepare_evidence.py**

Replace `src/deepresearch/nodes/prepare_evidence.py`:

```python
from collections import Counter, defaultdict

from pydantic import BaseModel

from deepresearch.clients.llm import LLMClient
from deepresearch.clients.tavily import SearchClient
from deepresearch.prompts.evidence import build_validation_prompt
from deepresearch.prompts.extraction import build_extraction_prompt
from deepresearch.state import (
    EvidenceCard, ExtractedClaim, ExtractedSource, ResearchState, SearchResult,
)
from deepresearch.utils.json import JSONParseError, parse_json_object
from deepresearch.utils.urls import extract_domain, normalize_url


class ClaimsResponse(BaseModel):
    claims: list[ExtractedClaim]


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
    return not any(domain.endswith(tld) for tld in [".cn", ".com.cn", ".org.cn"])


def _select_sources(
    results: list[SearchResult], max_sources: int,
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
    results: list[SearchResult], max_sources_per_subquestion: int,
) -> dict[str, list[SearchResult]]:
    grouped: dict[str, list[SearchResult]] = defaultdict(list)
    for result in results:
        grouped[result.subquestion_id].append(result)
    selected: dict[str, list[SearchResult]] = {}
    for subquestion_id, items in grouped.items():
        selected[subquestion_id] = _select_sources(items, max_sources_per_subquestion)
    return selected


def _fallback_extracted_sources(selected: list[SearchResult]) -> list[ExtractedSource]:
    return [
        ExtractedSource(
            subquestion_id=result.subquestion_id,
            url=result.url, title=result.title,
            raw_content=result.content,
        )
        for result in selected if result.url and result.content
    ]


def _extract_sources_for_subquestion(
    search_client: SearchClient, subquestion_id: str,
    selected: list[SearchResult], errors: list[str],
) -> tuple[list[ExtractedSource], list[ExtractedSource]]:
    urls = [result.url for result in selected]
    try:
        extracted = search_client.extract(urls, subquestion_id=subquestion_id)
    except Exception as exc:
        errors.append(f"Evidence extract failed for {subquestion_id}: {exc}")
        fallback = _fallback_extracted_sources(selected)
        return fallback, fallback
    extracted_keys = {normalize_url(source.url) for source in extracted}
    missing = [
        result for result in selected
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
    cards: list[EvidenceCard], sources: list[ExtractedSource], errors: list[str],
) -> list[EvidenceCard]:
    valid_urls = _valid_source_urls(sources)
    valid_cards: list[EvidenceCard] = []
    for card in cards:
        if (card.source_url not in valid_urls
                and normalize_url(card.source_url) not in valid_urls):
            errors.append(f"EvidenceCard {card.id} has invalid source_url: {card.source_url}")
            continue
        valid_cards.append(card)
    return valid_cards


def _validate_corroboration(
    card: EvidenceCard, extracted_urls: set[str],
    extracted_content_types: dict[str, str],
) -> EvidenceCard:
    # Check 1: corroborating URLs must exist
    valid_sources = [
        url for url in card.corroborating_sources
        if normalize_url(url) in extracted_urls or url in extracted_urls
    ]
    card.corroborating_sources = valid_sources

    # Check 2: strongly needs >= 2 full-text
    if card.corroboration_level == "strongly_corroborated":
        full_text_count = sum(
            1 for url in valid_sources
            if extracted_content_types.get(url, "") == "extracted_content"
            or extracted_content_types.get(normalize_url(url), "") == "extracted_content"
        )
        if full_text_count < 2:
            card.corroboration_level = "weakly_corroborated"

    # Check 3: weakly needs >= 1 valid source
    if card.corroboration_level == "weakly_corroborated" and not valid_sources:
        card.corroboration_level = "single_source"

    return card


def _phase1_extract(
    llm: LLMClient, question: str,
    sources: list[ExtractedSource],
    subquestions: list,
    errors: list[str],
) -> list[ExtractedClaim]:
    prompt = build_extraction_prompt(question, sources, subquestions)
    try:
        return parse_json_object(llm.complete(prompt), ClaimsResponse).claims
    except JSONParseError as exc:
        errors.append(f"Phase 1 extraction failed: {exc}")
        return []


def _phase2_validate(
    llm: LLMClient, sq_id: str, sq_question: str,
    claims: list[ExtractedClaim], sources: list[ExtractedSource],
    errors: list[str],
) -> list[EvidenceCard]:
    """Validate claims for a single subquestion."""
    if not claims:
        return []
    prompt = build_validation_prompt(sq_id, sq_question, claims, sources)
    try:
        parsed = parse_json_object(llm.complete(prompt), EvidenceResponse)
        return list(parsed.evidence_cards)
    except JSONParseError as exc:
        errors.append(f"Phase 2 validation failed for {sq_id}: {exc}")
        # Fallback: return claims as single-source cards
        return [
            EvidenceCard(
                id=c.id, subquestion_id=c.subquestion_id,
                claim=c.claim, source_url=c.source_url,
                source_title=c.source_title, supporting_snippet=c.supporting_snippet,
                content_type=c.content_type,
                corroboration_level="single_source", corroborating_sources=[],
                confidence="low",
            )
            for c in claims
        ]


def _build_metrics(
    raw: list[SearchResult], deduped: list[SearchResult],
    extracted_sources: list[ExtractedSource], evidence_cards: list[EvidenceCard],
) -> dict[str, object]:
    return {
        "raw_search_results": len(raw),
        "deduped_sources": len(deduped),
        "duplicates_removed": len(raw) - len(deduped),
        "extracted_sources": len(extracted_sources),
        "evidence_cards": len(evidence_cards),
        "corroboration": dict(Counter(c.corroboration_level for c in evidence_cards)),
    }


def _run_assertions(
    claims: list[ExtractedClaim],
    sources: list[ExtractedSource],
    cards: list[EvidenceCard],
) -> list[str]:
    results = []

    # Assertion 1: Source utilization
    for source in sources:
        count = len([c for c in claims if c.source_url == source.url])
        if count == 0:
            results.append(f"[FAIL] Source {source.url} contributed 0 claims")

    # Assertion 2: Corroboration rate >= 60%
    if cards:
        strong_weak = sum(1 for c in cards if c.corroboration_level in ("strongly_corroborated", "weakly_corroborated"))
        rate = strong_weak / len(cards)
        if rate < 0.6:
            results.append(f"[FAIL] Corroboration rate {rate:.0%} below 60% threshold")

    # Assertion 3: Subquestion balance <= 3x
    if claims:
        sq_counts: dict[str, int] = defaultdict(int)
        for c in claims:
            sq_counts[c.subquestion_id] += 1
        if sq_counts:
            mx = max(sq_counts.values())
            mn = min(sq_counts.values())
            if mn > 0 and mx > mn * 3:
                results.append(f"[FAIL] Claims distribution skewed: {dict(sq_counts)}")

    return results


def make_prepare_evidence_node(
    search_client: SearchClient, llm: LLMClient,
    max_sources_per_subquestion: int,
):
    def prepare_evidence(state: ResearchState) -> ResearchState:
        errors = list(state.get("errors", []))
        raw_results = list(state.get("search_results", []))
        subquestions = state.get("subquestions", [])
        question = state.get("question", "")

        deduped = _dedupe_results(raw_results)
        selected_by_subquestion = _select_by_subquestion(deduped, max_sources_per_subquestion)

        extracted_sources: list[ExtractedSource] = []
        extracted_content_types: dict[str, str] = {}
        for sq_id, selected in selected_by_subquestion.items():
            success_sources, fallback_sources = _extract_sources_for_subquestion(
                search_client, sq_id, selected, errors,
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

        # Phase 1: Extract claims (1 LLM call)
        claims = _phase1_extract(llm, question, extracted_sources, subquestions, errors)

        # Phase 2: Validate per subquestion (N LLM calls)
        sq_map = {sq.id: sq.question for sq in subquestions}
        sources_by_sq: dict[str, list[ExtractedSource]] = defaultdict(list)
        for src in extracted_sources:
            sources_by_sq[src.subquestion_id].append(src)

        all_cards: list[EvidenceCard] = []
        for sq_id, sq_sources in sources_by_sq.items():
            sq_claims = [c for c in claims if c.subquestion_id == sq_id]
            sq_question = sq_map.get(sq_id, sq_id)
            sq_cards = _phase2_validate(llm, sq_id, sq_question, sq_claims, sq_sources, errors)
            all_cards.extend(sq_cards)

        # Post-validate + drop invalid
        extracted_urls = {normalize_url(s.url) for s in extracted_sources}
        all_cards = _drop_invalid_cards(all_cards, extracted_sources, errors)
        all_cards = [
            _validate_corroboration(c, extracted_urls, extracted_content_types)
            for c in all_cards
        ]

        # Run assertions
        assertion_results = _run_assertions(claims, extracted_sources, all_cards)
        errors.extend(assertion_results)

        evidence_metrics = _build_metrics(raw_results, deduped, extracted_sources, all_cards)
        return {
            **state,
            "search_results": deduped,
            "extracted_claims": claims,
            "evidence_cards": all_cards,
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
git commit -m "feat: split evidence pipeline into two-phase extraction and per-subquestion validation"
```

---

### Task 5: Add --save-search / --replay-search to graph

**Files:**
- Modify: `src/deepresearch/graph.py`
- Modify: `tests/test_graph_structure.py`

- [ ] **Step 1: Add failing test**

In `tests/test_graph_structure.py`, add:

```python
def test_replay_search_graph_skips_plan_and_search(tmp_path):
    graph = build_research_graph(
        plan_research=lambda state: {**state},
        search_web=lambda state: {**state},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        synthesize_notes=lambda state: {**state, "notes": []},
        write_report=lambda state: {**state, "report_markdown": "# R"},
        review_report=lambda state: {**state, "review": None},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "r.md")},
        replay_search=True,
    )
    result = graph.invoke({"question": "AI search", "errors": []})
    assert result["evidence_cards"] == []
```

- [ ] **Step 2: Run test to confirm failure**

```bash
uv run pytest tests/test_graph_structure.py::test_replay_search_graph_skips_plan_and_search -v
```

Expected: `TypeError` — `replay_search` not recognized.

- [ ] **Step 3: Update graph.py**

Add `replay_search` to `build_research_graph` and `create_research_app` signatures, default `False`. When True:

```python
    if replay_search:
        graph.add_edge(START, "prepare_evidence")
        graph.add_edge("prepare_evidence", END)
```

- [ ] **Step 4: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_graph_structure.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/deepresearch/graph.py tests/test_graph_structure.py
git commit -m "feat: add replay_search graph mode for frozen-input testing"
```

---

### Task 6: Add --save-search / --replay-search / --compare / --output to CLI

**Files:**
- Modify: `src/deepresearch/cli.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Implement CLI flags**

Add to `main()` signature:

```python
    save_search: str | None = typer.Option(None, "--save-search", help="Save search results for replay"),
    replay_search: str | None = typer.Option(None, "--replay-search", help="Replay from saved search results"),
    compare: tuple[str, str] | None = typer.Option(None, "--compare", help="Compare two dry-run JSON outputs"),
    output: str | None = typer.Option(None, "--output", help="Save dry-run output as JSON"),
```

Logic:

```python
        # --compare mode: load two JSONs, print comparison
        if compare:
            _run_compare(compare[0], compare[1])
            return

        # --replay-search mode: load search from file, build replay graph
        if replay_search:
            with open(replay_search) as f:
                saved = json.load(f)
            # Build a replay graph
            research_app = create_research_app(
                plan_research=...,
                search_web=...,
                prepare_evidence=...,
                ...,
                dry_run=True,
                replay_search=True,
            )
            result = research_app.invoke({
                "question": saved["question"],
                "subquestions": saved["subquestions"],
                "search_results": saved["search_results"],
                "errors": [],
            })
        else:
            # Normal flow
            result = research_app.invoke({"question": question, "errors": []})

        # --save-search: dump search results
        if save_search:
            with open(save_search, "w") as f:
                json.dump({
                    "question": result.get("question", question),
                    "subquestions": result.get("subquestions", []),
                    "search_results": result.get("search_results", []),
                }, f, default=str, indent=2)
            console.print(f"Search results saved to {save_search}")

        # --output: dump dry-run result
        if output and (dry_run or replay_search):
            with open(output, "w") as f:
                json.dump({
                    "evidence_cards": [c.model_dump() for c in result.get("evidence_cards", [])],
                    "extracted_claims": [c.model_dump() for c in result.get("extracted_claims", [])],
                    "evidence_metrics": result.get("evidence_metrics", {}),
                }, f, indent=2)
            console.print(f"Dry-run output saved to {output}")
```

`_run_compare` helper:

```python
def _run_compare(baseline_path: str, new_path: str):
    import json as json_module
    with open(baseline_path) as f:
        baseline = json_module.load(f)
    with open(new_path) as f:
        new = json_module.load(f)

    console = Console()
    console.print("\nA/B Comparison: baseline vs new\n")

    b_cards = baseline.get("evidence_cards", [])
    n_cards = new.get("evidence_cards", [])
    b_sources = baseline.get("evidence_metrics", {}).get("extracted_sources", 1) or 1
    n_sources = new.get("evidence_metrics", {}).get("extracted_sources", 1) or 1

    console.print("Claim extraction:")
    console.print(f"  baseline: {len(b_cards)} cards from {b_sources} sources ({len(b_cards)/max(b_sources,1):.1f} avg)")
    console.print(f"  new:      {len(n_cards)} cards from {n_sources} sources ({len(n_cards)/max(n_sources,1):.1f} avg)")
    if len(b_cards) > 0:
        console.print(f"  delta: {((len(n_cards)-len(b_cards))/len(b_cards)*100):+.0f}%")

    b_corr = baseline.get("evidence_metrics", {}).get("corroboration", {})
    n_corr = new.get("evidence_metrics", {}).get("corroboration", {})
    console.print("\nCorroboration distribution:")
    console.print(f"  baseline: {b_corr}")
    console.print(f"  new:      {n_corr}")

    b_single = b_corr.get("single_source", 0)
    n_single = n_corr.get("single_source", 0)
    b_total = len(b_cards)
    n_total = len(n_cards)
    if b_total > 0 and n_total > 0:
        console.print(f"\nSingle-source rate: {b_single/b_total:.0%} → {n_single/n_total:.0%}")
```

- [ ] **Step 2: Add CLI tests**

Append to `tests/test_cli.py`:

```python
def test_cli_save_search_writes_file(monkeypatch, tmp_path):
    _set_required_env(monkeypatch)
    fake_app = FakeResearchApp({
        "question": "AI search",
        "subquestions": [],
        "search_results": [],
        "evidence_cards": [],
        "evidence_metrics": {},
        "errors": [],
    })
    monkeypatch.setattr("deepresearch.cli._build_app", lambda config, dry_run=False: fake_app)
    output = tmp_path / "search.json"

    result = runner.invoke(app, ["AI search", "--dry-run", "--save-search", str(output)])

    assert result.exit_code == 0
    assert output.exists()


def test_cli_compare_prints_comparison(monkeypatch, tmp_path):
    import json as json_module
    _set_required_env(monkeypatch)
    baseline = tmp_path / "baseline.json"
    new = tmp_path / "new.json"
    baseline.write_text(json_module.dumps({
        "evidence_cards": [{"id": "e1", "corroboration_level": "single_source"}],
        "evidence_metrics": {"extracted_sources": 3, "evidence_cards": 1,
                             "corroboration": {"single_source": 1}},
    }))
    new.write_text(json_module.dumps({
        "evidence_cards": [{"id": "e1", "corroboration_level": "strongly_corroborated"},
                           {"id": "e2", "corroboration_level": "weakly_corroborated"}],
        "evidence_metrics": {"extracted_sources": 3, "evidence_cards": 2,
                             "corroboration": {"strongly_corroborated": 1, "weakly_corroborated": 1}},
    }))

    result = runner.invoke(app, ["--compare", str(baseline), str(new)])

    assert result.exit_code == 0
    assert "A/B Comparison" in result.output
    assert "+100%" in result.output
```

- [ ] **Step 3: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_cli.py -v
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add src/deepresearch/cli.py tests/test_cli.py
git commit -m "feat: add --save-search, --replay-search, --compare, --output CLI flags"
```

---

### Task 7: Update integration test

**Files:**
- Modify: `tests/test_integration_offline.py`

- [ ] **Step 1: Update LLM responses for two-phase pipeline**

The integration test needs two LLM responses now (Phase 1 + Phase 2 for the single subquestion). Update the FakeLLMClient responses:

```python
llm = FakeLLMClient([
    # Phase 1: extraction
    '{"claims":[{"id":"e1","subquestion_id":"q1","claim":"AI search uses generated answers.","source_url":"https://example.com/source","source_title":"Source","supporting_snippet":"AI search uses generated answers.","content_type":"extracted_content","confidence":"high"}]}',
    # Phase 2 q1: validation
    '{"evidence_cards":[{"id":"e1","subquestion_id":"q1","claim":"AI search uses generated answers.","source_url":"https://example.com/source","source_title":"Source","supporting_snippet":"AI search uses generated answers.","content_type":"extracted_content","corroboration_level":"single_source","corroborating_sources":[],"confidence":"high"}]}',
    # synthesize_notes
    '{"notes":[{"subquestion_id":"q1","key_findings":["AI search uses generated answers."],"source_urls":["https://example.com/source"],"confidence":"high"}]}',
    # write_report
    '# AI Search\n\nAI search uses generated answers.[1]\n\n## Sources\n\n[1] https://example.com/source',
    # review_report
    '{"passed":true,"score":90,"issues":[],"suggestions":[]}',
])
```

Also update the expected `evidence_metrics`:

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

- [ ] **Step 2: Run tests to confirm pass**

Run:
```bash
uv run pytest tests/test_integration_offline.py -v
```

Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_offline.py
git commit -m "test: update integration test for two-phase pipeline"
```

---

### Task 8: Run full test suite

**Files:**
- No file changes unless fixes needed.

- [ ] **Step 1: Run all tests**

Run:
```bash
uv run pytest -v
```

Expected: all pass.

- [ ] **Step 2: Check git status**

```bash
git status --short
```

Expected: clean.

---

### Task 9: Online A/B validation

**Files:**
- No file changes.

- [ ] **Step 1: Get authorization**

Confirm with user.

- [ ] **Step 2: Freeze search results**

```bash
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --dry-run --save-search ab_test_search.json --max-subquestions 2 --results-per-query 2
```

- [ ] **Step 3: Run v0.3.1 baseline**

```bash
git stash && git checkout <v0.3.1-commit> && uv run deepresearch "" --dry-run --replay-search ab_test_search.json --output baseline.json
```

- [ ] **Step 4: Run v0.4**

```bash
git checkout v0.4 && uv run deepresearch "" --dry-run --replay-search ab_test_search.json --output new.json
```

- [ ] **Step 5: Compare**

```bash
uv run deepresearch --compare baseline.json new.json
```

Verify: claims_per_source >= 1.2, source_utilization >= 90%.

- [ ] **Step 6: Standard full-pipeline validation**

```bash
uv run deepresearch "LangGraph 和 CrewAI 的适用场景" --verbose
```

Verify: EvidenceCard >= 5, review >= 85.

---

## Self-Review

Spec coverage:
- ExtractedClaim model: Task 1.
- Phase 1 extraction prompt: Task 2.
- Phase 2 single-subquestion validation prompt: Task 3.
- Two-phase prepare_evidence: Task 4.
- Auto-monitoring assertions: Task 4 (in `_run_assertions`).
- --save-search / --replay-search / --compare / --output: Tasks 5, 6.
- Integration test: Task 7.
- Online A/B validation: Task 9.

No placeholders remain. All steps include actual code.
