"""Typer app and subcommand registration."""

from importlib.metadata import version
from typing import Annotated, Optional

import typer
from rich import print as rprint

app = typer.Typer(help="Spanish vocabulary study tool with Anki integration.")


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
def ingest() -> None:
    """Ingest a word list, lemmatize, and score by frequency."""
    rprint("not yet implemented")


@app.command()
def list() -> None:
    """List stored words sorted by frequency."""
    rprint("not yet implemented")


@app.command()
def enrich() -> None:
    """Enrich words with Wiktionary definitions."""
    rprint("not yet implemented")


@app.command()
def anki() -> None:
    """Review and insert cards into Anki."""
    rprint("not yet implemented")
