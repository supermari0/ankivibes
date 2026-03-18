"""WordStore protocol definition."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import WordEntry


@runtime_checkable
class WordStore(Protocol):
    def save(self, entry: WordEntry) -> None: ...
    def get(self, entry_id: str) -> WordEntry | None: ...
    def all(self) -> list[WordEntry]: ...
    def merge(self, entry: WordEntry) -> WordEntry: ...
