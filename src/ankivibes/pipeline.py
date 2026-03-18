"""Ingest pipeline: normalize → lemmatize → score."""
from __future__ import annotations

from .corpus import FrequencyCorpus
from .lemmatizer import Lemmatizer
from .store.models import (
    REASON_NO_FREQUENCY,
    REASON_NO_FREQUENCY_MULTIWORD,
    STATUS_NEEDS_REVIEW,
    STATUS_READY,
    WordEntry,
)


def normalize(raw: str) -> str:
    return raw.strip().lower()


def ingest_words(
    raw_words: list[str],
    source: str,
    lemmatizer: Lemmatizer,
    corpus: FrequencyCorpus,
) -> list[WordEntry]:
    """Process raw words into WordEntry objects.

    Deduplicates, lemmatizes single tokens, checks corpus for frequency.
    Multi-word inputs are checked against the corpus directly before
    attempting lemmatization.
    """
    seen: set[str] = set()
    entries: list[WordEntry] = []

    for raw in raw_words:
        # normalize raw input (strip whitespace, lowercase)
        normalized = normalize(raw)
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)

        # multiword input case - check the corpus for frequency data (something like "por favor" may be in the corpus)
        if " " in normalized:
            freq = corpus.lookup(normalized)
            if freq is not None:
                entries.append(WordEntry.create(
                    raw=raw,
                    normalized=normalized,
                    lemma=normalized,
                    frequency=freq,
                    status=STATUS_READY,
                    reason=None,
                    source=source,
                ))
            # if not found in corpus, schedule for manual review
            else:
                entries.append(WordEntry.create(
                    raw=raw,
                    normalized=normalized,
                    lemma=normalized,
                    frequency=None,
                    status=STATUS_NEEDS_REVIEW,
                    reason=REASON_NO_FREQUENCY_MULTIWORD,
                    source=source,
                ))
        # single word input case - check the corpus for frequency data
        else:
            lemma = lemmatizer.lemmatize(normalized)
            freq = corpus.lookup(lemma)
            if freq is not None:
                entries.append(WordEntry.create(
                    raw=raw,
                    normalized=normalized,
                    lemma=lemma,
                    frequency=freq,
                    status=STATUS_READY,
                    reason=None,
                    source=source,
                ))
            # if not found in corpus, schedule for manual review
            else:
                entries.append(WordEntry.create(
                    raw=raw,
                    normalized=normalized,
                    lemma=lemma,
                    frequency=None,
                    status=STATUS_NEEDS_REVIEW,
                    reason=REASON_NO_FREQUENCY,
                    source=source,
                ))

    return entries
