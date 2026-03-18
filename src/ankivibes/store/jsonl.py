"""JSONL storage implementation."""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .models import SCHEMA_VERSION, STATUS_INSERTED, WordEntry


class JsonlStore:
    def __init__(self, path: Path) -> None:
        self._path = path

    def _ensure_file(self) -> None:
        if not self._path.exists():
            self._path.parent.mkdir(parents=True, exist_ok=True)
            meta = {
                "__meta__": True,
                "schema_version": SCHEMA_VERSION,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self._path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

    def _read_raw(self) -> tuple[dict, list[dict]]:
        self._ensure_file()
        meta: dict = {}
        entries: list[dict] = []
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            if obj.get("__meta__"):
                meta = obj
            else:
                entries.append(obj)
        return meta, entries

    def _write_all(self, meta: dict, entries: list[dict]) -> None:
        lines = [json.dumps(meta)] + [json.dumps(e) for e in entries]
        self._path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _from_dict(self, d: dict) -> WordEntry:
        return WordEntry(
            id=d["id"],
            raw=d["raw"],
            normalized=d["normalized"],
            lemma=d["lemma"],
            frequency=d.get("frequency"),
            status=d["status"],
            reason=d.get("reason"),
            source=d["source"],
            pos=d.get("pos"),
            definitions=d.get("definitions", []),
            created_at=d["created_at"],
            updated_at=d["updated_at"],
            schema_version=d.get("schema_version", SCHEMA_VERSION),
        )

    def save(self, entry: WordEntry) -> None:
        meta, entries = self._read_raw()
        entry_dict = asdict(entry)
        for i, e in enumerate(entries):
            if e["id"] == entry.id:
                entries[i] = entry_dict
                self._write_all(meta, entries)
                return
        entries.append(entry_dict)
        self._write_all(meta, entries)

    def get(self, entry_id: str) -> WordEntry | None:
        _, entries = self._read_raw()
        for e in entries:
            if e["id"] == entry_id:
                return self._from_dict(e)
        return None

    def all(self) -> list[WordEntry]:
        _, entries = self._read_raw()
        return [self._from_dict(e) for e in entries]

    def merge(self, entry: WordEntry) -> WordEntry:
        """Merge entry into store. Preserves `inserted` status on re-ingest."""
        existing = self.get(entry.id)
        if existing is None:
            self.save(entry)
            return entry

        now = datetime.now(timezone.utc).isoformat()
        merged = asdict(entry)
        merged["created_at"] = existing.created_at
        merged["updated_at"] = now
        if existing.status == STATUS_INSERTED:
            merged["status"] = STATUS_INSERTED
            merged["reason"] = None

        result = self._from_dict(merged)
        self.save(result)
        return result
