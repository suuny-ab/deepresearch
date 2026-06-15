from datetime import datetime
from pathlib import Path

from deepresearch.errors import ReportWriteError
from deepresearch.state import ReviewResult
from deepresearch.utils.filenames import make_report_filename


def _format_bullets(items: list[str]) -> str:
    if not items:
        return "- None"
    return "\n".join(f"- {item}" for item in items)


def append_quality_review(report_markdown: str, review: ReviewResult) -> str:
    return (
        report_markdown.rstrip()
        + "\n\n---\n\n"
        + "## Quality Review\n\n"
        + f"Score: {review.score}/100\n\n"
        + f"Passed: {review.passed}\n\n"
        + "### Issues\n\n"
        + _format_bullets(review.issues)
        + "\n\n"
        + "### Suggestions\n\n"
        + _format_bullets(review.suggestions)
        + "\n"
    )


def save_report(
    question: str,
    report_markdown: str,
    review: ReviewResult | None,
    output_dir: str | Path,
    now: datetime | None = None,
    *,
    failed: bool = False,
) -> Path:
    directory = Path(output_dir)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / make_report_filename(question, now, failed=failed)
        content = append_quality_review(report_markdown, review) if review is not None else report_markdown
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise ReportWriteError(f"Failed to write report: {exc}") from exc
    return path
