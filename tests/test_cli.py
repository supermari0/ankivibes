"""Tests for the CLI subcommands."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ankivibes.cli import app
from ankivibes.store.jsonl import JsonlStore
from ankivibes.store.models import STATUS_INSERTED, STATUS_READY, WordEntry

runner = CliRunner()

FIXTURES_DIR = Path(__file__).parent / "fixtures"
SAMPLE_WORDS = FIXTURES_DIR / "sample_words.txt"
CORPUS_SAMPLE = FIXTURES_DIR / "corpus_sample.tsv"


def test_help_shows_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "list", "enrich", "anki", "review"):
        assert cmd in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "ankivibes" in result.output


def test_ingest_missing_file(tmp_path):
    result = runner.invoke(app, ["ingest", str(tmp_path / "nope.txt")])
    assert result.exit_code == 1


def test_ingest_produces_summary(tmp_path):
    store_path = tmp_path / "words.jsonl"
    result = runner.invoke(app, [
        "ingest", str(SAMPLE_WORDS),
        "--store-path", str(store_path),
    ])
    assert result.exit_code == 0
    assert "ready" in result.output
    assert "needs_review" in result.output


def test_list_empty_store(tmp_path):
    store_path = tmp_path / "words.jsonl"
    result = runner.invoke(app, ["list", "--store-path", str(store_path)])
    assert result.exit_code == 0
    assert "No words found" in result.output


def test_list_shows_entries(tmp_path):
    store_path = tmp_path / "words.jsonl"
    store = JsonlStore(store_path)
    store.save(WordEntry.create(
        raw="correr",
        normalized="correr",
        lemma="correr",
        frequency="0.015",
        status=STATUS_READY,
        reason=None,
        source="test",
    ))
    result = runner.invoke(app, ["list", "--store-path", str(store_path)])
    assert result.exit_code == 0
    assert "correr" in result.output


def test_list_status_filter(tmp_path):
    store_path = tmp_path / "words.jsonl"
    store = JsonlStore(store_path)
    store.save(WordEntry.create(
        raw="correr", normalized="correr", lemma="correr",
        frequency="0.015", status=STATUS_READY, reason=None, source="test",
    ))
    store.save(WordEntry.create(
        raw="xyz", normalized="xyz", lemma="xyz",
        frequency=None, status="needs_review", reason="no_frequency", source="test",
    ))
    result = runner.invoke(app, ["list", "--status", "needs_review", "--store-path", str(store_path)])
    assert result.exit_code == 0
    assert "xyz" in result.output
    assert "correr" not in result.output


def test_review_no_entries(tmp_path):
    store_path = tmp_path / "words.jsonl"
    result = runner.invoke(app, ["review", "--store-path", str(store_path)])
    assert result.exit_code == 0
    assert "No words need review" in result.output


def test_enrich_stub():
    result = runner.invoke(app, ["enrich"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output


def test_anki_stub():
    result = runner.invoke(app, ["anki"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output
