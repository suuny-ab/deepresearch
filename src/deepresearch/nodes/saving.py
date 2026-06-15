from pathlib import Path

from deepresearch.state import ResearchState
from deepresearch.utils.report_writer import save_report

try:
    from langsmith import Client
    from langsmith.run_helpers import get_current_run_tree as _get_current_run_tree
except ImportError:  # pragma: no cover
    Client = None  # type: ignore[assignment]
    _get_current_run_tree = None  # type: ignore[assignment]


def _try_sync_feedback(state: ResearchState) -> None:
    """Write citation compliance feedback to LangSmith if a trace is active.

    Gracefully no-ops when no LangSmith trace context exists (e.g. offline
    tests, or LANGCHAIN_TRACING_V2 not set).
    """
    if _get_current_run_tree is None:
        return

    run_tree = _get_current_run_tree()
    if run_tree is None:
        return

    report_status = state.get("report_status")
    passed = report_status == "success"

    comment = "Citation validation passed."
    if not passed:
        failures = state.get("validation_failures", [])
        reasons = [f.get("reason", "unknown") for f in failures] if failures else [report_status or "unknown"]
        comment = f"Citation validation failed: {', '.join(reasons)}"

    try:
        Client().create_feedback(  # type: ignore[misc]
            run_id=run_tree.trace_id,
            key="citation_compliance",
            score=1.0 if passed else 0.0,
            comment=comment,
        )
    except Exception:
        # Never let feedback failure block report saving.
        pass


def make_save_report_node(output_dir: str | Path):
    def save_report_node(state: ResearchState) -> ResearchState:
        failed = state.get("report_status") == "failed_validation"
        path = save_report(
            question=state["question"],
            report_markdown=state.get("report_markdown", ""),
            review=state.get("review"),
            output_dir=output_dir,
            failed=failed,
        )
        _try_sync_feedback(state)
        return {**state, "output_path": str(path)}

    return save_report_node
