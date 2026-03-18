"""FrequencyCorpus protocol and CORPESCorpus implementation."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Protocol


class FrequencyCorpus(Protocol):
    def lookup(self, lemma: str) -> str | None:
        """Return the DP frequency score for a lemma, or None if not found."""
        ...


class CORPESCorpus:
    """RAE CORPES frequency corpus loaded from the ALFA TSV file.

    Uses the DP (dispersion) score as the frequency metric. When a lemma
    appears with multiple POS entries, keeps the one with the highest
    normalized frequency.
    """

    def __init__(self, tsv_path: Path) -> None:
        self._data: dict[str, str] = {}
        self._load(tsv_path)

    def _load(self, tsv_path: Path) -> None:
        best_freq: dict[str, float] = {}
        with tsv_path.open(encoding="utf-8", newline="") as fh:
            reader = csv.reader(fh, delimiter="\t")
            for row in reader:
                if len(row) < 8:
                    continue
                orden = row[0].strip()
                # Skip header row and sub-entries (sub-entries have empty col 0)
                if not orden or orden == "Orden":
                    continue
                lemma = row[2].strip()
                if not lemma:
                    continue
                try:
                    freq_norm = float(row[6].strip())
                    dp = row[7].strip()
                    float(dp)  # validate it's a number
                except ValueError:
                    continue
                if lemma not in best_freq or freq_norm > best_freq[lemma]:
                    best_freq[lemma] = freq_norm
                    self._data[lemma] = dp

    def lookup(self, lemma: str) -> str | None:
        return self._data.get(lemma)
