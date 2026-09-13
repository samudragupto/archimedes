"""Unit tests for the tolerant LLM-JSON layer: think-block stripping, block
extraction, and escalating repair passes."""

from __future__ import annotations

import pytest

from app.services.nebius_client import (
    JSONRepairError,
    extract_json_block,
    parse_llm_json,
    repair_json,
    strip_think,
)


# ---------------------------------------------------------------------------
# strip_think — Nemotron reasoning blocks
# ---------------------------------------------------------------------------
def test_strip_think_removes_reasoning_block():
    raw = '<think>The user wants JSON. Maybe {"decoy": true}?</think>{"a": 1}'
    assert strip_think(raw) == '{"a": 1}'


def test_strip_think_multiple_blocks_keeps_last_answer():
    raw = '<think>step 1</think>partial <think>step 2</think>{"final": true}'
    assert strip_think(raw) == '{"final": true}'


def test_strip_think_passthrough_without_block():
    assert strip_think('{"a": 1}') == '{"a": 1}'


# ---------------------------------------------------------------------------
# extract_json_block — balanced-brace state machine
# ---------------------------------------------------------------------------
def test_extract_plain_object():
    assert extract_json_block('{"a": 1}') == '{"a": 1}'


def test_extract_ignores_braces_inside_strings():
    text = 'prose {"a": "not } a { brace"} trailing'
    assert extract_json_block(text) == '{"a": "not } a { brace"}'


def test_extract_nested_and_escaped_quotes():
    text = 'Here: {"a": {"b": "say \\"hi\\" [ok]"}} end'
    assert extract_json_block(text) == '{"a": {"b": "say \\"hi\\" [ok]"}}'


def test_extract_returns_none_without_block():
    assert extract_json_block("no json here") is None


def test_extract_array():
    assert extract_json_block('items: [1, 2, {"x": 3}]') == '[1, 2, {"x": 3}]'


# ---------------------------------------------------------------------------
# parse_llm_json — the full tolerant path
# ---------------------------------------------------------------------------
def test_parse_plain_json():
    assert parse_llm_json('{"a": 1}') == {"a": 1}


def test_parse_with_think_block_and_decoy_braces():
    raw = '<think>hmm { "decoy": [1,2] }</think>{"requirements": []}'
    assert parse_llm_json(raw) == {"requirements": []}


def test_parse_fenced_json():
    raw = '```json\n{"a": [1, 2]}\n```'
    assert parse_llm_json(raw) == {"a": [1, 2]}


def test_parse_json_with_prose_wrapper():
    raw = 'Sure! Here is the JSON you asked for: {"a": 1} — let me know.'
    assert parse_llm_json(raw) == {"a": 1}


def test_parse_trailing_commas():
    assert parse_llm_json('{"items": [1, 2,], "ok": true,}') == {"items": [1, 2], "ok": True}


def test_parse_single_quoted_keys_and_strings():
    assert parse_llm_json("{'key': 'value', 'n': 2}") == {"key": "value", "n": 2}


def test_parse_smart_quote_delimiters():
    assert parse_llm_json("{“key”: “value”}") == {"key": "value"}


def test_parse_literal_newline_inside_string():
    raw = '{"summary": "line one\nline two"}'  # raw control char — invalid JSON
    assert parse_llm_json(raw) == {"summary": "line one\nline two"}


def test_parse_empty_raises():
    with pytest.raises(JSONRepairError):
        parse_llm_json("   ")


def test_parse_garbage_raises():
    with pytest.raises(JSONRepairError):
        parse_llm_json("the model rambled and produced no json at all")


def test_repair_json_returns_loadable_string():
    assert parse_llm_json(repair_json("x: {'a': [1,2,],}")) == {"a": [1, 2]}
