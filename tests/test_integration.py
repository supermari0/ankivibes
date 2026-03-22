"""Integration tests that hit real external services.

Run with: ANKIVIBES_INTEGRATION=1 uv run pytest tests/test_integration.py -v
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

import pytest

from ankivibes.enrich import enrich_one
from ankivibes.store.jsonl import JsonlStore
from ankivibes.store.models import STATUS_ENRICHED, STATUS_READY, WordEntry

_SKIP_REASON = "Integration test — set ANKIVIBES_INTEGRATION=1 to run"
_INTEGRATION = os.environ.get("ANKIVIBES_INTEGRATION") == "1"


@pytest.mark.skipif(not _INTEGRATION, reason=_SKIP_REASON)
def test_enrich_real_wiktionary(tmp_path: Path) -> None:
    """Fetch definitions for 'caminar' from real Wiktionary API and enrich."""
    from pytionary import WiktionaryClient

    store = JsonlStore(tmp_path / "words.jsonl")
    entry = WordEntry.create(
        raw="caminar",
        normalized="caminar",
        lemma="caminar",
        frequency="0.025",
        status=STATUS_READY,
        reason=None,
        source="integration_test",
    )
    store.save(entry)

    client = WiktionaryClient("ankivibes-test@example.com")
    outcome, error = enrich_one(entry, client, store)

    assert outcome == "enriched", f"Expected enriched but got skipped: {error}"
    assert error is None

    saved = store.get(entry.id)
    assert saved is not None

    print("\n" + json.dumps(asdict(saved), indent=2, ensure_ascii=False))

    assert saved.status == STATUS_ENRICHED
    assert len(saved.definitions) > 0
    assert saved.pos is not None
