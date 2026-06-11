from collections.abc import Callable

from langgraph.graph import END, START, StateGraph

from deepresearch.state import ResearchState

NODE_SEQUENCE = [
    "plan_research",
    "search_web",
    "synthesize_notes",
    "write_report",
    "review_report",
    "save_report",
]

Node = Callable[[ResearchState], ResearchState]


def build_research_graph(
    *,
    plan_research: Node,
    search_web: Node,
    synthesize_notes: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
):
    graph = StateGraph(ResearchState)
    graph.add_node("plan_research", plan_research)
    graph.add_node("search_web", search_web)
    graph.add_node("synthesize_notes", synthesize_notes)
    graph.add_node("write_report", write_report)
    graph.add_node("review_report", review_report)
    graph.add_node("save_report", save_report)

    graph.add_edge(START, "plan_research")
    graph.add_edge("plan_research", "search_web")
    graph.add_edge("search_web", "synthesize_notes")
    graph.add_edge("synthesize_notes", "write_report")
    graph.add_edge("write_report", "review_report")
    graph.add_edge("review_report", "save_report")
    graph.add_edge("save_report", END)
    return graph.compile()


def create_research_app(
    *,
    plan_research: Node,
    search_web: Node,
    synthesize_notes: Node,
    write_report: Node,
    review_report: Node,
    save_report: Node,
):
    return build_research_graph(
        plan_research=plan_research,
        search_web=search_web,
        synthesize_notes=synthesize_notes,
        write_report=write_report,
        review_report=review_report,
        save_report=save_report,
    )
