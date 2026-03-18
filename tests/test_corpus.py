"""Tests for the frequency corpus."""
from __future__ import annotations

import pytest

from ankivibes.corpus import CORPESCorpus
from tests.conftest import CORPUS_SAMPLE


def test_lookup_known_single_word(sample_corpus):
    result = sample_corpus.lookup("correr")
    assert result is not None
    assert float(result) == pytest.approx(0.015, rel=1e-3)


def test_lookup_known_multiword(sample_corpus):
    result = sample_corpus.lookup("por favor")
    assert result is not None
    assert float(result) == pytest.approx(0.08887786, rel=1e-3)


def test_lookup_unknown_returns_none(sample_corpus):
    assert sample_corpus.lookup("xkyzqwerty") is None


def test_lookup_all_sample_words(sample_corpus):
    for lemma in ("hablar", "comer", "vivir", "libro", "ciudad", "trabajo"):
        assert sample_corpus.lookup(lemma) is not None


def test_duplicate_lemma_keeps_highest_frequency():
    """When a lemma appears with multiple POS, keep the entry with highest freq."""
    # Both rows have lemma "test"; second has higher Frec. norm. (999 vs 1)
    import tempfile
    from pathlib import Path

    tsv_content = (
        "\n"
        "Orden\tRango frec.\tLema\tForma\tEtiqueta\tFrec.\tFrec. norm.\tDP\tNúm. países\n"
        "         1. \t      100\ttest\t\tN\t       1\t         1.000000\t 0.50000000\t10\n"
        "\n"
        "         2. \t       10\ttest\t\tV\t    1000\t       999.000000\t 0.01000000\t21\n"
        "\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".tsv", encoding="utf-8", delete=False) as f:
        f.write(tsv_content)
        tmp = Path(f.name)

    corpus = CORPESCorpus(tmp)
    tmp.unlink()
    # Should keep the V entry (higher freq_norm=999) with DP=0.01
    assert float(corpus.lookup("test")) == pytest.approx(0.01, rel=1e-3)
