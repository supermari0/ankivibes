"""Tests for the Anki deck import module."""

from __future__ import annotations

from pathlib import Path

import pytest
from rich.panel import Panel

from ankivibes.anki_import import (
    AnkiNoteInfo,
    ImportCandidate,
    build_import_candidates,
    format_edit_with_reference,
    format_import_preview,
    strip_html,
)
from ankivibes.store.models import (
    STATUS_ENRICHED,
    STATUS_NEEDS_REVIEW,
    STATUS_READY,
    WordEntry,
)


# -- Helpers ----------------------------------------------------------------


def _make_entry(
    lemma: str,
    normalized: str | None = None,
    status: str = STATUS_ENRICHED,
    definitions: list[dict] | None = None,
    pos: str | None = "Noun",
    frequency: str | None = "0.500",
) -> WordEntry:
    norm = normalized or lemma.lower()
    return WordEntry.create(
        raw=lemma,
        normalized=norm,
        lemma=lemma,
        frequency=frequency,
        status=status,
        reason=None,
        source="test",
    )


def _make_note(
    note_id: int,
    front: str,
    back_html: str = "<p>definition</p>",
    note_type_name: str = "Basic",
) -> AnkiNoteInfo:
    return AnkiNoteInfo(
        note_id=note_id,
        front=front,
        back_html=back_html,
        note_type_name=note_type_name,
    )


# -- strip_html --------------------------------------------------------------


class TestStripHtml:
    def test_strips_tags(self) -> None:
        assert strip_html("<b>correr</b>") == "correr"

    def test_strips_nested_tags(self) -> None:
        assert strip_html("<p><em>to run</em></p>") == "to run"

    def test_plain_text_unchanged(self) -> None:
        assert strip_html("correr") == "correr"

    def test_strips_whitespace(self) -> None:
        assert strip_html("  correr  ") == "correr"


# -- build_import_candidates --------------------------------------------------


class TestBuildImportCandidates:
    def test_links_notes_to_entries(self) -> None:
        notes = [_make_note(1, "correr"), _make_note(2, "casa")]
        entries = [_make_entry("correr"), _make_entry("casa")]

        candidates = build_import_candidates(notes, entries)
        assert len(candidates) == 2
        assert candidates[0].entry.lemma == "correr"
        assert candidates[0].notes[0].note_id == 1

    def test_handles_duplicates(self) -> None:
        notes = [_make_note(1, "correr"), _make_note(2, "correr")]
        entries = [_make_entry("correr")]

        candidates = build_import_candidates(notes, entries)
        assert len(candidates) == 1
        assert len(candidates[0].notes) == 2

    def test_handles_html_fronts(self) -> None:
        notes = [_make_note(1, "<b>Correr</b>")]
        entries = [_make_entry("correr")]

        candidates = build_import_candidates(notes, entries)
        assert len(candidates) == 1

    def test_unmatched_entries_excluded(self) -> None:
        notes = [_make_note(1, "correr")]
        entries = [_make_entry("correr"), _make_entry("vivir")]

        candidates = build_import_candidates(notes, entries)
        assert len(candidates) == 1
        assert candidates[0].entry.lemma == "correr"

    def test_unmatched_notes_excluded(self) -> None:
        notes = [_make_note(1, "correr"), _make_note(2, "xyz")]
        entries = [_make_entry("correr")]

        candidates = build_import_candidates(notes, entries)
        assert len(candidates) == 1


# -- format_import_preview ---------------------------------------------------


class TestFormatImportPreview:
    def test_enriched_shows_both_sections(self) -> None:
        entry = _make_entry("correr", status=STATUS_ENRICHED)
        entry.definitions = [{"text": "to run", "examples": []}]
        entry.pos = "Verb"
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(1, "correr", "<p>to run fast</p>")],
        )

        panel = format_import_preview(candidate, 1, 10)
        assert isinstance(panel, Panel)
        text = panel.renderable.plain  # type: ignore[union-attr]
        assert "EXISTING CARD BACK" in text
        assert "WIKTIONARY ENRICHMENT" in text
        assert "[n] use new" in text

    def test_non_enriched_shows_old_only(self) -> None:
        entry = _make_entry("correr", status=STATUS_NEEDS_REVIEW)
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(1, "correr", "<p>to run</p>")],
        )

        panel = format_import_preview(candidate, 1, 10)
        text = panel.renderable.plain  # type: ignore[union-attr]
        assert "EXISTING CARD BACK" in text
        assert "WIKTIONARY ENRICHMENT" not in text
        assert "[n] use new" not in text
        assert "[o] keep old" in text

    def test_duplicate_warning(self) -> None:
        entry = _make_entry("correr", status=STATUS_ENRICHED)
        entry.definitions = [{"text": "to run", "examples": []}]
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(1, "correr"), _make_note(2, "correr")],
        )

        panel = format_import_preview(candidate, 1, 10)
        text = panel.renderable.plain  # type: ignore[union-attr]
        assert "2 cards share this front" in text


