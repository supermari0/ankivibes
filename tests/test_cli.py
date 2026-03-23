"""Tests for the CLI subcommands."""
from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from ankivibes.cli import app
from ankivibes.store.jsonl import JsonlStore
from unittest.mock import MagicMock, patch

from ankivibes.store.models import STATUS_ENRICHED, STATUS_INSERTED, STATUS_READY, WordEntry

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


CORRER_PAYLOAD = {
    "es": [
        {
            "partOfSpeech": "Verb",
            "definitions": [
                {
                    "definition": "to <b>run</b>",
                    "parsedExamples": [
                        {
                            "example": "El niño corre por el parque.",
                            "translation": "The child runs through the park.",
                        }
                    ],
                }
            ],
        }
    ]
}


def test_enrich_prompts_for_email(tmp_path):
    """When no contact_email is configured, enrich prompts for one."""
    store_path = tmp_path / "words.jsonl"
    config_path = tmp_path / "config.toml"
    store = JsonlStore(store_path)
    store.save(WordEntry.create(
        raw="correr", normalized="correr", lemma="correr",
        frequency="0.015", status=STATUS_READY, reason=None, source="test",
    ))

    mock_client = MagicMock()
    mock_client.fetch_definitions.return_value = CORRER_PAYLOAD

    with (
        patch("ankivibes.cli.cfg_module.load", return_value=MagicMock(
            contact_email=None, store_path=store_path,
        )),
        patch("ankivibes.cli.cfg_module.save") as mock_save,
        patch("ankivibes.cli.cfg_module._CONFIG_PATH", config_path),
        patch("pytionary.WiktionaryClient", return_value=mock_client),
    ):
        result = runner.invoke(app, ["enrich"], input="test@example.com\n")

    assert result.exit_code == 0
    assert "Contact email" in result.output
    mock_save.assert_called_once()


def test_enrich_summary_output(tmp_path):
    """Enrich prints a summary table with enriched/skipped counts."""
    store_path = tmp_path / "words.jsonl"
    store = JsonlStore(store_path)
    store.save(WordEntry.create(
        raw="correr", normalized="correr", lemma="correr",
        frequency="0.015", status=STATUS_READY, reason=None, source="test",
    ))

    mock_client = MagicMock()
    mock_client.fetch_definitions.return_value = CORRER_PAYLOAD

    with (
        patch("ankivibes.cli.cfg_module.load", return_value=MagicMock(
            contact_email="test@example.com", store_path=store_path,
        )),
        patch("pytionary.WiktionaryClient", return_value=mock_client),
    ):
        result = runner.invoke(app, ["enrich"])

    assert result.exit_code == 0
    assert "enriched" in result.output.lower()

    saved = store.get(store.all()[0].id)
    assert saved.status == STATUS_ENRICHED


def _enriched_entry(lemma="correr", frequency="0.015"):
    entry = WordEntry.create(
        raw=lemma, normalized=lemma, lemma=lemma,
        frequency=frequency, status=STATUS_ENRICHED, reason=None, source="test",
    )
    entry.pos = "Verb"
    entry.definitions = [
        {
            "text": "to run",
            "pos": "Verb",
            "examples": [
                {"text": "El niño corre.", "translation": "The child runs."}
            ],
        }
    ]
    return entry


def test_show_displays_enriched_entry(tmp_path):
    store_path = tmp_path / "words.jsonl"
    store = JsonlStore(store_path)
    store.save(_enriched_entry())

    result = runner.invoke(app, ["show", "correr", "--store-path", str(store_path)])
    assert result.exit_code == 0
    assert "correr" in result.output
    assert "Verb" in result.output
    assert "to run" in result.output
    assert "El niño corre." in result.output


def test_show_unknown_lemma(tmp_path):
    store_path = tmp_path / "words.jsonl"
    result = runner.invoke(app, ["show", "nope", "--store-path", str(store_path)])
    assert result.exit_code == 1
    assert "No entry found" in result.output


def test_edit_sets_edited_flag(tmp_path):
    store_path = tmp_path / "words.jsonl"
    store = JsonlStore(store_path)
    store.save(_enriched_entry())

    edited_text = "to run\n  El niño corre.\n  > The child runs.\n\nto sprint\n"

    def fake_editor(args):
        """Write edited content to the temp file the editor would open."""
        Path(args[1]).write_text(edited_text, encoding="utf-8")
        return MagicMock(returncode=0)

    with patch.dict("os.environ", {"EDITOR": "fake-editor"}), \
         patch("subprocess.run", side_effect=fake_editor):
        result = runner.invoke(app, ["edit", "correr", "--store-path", str(store_path)])

    assert result.exit_code == 0
    saved = store.get(store.all()[0].id)
    assert saved.edited is True


def test_anki_stub():
    result = runner.invoke(app, ["anki"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output
