from collections import Counter
from typing import Any


def format_verbose_summary(state: dict[str, Any]) -> str:
    lines: list[str] = ["Workflow details:", ""]

    subquestions = state.get("subquestions", [])
    lines.append("Subquestions:")
    if subquestions:
        for index, item in enumerate(subquestions, start=1):
            lines.append(f"{index}. {item.question}")
            lines.append(f"   query: {item.search_query}")
    else:
        lines.append("- None")

    results = state.get("search_results", [])
    result_counts = Counter(item.subquestion_id for item in results)
    lines.extend(["", "Search results:"])
    if result_counts:
        for subquestion_id, count in sorted(result_counts.items()):
            lines.append(f"- {subquestion_id}: {count} result(s)")
    else:
        lines.append("- None")

    notes = state.get("notes", [])
    lines.extend(["", "Research notes:"])
    if notes:
        for note in notes:
            lines.append(
                f"- {note.subquestion_id}: confidence={note.confidence}, "
                f"findings={len(note.key_findings)}, sources={len(note.source_urls)}"
            )
    else:
        lines.append("- None")

    review = state.get("review")
    lines.extend(["", "Review:"])
    if review is not None:
        lines.append(f"- passed: {review.passed}")
        lines.append(f"- score: {review.score}")
        lines.append(f"- issues: {len(review.issues)}")
        lines.append(f"- suggestions: {len(review.suggestions)}")
    else:
        lines.append("- None")

    errors = state.get("errors", [])
    lines.extend(["", "Errors:"])
    if errors:
        for error in errors:
            lines.append(f"- {error}")
    else:
        lines.append("- None")

    return "\n".join(lines)
