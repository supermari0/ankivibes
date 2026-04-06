"""Typer app and subcommand registration."""
from __future__ import annotations

from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from . import config as cfg_module
from .corpus import CORPESCorpus
from .lemmatizer import SpacyLemmatizer
from .pipeline import ingest_words
from .store.jsonl import JsonlStore
from .enrich import enrich_one, select_entries_to_enrich
from .store.models import STATUS_ENRICHED, STATUS_INSERTED, STATUS_NEEDS_REVIEW, STATUS_READY, WordEntry

app = typer.Typer(help="Spanish vocabulary study tool with Anki integration.")
console = Console()


def version_callback(value: bool) -> None:
    if value:
        v = version("ankivibes")
        rprint(f"ankivibes {v}")
        raise typer.Exit()


@app.callback()
def main(
    version: Annotated[
        Optional[bool],
        typer.Option("--version", callback=version_callback, is_eager=True, help="Show version and exit."),
    ] = None,
) -> None:
    """ankivibes — Spanish vocabulary study tool with Anki integration."""


@app.command()
def ingest(
    file: Annotated[Path, typer.Argument(help="Word list file (one word per line).")],
    store_path: Annotated[Optional[Path], typer.Option(help="Override default store path.")] = None,
) -> None:
    """Ingest a word list, lemmatize, and score by frequency."""
    if not file.exists():
        rprint(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    cfg = cfg_module.load()
    effective_store = store_path or cfg.store_path

    if not cfg.corpus_path.exists():
        rprint(f"[red]Error:[/red] Corpus file not found: {cfg.corpus_path}")
        rprint("Set [bold]corpus_path[/bold] in ~/.config/ankivibes/config.toml")
        raise typer.Exit(1)

    raw_words = file.read_text(encoding="utf-8").splitlines()
    corpus = CORPESCorpus(cfg.corpus_path)
    lemmatizer = SpacyLemmatizer()
    entries = ingest_words(raw_words, source=file.name, lemmatizer=lemmatizer, corpus=corpus)

    store = JsonlStore(effective_store)
    counts = {STATUS_READY: 0, STATUS_NEEDS_REVIEW: 0, STATUS_INSERTED: 0}
    for entry in entries:
        existing = store.get(entry.id)
        merged = store.merge(entry)
        if existing and existing.status == STATUS_INSERTED:
            counts[STATUS_INSERTED] += 1
        elif merged.status == STATUS_READY:
            counts[STATUS_READY] += 1
        else:
            counts[STATUS_NEEDS_REVIEW] += 1

    table = Table(title=f"Ingested {len(entries)} words from {file.name}")
    table.add_column("Status", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("ready", str(counts[STATUS_READY]), style="green")
    table.add_row("needs_review", str(counts[STATUS_NEEDS_REVIEW]), style="yellow")
    table.add_row("already inserted", str(counts[STATUS_INSERTED]), style="dim")
    console.print(table)


@app.command(name="list")
def list_words(
    status: Annotated[Optional[str], typer.Option(help="Filter by status.")] = None,
    top: Annotated[int, typer.Option(help="Show top N words by frequency.")] = 20,
    all: Annotated[bool, typer.Option("--all", help="Show all words (overrides --top).")] = False,
    store_path: Annotated[Optional[Path], typer.Option(help="Override default store path.")] = None,
) -> None:
    """List stored words sorted by frequency."""
    cfg = cfg_module.load()
    effective_store = store_path or cfg.store_path
    store = JsonlStore(effective_store)
    entries = store.all()

    if status:
        entries = [e for e in entries if e.status == status]

    # Sort by frequency ascending (lower DP = more common = show first)
    def sort_key(e):
        try:
            return float(e.frequency) if e.frequency else float("inf")
        except ValueError:
            return float("inf")

    entries.sort(key=sort_key)

    if not all:
        entries = entries[:top]

    if not entries:
        rprint("[dim]No words found.[/dim]")
        return

    table = Table()
    table.add_column("Lemma", style="bold")
    table.add_column("Normalized")
    table.add_column("Status")
    table.add_column("Frequency (DP)", justify="right")
    table.add_column("Source", style="dim")

    status_styles = {
        STATUS_READY: "green",
        STATUS_NEEDS_REVIEW: "yellow",
        STATUS_INSERTED: "blue",
        "enriched": "cyan",
        "skipped": "dim",
    }
    for entry in entries:
        style = status_styles.get(entry.status, "")
        table.add_row(
            entry.lemma,
            entry.normalized,
            entry.status,
            entry.frequency or "—",
            entry.source,
            style=style,
        )
    console.print(table)


@app.command()
def review(
    store_path: Annotated[Optional[Path], typer.Option(help="Override default store path.")] = None,
) -> None:
    """List words that need review, with their reason codes."""
    cfg = cfg_module.load()
    effective_store = store_path or cfg.store_path
    store = JsonlStore(effective_store)
    entries = [e for e in store.all() if e.status == STATUS_NEEDS_REVIEW]

    if not entries:
        rprint("[green]No words need review.[/green]")
        return

    table = Table(title=f"{len(entries)} words need review")
    table.add_column("Normalized")
    table.add_column("Lemma")
    table.add_column("Reason", style="yellow")
    table.add_column("Source", style="dim")
    for entry in entries:
        table.add_row(entry.normalized, entry.lemma, entry.reason or "—", entry.source)
    console.print(table)


@app.command()
def enrich(
    store_path: Annotated[Optional[Path], typer.Option(help="Override default store path.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Re-fetch definitions for already-enriched entries.")] = False,
    top: Annotated[Optional[int], typer.Option("--top", help="Only enrich the top N entries by frequency.")] = None,
) -> None:
    """Enrich words with Wiktionary definitions."""
    from pytionary import WiktionaryClient

    cfg = cfg_module.load()

    if cfg.contact_email is None:
        rprint("Wiktionary requests require a contact email for the User-Agent header.")
        cfg.contact_email = typer.prompt("Contact email")
        cfg_module.save(cfg)
        rprint(f"Saved to {cfg_module._CONFIG_PATH}")

    effective_store = store_path or cfg.store_path
    store = JsonlStore(effective_store)
    client = WiktionaryClient(cfg.contact_email)

    entries = select_entries_to_enrich(store, force=force, top_n=top)
    if not entries:
        rprint("[dim]No entries to enrich.[/dim]")
        return

    enriched_count = 0
    skipped_count = 0
    errors: list[tuple[str, str]] = []

    from rich.progress import track

    for entry in track(entries, description="Enriching..."):
        outcome, error_msg = enrich_one(entry, client, store)
        if outcome == "enriched":
            enriched_count += 1
        else:
            skipped_count += 1
            if error_msg:
                errors.append((entry.lemma, error_msg))

    table = Table(title="Enrichment Summary")
    table.add_column("Outcome", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("enriched", str(enriched_count), style="green")
    table.add_row("skipped", str(skipped_count), style="yellow")
    console.print(table)

    for lemma, msg in errors:
        rprint(f"  [yellow]Warning:[/yellow] {lemma}: {msg}")


@app.command()
def show(
    lemma: Annotated[str, typer.Argument(help="The lemma to look up.")],
    store_path: Annotated[Optional[Path], typer.Option(help="Override default store path.")] = None,
) -> None:
    """Show full details for a word."""
    from rich.panel import Panel
    from rich.text import Text

    cfg = cfg_module.load()
    effective_store = store_path or cfg.store_path
    store = JsonlStore(effective_store)

    entry = next((e for e in store.all() if e.lemma == lemma), None)
    if entry is None:
        rprint(f"[red]Error:[/red] No entry found with lemma '{lemma}'")
        raise typer.Exit(1)

    # TODO: Update this to show the normalized word, too, so you can check that the ingest pipeline didn't
    # do something weird.
    body = Text()
    body.append(f"Status: {entry.status}    POS: {entry.pos or '—'}    Edited: {'yes' if entry.edited else 'no'}\n")
    body.append(f"Frequency (DP): {entry.frequency or '—'}\n")
    body.append(f"Source: {entry.source}\n")

    if entry.definitions:
        body.append("\nDefinitions:\n")
        for i, defn in enumerate(entry.definitions, 1):
            body.append(f"  {i}. {defn.get('text', '—')}\n")
            examples = defn.get("examples", [])
            if examples:
                for ex in examples:
                    body.append(f'     "{ex.get("text", "")}"\n', style="italic")
                    tr = ex.get("translation")
                    if tr:
                        body.append(f"     → {tr}\n", style="dim")
            else:
                body.append("     (no examples)\n", style="dim")
    else:
        body.append("\n(no definitions)\n", style="dim")

    body.append(f"\nCreated: {entry.created_at}\n", style="dim")
    body.append(f"Updated: {entry.updated_at}\n", style="dim")

    console.print(Panel(body, title=entry.lemma, expand=False))


@app.command()
def edit(
    lemma: Annotated[str, typer.Argument(help="The lemma to edit.")],
    store_path: Annotated[Optional[Path], typer.Option(help="Override default store path.")] = None,
) -> None:
    """Edit definitions for a word in $EDITOR."""
    import os
    import subprocess
    import tempfile
    from datetime import datetime, timezone

    from .editor import definitions_to_text, text_to_definitions

    cfg = cfg_module.load()
    effective_store = store_path or cfg.store_path
    store = JsonlStore(effective_store)

    entry = next((e for e in store.all() if e.lemma == lemma), None)
    if entry is None:
        rprint(f"[red]Error:[/red] No entry found with lemma '{lemma}'")
        raise typer.Exit(1)

    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if not editor:
        rprint("[red]Error:[/red] $EDITOR is not set. Set it to your preferred text editor.")
        raise typer.Exit(1)

    original_text = definitions_to_text(entry.lemma, entry.pos, entry.definitions)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", prefix=f"ankivibes_{lemma}_", delete=False) as f:
        f.write(original_text)
        tmp_path = f.name

    try:
        result = subprocess.run([editor, tmp_path])
        if result.returncode != 0:
            rprint("[red]Editor exited with an error.[/red]")
            raise typer.Exit(1)

        edited_text = Path(tmp_path).read_text(encoding="utf-8")
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if edited_text == original_text:
        rprint("[dim]No changes made.[/dim]")
        return

    new_definitions = text_to_definitions(edited_text)
    entry.definitions = new_definitions
    if new_definitions and new_definitions[0].get("pos"):
        entry.pos = new_definitions[0]["pos"]
    entry.edited = True
    entry.updated_at = datetime.now(timezone.utc).isoformat()
    store.save(entry)
    rprint(f"[green]Updated {lemma} with {len(new_definitions)} definition(s).[/green]")


def _run_profile_setup(cfg: cfg_module.Config) -> Path:
    """Discover or create an Anki profile and save the collection path to config."""
    from .anki_profile import create_profile, discover_profiles, find_anki_base_dir, format_profile_menu, resolve_profile

    base_dir = find_anki_base_dir()
    if base_dir is None:
        rprint("No Anki data directory found.")
        path_str = typer.prompt("Path to your .anki2 file")
        col_path = Path(path_str).expanduser()
        cfg.anki.collection_path = col_path
        cfg_module.save(cfg)
        rprint(f"Saved to {cfg_module._CONFIG_PATH}")
        return col_path

    rprint("No Anki collection configured.")
    profiles = discover_profiles(base_dir)

    if not profiles:
        rprint(f"No existing Anki profiles found at {base_dir}/")
        if typer.confirm("Create a new Anki profile?", default=True):
            name = typer.prompt("Profile name", default="User 1")
            profile = create_profile(base_dir, name)
            rprint(f"Created new Anki profile at:\n  {profile.collection_path}")
        else:
            raise typer.Abort()

    elif len(profiles) == 1:
        p = profiles[0]
        rprint(f"Found Anki profile: {p.name}  ({p.collection_path})")
        if typer.confirm("Use this profile?", default=True):
            profile = p
        else:
            name = typer.prompt("Profile name", default="User 1")
            profile = create_profile(base_dir, name)
            rprint(f"Created new Anki profile at:\n  {profile.collection_path}")

    else:
        rprint("Found Anki profiles:")
        rprint(format_profile_menu(profiles))
        choice = typer.prompt("Select profile", type=int, default=1)
        if choice == len(profiles) + 1:
            name = typer.prompt("Profile name", default="User 1")
            profile = create_profile(base_dir, name)
            rprint(f"Created new Anki profile at:\n  {profile.collection_path}")
        else:
            profile = resolve_profile(profiles, choice)

    cfg.anki.collection_path = profile.collection_path
    cfg_module.save(cfg)
    rprint(f"Saved to {cfg_module._CONFIG_PATH}")
    return profile.collection_path


@app.command()
def anki(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview cards without writing to Anki.")] = False,
    store_path: Annotated[Optional[Path], typer.Option(help="Override default store path.")] = None,
) -> None:
    """Review and insert cards into Anki."""
    import os
    import subprocess
    import tempfile
    from datetime import datetime, timezone

    import click

    from .anki_bridge import (
        check_collection_locked,
        format_card_preview,
        insert_staged_notes,
        select_entries_for_anki,
    )
    from .editor import definitions_to_text, text_to_definitions

    cfg = cfg_module.load()
    effective_store = store_path or cfg.store_path
    store = JsonlStore(effective_store)

    entries = select_entries_for_anki(store)
    if not entries:
        rprint("[dim]No enriched entries to review.[/dim]")
        return

    # Set up collection path if not configured (only after confirming there's work)
    if not dry_run:
        if cfg.anki.collection_path is None:
            cfg.anki.collection_path = _run_profile_setup(cfg)

        collection_path = cfg.anki.collection_path
        assert collection_path is not None

        if not collection_path.exists():
            rprint(f"[yellow]Note:[/yellow] {collection_path} does not exist — a new collection will be created.")

        if check_collection_locked(collection_path):
            rprint("[red]Error:[/red] Anki appears to be open (collection is locked).")
            rprint("Close Anki before inserting cards.")
            raise typer.Exit(1)

    # Interactive review loop
    staged: list[WordEntry] = []
    skipped = 0
    total = len(entries)

    for i, entry in enumerate(entries, 1):
        console.print(format_card_preview(entry, i, total))
        while True:
            rprint("[dim]  Press a/e/s/q: [/dim]", end="")
            ch = click.getchar()
            rprint()  # newline after keypress
            if ch in ("a", "A"):
                staged.append(entry)
                rprint(f"  [green]Accepted[/green] {entry.lemma}")
                break
            elif ch in ("e", "E"):
                # Edit flow — reuse editor module
                editor_cmd = os.environ.get("EDITOR") or os.environ.get("VISUAL")
                if not editor_cmd:
                    rprint("  [yellow]$EDITOR not set — skipping edit.[/yellow]")
                    continue
                original_text = definitions_to_text(entry.lemma, entry.pos, entry.definitions)
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", prefix=f"ankivibes_{entry.lemma}_", delete=False
                ) as f:
                    f.write(original_text)
                    tmp_path = f.name
                try:
                    result = subprocess.run([editor_cmd, tmp_path])
                    if result.returncode != 0:
                        rprint("  [red]Editor exited with an error.[/red]")
                        continue
                    edited_text = Path(tmp_path).read_text(encoding="utf-8")
                finally:
                    Path(tmp_path).unlink(missing_ok=True)
                if edited_text != original_text:
                    new_defs = text_to_definitions(edited_text)
                    entry.definitions = new_defs
                    if new_defs and new_defs[0].get("pos"):
                        entry.pos = new_defs[0]["pos"]
                    entry.edited = True
                    entry.updated_at = datetime.now(timezone.utc).isoformat()
                    store.save(entry)
                    rprint(f"  [green]Updated definitions for {entry.lemma}[/green]")
                # Re-display after edit
                console.print(format_card_preview(entry, i, total))
            elif ch in ("s", "S"):
                skipped += 1
                rprint(f"  [dim]Skipped[/dim] {entry.lemma}")
                break
            elif ch in ("q", "Q"):
                rprint("  Quitting review.")
                break
            else:
                rprint("  [dim]Invalid key. Press a/e/s/q.[/dim]")
                continue
        if ch in ("q", "Q"):
            break

    # Summary
    rprint()
    summary = Table(title="Review Summary")
    summary.add_column("Outcome", style="bold")
    summary.add_column("Count", justify="right")
    summary.add_row("staged", str(len(staged)), style="green")
    summary.add_row("skipped", str(skipped), style="dim")
    console.print(summary)

    if not staged:
        return

    if dry_run:
        rprint("[dim]Dry run — no changes written to Anki.[/dim]")
        return

    # Confirm insertion
    if not typer.confirm(f"Insert {len(staged)} cards into your Anki deck?", default=False):
        rprint("[dim]Cancelled.[/dim]")
        return

    # Insert
    results = insert_staged_notes(
        collection_path=collection_path,
        deck_name=cfg.anki.deck_name,
        entries=staged,
        backup_dir=cfg.anki.backup_dir,
    )

    now = datetime.now(timezone.utc).isoformat()
    for res in results:
        res.entry.anki_note_id = res.anki_note_id
        res.entry.last_synced_at = now
        res.entry.status = STATUS_INSERTED
        res.entry.updated_at = now
        store.save(res.entry)

    rprint(f"\n[green]Inserted {len(results)} card(s) into deck '{cfg.anki.deck_name}'.[/green]")
    for res in results:
        rprint(f"  {res.entry.lemma} → note {res.anki_note_id}")


@app.command(name="import-deck")
def import_deck(
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without modifying Anki.")] = False,
    skip_enrich: Annotated[bool, typer.Option("--skip-enrich", help="Skip Wiktionary enrichment.")] = False,
    collection: Annotated[Optional[Path], typer.Option(help="Path to source .anki2 file (skips profile selection).")] = None,
    deck: Annotated[Optional[str], typer.Option(help="Deck name to import (skips deck selection).")] = None,
    store_path: Annotated[Optional[Path], typer.Option(help="Override default store path.")] = None,
) -> None:
    """Import an existing Anki deck into ankivibes management."""
    import os
    import subprocess
    import tempfile
    from datetime import datetime, timezone

    import click

    from .anki_import import (
        AnkiNoteInfo,
        build_import_candidates,
        format_edit_with_reference,
        format_import_preview,
        list_decks,
        migrate_notes,
        read_deck_notes,
    )
    from .anki_profile import discover_profiles, find_anki_base_dir, format_profile_menu, resolve_profile
    from .anki_bridge import check_collection_locked
    from .corpus import CORPESCorpus
    from .editor import text_to_definitions
    from .enrich import enrich_one, select_entries_to_enrich
    from .lemmatizer import SpacyLemmatizer
    from .pipeline import ingest_words
    from .store.models import STATUS_INSERTED

    cfg = cfg_module.load()
    effective_store = store_path or cfg.store_path
    store = JsonlStore(effective_store)

    # -- Phase A: Source selection ------------------------------------------
    if collection is not None:
        source_collection = collection.expanduser()
    else:
        base_dir = find_anki_base_dir()
        if base_dir is None:
            rprint("[red]No Anki data directory found.[/red]")
            rprint("Use --collection to specify the path directly.")
            raise typer.Exit(1)

        profiles = discover_profiles(base_dir)
        if not profiles:
            rprint(f"[red]No Anki profiles found at {base_dir}.[/red]")
            raise typer.Exit(1)

        if len(profiles) == 1:
            p = profiles[0]
            rprint(f"Found Anki profile: {p.name}  ({p.collection_path})")
            if not typer.confirm("Import from this profile?", default=True):
                raise typer.Abort()
            source_collection = p.collection_path
        else:
            rprint("Found Anki profiles:")
            rprint(format_profile_menu(profiles))
            choice = typer.prompt("Select profile", type=int, default=1)
            try:
                source_collection = resolve_profile(profiles, choice).collection_path
            except ValueError as exc:
                rprint(f"[red]{exc}[/red]")
                raise typer.Exit(1)

    if not source_collection.exists():
        rprint(f"[red]Collection not found: {source_collection}[/red]")
        raise typer.Exit(1)

    if check_collection_locked(source_collection):
        rprint("[red]Error:[/red] Anki appears to be open (collection is locked).")
        rprint("Close Anki before importing.")
        raise typer.Exit(1)

    # -- Deck selection -------------------------------------------------------
    if deck is not None:
        source_deck = deck
    else:
        deck_list = list_decks(source_collection)
        # Filter out the default deck ("Default" with id 1)
        deck_list = [(did, name) for did, name in deck_list if name != "Default"]
        if not deck_list:
            rprint("[red]No decks found in collection.[/red]")
            raise typer.Exit(1)

        if len(deck_list) == 1:
            source_deck = deck_list[0][1]
            rprint(f"Found deck: {source_deck}")
            if not typer.confirm("Import from this deck?", default=True):
                raise typer.Abort()
        else:
            rprint("Found decks:")
            for i, (_, name) in enumerate(deck_list, 1):
                rprint(f"  {i}. {name}")
            choice = typer.prompt("Select deck", type=int, default=1)
            if choice < 1 or choice > len(deck_list):
                rprint("[red]Invalid selection.[/red]")
                raise typer.Exit(1)
            source_deck = deck_list[choice - 1][1]

    rprint(f"\nImporting from: [bold]{source_collection}[/bold]  deck: [bold]{source_deck}[/bold]")

    # -- Phase B: Read & ingest -----------------------------------------------
    rprint("\n[bold]Reading notes...[/bold]")
    notes = read_deck_notes(source_collection, source_deck)
    if not notes:
        rprint("[dim]No Basic notes to import (all may already be AnkiVibes type).[/dim]")
        return

    rprint(f"Found {len(notes)} note(s) to import.")

    corpus = CORPESCorpus(cfg.corpus_path)
    lemmatizer = SpacyLemmatizer()
    fronts = [n.front for n in notes]
    entries = ingest_words(fronts, source=f"anki_import:{source_deck}", lemmatizer=lemmatizer, corpus=corpus)

    ready = sum(1 for e in entries if e.status == "ready")
    needs_review = sum(1 for e in entries if e.status == "needs_review")
    rprint(f"Pipeline: {ready} ready, {needs_review} needs_review")

    for entry in entries:
        store.merge(entry)

    # Build candidates linking entries to source notes
    candidates = build_import_candidates(notes, entries)
    rprint(f"Matched {len(candidates)} unique word(s) to source notes.")

    if dry_run:
        rprint("\n[dim]Dry run — no changes written.[/dim]")
        return

    # -- Phase C: Enrich -------------------------------------------------------
    if not skip_enrich:
        to_enrich = select_entries_to_enrich(store)
        if to_enrich:
            contact_email = cfg.contact_email
            if contact_email is None:
                rprint("\nWiktionary requests require a contact email for the User-Agent header.")
                contact_email = typer.prompt("Contact email")
                cfg.contact_email = contact_email
                cfg_module.save(cfg)

            from pytionary import WiktionaryClient

            client = WiktionaryClient(contact_email=contact_email)
            rprint(f"\n[bold]Enriching {len(to_enrich)} word(s)...[/bold]")
            enriched_count = 0
            skipped_count = 0
            for entry in to_enrich:
                outcome, err = enrich_one(entry, client, store)
                if outcome == "enriched":
                    enriched_count += 1
                else:
                    skipped_count += 1
                    if err:
                        rprint(f"  [dim]Skipped {entry.lemma}: {err}[/dim]")
            rprint(f"Enriched: {enriched_count}, skipped: {skipped_count}")

        # Reload entries from store to pick up enrichment
        refreshed: dict[str, object] = {}
        new_candidates = []
        for c in candidates:
            refreshed_entry = store.get(c.entry.id)
            if refreshed_entry is not None:
                from ankivibes.anki_import import ImportCandidate
                new_candidates.append(ImportCandidate(entry=refreshed_entry, notes=c.notes))
            else:
                new_candidates.append(c)
        candidates = new_candidates

    # -- Phase D: Interactive review ------------------------------------------
    rprint("\n[bold]Review each card:[/bold]")
    total = len(candidates)
    skipped_count = 0

    for i, candidate in enumerate(candidates, 1):
        console.print(format_import_preview(candidate, i, total))

        entry = candidate.entry
        has_enrichment = entry.status == "enriched" and bool(entry.definitions)
        valid_keys = {"n", "o", "e", "s", "q"} if has_enrichment else {"o", "s", "q"}

        while True:
            rprint("[dim]  Press key: [/dim]", end="")
            ch = click.getchar().lower()
            rprint()

            if ch not in valid_keys:
                rprint(f"  [dim]Invalid key. Press {'n/o/e/s/q' if has_enrichment else 'o/s/q'}.[/dim]")
                continue

            if ch == "n":
                candidate.decision = "new"
                rprint(f"  [green]Using new enrichment[/green] for {entry.lemma}")
                break
            elif ch == "o":
                candidate.decision = "old"
                rprint(f"  [green]Keeping old back[/green] for {entry.lemma}")
                break
            elif ch == "e":
                editor_cmd = os.environ.get("EDITOR") or os.environ.get("VISUAL")
                if not editor_cmd:
                    rprint("  [yellow]$EDITOR not set — skipping edit.[/yellow]")
                    continue
                edit_text = format_edit_with_reference(entry, candidate.notes[0].back_html)
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".txt", prefix=f"ankivibes_import_{entry.lemma}_", delete=False
                ) as f:
                    f.write(edit_text)
                    tmp_path_str = f.name
                try:
                    result = subprocess.run([editor_cmd, tmp_path_str])
                    if result.returncode != 0:
                        rprint("  [red]Editor exited with an error.[/red]")
                        continue
                    edited_text = Path(tmp_path_str).read_text(encoding="utf-8")
                finally:
                    Path(tmp_path_str).unlink(missing_ok=True)
                new_defs = text_to_definitions(edited_text)
                entry.definitions = new_defs
                if new_defs and new_defs[0].get("pos"):
                    entry.pos = new_defs[0]["pos"]
                entry.edited = True
                entry.updated_at = datetime.now(timezone.utc).isoformat()
                store.save(entry)
                from ankivibes.anki_bridge import format_card_back
                candidate.new_back_html = format_card_back(new_defs, entry.pos)
                candidate.decision = "edit"
                rprint(f"  [green]Edited[/green] {entry.lemma}")
                break
            elif ch == "s":
                candidate.decision = "skip"
                skipped_count += 1
                rprint(f"  [dim]Skipped[/dim] {entry.lemma}")
                break
            elif ch == "q":
                rprint("  Quitting review.")
                break

        if ch == "q":
            break

    # Summary
    rprint()
    decided = [c for c in candidates if c.decision in ("new", "old", "edit")]
    summary = Table(title="Import Review Summary")
    summary.add_column("Outcome", style="bold")
    summary.add_column("Count", justify="right")
    summary.add_row("to migrate", str(len(decided)), style="green")
    summary.add_row("skipped", str(skipped_count), style="dim")
    console.print(summary)

    if not decided:
        rprint("[dim]Nothing to migrate.[/dim]")
        return

    if not typer.confirm(f"Migrate {len(decided)} card(s) to AnkiVibes note type?", default=False):
        rprint("[dim]Cancelled.[/dim]")
        return

    # -- Phase E: Migrate ------------------------------------------------------
    results = migrate_notes(source_collection, cfg.anki.backup_dir, candidates)

    now = datetime.now(timezone.utc).isoformat()
    for res in results:
        res.entry.anki_note_id = res.anki_note_id
        res.entry.last_synced_at = now
        res.entry.status = STATUS_INSERTED
        res.entry.updated_at = now
        store.save(res.entry)

    rprint(f"\n[green]Migrated {len(results)} card(s) to AnkiVibes note type.[/green]")

    # -- Phase F: Update config ------------------------------------------------
    cfg.anki.collection_path = source_collection
    cfg.anki.deck_name = source_deck
    cfg_module.save(cfg)
    rprint(f"Config updated: collection_path → {source_collection}")
