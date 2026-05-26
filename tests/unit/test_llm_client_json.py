from __future__ import annotations

from newsalpha.llm.client import _try_parse_json


def test_parses_plain_json() -> None:
    assert _try_parse_json('{"a": 1, "b": "x"}') == {"a": 1, "b": "x"}


def test_parses_fenced_json_block() -> None:
    text = '```json\n{"polarity": 0.5}\n```'
    assert _try_parse_json(text) == {"polarity": 0.5}


def test_parses_fenced_no_lang() -> None:
    text = '```\n{"x": 1}\n```'
    assert _try_parse_json(text) == {"x": 1}


def test_strips_leading_prose() -> None:
    text = "Here is the result:\n\n{\"polarity\": -0.3, \"confidence\": 0.9}\n\nDone."
    assert _try_parse_json(text) == {"polarity": -0.3, "confidence": 0.9}


def test_returns_none_on_garbage() -> None:
    assert _try_parse_json("not json at all") is None
    assert _try_parse_json("") is None
    assert _try_parse_json("{ broken: ") is None


def test_returns_none_for_array() -> None:
    """Top-level JSON arrays aren't a dict — agents must always return objects."""
    # The extractor walks for outermost { ... } only; bare arrays return None.
    assert _try_parse_json("[1, 2, 3]") is None
