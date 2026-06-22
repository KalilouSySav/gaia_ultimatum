"""Unit tests for the JSON-backed prefs + run history."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from gaia_ultimatum import persistence
from gaia_ultimatum.persistence import (
    Prefs,
    RunRecord,
    append_run,
    load_history,
    load_prefs,
    save_prefs,
)


@pytest.fixture
def save_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect persistence I/O to ``tmp_path`` for the test's lifetime."""
    monkeypatch.setenv("GAIA_SAVE_DIR", str(tmp_path))
    return tmp_path


def test_load_prefs_returns_defaults_when_file_absent(save_dir: Path) -> None:
    prefs = load_prefs()
    assert prefs == Prefs()
    assert prefs.audio_muted is False
    assert prefs.last_catastrophe is None


def test_prefs_roundtrip_preserves_fields(save_dir: Path) -> None:
    written = Prefs(
        audio_muted=True,
        reduce_motion=True,
        disable_flash=False,
        high_contrast=True,
        last_catastrophe="Eau",
        last_difficulty="Apocalypse",
    )
    save_prefs(written)
    read_back = load_prefs()
    assert read_back == written


def test_prefs_from_dict_ignores_unknown_keys(save_dir: Path) -> None:
    """Forward-compatibility: a prefs.json written by a future version with
    extra keys must still load cleanly (legacy installs land here too)."""
    payload = {
        "audio_muted": True,
        "last_catastrophe": "Feu",
        "future_unknown_key": "ignore me",
    }
    (save_dir / "prefs.json").write_text(json.dumps(payload), encoding="utf-8")
    prefs = load_prefs()
    assert prefs.audio_muted is True
    assert prefs.last_catastrophe == "Feu"


def test_corrupt_prefs_file_is_backed_up_and_replaced(save_dir: Path) -> None:
    """A truncated/corrupt prefs.json must not crash the game on boot — it's
    renamed to ``.corrupted-*`` and defaults take over."""
    (save_dir / "prefs.json").write_text("{ not valid json", encoding="utf-8")
    prefs = load_prefs()
    assert prefs == Prefs()
    assert not (save_dir / "prefs.json").exists()
    corrupted = list(save_dir.glob("prefs.corrupted-*.json"))
    assert len(corrupted) == 1


def test_load_history_returns_empty_when_file_absent(save_dir: Path) -> None:
    assert load_history() == []


def test_append_run_roundtrip(save_dir: Path) -> None:
    record = RunRecord(
        catastrophe="Vie",
        difficulty="Normal",
        country="FRA",
        outcome="victory",
        turns=42,
        timestamp="2026-06-17T12:00:00Z",
    )
    append_run(record)
    history = load_history()
    assert len(history) == 1
    assert history[0] == record


def test_append_run_caps_at_50(save_dir: Path) -> None:
    """History is bounded — a 51st run pushes the oldest out."""
    for i in range(60):
        append_run(
            RunRecord(
                catastrophe="Eau",
                difficulty="Normal",
                country=f"C{i:03d}",
                outcome="defeat",
                turns=i,
                timestamp=f"2026-06-17T12:00:{i:02d}Z",
            )
        )
    history = load_history()
    assert len(history) == 50
    # FIFO eviction: the first 10 records are gone, the last 50 remain.
    assert history[0].country == "C010"
    assert history[-1].country == "C059"


def test_corrupt_history_file_is_backed_up(save_dir: Path) -> None:
    (save_dir / "history.json").write_text("not a list", encoding="utf-8")
    assert load_history() == []
    assert not (save_dir / "history.json").exists()
    corrupted = list(save_dir.glob("history.corrupted-*.json"))
    assert len(corrupted) == 1


def test_now_iso_emits_z_suffix() -> None:
    """Wire format stays ``YYYY-MM-DDTHH:MM:SSZ`` — pinned so disk-format
    consumers (existing history.json, log scrapers) don't see drift."""
    stamp = persistence.now_iso()
    assert stamp.endswith("Z")
    assert "T" in stamp
    assert "+" not in stamp  # no tz offset leaked through


def test_save_dir_honours_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("GAIA_SAVE_DIR", str(tmp_path / "custom"))
    assert persistence._save_dir() == tmp_path / "custom"
