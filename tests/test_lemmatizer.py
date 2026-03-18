"""Tests for the lemmatizer."""
from __future__ import annotations

import pytest

from ankivibes.lemmatizer import SpacyLemmatizer


def _spacy_model_available() -> bool:
    try:
        import spacy
        spacy.load("es_core_news_sm")
        return True
    except Exception:
        return False


skip_if_no_model = pytest.mark.skipif(
    not _spacy_model_available(), reason="es_core_news_sm not installed"
)


@skip_if_no_model
def test_lemmatizes_verb_form():
    lem = SpacyLemmatizer()
    assert lem.lemmatize("corriendo") == "correr"


@skip_if_no_model
def test_lemmatizes_base_form_unchanged():
    lem = SpacyLemmatizer()
    assert lem.lemmatize("hablar") == "hablar"


@skip_if_no_model
def test_multiword_input_does_not_crash():
    lem = SpacyLemmatizer()
    result = lem.lemmatize("por favor")
    assert isinstance(result, str)
    assert len(result) > 0


@skip_if_no_model
def test_empty_string_returns_empty():
    lem = SpacyLemmatizer()
    assert lem.lemmatize("") == ""
