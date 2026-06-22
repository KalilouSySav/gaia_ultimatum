"""Tests for the configuration layer."""

from __future__ import annotations

import json
from pathlib import Path

from gaia_ultimatum.config import DEFAULT_CONFIG, load_config


def test_defaults_are_sane() -> None:
    config = DEFAULT_CONFIG
    assert config.display.width > 0
    assert config.display.height > 0
    assert 30 <= config.display.fps <= 240
    assert 0.0 <= config.audio.master_volume <= 1.0
    assert 0.0 < config.gameplay.victory_threshold < 1.0


def test_json_overrides(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"display": {"width": 1920, "height": 1080}}))
    config = load_config(path)
    assert config.display.width == 1920
    assert config.display.height == 1080


def test_env_overrides(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("GAIA_WIDTH", "640")
    monkeypatch.setenv("GAIA_HEIGHT", "480")
    monkeypatch.setenv("GAIA_MUTED", "true")
    monkeypatch.setenv("GAIA_DEBUG", "1")
    config = load_config(tmp_path / "missing.json")
    assert config.display.width == 640
    assert config.display.height == 480
    assert config.audio.muted is True
    assert config.debug is True


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"display": {"wobble": 42}, "nonsense": 1}))
    config = load_config(path)
    assert config.display.width == DEFAULT_CONFIG.display.width


# ---------------------------------------------------------------------------
# Fullscreen precedence — CLI > env > config-file > touch-mode-default
# ---------------------------------------------------------------------------


def test_touch_mode_auto_enables_fullscreen(
    tmp_path: Path, monkeypatch,
) -> None:
    """When ``GAIA_TOUCH_MODE`` flips ``touch_mode`` on, ``fullscreen``
    follows by default — a windowed Android app would have the system
    status bar eat the tutorial chip and the canvas would float in
    black bars."""
    monkeypatch.delenv("GAIA_FULLSCREEN", raising=False)
    monkeypatch.setenv("GAIA_TOUCH_MODE", "1")
    config = load_config(tmp_path / "missing.json")
    assert config.display.touch_mode is True
    assert config.display.fullscreen is True


def test_env_fullscreen_wins_over_touch_mode_default(
    tmp_path: Path, monkeypatch,
) -> None:
    """``GAIA_FULLSCREEN=0`` explicitly overrides the touch-mode
    auto-fullscreen — used by a desktop dev who wants to inspect the
    touch UI in a windowed browser without losing dev tools."""
    monkeypatch.setenv("GAIA_TOUCH_MODE", "1")
    monkeypatch.setenv("GAIA_FULLSCREEN", "0")
    config = load_config(tmp_path / "missing.json")
    assert config.display.touch_mode is True
    assert config.display.fullscreen is False


def test_touch_mode_off_keeps_fullscreen_off_by_default(
    tmp_path: Path, monkeypatch,
) -> None:
    """Desktop default stays windowed — the touch-mode-driven auto-flip
    must only fire when touch_mode is True."""
    monkeypatch.delenv("GAIA_TOUCH_MODE", raising=False)
    monkeypatch.delenv("GAIA_FULLSCREEN", raising=False)
    config = load_config(tmp_path / "missing.json")
    # touch_mode may auto-detect True on a pygbag runner; only assert
    # the relationship "touch off ⇒ fullscreen off" rather than the
    # absolute fullscreen value.
    if not config.display.touch_mode:
        assert config.display.fullscreen is False
