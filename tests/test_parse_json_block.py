from llm import parse_json_block, LLMError
import pytest


def test_plain_json():
    assert parse_json_block('{"a": 1}') == {"a": 1}


def test_fenced_json():
    assert parse_json_block('```json\n{"a": 1}\n```') == {"a": 1}


def test_fence_without_lang():
    assert parse_json_block('```\n{"a": 1}\n```') == {"a": 1}


def test_prose_then_json():
    assert parse_json_block('Sure! Here you go: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}


def test_nested_braces_in_strings():
    assert parse_json_block('x {"a": "curly } inside", "b": 2} y') == {"a": "curly } inside", "b": 2}


def test_array_root():
    assert parse_json_block('here: [1, 2, 3] done') == [1, 2, 3]


def test_garbage_raises():
    with pytest.raises(LLMError):
        parse_json_block("no json here at all")