# -- format_edit_with_reference -----------------------------------------------


class TestFormatEditWithReference:
    def test_contains_old_back_as_comments(self) -> None:
        entry = _make_entry("correr", status=STATUS_ENRICHED)
        entry.definitions = [{"text": "to run", "examples": []}]
        entry.pos = "Verb"

        result = format_edit_with_reference(entry, "<p>to run fast</p>")
        assert "# to run fast" in result
        assert "# === OLD CARD BACK" in result

    def test_contains_enriched_definitions(self) -> None:
        entry = _make_entry("correr", status=STATUS_ENRICHED)
        entry.definitions = [{"text": "to run", "examples": []}]
        entry.pos = "Verb"

        result = format_edit_with_reference(entry, "<p>old</p>")
        assert "to run" in result
        assert "# correr (Verb)" in result


# -- Anki library tests (require anki package) --------------------------------

try:
    from anki.collection import Collection

    _HAS_ANKI = True
except ImportError:
    _HAS_ANKI = False

needs_anki = pytest.mark.skipif(not _HAS_ANKI, reason="anki package not installed")


def _create_basic_collection(col_path: Path, deck_name: str, cards: list[tuple[str, str]]) -> None:
    """Create a collection with Basic notes in the given deck."""
    col = Collection(str(col_path))
    try:
        basic_model = col.models.by_name("Basic")
        assert basic_model is not None
        deck_result = col.decks.add_normal_deck_with_name(deck_name)
        deck_id = deck_result.id

        for front, back in cards:
            note = col.new_note(basic_model)
            note["Front"] = front
            note["Back"] = back
            col.add_note(note, deck_id)  # type: ignore[arg-type]
    finally:
        col.close()


@needs_anki
class TestListDecks:
    def test_lists_decks(self, tmp_path: Path) -> None:
        from ankivibes.anki_import import list_decks

        col_path = tmp_path / "test.anki2"
        col = Collection(str(col_path))
        try:
            col.decks.add_normal_deck_with_name("Spanish")
            col.decks.add_normal_deck_with_name("French")
        finally:
            col.close()

        decks = list_decks(col_path)
        names = [name for _, name in decks]
        assert "Spanish" in names
        assert "French" in names


@needs_anki
class TestReadDeckNotes:
    def test_reads_basic_notes(self, tmp_path: Path) -> None:
        from ankivibes.anki_import import read_deck_notes

        col_path = tmp_path / "test.anki2"
        _create_basic_collection(col_path, "Spanish", [("correr", "to run"), ("casa", "house")])

        notes = read_deck_notes(col_path, "Spanish")
        assert len(notes) == 2
        fronts = {n.front for n in notes}
        assert fronts == {"correr", "casa"}
        assert all(n.note_type_name == "Basic" for n in notes)

    def test_skips_ankivibes_notes(self, tmp_path: Path) -> None:
        from ankivibes.anki_bridge import ensure_note_type
        from ankivibes.anki_import import read_deck_notes

        col_path = tmp_path / "test.anki2"
        _create_basic_collection(col_path, "Spanish", [("correr", "to run")])

        # Add an AnkiVibes note
        col = Collection(str(col_path))
        try:
            model = ensure_note_type(col)
            deck_result = col.decks.add_normal_deck_with_name("Spanish")
            note = col.new_note(model)
            note["Front"] = "vivir"
            note["Back"] = "to live"
            note["ankivibes_id"] = "abc123"
            col.add_note(note, deck_result.id)  # type: ignore[arg-type]
        finally:
            col.close()

        notes = read_deck_notes(col_path, "Spanish")
        assert len(notes) == 1
        assert notes[0].front == "correr"


