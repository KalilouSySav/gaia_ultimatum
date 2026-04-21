"""Game configuration.

All tunable values live here. Values are exposed as frozen dataclasses so they
are safe to share across modules and easy to override from tests.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from gaia_ultimatum.assets import DATA_DIR


@dataclass(frozen=True)
class DisplayConfig:
    width: int = 1200
    height: int = 800
    fps: int = 60
    title: str = "Gaia Ultimatum"
    fullscreen: bool = False


@dataclass(frozen=True)
class AudioConfig:
    master_volume: float = 0.8
    music_volume: float = 0.7
    effects_volume: float = 0.8
    muted: bool = False


@dataclass(frozen=True)
class GameplayConfig:
    victory_threshold: float = 0.90
    defeat_mortality_ratio: float = 0.80
    min_zoom: float = 0.2
    max_zoom: float = 5.0
    zoom_step: float = 1.1
    point_spawn_probability: float = 0.05
    point_lifetime_range: tuple[int, int] = (60, 180)
    point_size_range: tuple[float, float] = (4.0, 10.0)


@dataclass(frozen=True)
class Palette:
    background: tuple[int, int, int] = (5, 20, 30)
    country_outline: tuple[int, int, int] = (100, 100, 100)
    selected_outline: tuple[int, int, int] = (255, 255, 255)
    point_red: tuple[int, int, int] = (255, 50, 50)
    ui_background: tuple[int, int, int, int] = (30, 30, 40, 200)
    text: tuple[int, int, int] = (255, 255, 255)
    ui_highlight: tuple[int, int, int] = (70, 120, 200)
    healthy: tuple[int, int, int] = (50, 100, 255)
    affected: tuple[int, int, int] = (255, 50, 50)
    dead: tuple[int, int, int] = (10, 10, 10)


@dataclass(frozen=True)
class Config:
    display: DisplayConfig = field(default_factory=DisplayConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    gameplay: GameplayConfig = field(default_factory=GameplayConfig)
    palette: Palette = field(default_factory=Palette)
    debug: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_CONFIG = Config()
CONFIG_FILE: Path = DATA_DIR / "config.json"


def _apply_env_overrides(config: Config) -> Config:
    """Apply GAIA_* environment variables as overrides for common fields."""
    display = config.display
    audio = config.audio
    overrides_display: dict[str, Any] = {}
    overrides_audio: dict[str, Any] = {}

    if (value := os.environ.get("GAIA_WIDTH")) is not None:
        overrides_display["width"] = int(value)
    if (value := os.environ.get("GAIA_HEIGHT")) is not None:
        overrides_display["height"] = int(value)
    if (value := os.environ.get("GAIA_FPS")) is not None:
        overrides_display["fps"] = int(value)
    if (value := os.environ.get("GAIA_FULLSCREEN")) is not None:
        overrides_display["fullscreen"] = value.lower() in ("1", "true", "yes")
    if (value := os.environ.get("GAIA_MUTED")) is not None:
        overrides_audio["muted"] = value.lower() in ("1", "true", "yes")

    debug = os.environ.get("GAIA_DEBUG", "").lower() in ("1", "true", "yes") or config.debug

    return replace(
        config,
        display=replace(display, **overrides_display) if overrides_display else display,
        audio=replace(audio, **overrides_audio) if overrides_audio else audio,
        debug=debug,
    )


def load_config(path: Path | None = None) -> Config:
    """Load configuration, applying JSON file overrides then environment overrides.

    A missing file is not an error — defaults are used. Unknown keys are ignored.
    """
    config = DEFAULT_CONFIG
    config_path = path or CONFIG_FILE
    if config_path.is_file():
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        config = _merge(config, raw)
    return _apply_env_overrides(config)


def _merge(config: Config, overrides: Mapping[str, Any]) -> Config:
    display = overrides.get("display", {}) or {}
    audio = overrides.get("audio", {}) or {}
    gameplay = overrides.get("gameplay", {}) or {}
    return replace(
        config,
        display=replace(config.display, **{k: v for k, v in display.items() if hasattr(config.display, k)}),
        audio=replace(config.audio, **{k: v for k, v in audio.items() if hasattr(config.audio, k)}),
        gameplay=replace(
            config.gameplay,
            **{k: v for k, v in gameplay.items() if hasattr(config.gameplay, k)},
        ),
        debug=bool(overrides.get("debug", config.debug)),
    )
