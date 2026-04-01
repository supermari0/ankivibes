"""Tests for the Anki bridge module."""
from __future__ import annotations

from pathlib import Path

import pytest
from rich.panel import Panel

from ankivibes.anki_bridge import (
    ANKIVIBES_NOTE_TYPE,
    ANKIVIBES_TAG,
    InsertResult,
    backup_collection,
    build_note,
    check_collection_locked,
    ensure_note_type,
    format_card_back,
    format_card_preview,
    insert_staged_notes,
    select_entries_for_anki,
)
from ankivibes.store.jsonl import JsonlStore
from ankivibes.store.models import (
    STATUS_ENRICHED,
    STATUS_READY,
    WordEntry,
)


# -- Helpers ----------------------------------------------------------------


def _enriched_entry(
    lemma: str, frequency: str | None = "0.020", definitions: list | None = None
) -> WordEntry:
    entry = WordEntry.create(
        raw=lemma,
        normalized=lemma,
        lemma=lemma,
        frequency=frequency,
        status=STATUS_ENRICHED,
        reason=None,
        source="test",
    )
    entry.definitions = definitions or [
        {
            "text": "to run",
            "pos": "Verb",
            "examples": [
                {"text": "El niño corre.", "translation": "The child runs."}
            ],
        }
    ]
    entry.pos = "Verb"
    return entry


def _ready_entry(lemma: str) -> WordEntry:
    return WordEntry.create(
        raw=lemma,
        normalized=lemma,
        lemma=lemma,
        frequency="0.010",
        status=STATUS_READY,
        reason=None,
        source="test",
    )


# -- format_card_back -------------------------------------------------------


class TestFormatCardBack:
    def test_basic(self) -> None:
        definitions = [
            {
                "text": "to run",
                "examples": [
                    {"text": "El niño corre.", "translation": "The child runs."}
                ],
            }
        ]
        html = format_card_back(definitions)
        assert "<ol>" in html
        assert "<li>to run" in html
        assert "El niño corre." in html
        assert "The child runs." in html

    def test_multiple_definitions(self) -> None:
        definitions = [
            {"text": "to run", "examples": []},
            {"text": "to flow", "examples": []},
        ]
        html = format_card_back(definitions)
        assert html.count("<li>") == 2
        assert "to run" in html
        assert "to flow" in html

    def test_no_examples(self) -> None:
        definitions = [{"text": "to run", "examples": []}]
        html = format_card_back(definitions)
        assert "<li>to run" in html
        assert "<ul>" not in html

    def test_empty_definitions(self) -> None:
        html = format_card_back([])
        assert "No definitions" in html

    def test_with_pos(self) -> None:
        definitions = [{"text": "to run", "examples": []}]
        html = format_card_back(definitions, pos="Verb")
        assert "Verb" in html

    def test_html_escaping(self) -> None:
        definitions = [{"text": "a < b & c > d", "examples": []}]
        html = format_card_back(definitions)
        assert "&lt;" in html
        assert "&amp;" in html
        assert "&gt;" in html


# -- format_card_preview ----------------------------------------------------


class TestFormatCardPreview:
    def test_returns_panel(self) -> None:
        entry = _enriched_entry("correr")
        result = format_card_preview(entry, 1, 10)
        assert isinstance(result, Panel)

    def test_contains_lemma_and_index(self) -> None:
        entry = _enriched_entry("correr")
        panel = format_card_preview(entry, 3, 12)
        # The Panel renderable is a Text object
        text = str(panel.renderable)
        assert "correr" in text
        assert "[3/12]" in text

    def test_contains_definitions(self) -> None:
        entry = _enriched_entry("correr")
        panel = format_card_preview(entry, 1, 1)
        text = str(panel.renderable)
        assert "to run" in text


# -- select_entries_for_anki ------------------------------------------------


class TestSelectEntriesForAnki:
    def test_filters_enriched_only(self, tmp_store: JsonlStore) -> None:
        enriched = _enriched_entry("correr")
        ready = _ready_entry("hablar")
        tmp_store.save(enriched)
        tmp_store.save(ready)

        result = select_entries_for_anki(tmp_store)

        assert len(result) == 1
        assert result[0].lemma == "correr"

    def test_sorted_by_frequency_ascending(self, tmp_store: JsonlStore) -> None:
        common = _enriched_entry("ser", frequency="0.001")
        rare = _enriched_entry("correr", frequency="0.050")
        tmp_store.save(rare)
        tmp_store.save(common)

        result = select_entries_for_anki(tmp_store)

        assert result[0].lemma == "ser"
        assert result[1].lemma == "correr"


# -- backup_collection ------------------------------------------------------


