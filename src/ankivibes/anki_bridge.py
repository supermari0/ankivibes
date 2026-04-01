"""Anki deck integration: card formatting, backup, note type management, and insertion."""
from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.panel import Panel
from rich.text import Text

from .store.models import STATUS_ENRICHED, WordEntry
from .store.protocol import WordStore

ANKIVIBES_NOTE_TYPE = "AnkiVibes"
ANKIVIBES_TAG = "ankivibes"

FRONT_TEMPLATE = "{{Front}}"
BACK_TEMPLATE = "{{FrontSide}}\n<hr id=answer>\n{{Back}}"


# ---------------------------------------------------------------------------
# Pure functions (no Anki dependency)
# ---------------------------------------------------------------------------


def format_card_back(definitions: list[dict[str, Any]], pos: str | None = None) -> str:
    """Render definitions and examples as HTML for an Anki card back."""
    if not definitions:
        return "<p><em>No definitions available.</em></p>"

    parts: list[str] = []
    if pos:
        parts.append(f"<p><em>{_html_escape(pos)}</em></p>")

    parts.append("<ol>")
    for defn in definitions:
        text = _html_escape(defn.get("text", ""))
        parts.append(f"  <li>{text}")
        examples = defn.get("examples", [])
        if examples:
            parts.append("    <ul>")
            for ex in examples:
                ex_text = _html_escape(ex.get("text", ""))
                translation = ex.get("translation")
                parts.append(f'      <li><i>"{ex_text}"</i>')
                if translation:
                    parts.append(f"        <br><span>{_html_escape(translation)}</span>")
                parts.append("      </li>")
            parts.append("    </ul>")
        parts.append("  </li>")
    parts.append("</ol>")

    return "\n".join(parts)


def _html_escape(text: str) -> str:
    """Minimal HTML escaping for card content."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_card_preview(entry: WordEntry, index: int, total: int) -> Panel:
    """Build a Rich Panel previewing a card for the interactive review loop."""
    body = Text()

    header = f"[{index}/{total}]  {entry.lemma}"
    if entry.pos:
        header += f"  ({entry.pos})"
    if entry.frequency:
        header += f"  freq: {entry.frequency}"
    body.append(header + "\n\n")

    body.append("FRONT\n", style="bold")
    body.append(f"  {entry.lemma}\n\n")

    body.append("BACK\n", style="bold")
    if entry.definitions:
        for defn in entry.definitions:
            body.append(f"  {defn.get('text', '—')}\n")
            for ex in defn.get("examples", []):
                body.append(f'  "{ex.get("text", "")}"\n', style="italic")
                tr = ex.get("translation")
                if tr:
                    body.append(f"  → {tr}\n", style="dim")
    else:
        body.append("  (no definitions)\n", style="dim")

    body.append("\n  [a] accept   [e] edit   [s] skip   [q] quit", style="dim")

    return Panel(body, expand=False)


def select_entries_for_anki(store: WordStore) -> list[WordEntry]:
    """Return enriched entries sorted by frequency descending (most common first)."""
    entries = [e for e in store.all() if e.status == STATUS_ENRICHED]

    def sort_key(e: WordEntry) -> float:
        try:
            return float(e.frequency) if e.frequency else float("inf")
        except ValueError:
            return float("inf")

    entries.sort(key=sort_key)
    return entries


# ---------------------------------------------------------------------------
# Filesystem functions
# ---------------------------------------------------------------------------


def backup_collection(collection_path: Path, backup_dir: Path) -> Path:
    """Copy the .anki2 file to backup_dir with a timestamp. Returns the backup path."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"collection_{timestamp}.anki2"
    backup_path = backup_dir / backup_name
    shutil.copy2(collection_path, backup_path)
    return backup_path


def check_collection_locked(collection_path: Path) -> bool:
    """Check if the Anki collection appears to be locked (Anki is open)."""
    wal = collection_path.with_suffix(".anki2-wal")
    journal = collection_path.with_suffix(".anki2-journal")
    return wal.exists() or journal.exists()


# ---------------------------------------------------------------------------
# Anki library functions
# ---------------------------------------------------------------------------


@dataclass
class InsertResult:
    entry: WordEntry
    anki_note_id: int


def ensure_note_type(col: Any) -> Any:
    """Create the AnkiVibes note type if it doesn't exist. Returns the model dict."""
    existing = col.models.by_name(ANKIVIBES_NOTE_TYPE)
    if existing:
        return existing

    model = col.models.new(ANKIVIBES_NOTE_TYPE)

    for field_name in ("Front", "Back", "ankivibes_id"):
        fld = col.models.new_field(field_name)
        col.models.add_field(model, fld)

    tmpl = col.models.new_template("Card 1")
    tmpl["qfmt"] = FRONT_TEMPLATE
    tmpl["afmt"] = BACK_TEMPLATE
    col.models.add_template(model, tmpl)

    col.models.add(model)
    return model


def build_note(col: Any, model: Any, deck_id: Any, entry: WordEntry) -> Any:
    """Construct an Anki Note from a WordEntry."""
    note = col.new_note(model)
    note["Front"] = entry.lemma
    note["Back"] = format_card_back(entry.definitions, entry.pos)
    note["ankivibes_id"] = entry.id
    note.tags = [ANKIVIBES_TAG]
    note.note_type()["did"] = deck_id
    return note


def insert_staged_notes(
    collection_path: Path,
    deck_name: str,
    entries: list[WordEntry],
    backup_dir: Path,
) -> list[InsertResult]:
    """Back up the collection, then insert notes for the given entries.

    Returns a list of InsertResult with the Anki note IDs assigned.
    """
    from anki.collection import Collection

    if collection_path.exists():
        backup_collection(collection_path, backup_dir)

    col = Collection(str(collection_path))
    try:
        model = ensure_note_type(col)
        deck_result = col.decks.add_normal_deck_with_name(deck_name)
        deck_id = deck_result.id

        results: list[InsertResult] = []
        for entry in entries:
            note = build_note(col, model, deck_id, entry)
            col.add_note(note, deck_id)  # type: ignore[arg-type]
            results.append(InsertResult(entry=entry, anki_note_id=note.id))
    finally:
        col.close()

    return results
