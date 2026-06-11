from deepresearch.graph import NODE_SEQUENCE, build_research_graph


def test_node_sequence_is_fixed_mvp_pipeline():
    assert NODE_SEQUENCE == [
        "plan_research",
        "search_web",
        "synthesize_notes",
        "write_report",
        "review_report",
        "save_report",
    ]


def test_graph_compiles_with_fake_nodes(tmp_path):
    graph = build_research_graph(
        plan_research=lambda state: {**state, "subquestions": []},
        search_web=lambda state: {**state, "search_results": []},
        synthesize_notes=lambda state: {**state, "notes": []},
        write_report=lambda state: {**state, "report_markdown": "# Report"},
        review_report=lambda state: {**state, "review": None},
        save_report=lambda state: {**state, "output_path": str(tmp_path / "report.md")},
    )

    assert graph is not None
