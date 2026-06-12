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

    evidence_metrics = state.get("evidence_metrics")
    if evidence_metrics:
        derived_subquestion_count = len(subquestions)
        derived_total_queries = sum(
            len(item.search_queries) if getattr(item, "search_queries", []) else 1
            for item in subquestions
            if getattr(item, "search_queries", []) or getattr(item, "search_query", None)
        )
        coverage_values = {
            "subquestions": evidence_metrics.get("subquestions", derived_subquestion_count),
            "total_queries": evidence_metrics.get("total_queries", derived_total_queries),
        }

        lines.extend(["", "Search coverage:"])
        for key in [
            "subquestions",
            "total_queries",
            "raw_search_results",
            "deduped_sources",
            "duplicates_removed",
            "extracted_sources",
            "evidence_cards",
        ]:
            label = key.replace("_", " ")
            lines.append(f"- {label}: {coverage_values.get(key, evidence_metrics.get(key, 0))}")

        lines.extend(["", "Evidence corroboration:"])
        corroboration = evidence_metrics.get("corroboration", {})
        if corroboration:
            for key in ["strongly_corroborated", "weakly_corroborated", "single_source"]:
                label = key.replace("_", " ")
                value = corroboration.get(key, 0)
                description = ""
                if key == "strongly_corroborated":
                    description = " (3+ independent sources agree)"
                elif key == "weakly_corroborated":
                    description = " (2 independent sources agree)"
                elif key == "single_source":
                    description = " (only one source mentions this)"
                lines.append(f"- {label}: {value}{description}")
        else:
            lines.append("- None")

        lines.extend(["", "Evidence confidence:"])
        confidence = evidence_metrics.get("confidence", {})
        if confidence:
            for key in ["high", "medium", "low"]:
                value = confidence.get(key, 0)
                lines.append(f"- {key}: {value}")
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

    lines.extend(["", "Report validation:"])
    lines.append(f"- rewrite_attempted: {state.get('rewrite_attempted', False)}")
    lines.append(f"- validation_attempts: {state.get('validation_attempts', 0)}")
    lines.append(f"- final_status: {state.get('report_status', 'unknown')}")
    failures = state.get("validation_failures", [])
    if failures:
        for index, failure in enumerate(failures, start=1):
            reason = failure.get("reason", "unknown") if isinstance(failure, dict) else "unknown"
            lines.append(f"- attempt {index}: {reason}")
    else:
        lines.append("- failures: None")

    errors = state.get("errors", [])
    lines.extend(["", "Errors:"])
    if errors:
        for error in errors:
            lines.append(f"- {error}")
    else:
        lines.append("- None")

    return "\n".join(lines)
