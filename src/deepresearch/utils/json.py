import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class JSONParseError(ValueError):
    pass


def _extract_json_text(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped

    match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()

    raise JSONParseError("No JSON object or fenced JSON block found")


def parse_json_object(text: str, model: type[T]) -> T:
    try:
        raw = _extract_json_text(text)
        data = json.loads(raw)
        return model.model_validate(data)
    except (json.JSONDecodeError, ValidationError, TypeError) as exc:
        raise JSONParseError(str(exc)) from exc
