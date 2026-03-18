"""Tests for the CLI subcommands."""

from typer.testing import CliRunner

from ankivibes.cli import app

runner = CliRunner()


def test_help_shows_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("ingest", "list", "enrich", "anki"):
        assert cmd in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "ankivibes" in result.output


def test_ingest_stub():
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output


def test_list_stub():
    result = runner.invoke(app, ["list"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output


def test_enrich_stub():
    result = runner.invoke(app, ["enrich"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output


def test_anki_stub():
    result = runner.invoke(app, ["anki"])
    assert result.exit_code == 0
    assert "not yet implemented" in result.output