class TestBackupCollection:
    def test_creates_copy(self, tmp_path: Path) -> None:
        col_path = tmp_path / "collection.anki2"
        col_path.write_bytes(b"fake anki data")
        backup_dir = tmp_path / "backups"

        result = backup_collection(col_path, backup_dir)

        assert result.exists()
        assert result.read_bytes() == b"fake anki data"
        assert result.parent == backup_dir

    def test_creates_backup_dir(self, tmp_path: Path) -> None:
        col_path = tmp_path / "collection.anki2"
        col_path.write_bytes(b"data")
        backup_dir = tmp_path / "nested" / "backups"

        backup_collection(col_path, backup_dir)

        assert backup_dir.exists()


# -- check_collection_locked ------------------------------------------------


class TestCheckCollectionLocked:
    def test_not_locked(self, tmp_path: Path) -> None:
        col_path = tmp_path / "collection.anki2"
        col_path.write_bytes(b"data")
        assert check_collection_locked(col_path) is False

    def test_locked_wal(self, tmp_path: Path) -> None:
        col_path = tmp_path / "collection.anki2"
        col_path.write_bytes(b"data")
        (tmp_path / "collection.anki2-wal").write_bytes(b"wal")
        assert check_collection_locked(col_path) is True

    def test_locked_journal(self, tmp_path: Path) -> None:
        col_path = tmp_path / "collection.anki2"
        col_path.write_bytes(b"data")
        (tmp_path / "collection.anki2-journal").write_bytes(b"journal")
        assert check_collection_locked(col_path) is True


# -- Anki library tests (require anki package) ------------------------------

try:
    from anki.collection import Collection

    _HAS_ANKI = True
except ImportError:
    _HAS_ANKI = False

needs_anki = pytest.mark.skipif(not _HAS_ANKI, reason="anki package not installed")


@needs_anki
class TestEnsureNoteType:
    def test_creates_with_correct_fields(self, tmp_path: Path) -> None:
        col = Collection(str(tmp_path / "test.anki2"))
        try:
            model = ensure_note_type(col)
            field_names = [f["name"] for f in model["flds"]]
            assert field_names == ["Front", "Back", "ankivibes_id"]
        finally:
            col.close()

    def test_idempotent(self, tmp_path: Path) -> None:
        col = Collection(str(tmp_path / "test.anki2"))
        try:
            model1 = ensure_note_type(col)
            model2 = ensure_note_type(col)
            assert model1["id"] == model2["id"]
        finally:
            col.close()

    def test_template_excludes_ankivibes_id(self, tmp_path: Path) -> None:
        col = Collection(str(tmp_path / "test.anki2"))
        try:
            model = ensure_note_type(col)
            tmpl = model["tmpls"][0]
            assert "ankivibes_id" not in tmpl["qfmt"]
            assert "ankivibes_id" not in tmpl["afmt"]
        finally:
            col.close()


@needs_anki
class TestBuildNote:
    def test_correct_fields(self, tmp_path: Path) -> None:
        col = Collection(str(tmp_path / "test.anki2"))
        try:
            model = ensure_note_type(col)
            deck_result = col.decks.add_normal_deck_with_name("Test")
            entry = _enriched_entry("correr")
            note = build_note(col, model, deck_result.id, entry)

            assert note["Front"] == "correr"
            assert "to run" in note["Back"]
            assert note["ankivibes_id"] == entry.id
        finally:
            col.close()

    def test_has_tag(self, tmp_path: Path) -> None:
        col = Collection(str(tmp_path / "test.anki2"))
        try:
            model = ensure_note_type(col)
            deck_result = col.decks.add_normal_deck_with_name("Test")
            entry = _enriched_entry("correr")
            note = build_note(col, model, deck_result.id, entry)

            assert ANKIVIBES_TAG in note.tags
        finally:
            col.close()


@needs_anki
class TestInsertAndVerify:
    def test_roundtrip(self, tmp_path: Path) -> None:
        col_path = tmp_path / "collection.anki2"
        backup_dir = tmp_path / "backups"

        # Create an empty collection first
        col = Collection(str(col_path))
        col.close()

        entry = _enriched_entry("correr")
        results = insert_staged_notes(col_path, "Spanish", [entry], backup_dir)

        assert len(results) == 1
        assert results[0].entry.lemma == "correr"
        assert results[0].anki_note_id > 0

        # Verify backup was created
        assert backup_dir.exists()
        assert len(list(backup_dir.iterdir())) == 1

        # Reopen and verify
        col = Collection(str(col_path))
        try:
            note = col.get_note(results[0].anki_note_id)
            assert note["Front"] == "correr"
            assert "to run" in note["Back"]
            assert note["ankivibes_id"] == entry.id
            assert ANKIVIBES_TAG in note.tags
        finally:
            col.close()
