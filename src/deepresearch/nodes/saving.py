from pathlib import Path

from deepresearch.state import ResearchState
from deepresearch.utils.report_writer import save_report


def make_save_report_node(output_dir: str | Path):
    def save_report_node(state: ResearchState) -> ResearchState:
        path = save_report(
            question=state["question"],
            report_markdown=state.get("report_markdown", ""),
            review=state["review"],
            output_dir=output_dir,
        )
        return {**state, "output_path": str(path)}

    return save_report_node
