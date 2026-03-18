"""Tests for the ingest pipeline."""
from __future__ import annotations

import pytest

from ankivibes.pipeline import ingest_words, normalize
from ankivibes.store.models import (
    REASON_NO_FREQUENCY,
    REASON_NO_FREQUENCY_MULTIWORD,
    STATUS_NEEDS_REVIEW,
    STATUS_READY,
)
from tests.conftest import DictLemmatizer, FakeLemmatizer


def test_normalize_strips_and_lowercases():
    assert normalize("  Hola  ") == "hola"
    assert normalize("CORRER") == "correr"
    assert normalize("  ") == ""


def test_ready_single_word(sample_corpus, fake_lemmatizer):
    entries = ingest_words(["correr"], source="test", lemmatizer=fake_lemmatizer, corpus=sample_corpus)
    assert len(entries) == 1
    assert entries[0].status == STATUS_READY
    assert entries[0].lemma == "correr"
    assert entries[0].frequency is not None


def test_needs_review_unknown_word(sample_corpus, fake_lemmatizer):
    entries = ingest_words(["xkyzqwerty"], source="test", lemmatizer=fake_lemmatizer, corpus=sample_corpus)
    assert len(entries) == 1
    assert entries[0].status == STATUS_NEEDS_REVIEW
    assert entries[0].reason == REASON_NO_FREQUENCY


def test_multiword_in_corpus(sample_corpus, fake_lemmatizer):
    entries = ingest_words(["por favor"], source="test", lemmatizer=fake_lemmatizer, corpus=sample_corpus)
    assert len(entries) == 1
    assert entries[0].status == STATUS_READY
    assert entries[0].lemma == "por favor"


def test_multiword_not_in_corpus(sample_corpus, fake_lemmatizer):
    entries = ingest_words(["buenas noches"], source="test", lemmatizer=fake_lemmatizer, corpus=sample_corpus)
    assert len(entries) == 1
    assert entries[0].status == STATUS_NEEDS_REVIEW
    assert entries[0].reason == REASON_NO_FREQUENCY_MULTIWORD


def test_deduplication(sample_corpus, fake_lemmatizer):
    raw = ["correr", "CORRER", "correr", "  correr  "]
    entries = ingest_words(raw, source="test", lemmatizer=fake_lemmatizer, corpus=sample_corpus)
    assert len(entries) == 1


def test_lemmatizer_used_for_inflected_forms(sample_corpus):
    lem = DictLemmatizer({"corriendo": "correr"})
    entries = ingest_words(["corriendo"], source="test", lemmatizer=lem, corpus=sample_corpus)
    assert len(entries) == 1
    assert entries[0].status == STATUS_READY
    assert entries[0].lemma == "correr"
    assert entries[0].normalized == "corriendo"


def test_empty_lines_skipped(sample_corpus, fake_lemmatizer):
    entries = ingest_words(["", "  ", "correr"], source="test", lemmatizer=fake_lemmatizer, corpus=sample_corpus)
    assert len(entries) == 1


def test_mixed_ready_and_needs_review(sample_corpus, fake_lemmatizer):
    raw = ["correr", "hablar", "xkyzqwerty", "buenas noches", "por favor"]
    entries = ingest_words(raw, source="test", lemmatizer=fake_lemmatizer, corpus=sample_corpus)
    ready = [e for e in entries if e.status == STATUS_READY]
    review = [e for e in entries if e.status == STATUS_NEEDS_REVIEW]
    assert len(ready) == 3   # correr, hablar, por favor
    assert len(review) == 2  # xkyzqwerty, buenas noches


def test_source_is_set(sample_corpus, fake_lemmatizer):
    entries = ingest_words(["correr"], source="myfile.txt", lemmatizer=fake_lemmatizer, corpus=sample_corpus)
    assert entries[0].source == "myfile.txt"
