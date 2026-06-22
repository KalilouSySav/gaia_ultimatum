"""Tests for the cinematic library's lazy-open semantics.

These exercise the path-store + lazy-open + background-preload flow
without requiring cv2 — the lib degrades to ``None`` when cv2 is
missing AND when the file is absent, so the behavioural assertions
work the same regardless of whether OpenCV is installed.
"""

from __future__ import annotations

from pathlib import Path

from gaia_ultimatum.cinematics_player import CinematicLibrary


def test_from_paths_lazy_opens_no_clips(tmp_path: Path) -> None:
    """``from_paths_lazy`` must not touch any file at construction —
    boot perf depends on this being a pure dict-copy operation."""
    paths = {"intro": tmp_path / "missing-intro.mp4"}
    lib = CinematicLibrary.from_paths_lazy(paths)
    # No clips opened yet (pending), and the path is still registered.
    assert lib.clips == {}
    assert "intro" in lib.pending_paths


def test_lazy_get_drops_missing_file_to_none(tmp_path: Path) -> None:
    """First ``get`` on a path that doesn't exist resolves to None and
    removes the entry from pending so a second call doesn't re-attempt
    the open (cheap, deterministic fallback to procedural envelopes)."""
    paths = {"intro": tmp_path / "missing.mp4"}
    lib = CinematicLibrary.from_paths_lazy(paths)
    assert lib.get("intro") is None
    # Second call still returns None (cached + entry dropped from pending).
    assert lib.get("intro") is None
    assert "intro" not in lib.pending_paths


def test_get_unknown_name_returns_none(tmp_path: Path) -> None:
    lib = CinematicLibrary.from_paths_lazy({"intro": tmp_path / "intro.mp4"})
    assert lib.get("does_not_exist") is None


def test_preload_in_background_drains_pending(tmp_path: Path) -> None:
    """The background preloader must walk every pending entry. With
    missing files (test env: no real MP4s), the sweep should drain
    ``pending_paths`` to empty even though every clip resolves to
    None. Without this, a runtime player triggering a cinematic after
    boot would still pay the open cost despite the preloader having
    "run"."""
    paths = {
        "intro": tmp_path / "i.mp4",
        "victory": tmp_path / "v.mp4",
        "defeat": tmp_path / "d.mp4",
    }
    lib = CinematicLibrary.from_paths_lazy(paths)
    assert len(lib.pending_paths) == 3
    t = lib.preload_in_background()
    t.join(timeout=2.0)
    assert not t.is_alive()
    assert lib.pending_paths == {}


def test_close_all_clears_pending(tmp_path: Path) -> None:
    lib = CinematicLibrary.from_paths_lazy(
        {"intro": tmp_path / "intro.mp4", "outro": tmp_path / "outro.mp4"},
    )
    lib.close_all()
    assert lib.pending_paths == {}
    assert lib.clips == {}
