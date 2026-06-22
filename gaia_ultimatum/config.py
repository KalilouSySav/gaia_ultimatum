"""Game configuration.

All tunable values live here. Values are exposed as frozen dataclasses so they
are safe to share across modules and easy to override from tests.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from gaia_ultimatum.assets import DATA_DIR


def _running_on_pygbag() -> bool:
    """True when the runtime is pygbag's WebAssembly/emscripten target.

    Pygbag compiles via Pyodide → emscripten; both ``sys.platform`` and
    ``platform.system()`` come back as ``"emscripten"`` in that
    environment. We additionally check for the ``__BROWSER__`` marker
    pygbag sets on ``sys`` because emscripten can theoretically be
    reached via other tools, and the marker confirms we're inside a
    browser rather than a generic wasm host.
    """
    if sys.platform == "emscripten":
        return True
    return bool(getattr(sys, "__BROWSER__", False))


# Minimum tap target (Apple HIG: 44 pt; Material Design: 48 dp). We use
# 48 — the larger of the two — for a small finger-positioning safety
# margin. Exposed as a module constant rather than a config field
# because no reasonable game-side override exists (smaller would be
# unreachable on common devices, larger would just waste UI space).
MIN_TOUCH_TARGET: int = 48


def touch_grow(rect_w: int, rect_h: int) -> tuple[int, int]:
    """Grow a rect's shortest axis to ``MIN_TOUCH_TARGET`` for touch.

    Used by the renderer + input handler to upsize close ×, audio
    toggle, help, tutorial, and settings-toggle rects when
    ``display.touch_mode`` is on. Leaves the long axis alone so a
    pill-shaped 118 × 26 button becomes 118 × 48 (not 118 × 118)
    and keeps its visual identity.
    """
    return (max(rect_w, MIN_TOUCH_TARGET), max(rect_h, MIN_TOUCH_TARGET))


@dataclass(frozen=True)
class DisplayConfig:
    # Virtual canvas size. The actual window can be resized by the user; the
    # renderer always paints onto a canvas of (width × height) which is then
    # scaled into the window while preserving aspect ratio.
    width: int = 960
    height: int = 640
    fps: int = 60
    title: str = "Terre Vivante"
    fullscreen: bool = False
    resizable: bool = True
    # Touch-input mode. When True:
    #   * Small UI buttons (close ×, audio toggle, help, tutorial, settings
    #     toggles) grow to ≥ MIN_TOUCH_TARGET on their shortest axis so
    #     finger taps land reliably on them (Apple HIG / Material Design
    #     minimum is 44 px; we target 48 for a small safety margin).
    #   * Pinch gestures (MULTIGESTURE event) drive ``world.scale`` since
    #     mouse-wheel zoom is unreachable on touch.
    #   * The audio manager defers its first ``play_playlist`` until the
    #     first input event so mobile-browser autoplay policy doesn't
    #     reject the boot music.
    #
    # Auto-detected for pygbag/emscripten builds (no env override needed
    # in the web path) and respects ``GAIA_TOUCH_MODE`` for desktop
    # testing — set it on a desktop browser dev session to verify the
    # touch layout without a phone.
    touch_mode: bool = False


@dataclass(frozen=True)
class AudioConfig:
    master_volume: float = 0.8
    music_volume: float = 0.7
    effects_volume: float = 0.8
    muted: bool = False


@dataclass(frozen=True)
class GameplayConfig:
    # Tuned for reachability. Was 0.90/0.80 — victory was unreachable at
    # NORMAL difficulty within a typical 30-50 turn run, and defeat could
    # blindside the player. 0.75/0.65 gives both outcomes credible end-game
    # tension.
    victory_threshold: float = 0.75
    defeat_mortality_ratio: float = 0.65
    # Secondary defeat path — share of *people* (population-weighted, not
    # country-count-weighted) living in regions whose state >= 0.5. Was
    # a magic 0.75 buried inline in ``_check_outcome``; exposed here so
    # tuning is co-located with the primary mortality threshold and the
    # defeat-approach milestone (``half_critical_share`` at 0.50 — half
    # of this ratio) stays consistent if the threshold ever shifts.
    defeat_critical_share_ratio: float = 0.75
    min_zoom: float = 0.2
    max_zoom: float = 5.0
    zoom_step: float = 1.1
    # Catastrophe-point spawn rate per country per turn. Round-after-round
    # trim: 0.005 → 0.0035 → 0.0020 → 0.0010. The 0.0020 cadence (orb
    # roughly every 3-4 turns) still felt like *click-spam* over the
    # course of a 30-40 day run — the player kept reaching for the
    # mouse to harvest small drops. Halved to 0.0010 and orb value
    # doubled (see ``catastrophe.py``) so total ÉN income stays the
    # same per minute but **clicks halve**: each orb is a more
    # meaningful, higher-payout collect, spaced out enough that the
    # player can stay focused on the world map between collections.
    # The state-bias multiplier (×3 over critical countries) still
    # preserves the strategic-zone spawn rate; only the background
    # cadence drops.
    point_spawn_probability: float = 0.0010
    # Shorter lifetimes so unused orbs disappear quickly instead of stacking.
    point_lifetime_range: tuple[int, int] = (30, 80)
    # Smaller orbs (was 4-10) so they read as precise click targets, not
    # bouncing blobs.
    point_size_range: tuple[float, float] = (5.0, 8.0)


@dataclass(frozen=True)
class Palette:
    # Warm-indigo dark theme. Slightly bluer than the previous near-black so
    # the canvas feels like deep ocean rather than void, and accents read
    # warmer instead of clinical.
    background: tuple[int, int, int] = (15, 19, 32)
    ocean_grid: tuple[int, int, int] = (24, 30, 46)
    # Was (60, 72, 96) — almost the same luminance as the healthy
    # country fill (78, 92, 118), so small islands (Pacific atolls,
    # Cuba-sized landmasses) lost their edge against their own fill
    # and read as muddy blobs. Bumped to (95, 110, 138) — sits just
    # above the healthy fill, so even 2-3 px-wide polygons keep a
    # crisp readable border. Still distinctly dimmer than the
    # white-bright `selected_outline` so the selection cue isn't
    # weakened.
    country_outline: tuple[int, int, int] = (95, 110, 138)
    selected_outline: tuple[int, int, int] = (245, 248, 255)
    # Four tonal surface levels for card elevation. Each step shifts a few
    # hue-points warmer so hovered/active states feel approachable.
    surface_deep: tuple[int, int, int, int] = (19, 24, 38, 245)
    surface: tuple[int, int, int, int] = (27, 33, 50, 245)
    surface_elevated: tuple[int, int, int, int] = (38, 46, 68, 245)
    surface_overlay: tuple[int, int, int, int] = (52, 62, 88, 245)
    # ``ui_panel`` is the one surviving legacy alias — still read by the
    # milestone banner's body fill. ``ui_background`` was a duplicate of
    # ``surface_deep`` with one alpha point off and had no callers; same
    # for ``ui_accent_dim`` (≈30 % version of ui_accent, never wired up)
    # and ``point_red`` (a third copy of the same coral already exposed
    # as ``ui_accent`` / ``severe``).
    ui_panel: tuple[int, int, int, int] = (27, 33, 50, 245)
    ui_border: tuple[int, int, int] = (60, 74, 100)
    ui_border_soft: tuple[int, int, int] = (40, 50, 72)
    ui_accent: tuple[int, int, int] = (242, 110, 100)       # warm coral
    news_bg: tuple[int, int, int, int] = (12, 16, 28, 245)
    # Boosted contrast across the board so secondary text reads cleanly on
    # the deep-indigo surfaces (WCAG AA on the surface tone).
    text: tuple[int, int, int] = (245, 248, 255)
    text_dim: tuple[int, int, int] = (188, 198, 216)
    text_label: tuple[int, int, int] = (210, 222, 240)
    ui_highlight: tuple[int, int, int] = (110, 160, 230)    # softer cyan-blue
    # Country severity gradient: muted blue-grey → warm amber → coral → wine.
    # `dead` was (118, 38, 50) — luminance ≈ 0.10, contrast against the
    # deep-indigo background ≈ 3.4:1. That's *dimmer* than `healthy`
    # (4.5:1), so a collapsed country could read as "unaffected" at a
    # glance. Bumped to a brighter wine that keeps the destruction tone
    # but lifts contrast to ≈ 6.5:1 and makes dead unambiguously
    # distinguishable from healthy / background.
    healthy: tuple[int, int, int] = (78, 92, 118)
    affected: tuple[int, int, int] = (232, 168, 80)
    severe: tuple[int, int, int] = (242, 110, 100)
    dead: tuple[int, int, int] = (170, 55, 70)


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
    # touch_mode: explicit env override wins; otherwise auto-detect.
    # Detection covers (a) pygbag/emscripten, (b) Android via python-
    # for-android which exposes ``sys.platform == "android"``. Either
    # case is unambiguously a touch device, so we don't ask the
    # operating system.
    if (value := os.environ.get("GAIA_TOUCH_MODE")) is not None:
        overrides_display["touch_mode"] = value.lower() in ("1", "true", "yes")
    elif (
        sys.platform in ("android", "emscripten")
        or _running_on_pygbag()
        # p4a may report sys.platform as "linux"; ANDROID_ARGUMENT
        # is set by every p4a bootstrap, and ``getandroidapilevel``
        # exists on the Android Python stdlib build. Either is a
        # reliable Android signal even when sys.platform isn't.
        or "ANDROID_ARGUMENT" in os.environ
        or hasattr(sys, "getandroidapilevel")
    ):
        overrides_display["touch_mode"] = True

    # Auto-fullscreen on touch platforms when the user hasn't explicitly
    # picked one. Touch devices don't have a windowing concept — a
    # windowed Android app would just embed the canvas inside black
    # bars while the system status bar eats top-of-screen UI (the
    # tutorial chip lives at y = TOP_BAR_H + 10, well within the
    # status-bar zone). ``GAIA_FULLSCREEN`` still wins so a desktop
    # browser dev session with ``GAIA_TOUCH_MODE=1`` can keep the
    # surrounding tools visible by passing ``GAIA_FULLSCREEN=0``.
    # CLI ``--fullscreen``/``--no-fullscreen`` (applied in
    # ``app.run_async`` after this) wins over both, so per-run intent
    # always carries.
    if (
        overrides_display.get("touch_mode") is True
        and "fullscreen" not in overrides_display
    ):
        overrides_display["fullscreen"] = True

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
