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
