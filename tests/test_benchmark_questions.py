import json
import re
from pathlib import Path

import pytest

QUESTIONS_PATH = Path(__file__).resolve().parent.parent / "benchmark" / "questions.json"

_VALID_DIFFICULTIES = {"easy", "medium", "hard"}
_REQUIRED_FIELDS = {"id", "question", "tags", "difficulty"}


@pytest.fixture
def questions():
    """Parse the benchmark questions file, skipping if it doesn't exist yet."""
    if not QUESTIONS_PATH.exists():
        pytest.skip(f"{QUESTIONS_PATH} does not exist")
    with open(QUESTIONS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_questions_file_is_valid_json(questions):
    """The file must be a JSON array."""
    assert isinstance(questions, list), "questions.json must contain a JSON array"


def test_every_question_has_required_fields(questions):
    """Each question must have id, question, tags, and difficulty."""
    for i, q in enumerate(questions):
        missing = _REQUIRED_FIELDS - set(q)
        assert not missing, f"Question [{i}] is missing fields: {missing}"


def test_ids_are_unique(questions):
    """Question ids must not repeat."""
    ids = [q["id"] for q in questions]
    assert len(ids) == len(set(ids)), f"Duplicate ids found: {ids}"


def test_minimum_three_questions(questions):
    """We need at least 3 benchmark questions."""
    assert len(questions) >= 3, f"Expected >= 3 questions, got {len(questions)}"


def test_difficulty_values_are_valid(questions):
    """difficulty must be one of easy/medium/hard."""
    for q in questions:
        assert q["difficulty"] in _VALID_DIFFICULTIES, (
            f"Question '{q['id']}' has invalid difficulty: {q['difficulty']}"
        )


def test_all_questions_are_chinese(questions):
    """Every question text must contain at least one Chinese character."""
    chinese_char = re.compile(r"[一-鿿]")
    for q in questions:
        assert chinese_char.search(q["question"]), (
            f"Question '{q['id']}' contains no Chinese characters"
        )


def test_at_least_one_comparison_question(questions):
    """At least one question should be a comparison-type (contains 对比 or vs)."""
    comparison = re.compile(r"对比|[Vv][Ss]")
    found = [q["id"] for q in questions if comparison.search(q["question"])]
    assert found, "No comparison-type question found (expected 对比 or vs)"


def test_difficulty_coverage(questions):
    """The question set should cover at least 2 different difficulty levels."""
    difficulties = {q["difficulty"] for q in questions}
    assert len(difficulties) >= 2, f"Only {difficulties} covered, need >= 2"
