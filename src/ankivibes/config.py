"""Config loading (~/.config/ankivibes/config.toml)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_CONFIG_PATH = Path.home() / ".config" / "ankivibes" / "config.toml"
DEFAULT_STORE_PATH = Path.home() / ".local" / "share" / "ankivibes" / "words.jsonl"


def _default_corpus_path() -> Path:
    """Resolve the CORPES TSV path. Works in dev (project root) and when configured."""
    # In development: src/ankivibes/ -> src/ -> project root -> data/
    pkg_dir = Path(__file__).parent
    project_data = pkg_dir.parent.parent / "data" / "diccionario_frecuencias_corpes_alfa.tsv"
    if project_data.exists():
        return project_data
    # TODO: The data is in the repository, I'm not sure this is necessary unless we're looking at an ankivibes
    # web application.
    return Path.home() / ".local" / "share" / "ankivibes" / "diccionario_frecuencias_corpes_alfa.tsv"


@dataclass
class AnkiConfig:
    collection_path: Path | None = None
    deck_name: str = "Spanish"
    backup_dir: Path = field(
        default_factory=lambda: Path.home() / ".local" / "share" / "ankivibes" / "backups"
    )
    auto_sync: bool = True


@dataclass
class Config:
    store_path: Path = field(default_factory=lambda: DEFAULT_STORE_PATH)
    corpus_path: Path = field(default_factory=_default_corpus_path)
    contact_email: str | None = None
    anki: AnkiConfig = field(default_factory=AnkiConfig)


def load() -> Config:
    if not _CONFIG_PATH.exists():
        return Config()
    with _CONFIG_PATH.open("rb") as fh:
        data = tomllib.load(fh)
    cfg = Config()
    if "store_path" in data:
        cfg.store_path = Path(data["store_path"])
    if "corpus_path" in data:
        cfg.corpus_path = Path(data["corpus_path"])
    if "contact_email" in data:
        cfg.contact_email = data["contact_email"]
    if "anki" in data:
        anki_data = data["anki"]
        if "collection_path" in anki_data:
            cfg.anki.collection_path = Path(anki_data["collection_path"])
        if "deck_name" in anki_data:
            cfg.anki.deck_name = anki_data["deck_name"]
        if "backup_dir" in anki_data:
            cfg.anki.backup_dir = Path(anki_data["backup_dir"])
        if "auto_sync" in anki_data:
            cfg.anki.auto_sync = anki_data["auto_sync"]
    return cfg


def save(cfg: Config) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append(f'store_path = "{cfg.store_path}"')
    lines.append(f'corpus_path = "{cfg.corpus_path}"')
    if cfg.contact_email is not None:
        lines.append(f'contact_email = "{cfg.contact_email}"')
    lines.append("")
    lines.append("[anki]")
    if cfg.anki.collection_path is not None:
        lines.append(f'collection_path = "{cfg.anki.collection_path}"')
    lines.append(f'deck_name = "{cfg.anki.deck_name}"')
    lines.append(f'backup_dir = "{cfg.anki.backup_dir}"')
    lines.append(f"auto_sync = {str(cfg.anki.auto_sync).lower()}")
    _CONFIG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
