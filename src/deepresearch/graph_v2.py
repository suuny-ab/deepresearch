"""Multi-agent research graph.

Each subquestion gets its own independent agent (search -> extract -> validate).
The coordinator merges results and detects cross-agent patterns.

Topology::

    START -> plan -> run_agents(parallel) -> coordinator -> write -> review <=> save -> END
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Literal

from langgraph.graph import END, START, StateGraph

from deepresearch.agents.coordinator import (
    Contradiction,
    CoordinatorResult,
    coordinate,
)
from deepresearch.agents.subquestion_agent import (
    AgentResult,
    run_subquestion_agent,
)
from deepresearch.clients.llm import LLMClient
from deepresearch.clients.tavily import SearchClient
from deepresearch.state import ResearchState, TokenUsage

Node = Callable[[ResearchState], ResearchState]


def _review_router(state: ResearchState) -> Literal["write_report", "save_report"]:
    """Route after review: rewrite if feedback present, otherwise save."""
    if state.get("report_status") == "failed_validation":
        return "save_report"
    if state.get("review_feedback"):
        return "write_report"
    return "save_report"


def _format_contradictions_for_writer(contradictions: list[Contradiction]) -> str:
    """Format detected contradictions as a prompt section for the writer."""
    if not contradictions:
        return ""

    lines = [
        "",
        "## Cross-Agent Contradictions Detected",
        "",
        "The following topics received conflicting perspectives from independent research agents.",
        "Please present both sides in the report rather than choosing one.",
        "",
    ]
    for i, c in enumerate(contradictions, 1):
        lines.append(f"### Contradiction {i}: {c.topic}")
        lines.append(f"- Agent [{c.agent_a}] (source: {c.source_a}): {c.claim_a}")
        lines.append(f"- Agent [{c.agent_b}] (source: {c.source_b}): {c.claim_b}")
        if c.explanation:
            lines.append(f"- Context: {c.explanation}")
        lines.append("")
    return "\n".join(lines)


def make_run_agents_node(
    search_client: SearchClient,
    llm: LLMClient,
    results_per_query: int = 5,
    max_sources_per_subquestion: int = 3,
) -> Node:
    """Create the parallel agents execution node.

    This node fans out all subquestions to independent agents, runs them
    in parallel via ThreadPoolExecutor, and collects results.
    """

    def run_agents(state: ResearchState) -> ResearchState:
        question = state.get("question", "")
        subquestions = state.get("subquestions", [])
        errors = list(state.get("errors", []))
        usage_entries: list[TokenUsage] = list(state.get("token_usage", []))

        if not subquestions:
            return {**state, "evidence_cards": [], "errors": errors}

        agent_results: list[AgentResult] = []

        def _run_one(sq):
            return run_subquestion_agent(
                question=question,
                subquestion=sq,
                search_client=search_client,
                llm=llm,
                results_per_query=results_per_query,
                max_sources=max_sources_per_subquestion,
            )

        if len(subquestions) == 1:
            agent_results = [_run_one(subquestions[0])]
        else:
            with ThreadPoolExecutor(max_workers=len(subquestions)) as executor:
                futures = {executor.submit(_run_one, sq): sq.id for sq in subquestions}
                for future in as_completed(futures):
                    sq_id = futures[future]
                    try:
                        result = future.result()
                        agent_results.append(result)
                    except Exception as exc:
                        errors.append(f"Agent for subquestion {sq_id} crashed: {exc}")

        for result in agent_results:
            errors.extend(result.errors)
            usage_entries.extend(result.token_usage)

        return {
            **state,
            "errors": errors,
            "token_usage": usage_entries,
            "_agent_results": agent_results,
        }

    return run_agents


def make_coordinator_node() -> Node:
    """Create the coordinator node.

    Merges evidence cards from all agents, detects cross-agent corroboration
    and contradictions, and prepares the merged evidence for the writer.
    """

    def coordinator_node(state: ResearchState) -> ResearchState:
        agent_results: list[AgentResult] = state.get("_agent_results", [])
        coordinator_result: CoordinatorResult = coordinate(agent_results)

        contradictions_text = _format_contradictions_for_writer(
            coordinator_result.contradictions
        )

        return {
            **state,
            "evidence_cards": coordinator_result.evidence_cards,
            "_contradictions": coordinator_result.contradictions,
            "_contradictions_text": contradictions_text,
            "_cross_agent_corroborations": coordinator_result.cross_agent_corroborations,
        }

    return coordinator_node


def build_multi_agent_graph(
    *,
    plan_research: Node,
    search_web: Node,
    run_agents: Node,
    coordinator: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
):
    """Build the multi-agent StateGraph.

    Unlike the single-pipeline graph, this graph fans out subquestion
    processing to independent parallel agents before coordinating.
    """
    _ = search_web  # explicitly unused in multi-agent mode

    graph = StateGraph(ResearchState)
    graph.add_node("plan_research", plan_research)
    graph.add_node("run_agents", run_agents)
    graph.add_node("coordinator", coordinator)
    graph.add_node("write_report", write_report)
    graph.add_node("review_report", review_report)
    graph.add_node("save_report", save_report)

    graph.add_edge(START, "plan_research")
    graph.add_edge("plan_research", "run_agents")
    graph.add_edge("run_agents", "coordinator")
    graph.add_edge("coordinator", "write_report")
    graph.add_edge("write_report", "review_report")
    graph.add_conditional_edges(
        "review_report",
        _review_router,
        {"write_report": "write_report", "save_report": "save_report"},
    )
    graph.add_edge("save_report", END)

    return graph.compile()
