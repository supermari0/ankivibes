"""Tests for the Anki profile discovery and creation module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from ankivibes.anki_profile import (
    AnkiProfile,
    create_profile,
    discover_profiles,
    find_anki_base_dir,
    format_profile_menu,
    resolve_profile,
)


# -- find_anki_base_dir -------------------------------------------------------


class TestFindAnkiBaseDir:
    def test_darwin(self, tmp_path: Path) -> None:
        base = tmp_path / "Library" / "Application Support" / "Anki2"
        base.mkdir(parents=True)
        with (
            patch("ankivibes.anki_profile.sys") as mock_sys,
            patch("ankivibes.anki_profile.Path") as mock_path_cls,
        ):
            mock_sys.platform = "darwin"
            mock_path_cls.home.return_value = tmp_path
            # We need the real Path for everything else, so call the real function
            # with a more targeted approach.
        # Better approach: just mock sys.platform and Path.home()
        with patch("ankivibes.anki_profile.sys.platform", "darwin"), patch.object(
            Path, "home", return_value=tmp_path
        ):
            result = find_anki_base_dir()
            assert result == base

    def test_linux(self, tmp_path: Path) -> None:
        base = tmp_path / ".local" / "share" / "Anki2"
        base.mkdir(parents=True)
        with patch("ankivibes.anki_profile.sys.platform", "linux"), patch.object(
            Path, "home", return_value=tmp_path
        ):
            result = find_anki_base_dir()
            assert result == base

    def test_win32(self, tmp_path: Path) -> None:
        base = tmp_path / "Anki2"
        base.mkdir(parents=True)
        with (
            patch("ankivibes.anki_profile.sys.platform", "win32"),
            patch.dict("os.environ", {"APPDATA": str(tmp_path)}),
        ):
            result = find_anki_base_dir()
            assert result == base

    def test_win32_no_appdata(self) -> None:
        with (
            patch("ankivibes.anki_profile.sys.platform", "win32"),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = find_anki_base_dir()
            assert result is None

    def test_missing_directory(self, tmp_path: Path) -> None:
        with patch("ankivibes.anki_profile.sys.platform", "darwin"), patch.object(
            Path, "home", return_value=tmp_path
        ):
            # tmp_path/Library/Application Support/Anki2 does not exist
            result = find_anki_base_dir()
            assert result is None


# -- discover_profiles ---------------------------------------------------------


class TestDiscoverProfiles:
    def test_empty_dir(self, tmp_path: Path) -> None:
        assert discover_profiles(tmp_path) == []

    def test_nonexistent_dir(self, tmp_path: Path) -> None:
        assert discover_profiles(tmp_path / "nope") == []

    def test_one_profile(self, tmp_path: Path) -> None:
        profile_dir = tmp_path / "Spanish"
        profile_dir.mkdir()
        (profile_dir / "collection.anki2").touch()

        profiles = discover_profiles(tmp_path)
        assert len(profiles) == 1
        assert profiles[0].name == "Spanish"
        assert profiles[0].collection_path == profile_dir / "collection.anki2"

    def test_multiple_profiles_sorted(self, tmp_path: Path) -> None:
        for name in ["Zebra", "Alpha", "Middle"]:
            d = tmp_path / name
            d.mkdir()
            (d / "collection.anki2").touch()

        profiles = discover_profiles(tmp_path)
        assert [p.name for p in profiles] == ["Alpha", "Middle", "Zebra"]

    def test_excludes_non_profile_dirs(self, tmp_path: Path) -> None:
        for name in ["addons21", "crash_reports", "logs"]:
            d = tmp_path / name
            d.mkdir()
            (d / "collection.anki2").touch()

        assert discover_profiles(tmp_path) == []

    def test_excludes_dirs_without_collection(self, tmp_path: Path) -> None:
        (tmp_path / "Empty Profile").mkdir()
        assert discover_profiles(tmp_path) == []


# -- create_profile ------------------------------------------------------------

try:
    from anki.collection import Collection

    _HAS_ANKI = True
except ImportError:
    _HAS_ANKI = False

needs_anki = pytest.mark.skipif(not _HAS_ANKI, reason="anki package not installed")


@needs_anki
class TestCreateProfile:
    def test_creates_collection(self, tmp_path: Path) -> None:
        profile = create_profile(tmp_path, "Spanish")
        assert profile.name == "Spanish"
        assert profile.path == tmp_path / "Spanish"
        assert profile.collection_path.exists()

    def test_collection_is_valid(self, tmp_path: Path) -> None:
        profile = create_profile(tmp_path, "Test")
        col = Collection(str(profile.collection_path))
        try:
            assert col.note_count() == 0
        finally:
            col.close()

    def test_existing_dir_no_error(self, tmp_path: Path) -> None:
        (tmp_path / "Existing").mkdir()
        profile = create_profile(tmp_path, "Existing")
        assert profile.collection_path.exists()


# -- resolve_profile -----------------------------------------------------------


class TestResolveProfile:
    @pytest.fixture()
    def profiles(self) -> list[AnkiProfile]:
        return [
            AnkiProfile(name="Alpha", path=Path("/a"), collection_path=Path("/a/collection.anki2")),
            AnkiProfile(name="Beta", path=Path("/b"), collection_path=Path("/b/collection.anki2")),
        ]

    def test_valid_choice(self, profiles: list[AnkiProfile]) -> None:
        assert resolve_profile(profiles, 1).name == "Alpha"
        assert resolve_profile(profiles, 2).name == "Beta"

    def test_zero_raises(self, profiles: list[AnkiProfile]) -> None:
        with pytest.raises(ValueError, match="out of range"):
            resolve_profile(profiles, 0)

    def test_out_of_range_raises(self, profiles: list[AnkiProfile]) -> None:
        with pytest.raises(ValueError, match="out of range"):
            resolve_profile(profiles, 3)


# -- format_profile_menu -------------------------------------------------------


class TestFormatProfileMenu:
    def test_single_profile(self) -> None:
        profiles = [
            AnkiProfile(name="Spanish", path=Path("/s"), collection_path=Path("/s/collection.anki2")),
        ]
        menu = format_profile_menu(profiles)
        assert "1. Spanish" in menu
        assert "2. Create new profile" in menu

    def test_multiple_profiles(self) -> None:
        profiles = [
            AnkiProfile(name="A", path=Path("/a"), collection_path=Path("/a/collection.anki2")),
            AnkiProfile(name="B", path=Path("/b"), collection_path=Path("/b/collection.anki2")),
        ]
        menu = format_profile_menu(profiles)
        assert "1. A" in menu
        assert "2. B" in menu
        assert "3. Create new profile" in menu
