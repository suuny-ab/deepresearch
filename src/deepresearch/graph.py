from collections.abc import Callable
from typing import Literal

from langgraph.graph import END, START, StateGraph

from deepresearch.state import ResearchState

Node = Callable[[ResearchState], ResearchState]


def _review_router(state: ResearchState) -> Literal["write_report", "save_report"]:
    """Route after review_report: rewrite if feedback is present, otherwise save."""
    if state.get("report_status") == "failed_validation":
        return "save_report"
    if state.get("review_feedback"):
        return "write_report"
    return "save_report"


def build_research_graph(
    *,
    plan_research: Node,
    search_web: Node,
    prepare_evidence: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
):
    graph = StateGraph(ResearchState)
    graph.add_node("plan_research", plan_research)
    graph.add_node("search_web", search_web)
    graph.add_node("prepare_evidence", prepare_evidence)
    graph.add_node("write_report", write_report)
    graph.add_node("review_report", review_report)
    graph.add_node("save_report", save_report)

    graph.add_edge(START, "plan_research")
    graph.add_edge("plan_research", "search_web")
    graph.add_edge("search_web", "prepare_evidence")
    graph.add_edge("prepare_evidence", "write_report")
    graph.add_edge("write_report", "review_report")
    graph.add_conditional_edges(
        "review_report",
        _review_router,
        {"write_report": "write_report", "save_report": "save_report"},
    )
    graph.add_edge("save_report", END)

    return graph.compile()


def create_research_app(
    *,
    plan_research: Node,
    search_web: Node,
    prepare_evidence: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
):
    return build_research_graph(
        plan_research=plan_research,
        search_web=search_web,
        prepare_evidence=prepare_evidence,
        write_report=write_report,
        review_report=review_report,
        save_report=save_report,
    )
