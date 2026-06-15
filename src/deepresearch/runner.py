from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from deepresearch.agents.react_agent import ReActAgent
from deepresearch.clients.llm import LLMClient
from deepresearch.clients.tavily import SearchClient
from deepresearch.graph import Node, create_research_app
from deepresearch.graph_v2 import build_multi_agent_graph, make_coordinator_node, make_run_agents_node
from deepresearch.tools import TavilySearchTool, ToolRegistry, WebFetchTool
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
    architecture: Literal["pipeline", "multi-agent", "react"] = "pipeline",
) -> Callable[[str], ResearchState]:
    """Build a research agent with injected dependencies.

    Parameters
    ----------
    architecture:
        ``"pipeline"`` (default) — single linear 6-node LangGraph pipeline.
        ``"multi-agent"`` — each subquestion gets its own independent agent
        that searches, extracts, and validates in parallel; results are
        merged by a coordinator node before writing.
        ``"react"`` — autonomous ReAct agent with tool-calling loop that
        decides when to search, fetch, and write.
    """
    _wrap = wrap_node or (lambda _label, n: n)

    plan_research = _wrap("[1/6] Planning research...", make_plan_research_node(llm, max_subquestions))
    search_web = _wrap("[2/6] Searching web...", make_search_web_node(search, results_per_query))
    prepare_evidence = _wrap("[3/6] Preparing evidence...", make_prepare_evidence_node(search, llm, max_sources_per_subquestion=max_sources_per_subquestion))
    write_report = _wrap("[4/6] Writing report...", make_write_report_node(llm))
    review_report = _wrap("[5/6] Reviewing report...", make_review_report_node(llm))
    save_report = _wrap("[6/6] Saving report...", make_save_report_node(output_dir))

    if architecture == "react":
        tools = ToolRegistry([
            TavilySearchTool(search),
            WebFetchTool(),
        ])
        react_agent = ReActAgent(llm=llm, tools=tools)

        def run(question: str) -> ResearchState:
            from deepresearch.state import ResearchState as RS
            result = react_agent.run(question)
            # Save report to disk
            from deepresearch.utils.filenames import make_report_filename
            from pathlib import Path
            output_path = Path(output_dir) / make_report_filename(question)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(result.report, encoding="utf-8")
            # Collect search results from tool calls for process metrics
            from deepresearch.state import SearchResult
            search_results: list[SearchResult] = []
            for step in result.steps:
                if step.action == "search" and step.new_urls:
                    for url in step.new_urls:
                        search_results.append(SearchResult(
                            subquestion_id="react", title="", url=url,
                            content=step.observation[:200] if step.observation else "",
                            score=None,
                        ))
            return RS(
                question=question,
                report_markdown=result.report,
                report_status="success" if result.report and "could not find" not in result.report[:100] else "failed_validation",
                errors=result.errors,
                output_path=str(output_path),
                token_usage=result.token_usage,
                search_results=search_results,
                _react_steps=result.steps,  # type: ignore[typeddict-item]
            )  # type: ignore[return-value]

        return run

    if architecture == "multi-agent":
        run_agents = _wrap("[2+3/6] Running subquestion agents...", make_run_agents_node(
            search_client=search, llm=llm,
            results_per_query=results_per_query,
            max_sources_per_subquestion=max_sources_per_subquestion,
        ))
        coordinator = _wrap("[3.5/6] Coordinating results...", make_coordinator_node())

        app = build_multi_agent_graph(
            plan_research=plan_research,
            search_web=search_web,  # unused but required by signature
            run_agents=run_agents,
            coordinator=coordinator,
            write_report=write_report,
            review_report=review_report,
            save_report=save_report,
        )
    else:
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
