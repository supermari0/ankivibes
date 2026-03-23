"""Tests for the editor text format (serialize/parse)."""
from __future__ import annotations

from ankivibes.editor import definitions_to_text, text_to_definitions


def test_round_trip():
    definitions = [
        {
            "text": "to run",
            "pos": "Verb",
            "examples": [
                {"text": "El niño corre.", "translation": "The child runs."}
            ],
        },
        {
            "text": "to flow",
            "pos": "Verb",
            "examples": [],
        },
    ]

    text = definitions_to_text("correr", "Verb", definitions)
    parsed = text_to_definitions(text)

    assert len(parsed) == 2
    assert parsed[0]["text"] == "to run"
    assert len(parsed[0]["examples"]) == 1
    assert parsed[0]["examples"][0]["text"] == "El niño corre."
    assert parsed[0]["examples"][0]["translation"] == "The child runs."
    assert parsed[1]["text"] == "to flow"
    assert parsed[1]["examples"] == []


def test_comments_are_ignored():
    text = "# comment\nto run\n# another comment\n"
    parsed = text_to_definitions(text)
    assert len(parsed) == 1
    assert parsed[0]["text"] == "to run"


def test_empty_input():
    parsed = text_to_definitions("")
    assert parsed == []


def test_multiple_examples():
    text = "to run\n  He runs fast.\n  > Corre rápido.\n  She runs too.\n"
    parsed = text_to_definitions(text)
    assert len(parsed) == 1
    assert len(parsed[0]["examples"]) == 2
    assert parsed[0]["examples"][0]["translation"] == "Corre rápido."
    assert parsed[0]["examples"][1]["text"] == "She runs too."
    assert parsed[0]["examples"][1]["translation"] is None
