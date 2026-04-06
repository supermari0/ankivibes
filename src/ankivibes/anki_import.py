"""Import existing Anki deck into ankivibes management."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from anki.notes import NoteId

from rich.panel import Panel
from rich.text import Text

from .anki_bridge import (
    ANKIVIBES_NOTE_TYPE,
    ANKIVIBES_TAG,
    backup_collection,
    ensure_note_type,
    format_card_back,
)
from .editor import definitions_to_text
from .pipeline import normalize
from .store.models import STATUS_ENRICHED, STATUS_INSERTED, WordEntry


@dataclass
class AnkiNoteInfo:
    """Lightweight representation of a note read from an Anki collection."""

    note_id: int
    front: str
    back_html: str
    note_type_name: str


@dataclass
class ImportCandidate:
    """A store entry linked to its source Anki note(s) for the review loop."""

    entry: WordEntry
    notes: list[AnkiNoteInfo]
    decision: str | None = None  # "new", "old", "edit", "skip"
    new_back_html: str | None = None  # set when decision is "new" or "edit"


@dataclass
class MigrateResult:
    """Result of migrating a single note."""

    entry: WordEntry
    anki_note_id: int


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

_HTML_TAG_RE = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Remove HTML tags from text. Simple regex approach for card fronts."""
    return _HTML_TAG_RE.sub("", text).strip()


# ---------------------------------------------------------------------------
# Anki reading functions (require anki package)
# ---------------------------------------------------------------------------


def list_decks(collection_path: Path) -> list[tuple[int, str]]:
    """Return (deck_id, deck_name) pairs for all decks in the collection."""
    from anki.collection import Collection

    col = Collection(str(collection_path))
    try:
        result = []
        for entry in col.decks.all_names_and_ids():
            result.append((entry.id, entry.name))
        return result
    finally:
        col.close()


def read_deck_notes(collection_path: Path, deck_name: str) -> list[AnkiNoteInfo]:
    """Read all Basic notes from a deck, skipping AnkiVibes notes."""
    from anki.collection import Collection

    col = Collection(str(collection_path))
    try:
        note_ids = col.find_notes(f'"deck:{deck_name}"')
        notes: list[AnkiNoteInfo] = []
        for nid in note_ids:
            note = col.get_note(nid)
            note_type = note.note_type()
            type_name = note_type["name"] if note_type is not None else ""
            if type_name == ANKIVIBES_NOTE_TYPE:
                continue
            notes.append(
                AnkiNoteInfo(
                    note_id=note.id,
                    front=note["Front"],
                    back_html=note["Back"],
                    note_type_name=type_name,
                )
            )
        return notes
    finally:
        col.close()


# ---------------------------------------------------------------------------
# Candidate building (pure functions)
# ---------------------------------------------------------------------------


def build_import_candidates(
    notes: list[AnkiNoteInfo],
    entries: list[WordEntry],
) -> list[ImportCandidate]:
    """Link WordEntries to their source Anki notes via normalized front text."""
    # Build lookup: normalized front -> list of notes
    notes_by_normalized: dict[str, list[AnkiNoteInfo]] = {}
    for note in notes:
        key = normalize(strip_html(note.front))
        notes_by_normalized.setdefault(key, []).append(note)

    candidates: list[ImportCandidate] = []
    for entry in entries:
        matched_notes = notes_by_normalized.get(entry.normalized, [])
        if matched_notes:
            candidates.append(ImportCandidate(entry=entry, notes=matched_notes))

    return candidates


# ---------------------------------------------------------------------------
# Display functions (pure, no Anki dependency)
# ---------------------------------------------------------------------------


def format_import_preview(candidate: ImportCandidate, index: int, total: int) -> Panel:
    """Rich panel comparing old card back vs enriched content."""
    entry = candidate.entry
    body = Text()

    header = f"[{index}/{total}]  {entry.lemma}"
    if entry.pos:
        header += f"  ({entry.pos})"
    if entry.frequency:
        header += f"  freq: {entry.frequency}"
    body.append(header + "\n\n")

    # Show the old card back (from first note — all notes share the same front)
    body.append("EXISTING CARD BACK\n", style="bold")
    old_text = strip_html(candidate.notes[0].back_html)
    if old_text:
        for line in old_text.splitlines():
            body.append(f"  {line}\n")
    else:
        body.append("  (empty)\n", style="dim")

    # Show enriched content if available
    if entry.status == STATUS_ENRICHED and entry.definitions:
        body.append("\nWIKTIONARY ENRICHMENT\n", style="bold")
        for defn in entry.definitions:
            body.append(f"  {defn.get('text', '—')}\n")
            for ex in defn.get("examples", []):
                body.append(f'  "{ex.get("text", "")}"\n', style="italic")
                tr = ex.get("translation")
                if tr:
                    body.append(f"  → {tr}\n", style="dim")
        body.append("\n  [n] use new   [o] keep old   [e] edit   [s] skip   [q] quit", style="dim")
    else:
        body.append("\n  [o] keep old   [s] skip   [q] quit", style="dim")

    if len(candidate.notes) > 1:
        body.append(
            f"\n  Note: {len(candidate.notes)} cards share this front — all will be migrated together.",
            style="yellow",
        )

    return Panel(body, expand=False)


def format_edit_with_reference(entry: WordEntry, old_back_html: str) -> str:
    """Enriched definitions as editable text, with old card back as comment header."""
    lines: list[str] = []

    # Old card back as comment
    old_text = strip_html(old_back_html)
    lines.append("# === OLD CARD BACK (reference — delete these lines) ===")
    for line in old_text.splitlines():
        lines.append(f"# {line}")
    lines.append("# ======================================================")
    lines.append("")

    # Enriched definitions in standard edit format
    enriched_text = definitions_to_text(entry.lemma, entry.pos, entry.definitions)
    lines.append(enriched_text)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Migration (requires anki package)
# ---------------------------------------------------------------------------


def migrate_notes(
    collection_path: Path,
    backup_dir: Path,
    candidates: list[ImportCandidate],
) -> list[MigrateResult]:
    """Back up collection, then migrate notes from Basic to AnkiVibes type.

    Only processes candidates whose decision is not "skip" and not None.
    """
    from anki.collection import Collection

    # Filter to actionable candidates
    actionable = [c for c in candidates if c.decision in ("new", "old", "edit")]
    if not actionable:
        return []

    backup_collection(collection_path, backup_dir)

    col = Collection(str(collection_path))
    try:
        model = ensure_note_type(col)
        model_id = model["id"]
        results: list[MigrateResult] = []

        for candidate in actionable:
            # Determine the back HTML to use
            if candidate.decision == "new":
                back_html = format_card_back(candidate.entry.definitions, candidate.entry.pos)
            elif candidate.decision == "edit":
                back_html = candidate.new_back_html or candidate.notes[0].back_html
            else:  # "old"
                back_html = candidate.notes[0].back_html

            for note_info in candidate.notes:
                from anki.notes import NoteId
                note = col.get_note(NoteId(note_info.note_id))

                # Read current fields before changing type
                front = note["Front"]

                # Change model and rebuild fields
                note.mid = model_id
                note.fields = [front, back_html, candidate.entry.id]

                # Add tag
                if ANKIVIBES_TAG not in note.tags:
                    note.tags.append(ANKIVIBES_TAG)

                col.update_note(note)

                results.append(
                    MigrateResult(entry=candidate.entry, anki_note_id=note.id)
                )
    finally:
        col.close()

    return results
