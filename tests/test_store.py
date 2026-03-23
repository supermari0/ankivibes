"""Tests for the JSONL word store."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ankivibes.store.jsonl import JsonlStore
from ankivibes.store.models import (
    SCHEMA_VERSION,
    STATUS_INSERTED,
    STATUS_READY,
    WordEntry,
)
from tests.conftest import CORPUS_SAMPLE, FakeLemmatizer
from ankivibes.corpus import CORPESCorpus
from ankivibes.pipeline import ingest_words


def _make_entry(normalized: str = "correr", lemma: str = "correr") -> WordEntry:
    return WordEntry.create(
        raw=normalized,
        normalized=normalized,
        lemma=lemma,
        frequency="0.015",
        status=STATUS_READY,
        reason=None,
        source="test",
    )


def test_round_trip(tmp_store):
    entry = _make_entry()
    tmp_store.save(entry)
    result = tmp_store.get(entry.id)
    assert result is not None
    assert result.id == entry.id
    assert result.lemma == entry.lemma
    assert result.frequency == entry.frequency


def test_all_returns_saved_entries(tmp_store):
    e1 = _make_entry("correr", "correr")
    e2 = _make_entry("hablar", "hablar")
    tmp_store.save(e1)
    tmp_store.save(e2)
    all_entries = tmp_store.all()
    assert len(all_entries) == 2
    ids = {e.id for e in all_entries}
    assert e1.id in ids
    assert e2.id in ids


def test_save_updates_existing(tmp_store):
    entry = _make_entry()
    tmp_store.save(entry)
    updated = WordEntry(
        **{**entry.__dict__, "frequency": "0.099", "status": STATUS_READY}
    )
    tmp_store.save(updated)
    assert len(tmp_store.all()) == 1
    assert tmp_store.get(entry.id).frequency == "0.099"


def test_get_missing_returns_none(tmp_store):
    assert tmp_store.get("nonexistent") is None


def test_schema_version_in_metadata(tmp_store):
    tmp_store.save(_make_entry())
    raw = tmp_store._path.read_text(encoding="utf-8")
    first_line = json.loads(raw.splitlines()[0])
    assert first_line.get("__meta__") is True
    assert first_line["schema_version"] == SCHEMA_VERSION


def test_merge_new_entry(tmp_store):
    entry = _make_entry()
    result = tmp_store.merge(entry)
    assert result.id == entry.id
    assert len(tmp_store.all()) == 1


def test_merge_preserves_inserted_status(tmp_store):
    entry = _make_entry()
    inserted = WordEntry(**{**entry.__dict__, "status": STATUS_INSERTED})
    tmp_store.save(inserted)

    re_ingested = _make_entry()
    merged = tmp_store.merge(re_ingested)
    assert merged.status == STATUS_INSERTED


def test_merge_updates_frequency_for_non_inserted(tmp_store):
    entry = _make_entry()
    tmp_store.save(entry)

    updated = WordEntry(**{**entry.__dict__, "frequency": "0.099"})
    merged = tmp_store.merge(updated)
    assert merged.frequency == "0.099"


def test_merge_preserves_created_at(tmp_store):
    entry = _make_entry()
    tmp_store.save(entry)
    original_created = tmp_store.get(entry.id).created_at

    updated = WordEntry(**{**entry.__dict__, "frequency": "0.099"})
    merged = tmp_store.merge(updated)
    assert merged.created_at == original_created


def test_edited_field_defaults_false(tmp_store):
    """Entries without an 'edited' field in JSONL deserialize with edited=False."""
    entry = _make_entry()
    tmp_store.save(entry)
    loaded = tmp_store.get(entry.id)
    assert loaded.edited is False


def test_integration_ingest_fixture_file(tmp_store, tmp_path):
    """Integration test: ingest sample fixture, check store has expected entries."""
    corpus = CORPESCorpus(CORPUS_SAMPLE)
    lemmatizer = FakeLemmatizer()
    sample = Path(__file__).parent / "fixtures" / "sample_words.txt"
    raw_words = sample.read_text(encoding="utf-8").splitlines()

    entries = ingest_words(raw_words, source="sample_words.txt", lemmatizer=lemmatizer, corpus=corpus)
    for e in entries:
        tmp_store.merge(e)

    all_entries = tmp_store.all()
    # Deduplication: "correr" appears 3 times (correr, CORRER, correr) → 1 entry
    normalized = {e.normalized for e in all_entries}
    assert "correr" in normalized
    assert "por favor" in normalized
    # por favor should be ready (it's in the corpus)
    pf = next(e for e in all_entries if e.normalized == "por favor")
    assert pf.status == STATUS_READY
    # buenas noches should be needs_review
    bn = next(e for e in all_entries if e.normalized == "buenas noches")
    assert bn.status != STATUS_READY
