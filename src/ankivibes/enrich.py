"""Enrichment service — fetch Wiktionary definitions for ready words."""
from __future__ import annotations

from datetime import datetime, timezone

from pytionary import ClientError, WiktionaryClient, parse_spanish_definitions

from .store.models import STATUS_ENRICHED, STATUS_READY, WordEntry
from .store.protocol import WordStore


def select_entries_to_enrich(
    store: WordStore,
    *,
    force: bool = False,
    top_n: int | None = None,
) -> list[WordEntry]:
    """Return entries eligible for enrichment, sorted by frequency ascending."""
    allowed = {STATUS_READY}
    if force:
        allowed.add(STATUS_ENRICHED)

    entries = [e for e in store.all() if e.status in allowed]

    def sort_key(e: WordEntry) -> float:
        try:
            return float(e.frequency) if e.frequency else float("inf")
        except ValueError:
            return float("inf")

    entries.sort(key=sort_key)

    if top_n is not None:
        entries = entries[:top_n]

    return entries


def enrich_one(
    entry: WordEntry,
    client: WiktionaryClient,
    store: WordStore,
) -> tuple[str, str | None]:
    """Enrich a single entry. Returns (outcome, error_message | None)."""
    try:
        payload = client.fetch_definitions(entry.lemma)
    except ClientError as exc:
        return ("skipped", str(exc))

    definitions = parse_spanish_definitions(payload)
    if not definitions:
        return ("skipped", f"no Spanish definitions found for '{entry.lemma}'")

    entry.definitions = [d.to_dict() for d in definitions]
    entry.pos = definitions[0].pos
    entry.status = STATUS_ENRICHED
    entry.updated_at = datetime.now(timezone.utc).isoformat()
    store.save(entry)
    return ("enriched", None)
