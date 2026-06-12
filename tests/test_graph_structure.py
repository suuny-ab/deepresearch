from deepresearch.graph import NODE_SEQUENCE, build_research_graph
from deepresearch.state import ReviewResult


def test_dry_run_graph_compiles_with_prepare_evidence_to_end(tmp_path):
    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        write_report=lambda state: {**state, "report_markdown": "# Report"},
        review_report=lambda state: {**state, "review": None},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
        dry_run=True,
    )

    assert graph is not None
    result = graph.invoke({"question": "AI search", "errors": []})
    assert "report_markdown" not in result


def test_node_sequence_is_fixed_mvp_pipeline():
    assert NODE_SEQUENCE == [
        "plan_research",
        "search_web",
        "prepare_evidence",
        "write_report",
        "review_report",
        "save_report",
    ]


def test_replay_search_graph_skips_plan_and_search(tmp_path):
    graph = build_research_graph(
        plan_research=lambda state: {**state},
        search_web=lambda state: {**state},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        write_report=lambda state: {**state, "report_markdown": "# R"},
        review_report=lambda state: {**state, "review": None},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "r.md")},
        replay_search=True,
    )
    result = graph.invoke({"question": "AI search", "errors": []})
    assert result["evidence_cards"] == []


def test_graph_compiles_with_fake_nodes(tmp_path):
    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        write_report=lambda state: {**state, "report_markdown": "# Report"},
        review_report=lambda state: {**state, "review": None},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
    )

    assert graph is not None


def test_review_conditional_edge_routes_to_write_when_score_below_70(tmp_path):
    """When review score < 70 and no rewrite happened yet, route to write_report."""
    write_calls = []
    review_calls = []

    def tracking_write(state):
        write_calls.append(True)
        if state.get("review_feedback"):
            return {**state, "report_markdown": "# Rewritten", "review_feedback": None, "review_rewritten": True}
        return {**state, "report_markdown": "# Initial"}

    def mock_review(state):
        review_calls.append(True)
        if not state.get("review_rewritten"):
            return {**state, "review": ReviewResult(passed=False, score=50, issues=["Bad"], suggestions=["Fix it"]), "review_feedback": "Issues: Bad"}
        return {**state, "review": ReviewResult(passed=False, score=50, issues=["Bad"], suggestions=["Fix it"])}

    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        write_report=tracking_write,
        review_report=mock_review,
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
    )

    result = graph.invoke({
        "question": "AI search",
        "errors": [],
        "review_feedback": None,
        "review_rewritten": False,
    })

    assert len(write_calls) == 2  # Initial write + rewrite
    assert len(review_calls) == 2  # Review after initial + review after rewrite
    assert result["report_markdown"] == "# Rewritten"


def test_review_conditional_edge_skips_rewrite_when_score_above_70(tmp_path):
    """When review score >= 70, route directly to save_report."""
    write_calls = []

    def tracking_write(state):
        write_calls.append(True)
        return {**state, "report_markdown": "# Report"}

    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        write_report=tracking_write,
        review_report=lambda state: {**state, "review": ReviewResult(passed=True, score=85, issues=[], suggestions=[])},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
    )

    result = graph.invoke({
        "question": "AI search",
        "errors": [],
        "review_feedback": None,
        "review_rewritten": False,
    })

    assert len(write_calls) == 1  # Only the initial write, no rewrite
    assert result["review"].score == 85


def test_review_conditional_edge_skips_rewrite_when_already_rewritten(tmp_path):
    """When review_rewritten is True, don't rewrite again even if score < 70."""
    write_calls = []

    def counting_write(state):
        write_calls.append(True)
        return {**state, "report_markdown": "# Report"}

    def mock_review(state):
        if not state.get("review_rewritten"):
            return {**state, "review": ReviewResult(passed=False, score=50, issues=["Bad"], suggestions=["Fix it"]), "review_feedback": "Issues: Bad"}
        return {**state, "review": ReviewResult(passed=False, score=50, issues=["Bad"], suggestions=["Fix it"])}

    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        prepare_evidence=lambda state: {**state, "evidence_cards": [], "evidence_metrics": {}},
        write_report=counting_write,
        review_report=mock_review,
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
    )

    result = graph.invoke({
        "question": "AI search",
        "errors": [],
        "review_feedback": None,
        "review_rewritten": True,  # Already rewritten
    })

    assert len(write_calls) == 1  # Only initial write
