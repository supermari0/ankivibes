"""Lemmatizer protocol and SpacyLemmatizer implementation."""
from __future__ import annotations

from typing import Protocol


class Lemmatizer(Protocol):
    def lemmatize(self, word: str) -> str:
        """Return the base lemma for a single word."""
        ...


class SpacyLemmatizer:
    """spaCy-based lemmatizer using es_core_news_sm."""

    def __init__(self) -> None:
        self._nlp = None

    def _get_nlp(self):
        if self._nlp is None:
            import spacy
            self._nlp = spacy.load("es_core_news_sm")
        return self._nlp

    def lemmatize(self, word: str) -> str:
        nlp = self._get_nlp()
        doc = nlp(word)
        if not doc:
            return word
        return doc[0].lemma_
