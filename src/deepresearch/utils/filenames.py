import re
from datetime import datetime


def slugify_question(question: str, max_length: int = 60) -> str:
    lowered = question.lower()
    asciiish = re.sub(r"[^a-z0-9]+", "-", lowered)
    slug = re.sub(r"-+", "-", asciiish).strip("-")
    if not slug:
        return "report"
    return slug[:max_length].strip("-") or "report"


def make_report_filename(question: str, now: datetime | None = None) -> str:
    current = now or datetime.now()
    timestamp = current.strftime("%Y-%m-%d-%H%M%S")
    slug = slugify_question(question)
    return f"{timestamp}-{slug}.md"
