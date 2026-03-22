"""Tests for the enrichment service."""
from __future__ import annotations

from pathlib import Path

import pytest

from pytionary import ClientError

from ankivibes.enrich import enrich_one, select_entries_to_enrich
from ankivibes.store.jsonl import JsonlStore
from ankivibes.store.models import (
    STATUS_ENRICHED,
    STATUS_NEEDS_REVIEW,
    STATUS_READY,
    WordEntry,
)

# -- Fake client -----------------------------------------------------------

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

NO_SPANISH_PAYLOAD = {
    "en": [
        {
            "partOfSpeech": "Noun",
            "definitions": [{"definition": "something in English"}],
        }
    ]
}


class FakeWiktionaryClient:
    """Test double for WiktionaryClient."""

    def __init__(
        self,
        responses: dict[str, dict] | None = None,
        errors: dict[str, ClientError] | None = None,
    ) -> None:
        self._responses = responses or {}
        self._errors = errors or {}

    def fetch_definitions(self, lemma: str) -> dict:
        if lemma in self._errors:
            raise self._errors[lemma]
        if lemma in self._responses:
            return self._responses[lemma]
        raise ClientError(message=f"HTTP 404 for '{lemma}'", status_code=404)


# -- Helpers ----------------------------------------------------------------

def _ready_entry(lemma: str, frequency: str | None = "0.015") -> WordEntry:
    return WordEntry.create(
        raw=lemma, normalized=lemma, lemma=lemma,
        frequency=frequency, status=STATUS_READY, reason=None, source="test",
    )


def _enriched_entry(lemma: str, frequency: str | None = "0.020") -> WordEntry:
    entry = WordEntry.create(
        raw=lemma, normalized=lemma, lemma=lemma,
        frequency=frequency, status=STATUS_ENRICHED, reason=None, source="test",
    )
    entry.definitions = [{"text": "existing def", "pos": "Verb", "examples": []}]
    entry.pos = "Verb"
    return entry


# -- enrich_one tests -------------------------------------------------------

class TestEnrichOne:
    def test_success(self, tmp_store: JsonlStore) -> None:
        entry = _ready_entry("correr")
        tmp_store.save(entry)
        client = FakeWiktionaryClient(responses={"correr": CORRER_PAYLOAD})

        outcome, error = enrich_one(entry, client, tmp_store)

        assert outcome == "enriched"
        assert error is None
        saved = tmp_store.get(entry.id)
        assert saved is not None
        assert saved.status == STATUS_ENRICHED
        assert saved.pos == "Verb"
        assert len(saved.definitions) == 1
        assert saved.definitions[0]["text"] == "to run"

    def test_no_spanish_definitions(self, tmp_store: JsonlStore) -> None:
        entry = _ready_entry("blah")
        tmp_store.save(entry)
        client = FakeWiktionaryClient(responses={"blah": NO_SPANISH_PAYLOAD})

        outcome, error = enrich_one(entry, client, tmp_store)

        assert outcome == "skipped"
        assert error is not None
        assert "no Spanish definitions" in error
        # Entry should not be modified in store
        saved = tmp_store.get(entry.id)
        assert saved is not None
        assert saved.status == STATUS_READY

    def test_client_error(self, tmp_store: JsonlStore) -> None:
        entry = _ready_entry("unknown")
        tmp_store.save(entry)
        client = FakeWiktionaryClient(
            errors={"unknown": ClientError(message="HTTP 404", status_code=404)}
        )

        outcome, error = enrich_one(entry, client, tmp_store)

        assert outcome == "skipped"
        assert error is not None
        assert "404" in error
        saved = tmp_store.get(entry.id)
        assert saved is not None
        assert saved.status == STATUS_READY


# -- select_entries_to_enrich tests -----------------------------------------

class TestSelectEntries:
    def test_filters_ready_only(self, tmp_store: JsonlStore) -> None:
        tmp_store.save(_ready_entry("correr"))
        tmp_store.save(_enriched_entry("hablar"))
        tmp_store.save(WordEntry.create(
            raw="xyz", normalized="xyz", lemma="xyz",
            frequency=None, status=STATUS_NEEDS_REVIEW,
            reason="no_frequency", source="test",
        ))

        entries = select_entries_to_enrich(tmp_store)
        assert len(entries) == 1
        assert entries[0].lemma == "correr"

    def test_with_force(self, tmp_store: JsonlStore) -> None:
        tmp_store.save(_ready_entry("correr"))
        tmp_store.save(_enriched_entry("hablar"))

        entries = select_entries_to_enrich(tmp_store, force=True)
        assert len(entries) == 2

    def test_top_n(self, tmp_store: JsonlStore) -> None:
        tmp_store.save(_ready_entry("a", "0.010"))
        tmp_store.save(_ready_entry("b", "0.020"))
        tmp_store.save(_ready_entry("c", "0.030"))

        entries = select_entries_to_enrich(tmp_store, top_n=2)
        assert len(entries) == 2
        assert entries[0].lemma == "a"
        assert entries[1].lemma == "b"

    def test_sorts_by_frequency_ascending(self, tmp_store: JsonlStore) -> None:
        tmp_store.save(_ready_entry("high", "0.090"))
        tmp_store.save(_ready_entry("low", "0.010"))
        tmp_store.save(_ready_entry("none", None))

        entries = select_entries_to_enrich(tmp_store)
        assert [e.lemma for e in entries] == ["low", "high", "none"]
