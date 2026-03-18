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
class Config:
    store_path: Path = field(default_factory=lambda: DEFAULT_STORE_PATH)
    corpus_path: Path = field(default_factory=_default_corpus_path)
    contact_email: str | None = None


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
    return cfg


def save(cfg: Config) -> None:
    raise NotImplementedError("Config writing requires tomli-w; implement in Phase 3.")
