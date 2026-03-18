"""Shared test fixtures."""
from __future__ import annotations

from pathlib import Path

import pytest

from ankivibes.corpus import CORPESCorpus
from ankivibes.store.jsonl import JsonlStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
CORPUS_SAMPLE = FIXTURES_DIR / "corpus_sample.tsv"
SAMPLE_WORDS = FIXTURES_DIR / "sample_words.txt"


class FakeLemmatizer:
    """Identity lemmatizer for tests — returns the word unchanged."""

    def lemmatize(self, word: str) -> str:
        return word


class DictLemmatizer:
    """Lookup-table lemmatizer for tests."""

    def __init__(self, table: dict[str, str]) -> None:
        self._table = table

    def lemmatize(self, word: str) -> str:
        return self._table.get(word, word)


@pytest.fixture
def fake_lemmatizer() -> FakeLemmatizer:
    return FakeLemmatizer()


@pytest.fixture
def sample_corpus() -> CORPESCorpus:
    return CORPESCorpus(CORPUS_SAMPLE)


@pytest.fixture
def tmp_store(tmp_path: Path) -> JsonlStore:
    return JsonlStore(tmp_path / "words.jsonl")