@needs_anki
class TestMigrateNotes:
    def test_changes_note_type(self, tmp_path: Path) -> None:
        from ankivibes.anki_import import migrate_notes

        col_path = tmp_path / "test.anki2"
        _create_basic_collection(col_path, "Spanish", [("correr", "to run")])

        # Read the note ID
        col = Collection(str(col_path))
        try:
            note_ids = col.find_notes("")
            note_id = note_ids[0]
        finally:
            col.close()

        entry = _make_entry("correr")
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(note_id, "correr", "to run")],
            decision="old",
        )

        backup_dir = tmp_path / "backups"
        results = migrate_notes(col_path, backup_dir, [candidate])
        assert len(results) == 1

        # Verify the note type changed
        col = Collection(str(col_path))
        try:
            note = col.get_note(note_id)
            assert note.note_type()["name"] == "AnkiVibes"
            assert note["Front"] == "correr"
            assert note["Back"] == "to run"  # kept old
            assert note["ankivibes_id"] == entry.id
            assert "ankivibes" in note.tags
        finally:
            col.close()

    def test_updates_back_when_new(self, tmp_path: Path) -> None:
        from ankivibes.anki_import import migrate_notes

        col_path = tmp_path / "test.anki2"
        _create_basic_collection(col_path, "Spanish", [("correr", "old back")])

        col = Collection(str(col_path))
        try:
            note_id = col.find_notes("")[0]
        finally:
            col.close()

        entry = _make_entry("correr", status=STATUS_ENRICHED)
        entry.definitions = [{"text": "to run", "examples": []}]
        entry.pos = "Verb"
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(note_id, "correr", "old back")],
            decision="new",
        )

        results = migrate_notes(col_path, tmp_path / "backups", [candidate])
        assert len(results) == 1

        col = Collection(str(col_path))
        try:
            note = col.get_note(note_id)
            assert "to run" in note["Back"]
            assert "old back" not in note["Back"]
        finally:
            col.close()

    def test_preserves_back_when_old(self, tmp_path: Path) -> None:
        from ankivibes.anki_import import migrate_notes

        col_path = tmp_path / "test.anki2"
        _create_basic_collection(col_path, "Spanish", [("correr", "my custom back")])

        col = Collection(str(col_path))
        try:
            note_id = col.find_notes("")[0]
        finally:
            col.close()

        entry = _make_entry("correr", status=STATUS_ENRICHED)
        entry.definitions = [{"text": "to run", "examples": []}]
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(note_id, "correr", "my custom back")],
            decision="old",
        )

        migrate_notes(col_path, tmp_path / "backups", [candidate])

        col = Collection(str(col_path))
        try:
            note = col.get_note(note_id)
            assert note["Back"] == "my custom back"
        finally:
            col.close()

    def test_skips_skip_decision(self, tmp_path: Path) -> None:
        from ankivibes.anki_import import migrate_notes

        col_path = tmp_path / "test.anki2"
        _create_basic_collection(col_path, "Spanish", [("correr", "to run")])

        entry = _make_entry("correr")
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(1, "correr")],
            decision="skip",
        )

        results = migrate_notes(col_path, tmp_path / "backups", [candidate])
        assert len(results) == 0

    def test_creates_backup(self, tmp_path: Path) -> None:
        from ankivibes.anki_import import migrate_notes

        col_path = tmp_path / "test.anki2"
        _create_basic_collection(col_path, "Spanish", [("correr", "to run")])

        col = Collection(str(col_path))
        try:
            note_id = col.find_notes("")[0]
        finally:
            col.close()

        entry = _make_entry("correr")
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(note_id, "correr", "to run")],
            decision="old",
        )

        backup_dir = tmp_path / "backups"
        migrate_notes(col_path, backup_dir, [candidate])
        assert any(backup_dir.iterdir())

    def test_preserves_review_history(self, tmp_path: Path) -> None:
        from ankivibes.anki_import import migrate_notes

        col_path = tmp_path / "test.anki2"
        _create_basic_collection(col_path, "Spanish", [("correr", "to run")])

        # Simulate a review by modifying card scheduling data
        col = Collection(str(col_path))
        try:
            note_id = col.find_notes("")[0]
            card_ids = col.find_cards("")
            card = col.get_card(card_ids[0])
            card.ivl = 30  # 30-day interval
            card.reps = 5
            card.lapses = 1
            col.update_card(card)
            original_ivl = card.ivl
            original_reps = card.reps
            original_lapses = card.lapses
        finally:
            col.close()

        entry = _make_entry("correr")
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(note_id, "correr", "to run")],
            decision="old",
        )

        migrate_notes(col_path, tmp_path / "backups", [candidate])

        # Verify scheduling data preserved
        col = Collection(str(col_path))
        try:
            card = col.get_card(card_ids[0])
            assert card.ivl == original_ivl
            assert card.reps == original_reps
            assert card.lapses == original_lapses
        finally:
            col.close()

    def test_idempotent(self, tmp_path: Path) -> None:
        """Running import twice: second pass finds no Basic notes to migrate."""
        from ankivibes.anki_import import migrate_notes, read_deck_notes

        col_path = tmp_path / "test.anki2"
        _create_basic_collection(col_path, "Spanish", [("correr", "to run")])

        col = Collection(str(col_path))
        try:
            note_id = col.find_notes("")[0]
        finally:
            col.close()

        entry = _make_entry("correr")
        candidate = ImportCandidate(
            entry=entry,
            notes=[_make_note(note_id, "correr", "to run")],
            decision="old",
        )

        migrate_notes(col_path, tmp_path / "backups", [candidate])

        # Second read should find no Basic notes
        notes = read_deck_notes(col_path, "Spanish")
        assert len(notes) == 0
