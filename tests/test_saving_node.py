from deepresearch.nodes.saving import make_save_report_node
from deepresearch.state import ReviewResult


def test_save_report_node_uses_failed_filename_for_failed_validation(tmp_path):
    node = make_save_report_node(tmp_path)

    result = node({
        "question": "AI Search",
        "report_markdown": "# 研究报告生成失败",
        "review": ReviewResult(passed=False, score=0, issues=[], suggestions=[]),
        "report_status": "failed_validation",
    })

    assert result["output_path"].endswith("-failed.md")
