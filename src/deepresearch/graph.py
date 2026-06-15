from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from deepresearch.state import ResearchState

Node = Callable[[ResearchState], ResearchState]


def build_research_graph(
    *,
    plan_research: Node,
    search_web: Node,
    prepare_evidence: Node,
    write_report: Node,
    save_report: Node,
):
    """Build the standard 5-node pipeline graph (review node removed in v0.6.x).

    write_report handles citation validation + rewrite internally.
    No separate review LLM call — proved to be a no-op (honesty=const 5.0,
    coverage ceiling 0.94-1.00, rewrite trigger rate 0/27 rounds).
    """
    graph = StateGraph(ResearchState)
    graph.add_node("plan_research", plan_research)
    graph.add_node("search_web", search_web)
    graph.add_node("prepare_evidence", prepare_evidence)
    graph.add_node("write_report", write_report)
    graph.add_node("save_report", save_report)

    graph.add_edge(START, "plan_research")
    graph.add_edge("plan_research", "search_web")
    graph.add_edge("search_web", "prepare_evidence")
    graph.add_edge("prepare_evidence", "write_report")
    graph.add_edge("write_report", "save_report")
    graph.add_edge("save_report", END)

    return graph.compile()


def build_replay_graph(
    *,
    prepare_evidence: Node,
    write_report: Node,
    save_report: Node,
):
    """Replay graph: starts from pre-populated state, skips plan+search+review."""
    graph = StateGraph(ResearchState)
    graph.add_node("prepare_evidence", prepare_evidence)
    graph.add_node("write_report", write_report)
    graph.add_node("save_report", save_report)

    graph.add_edge(START, "prepare_evidence")
    graph.add_edge("prepare_evidence", "write_report")
    graph.add_edge("write_report", "save_report")
    graph.add_edge("save_report", END)

    return graph.compile()


def create_research_app(
    *,
    plan_research: Node,
    search_web: Node,
    prepare_evidence: Node,
    write_report: Node,
    save_report: Node,
):
    return build_research_graph(
        plan_research=plan_research,
        search_web=search_web,
        prepare_evidence=prepare_evidence,
        write_report=write_report,
        save_report=save_report,
    )
