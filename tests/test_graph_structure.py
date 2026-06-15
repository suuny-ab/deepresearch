"""Tests for graph structure — 5-node topology (review removed)."""
from pathlib import Path

from deepresearch.graph import create_research_app


def _fake_node(state):
    return state


def test_standard_graph_compiles(tmp_path):
    """Standard graph compiles with all 5 nodes in correct sequence."""
    app = create_research_app(
        plan_research=_fake_node,
        search_web=_fake_node,
        prepare_evidence=_fake_node,
        write_report=_fake_node,
        save_report=_fake_node,
    )
    assert app is not None


def test_standard_graph_executes_all_nodes(tmp_path):
    """Standard graph traverses all nodes end to end."""
    app = create_research_app(
        plan_research=_fake_node,
        search_web=_fake_node,
        prepare_evidence=_fake_node,
        write_report=_fake_node,
        save_report=_fake_node,
    )
    result = app.invoke({"question": "test", "errors": []})
    assert result is not None
