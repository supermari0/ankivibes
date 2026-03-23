"""WordEntry dataclass and status constants."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SCHEMA_VERSION = 1

STATUS_READY = "ready"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_ENRICHED = "enriched"
STATUS_INSERTED = "inserted"
STATUS_SKIPPED = "skipped"

REASON_NO_FREQUENCY = "no_frequency"
REASON_NO_FREQUENCY_MULTIWORD = "no_frequency_multiword"


def _entry_id(normalized: str, lemma: str) -> str:
    key = f"{normalized}\x00{lemma}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WordEntry:
    id: str
    raw: str
    normalized: str
    lemma: str
    frequency: str | None
    status: str
    reason: str | None
    source: str
    pos: str | None
    definitions: list[dict[str, Any]]
    created_at: str
    updated_at: str
    schema_version: int = field(default=SCHEMA_VERSION)
    edited: bool = False

    @classmethod
    def create(
        cls,
        *,
        raw: str,
        normalized: str,
        lemma: str,
        frequency: str | None,
        status: str,
        reason: str | None,
        source: str,
    ) -> "WordEntry":
        now = _utcnow()
        return cls(
            id=_entry_id(normalized, lemma),
            raw=raw,
            normalized=normalized,
            lemma=lemma,
            frequency=frequency,
            status=status,
            reason=reason,
            source=source,
            pos=None,
            definitions=[],
            created_at=now,
            updated_at=now,
        )
