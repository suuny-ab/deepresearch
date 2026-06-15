from collections.abc import Callable
from pathlib import Path
from typing import Any

from deepresearch.clients.llm import LLMClient
from deepresearch.clients.tavily import SearchClient
from deepresearch.graph import Node, create_research_app
from deepresearch.nodes.planning import make_plan_research_node
from deepresearch.nodes.prepare_evidence import make_prepare_evidence_node
from deepresearch.nodes.reviewing import make_review_report_node
from deepresearch.nodes.saving import make_save_report_node
from deepresearch.nodes.searching import make_search_web_node
from deepresearch.nodes.writing import make_write_report_node
from deepresearch.state import ResearchState

NodeWrapper = Callable[[str, Node], Node]


def build_agent(
    *,
    llm: LLMClient,
    search: SearchClient,
    max_subquestions: int = 5,
    results_per_query: int = 5,
    max_sources_per_subquestion: int = 3,
    output_dir: str | Path = "reports",
    wrap_node: NodeWrapper | None = None,
) -> Callable[[str], ResearchState]:
    """Build a research agent with injected dependencies.

    Returns a callable that accepts a research question string and returns
    the final ``ResearchState`` after the full pipeline completes.

    Parameters
    ----------
    llm:
        An ``LLMClient`` implementation (e.g. ``DeepSeekLLMClient`` or a fake for tests).
    search:
        A ``SearchClient`` implementation (e.g. ``TavilySearchClient`` or a fake for tests).
    max_subquestions:
        Maximum number of subquestions the planner will generate.
    results_per_query:
        Number of search results requested per query.
    max_sources_per_subquestion:
        Maximum sources selected per subquestion (domain-diversity constrained).
    output_dir:
        Directory where the final report file is saved.
    wrap_node:
        Optional callback ``(label: str, node) -> node`` to decorate each pipeline
        node (e.g. for progress reporting).  When *None*, nodes are used as-is.
    """
    _wrap = wrap_node or (lambda _label, n: n)

    plan_research = _wrap("[1/6] Planning research...", make_plan_research_node(llm, max_subquestions))
    search_web = _wrap("[2/6] Searching web...", make_search_web_node(search, results_per_query))
    prepare_evidence = _wrap("[3/6] Preparing evidence...", make_prepare_evidence_node(search, llm, max_sources_per_subquestion=max_sources_per_subquestion))
    write_report = _wrap("[4/6] Writing report...", make_write_report_node(llm))
    review_report = _wrap("[5/6] Reviewing report...", make_review_report_node(llm))
    save_report = _wrap("[6/6] Saving report...", make_save_report_node(output_dir))

    app = create_research_app(
        plan_research=plan_research,
        search_web=search_web,
        prepare_evidence=prepare_evidence,
        write_report=write_report,
        review_report=review_report,
        save_report=save_report,
    )

    def run(question: str) -> ResearchState:
        return app.invoke({"question": question, "errors": []})

    return run
