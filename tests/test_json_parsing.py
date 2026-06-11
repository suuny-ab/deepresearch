import pytest
from pydantic import BaseModel

from deepresearch.utils.json import JSONParseError, parse_json_object


class Item(BaseModel):
    name: str


def test_parse_raw_json_object():
    item = parse_json_object('{"name": "alpha"}', Item)

    assert item.name == "alpha"


def test_parse_fenced_json_object():
    item = parse_json_object('Here is JSON:\n```json\n{"name": "beta"}\n```', Item)

    assert item.name == "beta"


def test_invalid_json_raises_parse_error():
    with pytest.raises(JSONParseError):
        parse_json_object("not json", Item)


def test_missing_required_field_raises_parse_error():
    with pytest.raises(JSONParseError):
        parse_json_object("{}", Item)
