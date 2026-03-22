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
from .store.models import STATUS_ENRICHED, STATUS_INSERTED, STATUS_NEEDS_REVIEW, STATUS_READY

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
def anki() -> None:
    """Review and insert cards into Anki."""
    rprint("not yet implemented")
