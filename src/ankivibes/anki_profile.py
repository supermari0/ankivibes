"""Anki profile discovery, creation, and selection."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

_NON_PROFILE_DIRS = {"addons21", "crash_reports", "logs"}


@dataclass
class AnkiProfile:
    """A discovered Anki profile on disk."""

    name: str
    path: Path
    collection_path: Path


def find_anki_base_dir() -> Path | None:
    """Return the platform-appropriate Anki data directory, or None if it doesn't exist."""
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support" / "Anki2"
    elif sys.platform == "win32":
        try:
            base = Path(os.environ["APPDATA"]) / "Anki2"
        except KeyError:
            return None
    else:
        # Linux and other Unix-likes
        base = Path.home() / ".local" / "share" / "Anki2"

    return base if base.is_dir() else None


def discover_profiles(base_dir: Path) -> list[AnkiProfile]:
    """Scan base_dir for Anki profiles containing a collection.anki2 file."""
    profiles: list[AnkiProfile] = []
    if not base_dir.is_dir():
        return profiles
    for child in sorted(base_dir.iterdir()):
        if not child.is_dir() or child.name in _NON_PROFILE_DIRS:
            continue
        col = child / "collection.anki2"
        if col.exists():
            profiles.append(AnkiProfile(name=child.name, path=child, collection_path=col))
    return profiles


def create_profile(base_dir: Path, profile_name: str) -> AnkiProfile:
    """Create a new Anki profile directory with an empty collection."""
    from anki.collection import Collection

    profile_dir = base_dir / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    col_path = profile_dir / "collection.anki2"
    col = Collection(str(col_path))
    col.close()
    return AnkiProfile(name=profile_name, path=profile_dir, collection_path=col_path)


def format_profile_menu(profiles: list[AnkiProfile]) -> str:
    """Return a numbered menu string for profile selection."""
    lines: list[str] = []
    for i, p in enumerate(profiles, 1):
        lines.append(f"  {i}. {p.name}  ({p.collection_path})")
    lines.append(f"  {len(profiles) + 1}. Create new profile")
    return "\n".join(lines)


def resolve_profile(profiles: list[AnkiProfile], choice: int) -> AnkiProfile:
    """Return the profile at 1-based index choice, or raise ValueError."""
    if choice < 1 or choice > len(profiles):
        msg = f"Choice {choice} is out of range (1-{len(profiles)})"
        raise ValueError(msg)
    return profiles[choice - 1]
