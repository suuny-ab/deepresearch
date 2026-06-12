from deepresearch.graph import NODE_SEQUENCE, build_research_graph


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
