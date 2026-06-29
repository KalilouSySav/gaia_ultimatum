"""Rendering: the only layer allowed to touch ``pygame.Surface``.

Plague-Inc-inspired layout:

    ┌────────────────────────── top bar ─────────────────────────────┐
    │ TURN  CATASTROPHE              [ balance bar ]    EVO POINTS   │
    ├──────────────────────────────────────────────────┬─────────────┤
    │                                                  │  STATS      │
    │             world map (severity colored)         │  • Pop      │
    │                                                  │  • Affected │
    │                                                  │  • Dead     │
    │                                                  │  • Catastr. │
    ├──────────────────────────────────────────────────┴─────────────┤
    │  ◀ scrolling news ticker ◀                                     │
    └────────────────────────────────────────────────────────────────┘

Uses ``pygame.draw`` exclusively (not ``pygame.gfxdraw``) so the module loads
on pygame-ce WebAssembly builds (pygbag), which do not ship gfxdraw and whose
import resolver would otherwise try to fetch it from PyPI.
"""

from __future__ import annotations

import logging
import math
import random
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:  # pragma: no cover — type-only import
    from gaia_ultimatum.cinematics_player import CinematicLibrary

try:  # Pillow is a soft dependency: drop shadows degrade to no-op without it.
    from PIL import Image, ImageDraw, ImageFilter
    _PIL_AVAILABLE = True
except ImportError:  # pragma: no cover — handled at runtime
    _PIL_AVAILABLE = False

logger = logging.getLogger(__name__)

from gaia_ultimatum import __version__
from gaia_ultimatum.config import MIN_TOUCH_TARGET, Config, Palette
from gaia_ultimatum.models import Country, Difficulty, Game, Phase, World
from gaia_ultimatum.models.game import TUTORIAL_SLIDE_COUNT
from gaia_ultimatum.models.catastrophe import Catastrophe
from gaia_ultimatum.models.evolution import (
    BRANCH_LABELS,
    BRANCH_TO_AXIS,
    BRANCHES,
    EvolutionTree,
)
from gaia_ultimatum.models.skill_catalog import Skill
from gaia_ultimatum.view.fonts import (
    Fonts,
    ICON_QUESTION,
    ICON_VOLUME_OFF,
    ICON_VOLUME_UP,
)

INSTRUCTIONS = (
    # French typography rule: a space precedes ``:`` (and ``;``, ``!``,
    # ``?``). The previous list omitted it on every line — the cheats
    # box was the *most* user-visible French-text panel in the game and
    # was misspelt eight times in a row.
    "CLIC : pays / point",
    "MOLETTE / +/− : zoom",
    "GLISSER / FLÈCHES : pan",
    "ESPACE : pause / reprise",
    "1 / 2 / 3 : vitesse",
    "C : catastrophe",
    "E : évolution",
    "M : muet",
)

TOP_BAR_H = 60
RIGHT_PANEL_W = 296
NEWS_BAR_H = 38
INFO_PANEL_W = 324
INFO_PANEL_H = 420  # shorter now that content is paged by tabs

# Spacing rhythm — keep all panel content aligned to these values.
PAD = 16
PAD_SM = 8
GAP_SM = 6
GAP = 10
GAP_LG = 16

# Evolution overlay layout constants (used by both renderer and input handler).
EVO_NODE_W = 168
EVO_NODE_H = 84
EVO_NODE_GAP_X = 28
EVO_ROW_GAP = 24
EVO_ROW_LABEL_W = 168

PHASE_FADE_MS = 110  # phase-change fade-in duration (ms) — was 160


SPEED_BUTTON_W = 38
SPEED_BUTTON_H = 28
SPEED_BUTTON_GAP = 4
SPEED_BUTTON_LABELS: dict[int, str] = {0: "II", 1: "▶", 2: "▶▶", 3: "▶▶▶"}

# Country info / dashboard card palette — kept as constants for back-compat,
# but the values now match the main dark theme so the info panel doesn't pop
# as a bright white sheet on top of the dark game canvas.
LIGHT_CARD_BG = (27, 33, 50)
LIGHT_CARD_TEXT = (240, 244, 252)
LIGHT_CARD_DIM = (148, 160, 184)
LIGHT_CARD_LABEL = (180, 194, 220)
LIGHT_CARD_RULE = (60, 74, 100)
LIGHT_TRACK = (50, 60, 88)
# Was (38, 46, 68) — same luminance as the info-panel card body, so
# chips / sparkline trough / tab pills barely lifted off the surface
# (1.5:1 luminance ratio against LIGHT_CARD_BG). (50, 60, 88) keeps
# the same indigo family but raises the luminance enough for a clear
# Material-style elevation cue — chips and the TENDANCE chart now
# read as discrete surfaces resting on the card.
LIGHT_HEADER_TEXT = (245, 248, 255)
LIGHT_SUCCESS = (90, 200, 130)
LIGHT_WARNING = (232, 168, 80)
LIGHT_DANGER = (242, 110, 100)
# Softer status variants used in dense overlays (country tooltip, outro
# population row, picker step markers). The dashboard's LIGHT_WARNING /
# LIGHT_SUCCESS are tuned to pop on light card surfaces; in a hovering
# tooltip the same saturation reads as neon spam against the deep
# indigo backdrop. These are the same hue family at lower chroma so
# the cohesion stays — the country tooltip's "Sain" pip and the outro
# population badge use the same sage / amber here. ``SOFT_SEVERE``
# isn't needed: the bright ``palette.severe`` IS the right colour for
# the alarming branches (the tooltip comment block already chose the
# bright variant intentionally to retain urgency).
SOFT_WARNING = (220, 165, 75)
SOFT_SUCCESS = (115, 185, 130)

GAME_OVER_BTN_W = 220
GAME_OVER_BTN_H = 52
GAME_OVER_BTN_GAP = 18

TITLE_BTN_W = 240
TITLE_BTN_H = 48
TITLE_BTN_GAP = 14


class Renderer:
    def __init__(self, config: Config, fonts: Fonts) -> None:
        self.config = config
        self.palette: Palette = config.palette
        self.fonts = fonts
        self._news_scroll_x: float = 0.0
        # Cache key widened from a flat ``text_str`` to
        # ``(tuple(news), cat_color)`` — the rolling strip now bakes
        # cat-tinted bullet separators between items, so the rendered
        # Surface depends on both the news content AND which catastrophe
        # is active. Cycling catastrophes invalidates the cache.
        self._news_text_cache: tuple[
            tuple[tuple[str, ...], tuple[int, int, int]], pygame.Surface
        ] | None = None
        self._gradient_cache: dict[tuple[int, int, tuple, tuple], pygame.Surface] = {}
        self._shadow_cache: dict[tuple[int, int, int, int], pygame.Surface] = {}
        # Minimap cache — full re-render is ~700ms with 239 polygons; refresh
        # every N frames so it tracks state without dominating frame budget.
        self._minimap_cache: pygame.Surface | None = None
        self._minimap_last_refresh: int = -10_000  # force first build
        self._minimap_refresh_interval_ms: int = 750
        # Ambient particle field on the title screen.
        self._title_particles: list[dict] = []
        # Ambient particles inside the evolution overlay (catastrophe-tinted).
        self._evo_particles: list[dict] = []
        # Last-frame snapshot of purchased levels — used to detect level deltas
        # and trigger purchase-burst particles at the card center.
        self._last_purchased_levels: dict[str, int] = {}
        # Phase fade-in transitioning state. When game.phase changes, fade in
        # from black over PHASE_FADE_MS so screen-to-screen swaps don't hard-cut.
        self._last_phase: object | None = None
        self._phase_transition_start_ms: int = 0
        # True after the first overlay frame so bursts don't fire on first open.
        self._overlay_was_open: bool = False
        # MP4 cinematic library attached by the app at startup. None until
        # attach_cinematics() is called.
        self._cinematics: "CinematicLibrary | None" = None
        # Per-clip cached letterbox layout (logical_w, logical_h, clip_w,
        # clip_h) → (dest_rect, scaled_size). Recomputed when window resizes.
        self._cinematic_layout_cache: dict[tuple[int, int, int, int], pygame.Rect] = {}
        # Single-entry cache for the *scaled* frame, keyed on
        # (source-frame-id, dest-size). VideoClip already caches the
        # decoded source surface per frame_idx — when the game runs at
        # 60 fps over a 30 fps clip, every other render call would
        # otherwise re-do ``pygame.transform.smoothscale`` on the same
        # source pixels. Caching here makes those redraws free.
        # Identity-by-``id()`` is safe because VideoClip holds a strong
        # ref to its current surface (no GC reuse during playback);
        # entries are cleared when the cinematic ends.
        self._cinematic_scaled_cache: tuple[int, tuple[int, int], pygame.Surface] | None = None
        # Tracks the cinematic that was active last frame so the draw() loop
        # can reset _phase_transition_start_ms the instant it ends — that lets
        # the destination phase's procedural envelope play in full.
        self._last_cinematic: str | None = None
        # Per-frame polygon transform cache for the world map. The map
        # has ~239 countries with ~50 polygons each (~50k vertices
        # total); calling ``world.transform_point`` in the country
        # draw loop was the dominant per-frame cost (885k Python
        # calls / frame on average, ~25 ms on a real ARM phone
        # alone — that's 1.5 frame budgets at 60 fps). The transform
        # is a pure function of (scale, offset_x, offset_y,
        # view_center_y, screen_size); when none of those change
        # between frames (the common case: player is reading the
        # screen, not panning/zooming), we serve the cached
        # transformed polygons and skip all the math.
        # Cache miss only on the first frame after any view change.
        self._polygon_xform_cache: dict[str, list[list[tuple[float, float]]]] = {}
        self._polygon_xform_key: tuple | None = None
        # Shared map-sized SRCALPHA scratch surface — reused by the ring
        # pulse, off-screen arrows, and spread arcs draws. Each consumer
        # acquires it via ``_acquire_map_overlay``, paints into it, and
        # blits it onto the main surface before returning, so a single
        # buffer fits all three (they never overlap in time within a
        # single frame). Replaces three per-frame ``Surface((w, h),
        # SRCALPHA)`` allocations — on mobile pygame the per-pixel-alpha
        # surface alloc + clear is one of the dominant per-frame costs.
        self._map_overlay: pygame.Surface | None = None
        # Cache for static ``font.render`` outputs keyed on
        # ``(font_id, text, color)``. Tab labels, section headers, axis
        # titles, etc. re-render the same Surface every frame for nothing
        # — the SDL_ttf raster + per-pixel-alpha blit is expensive on
        # mobile. Cap the cache at a sane size (clear when exceeded) to
        # bound memory if a caller passes unbounded dynamic text in by
        # mistake.
        self._text_cache: dict[
            tuple[int, str, tuple[int, int, int]], pygame.Surface
        ] = {}

    def attach_cinematics(self, library: "CinematicLibrary") -> None:
        """Bind the app-level cinematic library so MP4 frames can be drawn."""
        self._cinematics = library

    @property
    def screen_size(self) -> tuple[int, int]:
        return (self.config.display.width, self.config.display.height)

    @property
    def map_rect(self) -> pygame.Rect:
        w, h = self.screen_size
        sidebar_w = RIGHT_PANEL_W if not self._sidebar_collapsed else 0
        return pygame.Rect(0, TOP_BAR_H, w - sidebar_w, h - TOP_BAR_H - NEWS_BAR_H)

    @property
    def _sidebar_collapsed(self) -> bool:
        # Read lazily from the last drawn game (set in draw()). Defaults to
        # False so layouts work even before the first draw call.
        return getattr(self, "_last_sidebar_collapsed", False)

    def _world_view_center_y(self, game: Game) -> float:
        """Vertical centring offset for the visible map area, per phase.

        Returns the delta (in screen pixels) that should be added to
        ``height / 2`` so the world's lat=0 line lands in the centre of
        whatever vertical band the current phase leaves for the map.

          - PLAYING: aligns to ``map_rect.centery`` (top bar + news bar).
          - PICKER: aligns to the centre of the area between the
            picker title row (~y=98) and the nav button row (~y=552).
            World was previously 14 px above that centre, leaving the
            map looking slightly high in the picker step-2 view.
          - other phases (TITLE, OUTRO): no map shown, value is unused.

        Pixels rather than ratios so the offsets stay stable when the
        window is resized — the reserved rows are constants either way.
        """
        h = self.config.display.height
        canvas_center_y = h / 2
        if game.phase is Phase.PLAYING:
            visible_center = TOP_BAR_H + (h - TOP_BAR_H - NEWS_BAR_H) / 2
            return visible_center - canvas_center_y
        if game.phase is Phase.PICKER:
            # Visible area in picker step 2: from the picker tagline
            # bottom (~y=98) to the nav button top (~y=552). Centre at
            # ~325. Title + tagline heights aren't perfectly stable
            # across fonts; ±2 px tolerance is fine for the eye.
            picker_top = 98
            picker_bottom = h - 88  # nav button at h-48-40, then 88 of clearance
            return (picker_top + picker_bottom) / 2 - canvas_center_y
        return 0.0

    def draw(self, surface: pygame.Surface, game: Game) -> None:
        surface.fill(self.palette.background)
        # MP4 cinematic preempts everything else when one is playing. The
        # underlying phase / overlays continue to update behind the scenes
        # but only the video frame + skip controls are drawn until it ends.
        was_in_cinematic = self._last_cinematic is not None
        if (
            game.cinematic_playing is not None
            and self._cinematics is not None
        ):
            self._last_cinematic = game.cinematic_playing
            handled = self._draw_cinematic(surface, game)
            if handled:
                return
        # The cinematic just ended this frame (either auto-finish or skipped
        # via input). Reset the phase-transition timer so the destination
        # screen's procedural cinematic envelope plays its full duration.
        # Also drop the scaled-frame cache — the next cinematic (if any)
        # will hold a different Surface identity and we don't want a
        # stale entry kept alive for nothing between plays.
        if was_in_cinematic and game.cinematic_playing is None:
            self._phase_transition_start_ms = pygame.time.get_ticks()
            self._last_cinematic = None
            self._cinematic_scaled_cache = None
        # Detect phase swap and start a fade-in.
        if self._last_phase is None or self._last_phase is not game.phase:
            self._phase_transition_start_ms = pygame.time.get_ticks()
            self._last_phase = game.phase
        if game.phase is Phase.TITLE:
            self._draw_title_screen(
                surface,
                reduce_motion=game.reduce_motion,
                last_run=game.last_run_summary,
            )
            self._draw_phase_fade(surface, reduce_motion=game.reduce_motion)
            return
        # Stash the sidebar-collapsed flag so `map_rect` reflects the layout
        # for this frame (read by world/ocean drawing). The right panel is
        # only drawn during PLAYING with the sidebar expanded — anywhere
        # else (PICKER, OUTRO, PLAYING-with-collapsed-sidebar) the map
        # should occupy the full canvas width. The previous condition only
        # set this flag during PLAYING, so during PICKER the world was
        # silently clipped at x = width − RIGHT_PANEL_W = 664 even though
        # no panel was drawn — chopping off ~30 % of the world on the
        # right side of the map.
        self._last_sidebar_collapsed = not (
            game.phase is Phase.PLAYING
            and not getattr(game, "sidebar_collapsed", False)
        )
        # Phase-aware vertical centring of the world inside the visible map
        # box. ``view_center_y`` shifts where the world's lat=0 line lands
        # on the canvas so the rendered map sits in the geometric centre of
        # the *visible* area rather than the canvas centre. Click hit-tests
        # use ``inverse_transform`` which reads the same offset, so clicks
        # always land on the country the player visually targets.
        game.world.view_center_y = self._world_view_center_y(game)
        self._draw_ocean_grid(surface)
        self._draw_world(
            surface, game.world,
            hovered=game.hovered_country,
            reduce_motion=game.reduce_motion,
        )
        # Textured atmospheric overlay — laid over the countries but
        # *under* the gameplay-focus elements (spread arcs, orbs,
        # floating texts) so it grades the land/ocean tone without
        # touching anything the player needs to track. Adds the
        # "modern map" qualities the flat country fills were missing:
        # color-temperature variation (warm top → cool bottom, Earth-
        # from-space tonal scheme), and fine film-grain noise to give
        # the colour areas material texture instead of reading as
        # uniform flat fills. Cached at first call so per-frame cost
        # is one blit.
        self._draw_map_texture_overlay(surface)
        self._draw_spread_arcs(surface, game)
        self._draw_points(surface, game.world, game.gaia.active)
        self._draw_floating_texts(surface, game)
        # Top bar / right panel / news ticker are gameplay HUD only.
        # Showing them during PICKER or OUTRO would let their content poke
        # through the briefing/end-screen modals.
        if game.phase is Phase.PLAYING:
            self._draw_top_bar(surface, game)
            if not game.sidebar_collapsed:
                self._draw_right_panel(surface, game)
            self._draw_sidebar_toggle(surface, game)
            self._draw_recenter_button(surface, game)
            self._draw_news_ticker(surface, game)
        if game.info_panel_visible and game.info_panel_country:
            country = game.world.countries.get(game.info_panel_country)
            if country:
                self._draw_info_panel(surface, country, game)
            else:
                game.info_panel_visible = False
        if (
            game.speed == 0
            and not game.awaiting_start
            and not game.game_over
            and not game.evolution_open
            and not game.pause_menu_open
            and not game.settings_open
            and not game.help_open
            and game.flash is None
        ):
            self._draw_pause_overlay(surface, game)
        if game.hovered_country and not game.evolution_open and not game.game_over:
            self._draw_country_tooltip(surface, game)
        # Side event cards retired — the news ticker carries the same
        # information without cluttering the corner. Only the central
        # auto-fading milestone banner remains for major moments.
        if game.milestone_banners:
            self._draw_milestone_banners(surface, game)
        if game.awaiting_start:
            self._draw_intro_picker(surface, game)
        if game.loading_bridge is not None:
            self._draw_loading_bridge(surface, game)
        if game.flash is not None:
            self._draw_flash(surface, game)
        if game.evolution_open:
            self._draw_evolution_overlay(surface, game)
        else:
            # Reset the level-delta tracker so reopening doesn't fire stale bursts.
            self._overlay_was_open = False
        if game.impact_card is not None:
            self._draw_impact_card(surface, game)
        # Discrete tutorial chip at the top-left of the map — visible
        # during PLAYING when no other modal is active. The helper
        # gates on the same conditions internally so it can be called
        # unconditionally here.
        self._draw_tutorial_button(surface, game)
        if game.tutorial_open:
            self._draw_tutorial_overlay(surface, game)
        if game.help_open:
            self._draw_help_modal(surface)
        if game.pause_menu_open:
            self._draw_pause_menu(surface, game)
        if game.settings_open:
            self._draw_settings_overlay(surface, game)
        if game.game_over:
            self._draw_game_over(surface, game)
        # Phase fade — last layer so transitions cover all content.
        self._draw_phase_fade(surface, reduce_motion=game.reduce_motion)

    def _draw_cinematic(self, surface: pygame.Surface, game: Game) -> bool:
        """Draw the active MP4 cinematic + skip controls.

        Returns ``True`` when the cinematic absorbed this frame (so the normal
        rendering pipeline should be skipped). Returns ``False`` and clears
        ``game.cinematic_playing`` when the clip is finished or the library
        can't provide it — letting the caller fall back to the procedural
        intro/outro envelope built into the destination screen.
        """
        name = game.cinematic_playing
        if name is None:
            return False
        library = self._cinematics
        if library is None:
            # No library attached. Defensive: in production
            # ``attach_cinematics`` runs at app boot, but a headless
            # test path or a partial init can leave ``_cinematics``
            # None. Without cleanup the game stays stuck with
            # "cinematic active" forever — music dampened, normal
            # rendering blocked from the cinematic side, no skip
            # control reachable. Same recovery as the library-has-no-
            # clip branch just below: mark played, clear playing,
            # fall through to the destination phase's procedural
            # envelope.
            game.cinematic_played.add(name)
            game.cinematic_playing = None
            self._cinematic_scaled_cache = None
            return False
        clip = library.get(name)
        if clip is None or not clip.available:
            # No video for this name — mark as played so we don't loop forever
            # asking the player to skip something that can't render.
            game.cinematic_played.add(name)
            game.cinematic_playing = None
            self._cinematic_scaled_cache = None
            return False

        w, h = self.screen_size
        elapsed_ms = pygame.time.get_ticks() - game.cinematic_started_ms
        # Auto-advance when the clip ends — the destination phase's normal
        # rendering picks up on the next frame. Reset the phase-transition
        # timer so the procedural cinematic envelope (title drift, shockwave
        # ring) plays *after* the MP4 instead of being skipped because the
        # phase change happened seconds ago.
        if clip.is_finished(elapsed_ms):
            game.cinematic_played.add(name)
            game.cinematic_playing = None
            self._cinematic_scaled_cache = None
            self._phase_transition_start_ms = pygame.time.get_ticks()
            return False

        frame = clip.frame_at(elapsed_ms)

        # Letterbox-fit the frame to the logical surface. Source aspect is
        # preserved so portrait or wide clips never stretch oddly. The
        # letterbox bars (around the frame on aspect-mismatched clips)
        # used to fill in pure ``(0, 0, 0)`` — a hard cut that read as
        # "the canvas has a hole punched in it". The fill now uses the
        # palette's deep-navy background so the cinematic feels embedded
        # in the UI rather than overlaid on void. Frame-size cache is
        # per (w, h, clip_w, clip_h) tuple (window resize-safe).
        surface.fill(self.palette.background)
        if frame is not None:
            clip_w, clip_h = clip.size
            if clip_w > 0 and clip_h > 0:
                cache_key = (w, h, clip_w, clip_h)
                dest = self._cinematic_layout_cache.get(cache_key)
                if dest is None:
                    scale = min(w / clip_w, h / clip_h)
                    sw, sh = int(clip_w * scale), int(clip_h * scale)
                    dest = pygame.Rect(
                        (w - sw) // 2, (h - sh) // 2, sw, sh,
                    )
                    self._cinematic_layout_cache[cache_key] = dest
                # Scaled-frame cache: same source-frame Surface + same
                # dest size → skip ``smoothscale`` entirely. Single
                # entry (LRU=1); the cache is cleared when the
                # cinematic ends so memory doesn't carry between
                # plays.
                frame_id = id(frame)
                cached = self._cinematic_scaled_cache
                if (
                    cached is not None
                    and cached[0] == frame_id
                    and cached[1] == dest.size
                ):
                    scaled = cached[2]
                else:
                    scaled = pygame.transform.smoothscale(frame, dest.size)
                    self._cinematic_scaled_cache = (
                        frame_id, dest.size, scaled,
                    )
                surface.blit(scaled, dest.topleft)

        # Cinematic envelope: 300 ms fade-in at the start, 400 ms fade-out at
        # the tail. Soft black overlay so the transition into/out of the clip
        # is never a hard cut.
        #
        # Curves were linear (`alpha = 255 * t`) while every other transition
        # in the renderer — ``_draw_phase_fade``, the title-particle
        # envelope, the milestone-banner birth halo, the indicator-dial
        # success halo — uses cubic easing. The mismatch made cinematic
        # boundaries feel more mechanical than the rest of the UI.
        #
        # New curves:
        #   * **Fade-in**: ``(1 - t)^3`` on the veil alpha — fast drop
        #     then slow tail. Matches ``_draw_phase_fade`` exactly so a
        #     cinematic entering the screen reads as the same engine
        #     primitive as a phase change. The player gets to see the
        #     opener cinematic faster (50 % alpha by t = 0.21, vs t = 0.5
        #     linear), with the residual veil holding longer near the
        #     tail to soften the lead-in.
        #   * **Fade-out**: ``t^3`` on the veil alpha — slow ramp then
        #     fast cut. Reverses the fade-in curve so the cinematic
        #     stays viewable longer (the chrome can ramp out gracefully
        #     against an unveiled frame) and then snaps to black at the
        #     last moment for a clean cut to the destination phase.
        duration = clip.duration_ms()
        fade_in_ms = 300
        fade_out_ms = 400
        if elapsed_ms < fade_in_ms:
            t = elapsed_ms / fade_in_ms
            alpha = int(255 * (1.0 - t) ** 3)
            if alpha > 0:
                veil = pygame.Surface((w, h), pygame.SRCALPHA)
                veil.fill((0, 0, 0, alpha))
                surface.blit(veil, (0, 0))
        elif duration > 0 and elapsed_ms > duration - fade_out_ms:
            t = (elapsed_ms - (duration - fade_out_ms)) / fade_out_ms
            t = min(1.0, max(0.0, t))
            alpha = int(255 * t ** 3)
            if alpha > 0:
                veil = pygame.Surface((w, h), pygame.SRCALPHA)
                veil.fill((0, 0, 0, alpha))
                surface.blit(veil, (0, 0))

        # Skip control + progress bar — design-consistent with the rest of the
        # UI (translucent rounded panel, label uppercase, catastrophe-neutral
        # so it reads across all cinematics).
        chrome_alpha = self._cinematic_chrome_alpha(
            elapsed_ms, duration, fade_in_ms, fade_out_ms,
        )
        if chrome_alpha > 0:
            # Run-state context strip — surfaces scenario-specific data on
            # top of the cinematic so the same MP4 lands differently each
            # run. Drawn under the skip UI so its alpha tracks the same
            # chrome envelope.
            self._draw_cinematic_context_strip(
                surface, game, name, alpha_t=chrome_alpha,
            )
            self._draw_cinematic_skip_ui(
                surface, clip, elapsed_ms, alpha_t=chrome_alpha,
            )
        return True

    def _draw_cinematic_context_strip(
        self,
        surface: pygame.Surface,
        game: Game,
        name: str,
        *,
        alpha_t: float,
    ) -> None:
        """Draw scenario-specific data over the cinematic frame.

        The MP4 carries the cinematic's *static* identity (palette,
        glyph, title, subtitle). This overlay adds the run-specific
        beat: which day it is, which country just tipped, the current
        mortality — so the same clip lands differently across runs
        without needing pre-rendered variants. Reads game state at
        render time, so the chip values track live state changes
        during the clip's 4 s play.

        Layout: a single editorial line of chips ("LABEL N · LABEL X")
        centred above the progress bar at the bottom of the canvas.
        Alpha modulated by ``alpha_t`` so the strip fades in/out with
        the rest of the cinematic chrome envelope.
        """
        w, h = self.screen_size
        cat_color = game.gaia.active.arc_color

        def mod(a: int) -> int:
            return int(a * alpha_t)

        # Pick chips based on which cinematic is playing. Returns a list
        # of (label, value, value_color) tuples; label uses text_label
        # tone, value uses the per-chip semantic colour.
        chips: list[tuple[str, str, tuple[int, int, int]]] = []
        total_pop = sum(c.population for c in game.world.countries.values())
        total_dead = sum(c.dead for c in game.world.countries.values())
        mortality_pct = (
            int(total_dead / total_pop * 100) if total_pop > 0 else 0
        )

        if name.startswith("element_"):
            # First-critical beat: day, the populous country that tipped,
            # and the count of countries currently exposed (state 0.2-0.5).
            chips.append(("JOUR", str(game.turn), self.palette.text))
            critical = [
                c for c in game.world.countries.values() if c.state >= 0.5
            ]
            if critical:
                top = max(critical, key=lambda c: c.population)
                chips.append(("FOYER", top.name.upper(), cat_color))
            exposed = sum(
                1 for c in game.world.countries.values()
                if 0.2 <= c.state < 0.5
            )
            if exposed:
                chips.append(("EXPOSÉS", str(exposed), self.palette.text_label))
        elif name == "point_de_non_retour":
            # Quarter-dead beat: day, live mortality, critical-country
            # count. Was EFFONDRÉS (state >= 1.0 fully-collapsed
            # countries) — but at 25 % mortality very few or zero
            # countries have fully collapsed yet, so the chip was
            # often empty. CRITIQUES (state >= 0.5) is guaranteed to
            # be populated by the time this fires.
            #
            # Chip colour is a slightly darker coral than LIGHT_DANGER
            # — 22 R units below the dashboard variant — chosen so
            # the value text reads against bright cinematic video
            # frames (LIGHT_DANGER at (242, 110, 100) tested too
            # bright over the warm-frame moments of the PNR clip).
            # Local variable so the two chips share one source of
            # truth instead of duplicating the literal.
            pnr_chip_color = (220, 110, 95)
            chips.append(("JOUR", str(game.turn), self.palette.text))
            chips.append(("PERTES", f"{mortality_pct} %", pnr_chip_color))
            critical_n = sum(
                1 for c in game.world.countries.values() if c.state >= 0.5
            )
            if critical_n:
                chips.append(("CRITIQUES", str(critical_n), pnr_chip_color))
        elif name == "midgame":
            # World-tipping beat. Lead with the population-weighted
            # share that *triggered* the cinematic — the world-tip
            # condition crossed from raw country count to ``crit_pop /
            # total_pop >= 0.50`` earlier this session, so the chip
            # should report the same metric the trigger gates on
            # instead of the country count it used to report. The
            # subtitle "la moitié du monde a vacillé" reads on
            # population terms, so the chip now matches its own line.
            chips.append(("JOUR", str(game.turn), self.palette.text))
            crit_pop = sum(
                c.population for c in game.world.countries.values()
                if c.state >= 0.5
            )
            crit_share_pct = (
                int(crit_pop / total_pop * 100) if total_pop > 0 else 0
            )
            chips.append(
                ("MONDE EN CRISE", f"{crit_share_pct} %", cat_color),
            )
        elif name in ("victory", "defeat", "outro"):
            # End-game beat: final mortality + equilibrium + day count.
            chips.append(("JOUR", str(game.turn), self.palette.text))
            chips.append(
                ("PERTES", f"{mortality_pct} %", self.palette.severe),
            )
            eq_pct = int(game.humans.global_progress * 100)
            chips.append(
                ("ÉQUILIBRE", f"{eq_pct} %", _progress_color(game.humans.global_progress)),
            )
        if not chips:
            return

        # Render chips on a single horizontal line. Each chip is rendered
        # as "LABEL value" with a small gap, separated by middle-dot.
        label_font = self.fonts.label
        value_font = self.fonts.medium
        # Pre-render each chip's label + value surfaces and measure.
        rendered: list[tuple[pygame.Surface, pygame.Surface]] = []
        for label, value, color in chips:
            l_surf = label_font.render(label, True, self.palette.text_label)
            v_surf = value_font.render(value, True, color)
            rendered.append((l_surf, v_surf))
        chip_gap = 6   # label → value
        sep_w = 18     # middle-dot block between chips
        # Total width = sum(label + gap + value) for each chip + (n-1)*sep_w.
        total_w = sum(
            l.get_width() + chip_gap + v.get_width()
            for l, v in rendered
        ) + (len(rendered) - 1) * sep_w
        x = (w - total_w) // 2
        # Sit ~28 px above the progress bar (h-38) — keeps clear of the
        # skip pill which lives bottom-right at h-pill_h-8.
        # Use the value font's height for the row centerline.
        row_h = max(l.get_height() for l, _ in rendered)
        y = h - 38 - row_h - 18
        # Subtle backing bar — translucent black behind the chips so the
        # text reads against bright cinematic frames (e.g. mid-bloom on
        # the element cards). Inset 12 px each side from the chip block.
        pad_x = 14
        pad_y = 6
        backing = pygame.Surface(
            (total_w + pad_x * 2, row_h + pad_y * 2), pygame.SRCALPHA,
        )
        pygame.draw.rect(
            backing, (0, 0, 0, mod(140)),
            (0, 0, backing.get_width(), backing.get_height()),
            border_radius=row_h // 2 + pad_y,
        )
        # 1-px cat-tinted hairline border so the strip carries run identity.
        pygame.draw.rect(
            backing, (*cat_color, mod(90)),
            (0, 0, backing.get_width(), backing.get_height()),
            1, border_radius=row_h // 2 + pad_y,
        )
        surface.blit(backing, (x - pad_x, y - pad_y))
        # Draw each chip: label + value, separated by " · " between chips.
        cur_x = x
        for i, (l_surf, v_surf) in enumerate(rendered):
            if alpha_t < 1.0:
                l_surf = l_surf.copy()
                v_surf = v_surf.copy()
                l_surf.set_alpha(mod(255))
                v_surf.set_alpha(mod(255))
            # Vertical centring — small font for label, medium for value
            # → align both to the row centerline.
            surface.blit(
                l_surf,
                (cur_x, y + (row_h - l_surf.get_height()) // 2),
            )
            cur_x += l_surf.get_width() + chip_gap
            surface.blit(
                v_surf,
                (cur_x, y + (row_h - v_surf.get_height()) // 2),
            )
            cur_x += v_surf.get_width()
            if i < len(rendered) - 1:
                # Middle-dot separator — cat-tinted, vertically centred.
                dot_color = (*cat_color, mod(180))
                dot_layer = pygame.Surface((sep_w, row_h), pygame.SRCALPHA)
                pygame.draw.circle(
                    dot_layer, dot_color,
                    (sep_w // 2, row_h // 2), 2,
                )
                surface.blit(dot_layer, (cur_x, y))
                cur_x += sep_w

    @staticmethod
    def _cinematic_chrome_alpha(
        elapsed_ms: int,
        duration_ms: int,
        fade_in_ms: int,
        fade_out_ms: int,
    ) -> float:
        """Skip-UI alpha envelope, mirroring the cinematic's own veil.

        Returns 0..1 with the following stages:

          * **Hold dark** for the duration of the cinematic's fade-in
            (the veil is at full opacity here — chrome would be drawn
            over the veil and look like a free-floating UI panel over
            black) + an extra 200 ms grace so the opener gets undivided
            attention.
          * **Ramp in** over the next 400 ms — same easing curve as
            ``_draw_phase_fade`` so the UI feels native to the engine's
            transition language.
          * **Hold** at 1.0 through the middle.
          * **Ramp out** in lockstep with the cinematic's tail veil so
            the chrome can't outlive its underlying frame and float
            over a fading-to-black canvas.

        ``duration_ms == 0`` means a clip with no known length; in that
        case the ramp-in still applies but the ramp-out is skipped —
        progress is unknowable anyway, and we don't want to make the
        skip control unreachable on infinite / unknown-length clips.
        """
        appear_delay = fade_in_ms + 200
        appear_ramp = 400
        if elapsed_ms < appear_delay:
            return 0.0
        if elapsed_ms < appear_delay + appear_ramp:
            t = (elapsed_ms - appear_delay) / appear_ramp
            return 1.0 - (1.0 - t) ** 3
        if duration_ms <= 0:
            return 1.0
        tail_start = duration_ms - fade_out_ms
        if elapsed_ms >= tail_start:
            t = max(0.0, min(1.0, (elapsed_ms - tail_start) / fade_out_ms))
            return max(0.0, 1.0 - t)
        return 1.0

    def _draw_cinematic_skip_ui(
        self,
        surface: pygame.Surface,
        clip: "object",
        elapsed_ms: int,
        *,
        alpha_t: float = 1.0,
    ) -> None:
        """Bottom skip pill + progress bar + elapsed-time chip.

        Whole chrome (bar + chip + pill) modulates by ``alpha_t`` so the
        UI fades in after the cinematic opener lands and fades out in
        lockstep with the tail veil — no free-floating controls over a
        veil'd canvas.
        """
        w, h = self.screen_size
        # Pre-multiply all alpha channels by the envelope ``alpha_t`` so
        # the chrome modulates as a whole instead of piece-by-piece.
        def mod(a: int) -> int:
            return int(a * alpha_t)

        # Progress bar — full width, sits 1 px above the skip pill row.
        # Was a flat 3-px white track + brighter white fill; the hard
        # top/bottom edges read as a painted strip rather than a video
        # scrubber. Now layered as:
        #   * Thin shadow line just below the bar (1 px black α 60) so
        #     the bar appears to rest on the video, not embedded into it
        #   * Track with a soft upper halo (1 px white at half the
        #     track alpha) so the top edge bleeds rather than cuts
        #   * Fill with a 1-px specular highlight on top + a soft glow
        #     bloom at the leading edge so the playhead reads as a
        #     light moving across the frame
        bar_y = h - 38
        bar_h = 3
        # Subtle drop shadow on the bottom edge.
        shadow = pygame.Surface((w, 1), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, mod(60)))
        surface.blit(shadow, (0, bar_y + bar_h))
        # Soft halo above the track — 1 px at half alpha bleeds the
        # top edge into the video frame instead of cutting hard.
        halo = pygame.Surface((w, 1), pygame.SRCALPHA)
        halo.fill((255, 255, 255, mod(45)))
        surface.blit(halo, (0, bar_y - 1))
        track = pygame.Surface((w, bar_h), pygame.SRCALPHA)
        track.fill((255, 255, 255, mod(90)))
        surface.blit(track, (0, bar_y))
        duration = clip.duration_ms() if hasattr(clip, "duration_ms") else 0
        progress = min(1.0, elapsed_ms / duration) if duration else 0.0
        fill_w = int(w * progress)
        if fill_w > 0:
            fill = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
            fill.fill((245, 248, 255, mod(220)))
            surface.blit(fill, (0, bar_y))
            # 1-px specular highlight at the very top of the fill so it
            # reads as light catching the leading edge.
            spec = pygame.Surface((fill_w, 1), pygame.SRCALPHA)
            spec.fill((255, 255, 255, mod(180)))
            surface.blit(spec, (0, bar_y))
            # Leading-edge bloom — soft white halo at the playhead so
            # the scrubber feels like a moving light source rather than
            # a static painted edge. Skipped when the bar is full.
            if fill_w < w:
                bloom_r = 10
                bloom = pygame.Surface(
                    (bloom_r * 2 + 4, bloom_r * 2 + 4), pygame.SRCALPHA,
                )
                for r in range(bloom_r, 0, -1):
                    t = r / bloom_r
                    a = int(mod(140) * (1 - t) ** 1.6)
                    if a <= 0:
                        continue
                    pygame.draw.circle(
                        bloom, (255, 255, 255, a),
                        (bloom_r + 2, bloom_r + 2), r,
                    )
                surface.blit(
                    bloom,
                    (fill_w - bloom_r - 2, bar_y + bar_h // 2 - bloom_r - 2),
                )

        # Elapsed-time chip: small "mm:ss" readout to the left of the
        # skip pill so the player can tell how much longer they're held
        # in the cinematic. Format mirrors media-player convention
        # (Spotify / YouTube / VLC bottom-bar elapsed indicator).
        remaining_ms = max(0, duration - elapsed_ms) if duration > 0 else 0
        remaining_s = remaining_ms // 1000
        time_label = f"-{remaining_s // 60}:{remaining_s % 60:02d}" if duration > 0 else ""

        # Skip pill at the bottom-right. Translucent + uppercase label +
        # skip-forward glyph (two right-pointing triangles + a vertical
        # bar) so the pill reads as a media control, not just text.
        # "PASSER · ÉCHAP" — the previous "PASSER · ESC" used the
        # anglo abbreviation in an otherwise French UI; every other
        # escape-key prompt (title hint, pause overlay, settings
        # footer, help footer, help modal shortcut list) uses
        # "ÉCHAP". Middle-dot separator matches the standard
        # control-affordance convention (media UIs use it for
        # "feature · shortcut").
        pill_label = "PASSER · ÉCHAP"
        pill_text = self.fonts.label.render(pill_label, True, (245, 248, 255))
        # Glyph width is fixed (~14 px) + gap; bump pill width to fit.
        glyph_w = 14
        glyph_gap = 8
        pill_w = pill_text.get_width() + 24 + glyph_w + glyph_gap
        pill_h = pill_text.get_height() + 10
        pill_rect = pygame.Rect(
            w - pill_w - 16, h - pill_h - 8, pill_w, pill_h,
        )
        mouse_hover = pill_rect.collidepoint(pygame.mouse.get_pos())
        pill_layer = pygame.Surface(pill_rect.size, pygame.SRCALPHA)
        bg_alpha = mod(200 if mouse_hover else 140)
        pygame.draw.rect(
            pill_layer, (16, 18, 26, bg_alpha),
            (0, 0, pill_rect.width, pill_rect.height),
            border_radius=pill_rect.height // 2,
        )
        # Subtle inner top-edge highlight + bottom-edge shadow — gives
        # the pill a sense of being a raised key resting on the video
        # instead of a flat translucent rect. Same depth idiom shipped
        # on every other elevated chrome surface in the renderer, with
        # alphas modulated through ``mod`` so the depth fades in
        # lockstep with the rest of the cinematic chrome envelope.
        pygame.draw.line(
            pill_layer, (255, 255, 255, mod(55 if mouse_hover else 35)),
            (pill_rect.height // 2, 1),
            (pill_rect.width - pill_rect.height // 2, 1),
        )
        pygame.draw.line(
            pill_layer, (0, 0, 0, mod(110 if mouse_hover else 70)),
            (pill_rect.height // 2, pill_rect.height - 2),
            (pill_rect.width - pill_rect.height // 2, pill_rect.height - 2),
        )
        pygame.draw.rect(
            pill_layer, (255, 255, 255, mod(180 if mouse_hover else 100)),
            (0, 0, pill_rect.width, pill_rect.height),
            1, border_radius=pill_rect.height // 2,
        )
        surface.blit(pill_layer, pill_rect.topleft)

        # Time chip — placed just to the left of the pill, dim+mono so it
        # reads as auxiliary info, not a clickable control. Hidden when
        # the duration is unknown (no usable countdown).
        if time_label:
            chip_surf = self.fonts.label.render(
                time_label, True, (210, 215, 230),
            )
            chip_surf.set_alpha(mod(180))
            chip_x = pill_rect.left - chip_surf.get_width() - 14
            chip_y = pill_rect.centery - chip_surf.get_height() // 2
            surface.blit(chip_surf, (chip_x, chip_y))

        # Skip-forward glyph on the left side of the pill.
        # Glyph + text alpha — we can't tint pygame.draw.polygon with
        # alpha directly, so render them through a per-channel surface
        # and blit with set_alpha.
        glyph_color = (245, 248, 255) if mouse_hover else (210, 215, 230)
        gx = pill_rect.left + 12
        gcy = pill_rect.centery
        # Two triangles pointing right + a thin trailing bar — universal
        # "skip forward" iconography. Draw onto a transparent surface so
        # the chrome envelope can scale the alpha uniformly.
        glyph_layer = pygame.Surface(
            (glyph_w + 4, pill_rect.height), pygame.SRCALPHA,
        )
        gl_gcy = glyph_layer.get_height() // 2
        tri_h = 6
        tri_w = 5
        for offset in (0, tri_w + 1):
            pts = [
                (offset, gl_gcy - tri_h),
                (offset + tri_w, gl_gcy),
                (offset, gl_gcy + tri_h),
            ]
            pygame.draw.polygon(glyph_layer, glyph_color, pts)
        bar_x_local = (tri_w + 1) + tri_w + 2
        pygame.draw.line(
            glyph_layer, glyph_color,
            (bar_x_local, gl_gcy - tri_h),
            (bar_x_local, gl_gcy + tri_h), 2,
        )
        glyph_layer.set_alpha(mod(255))
        surface.blit(glyph_layer, (gx, pill_rect.top))
        # Shift the text right past the glyph block.
        text_x = gx + glyph_w + glyph_gap
        pill_text.set_alpha(mod(255))
        surface.blit(
            pill_text,
            (text_x,
             pill_rect.centery - pill_text.get_height() // 2),
        )

    def _draw_phase_fade(
        self, surface: pygame.Surface, *, reduce_motion: bool = False,
    ) -> None:
        """Overlay that fades out after every phase change.

        Was a flat linear-alpha black wash — perceptually it accelerates
        near full opacity, which read as "loading screen, then snap"
        rather than a smooth handoff. Now:

          1. **Ease-out cubic** alpha curve — the overlay leaves quickly
             at first and lingers near zero, which the eye reads as a
             gentle settle into the new screen.
          2. **Tinted edges** — a soft vignette around the perimeter
             carries the new screen's deep-ocean colour while the centre
             fades faster. Same idea as a cinema iris-out: the outside
             of the frame holds longer than the centre.
          3. **Centre punch-through** — the very middle of the overlay
             clears about 30 % faster than the edges so the player's
             eyes lock onto the new screen's focal point first.
        """
        if reduce_motion:
            return
        elapsed = pygame.time.get_ticks() - self._phase_transition_start_ms
        if elapsed >= PHASE_FADE_MS:
            return
        # Ease-out cubic: 1 - (1 - t)^3 — flips to "alpha drops fast at
        # first, then lingers" by computing as (1 - t_eased) on the
        # alpha rather than (1 - t_linear).
        t = elapsed / PHASE_FADE_MS
        eased = 1.0 - (1.0 - t) ** 3
        alpha = int(255 * (1.0 - eased))
        if alpha <= 0:
            return
        w, h = self.screen_size
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        # Base wash — black at the rim, slightly translucent at the
        # centre so the new screen peeks through the focal point first.
        # Implemented as a radial darkening: a 1-channel black fill
        # plus a soft transparent circle in the centre that punches
        # through. The circle radius grows with progress.
        overlay.fill((0, 0, 0, alpha))
        cx, cy = w // 2, h // 2
        max_r = int(math.hypot(cx, cy))
        # Punch radius starts at 0 and ramps with eased progress, so by
        # mid-fade the centre is materially clearer than the edges.
        punch_r = int(max_r * 0.55 * eased)
        if punch_r > 20:
            punch_alpha_step = int(alpha * 0.85)
            punch = pygame.Surface(
                (punch_r * 2, punch_r * 2), pygame.SRCALPHA,
            )
            # Build a soft-edged punch by drawing concentric reductions
            # of the centre alpha. Cosine taper toward the punch radius
            # so the border between "punched" and "rim" stays smooth.
            for r in range(punch_r, 0, -6):
                tt = r / punch_r
                # cos^2 taper: punches hardest at the centre, fades to
                # zero at the rim.
                reduction = int(punch_alpha_step * (math.cos(tt * math.pi / 2) ** 2))
                if reduction < 1:
                    continue
                pygame.draw.circle(
                    punch, (0, 0, 0, max(0, 255 - reduction)),
                    (punch_r, punch_r), r,
                )
            # Use the punch as a multiplicative mask: instead of blitting
            # it on top (which would just stack alpha), we paint it onto
            # the overlay with BLEND_RGBA_MIN so the centre's alpha gets
            # *reduced* toward the punch's lower values.
            overlay.blit(
                punch,
                (cx - punch_r, cy - punch_r),
                special_flags=pygame.BLEND_RGBA_MIN,
            )
        surface.blit(overlay, (0, 0))

    # ------------------------------------------------------------------ map

    def _draw_ocean_grid(self, surface: pygame.Surface) -> None:
        """Subtle latitude/longitude grid in the map area.

        Major lines every 120px (slightly brighter), minor lines every 60px
        (very faint) — a denser grid reads more like a navigational chart.
        A faint vertical deep-ocean gradient sits below the grid to lift the
        map area off the flat background. Grid lines are baked into the
        cached background so the per-frame cost is a single blit instead
        of ~100 ``draw.line`` calls.
        """
        rect = self.map_rect
        ocean = getattr(self, "_ocean_bg_cache", None)
        if ocean is None or ocean.get_size() != rect.size:
            base = self._gradient_surface(
                rect.width, rect.height,
                (10, 18, 32, 255), (4, 8, 16, 255),
            )
            # Soft vignette in the corners — a radial darkening that draws the
            # eye toward the middle of the map.
            vignette = pygame.Surface(rect.size, pygame.SRCALPHA)
            cx, cy = rect.width // 2, rect.height // 2
            max_r = int(math.hypot(cx, cy))
            for r in range(max_r, max_r // 2, -8):
                alpha = int(60 * (r - max_r // 2) / (max_r - max_r // 2))
                pygame.draw.circle(vignette, (0, 0, 0, alpha), (cx, cy), r, 8)
            base.blit(vignette, (0, 0))
            # Bake the grid into the cached background. Grid coordinates
            # are local to ``base`` (origin (0, 0)) — they get translated
            # to ``rect.topleft`` for free by the blit below.
            minor = self.palette.ocean_grid
            major = _shade(self.palette.ocean_grid, 1.6)
            step = 60
            for x in range(0, rect.width, step):
                line_color = major if x % (step * 2) == 0 else minor
                pygame.draw.line(base, line_color, (x, 0), (x, rect.height), 1)
            for y in range(0, rect.height, step):
                line_color = major if y % (step * 2) == 0 else minor
                pygame.draw.line(base, line_color, (0, y), (rect.width, y), 1)
            ocean = base
            self._ocean_bg_cache = ocean
        surface.blit(ocean, rect.topleft)

    def _draw_world(
        self,
        surface: pygame.Surface,
        world: World,
        hovered: str | None = None,
        reduce_motion: bool = False,
    ) -> None:
        clip = surface.get_clip()
        surface.set_clip(self.map_rect)
        # Country labels used to render on-map (clutter at moderate
        # zoom; tiny-country flood at deep zoom). The right-panel
        # country details pane is the single source of truth for
        # country names now — the on-map labels were redundant with
        # it. Selected/hovered country still draws its outline glow
        # and centroid ring, so the visual "this is selected" signal
        # remains; the text answer lives in the side panel.
        # Pulse modulator for critical countries (state >= 0.5). One sin per
        # frame, applied as a brightness blend so hotspots draw the eye.
        ticks = pygame.time.get_ticks()
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
        # Outer-ring pulse phase 0..1 cycling every 1100 ms — peripheral-vision
        # hook that's much more salient than internal luminance change.
        ring_phase = (ticks % 1100) / 1100.0
        critical_centroids: list[tuple[int, int]] = []
        # Hover ring uses an independent slower sin for variety.
        hover_pulse = 0.5 + 0.5 * math.sin(ticks * 0.003)
        # Refresh the polygon transform cache only when the view
        # changed (zoom / pan / window resize / new world). Cache hit
        # eliminates ~885k ``transform_point`` Python calls per frame.
        # Key includes ``id(world)`` so a new game with a new World
        # instance correctly invalidates.
        view_key = (
            id(world),
            world.scale, world.offset_x, world.offset_y,
            world.view_center_y, self.screen_size,
        )
        if self._polygon_xform_key != view_key:
            self._polygon_xform_cache = {
                cid: [
                    [world.transform_point(p, self.screen_size) for p in polygon]
                    for polygon in c.polygons
                ]
                for cid, c in world.countries.items()
            }
            self._polygon_xform_key = view_key
        try:
            for country_id, country in world.countries.items():
                color = _country_color(country, self.palette)
                # Map-only saturation lift: pull each channel further
                # from luminance midpoint by ~30 %. Factor was 1.15
                # earlier this session — perceptible but conservative;
                # the user explicitly asked for more vibrance after
                # that, so 1.30 is the next step up. Still well below
                # the point where channels clip wholesale (which would
                # blow out highlights), and the linear-RGB blend's
                # muddy mid-tones (where the chroma drops between
                # palette stops) get the biggest lift — exactly the
                # values the eye was reading as "washed out".
                #
                # The palette colours are shared with sparklines,
                # dials, TENDANCE chips, and the BILAN tab — so the
                # lift is applied here on the map render path only,
                # not in the palette itself. Cheap: 3 mul + 3 clamp +
                # 1 tuple per country per frame (~239 countries) ≈
                # 1500 ops. Negligible.
                _lum = (color[0] + color[1] + color[2]) / 3.0
                color = (
                    max(0, min(255, int(_lum + (color[0] - _lum) * 1.30))),
                    max(0, min(255, int(_lum + (color[1] - _lum) * 1.30))),
                    max(0, min(255, int(_lum + (color[2] - _lum) * 1.30))),
                )
                if country.state >= 0.5:
                    # Keep a subtle internal luminance cue (small, not load-bearing).
                    color = _blend(color, self.palette.severe, 0.10 + 0.18 * pulse)
                    cx, cy = world.transform_point(country.centroid, self.screen_size)
                    if (
                        self.map_rect.left <= cx <= self.map_rect.right
                        and self.map_rect.top <= cy <= self.map_rect.bottom
                    ):
                        critical_centroids.append((int(cx), int(cy)))
                is_selected = country_id == world.selected_country
                is_hovered = country_id == hovered
                if is_selected:
                    outline = self.palette.selected_outline
                    outline_w = 2
                elif is_hovered:
                    # Brighten outline + thicken slightly when hovered, with a soft pulse.
                    outline = _blend(
                        self.palette.country_outline,
                        self.palette.selected_outline,
                        0.4 + 0.4 * hover_pulse,
                    )
                    outline_w = 2
                else:
                    # State-aware outline. Was a flat
                    # ``palette.country_outline`` (cool grey
                    # ``(95, 110, 138)``) for every non-selected /
                    # non-hovered country regardless of state — so
                    # critical countries had vivid red/coral fills
                    # *framed by dim grey*. The eye read "vibrant
                    # fill in a neutral frame" rather than "the whole
                    # country is energised". Above state=0.3 the
                    # outline blends toward a brightened version of
                    # the country's own fill colour (capped at 35 %
                    # of the way to preserve the boundary cue —
                    # outline must stay distinct from fill to still
                    # *read as a boundary*). Below 0.3 the outline
                    # stays cool grey so healthy countries keep their
                    # neutral map-boundary look. Cheap: 1 conditional
                    # + a blend per country per frame.
                    if country.state >= 0.3:
                        warm_t = min(0.35, (country.state - 0.3) * 0.6)
                        rim = (
                            min(255, color[0] + 22),
                            min(255, color[1] + 22),
                            min(255, color[2] + 22),
                        )
                        outline = _blend(
                            self.palette.country_outline, rim, warm_t,
                        )
                    else:
                        outline = self.palette.country_outline
                    outline_w = 1
                for transformed in self._polygon_xform_cache.get(country_id, ()):
                    if len(transformed) < 3:
                        continue
                    # Selected country gets a soft outer glow drawn
                    # *before* the fill, so a wider dim halo extends
                    # outside the polygon edge — reads as "this is in
                    # focus" without needing a second pass after the
                    # outline. Two passes at 4 px and 3 px in muted
                    # whites give a barely-pulsing ambient halo.
                    if is_selected:
                        pygame.draw.polygon(
                            surface,
                            _blend(self.palette.selected_outline, color, 0.65),
                            transformed, 4,
                        )
                        pygame.draw.polygon(
                            surface,
                            _blend(self.palette.selected_outline, color, 0.35),
                            transformed, 3,
                        )
                    pygame.draw.polygon(surface, color, transformed)
                    pygame.draw.polygon(surface, outline, transformed, outline_w)

            # Critical-country outer-ring pulse — concentric expanding circle
            # at each centroid, fades alpha as it grows. Peripheral-vision
            # signal much stronger than internal brightness shift.
            if critical_centroids and not reduce_motion:
                # Two staggered rings offset by 0.5 phase so each
                # centroid radiates a *double sonar*: one ring is at
                # the bright start of its cycle while the other is at
                # the dim tail. Reads as active radar instead of a
                # single slow blink. Both rings use the same severe
                # tint so the cue stays unambiguous.
                overlay_w = self.map_rect.width
                overlay_h = self.map_rect.height
                rings = self._acquire_map_overlay((overlay_w, overlay_h))
                for phase_offset in (0.0, 0.5):
                    phase = (ring_phase + phase_offset) % 1.0
                    r = int(4 + phase * 18)
                    a = int(200 * (1.0 - phase))
                    if a <= 0:
                        continue
                    ring_color = (*self.palette.severe, a)
                    for cx, cy in critical_centroids:
                        local = (cx - self.map_rect.left, cy - self.map_rect.top)
                        if 0 <= local[0] < overlay_w and 0 <= local[1] < overlay_h:
                            pygame.draw.circle(rings, ring_color, local, r, 2)
                surface.blit(rings, self.map_rect.topleft)
        finally:
            surface.set_clip(clip)

    def _draw_points(self, surface: pygame.Surface, world: World, catastrophe: Catastrophe) -> None:
        """Render the catastrophe orbs (click targets) with visual feedback.

        Each orb gets three visual layers:
          1. A faint pulsing "click-zone" ring at the actual hit radius,
             so players intuit that the clickable area extends beyond
             the visible body (input handler uses
             ``max(point.size * 2.2, 16)`` as the generous hit threshold).
          2. The orb body itself: halo + tinted body + bright core.
          3. A hover-near highlight: when the cursor is inside the hit
             zone, the click-zone ring intensifies and a thin outline
             draws around the body so the player knows the click will
             register.
        """
        clip = surface.get_clip()
        surface.set_clip(self.map_rect)
        point_color = catastrophe.point_color
        offscreen_targets: list[tuple[float, float]] = []
        mouse_pos = pygame.mouse.get_pos()
        # Slow pulse for the click-zone ring; ties to ticks so several
        # orbs on screen pulse together (visual coherence).
        ticks = pygame.time.get_ticks()
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.004)
        try:
            for point in catastrophe.active_points:
                pos = world.transform_point(point.position, self.screen_size)
                lifetime_ratio = point.lifetime / point.max_lifetime if point.max_lifetime else 0.0
                size = max(1, int(point.size * (0.8 + lifetime_ratio * 0.2)))
                cx, cy = int(pos[0]), int(pos[1])
                # Off-screen points → flag for edge-arrow rendering after the loop.
                if not self.map_rect.collidepoint(cx, cy):
                    offscreen_targets.append((float(cx), float(cy)))
                    continue

                # Click-zone ring at the input-handler hit radius. Faint
                # by default, brighter when the cursor is near.
                hit_r = int(max(point.size * 2.2, 16.0))
                near = math.hypot(mouse_pos[0] - cx, mouse_pos[1] - cy) < hit_r
                ring_alpha = int((80 if near else 30) + 50 * pulse)
                ring_layer = pygame.Surface(
                    (hit_r * 2 + 2, hit_r * 2 + 2), pygame.SRCALPHA,
                )
                pygame.draw.circle(
                    ring_layer, (*point_color, ring_alpha),
                    (hit_r + 1, hit_r + 1), hit_r, 1,
                )
                surface.blit(
                    ring_layer, (cx - hit_r - 1, cy - hit_r - 1),
                )

                # Dying-soon warning: during the last 25 % of the orb's
                # lifetime, add a fast outer pulse ring so the player
                # knows it's about to disappear. Earlier the orb just
                # quietly shrank from 1.0× → 0.8× — easy to miss, easy
                # to lose the orb's value. Now there's a clear "grab
                # this now" affordance for orbs about to expire.
                if lifetime_ratio < 0.25:
                    warn_t = 1.0 - (lifetime_ratio / 0.25)  # 0 → 1 as it dies
                    fast_pulse = 0.5 + 0.5 * math.sin(ticks * 0.012)
                    warn_r = size + 4 + int(warn_t * 6 * fast_pulse)
                    warn_alpha = int((80 + 100 * fast_pulse) * warn_t)
                    if warn_alpha > 0:
                        warn_layer = pygame.Surface(
                            (warn_r * 2 + 2, warn_r * 2 + 2), pygame.SRCALPHA,
                        )
                        pygame.draw.circle(
                            warn_layer, (*point_color, warn_alpha),
                            (warn_r + 1, warn_r + 1), warn_r, 2,
                        )
                        surface.blit(
                            warn_layer, (cx - warn_r - 1, cy - warn_r - 1),
                        )

                # Soft halo ring + tinted body + bright core + glossy
                # inner highlight. The highlight (small bright spot
                # offset toward the upper-left of the body) gives the
                # orb a 3D-sphere feel — was a flat tinted dot with a
                # central bright core that read as a 2D disc.
                halo = _blend(self.palette.background, point_color, lifetime_ratio * 0.7)
                pygame.draw.circle(surface, halo, (cx, cy), size + 4, 1)
                pygame.draw.circle(surface, point_color, (cx, cy), size)
                core = _blend(point_color, (255, 255, 255), 0.55)
                pygame.draw.circle(surface, core, (cx, cy), max(1, size - 3))
                # Glossy highlight: small near-white spot, sized to the
                # body. Skipped for very small orbs where it'd just be
                # noise. Stays in the upper-left quadrant to suggest a
                # consistent overhead light.
                if size >= 4:
                    hl_r = max(1, size // 3)
                    hl_x = cx - size // 3
                    hl_y = cy - size // 3
                    pygame.draw.circle(
                        surface, (245, 250, 255), (hl_x, hl_y), hl_r,
                    )

                # Hover-near outline — white ring at the body edge tells
                # the player the click is armed.
                if near:
                    pygame.draw.circle(
                        surface, (245, 248, 255), (cx, cy), size + 2, 1,
                    )
        finally:
            surface.set_clip(clip)
        # Edge arrows (drawn outside the clip so they sit at the rect border).
        if offscreen_targets:
            self._draw_offscreen_arrows(surface, offscreen_targets, point_color)

    def _draw_offscreen_arrows(
        self,
        surface: pygame.Surface,
        targets: list[tuple[float, float]],
        color: tuple[int, int, int],
    ) -> None:
        """For each off-screen target, draw a small arrow at the map_rect edge.

        Standard atan2 + clamp implementation: project the line from rect center
        to target onto the rect bounds, then rotate the arrow head to point.

        Visual layers per arrow (was a flat triangle + single pulse alpha):
          1. Soft glow halo behind the head so it reads against busy
             country fills, not just against the ocean.
          2. Short tapered "comet trail" pointing back toward the map
             centre — gives a direction cue that scales with distance.
             The further off-screen the target, the longer the trail.
          3. The arrow head itself (existing triangle) on top.

        Arrows that would land within ~16 px of each other are clustered
        into one head with a count badge ("×3") — was previously stacking
        identical triangles on the same pixel, which read as one slightly
        thicker arrow instead of "three orbs out there".
        """
        rect = self.map_rect
        cx_r, cy_r = rect.centerx, rect.centery
        ticks = pygame.time.get_ticks()
        # Soft pulse on opacity so arrows feel alive rather than static.
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
        alpha = int(170 + 60 * pulse)
        margin = 18  # keep arrows just inside the map edge

        # First pass — resolve every target to its arrow anchor + distance,
        # then cluster anchors within ~16 px so co-located off-screen orbs
        # collapse to one arrow with a count badge instead of stacked
        # triangles. Distance is the un-clamped chord length to the
        # target; we use it to scale the comet trail.
        anchors: list[dict] = []
        half_w = rect.width / 2 - margin
        half_h = rect.height / 2 - margin
        diagonal = math.hypot(rect.width, rect.height)
        for tx, ty in targets:
            dx = tx - cx_r
            dy = ty - cy_r
            if abs(dx) < 1 and abs(dy) < 1:
                continue
            scale_x = half_w / abs(dx) if dx else float("inf")
            scale_y = half_h / abs(dy) if dy else float("inf")
            scale = min(scale_x, scale_y)
            ax = cx_r + dx * scale
            ay = cy_r + dy * scale
            angle = math.atan2(dy, dx)
            chord = math.hypot(dx, dy)
            placed = False
            for a in anchors:
                if math.hypot(ax - a["x"], ay - a["y"]) < 16.0:
                    a["count"] += 1
                    # Use the furthest target in the cluster so the trail
                    # length reflects "the furthest orb in this group".
                    if chord > a["chord"]:
                        a["chord"] = chord
                    placed = True
                    break
            if not placed:
                anchors.append({
                    "x": ax, "y": ay, "angle": angle,
                    "chord": chord, "count": 1,
                })

        overlay = self._acquire_map_overlay(rect.size)
        ox, oy = rect.left, rect.top
        for a in anchors:
            ax, ay = a["x"], a["y"]
            angle = a["angle"]
            # Comet trail — short tapered segment pointing *back* into the
            # viewport. Length scales with how far off-screen the target
            # is, normalised so a corner orb gets the longest trail and a
            # just-edge orb gets a stub. Capped at 28 px so it never
            # crowds nearby UI.
            trail_norm = min(1.0, a["chord"] / (diagonal * 0.6))
            trail_len = 6 + int(22 * trail_norm)
            for i in range(trail_len):
                # Walk back along the inverse arrow direction. Alpha
                # tapers cosine-shaped so the trail fades into the
                # ocean instead of cutting at a fixed step.
                t = i / trail_len
                tx_p = ax - math.cos(angle) * (i + 2)
                ty_p = ay - math.sin(angle) * (i + 2)
                seg_alpha = int(alpha * (1.0 - t) ** 1.8 * 0.55)
                if seg_alpha < 4:
                    continue
                # 2-px width near the head, 1-px near the tail.
                w = 2 if t < 0.45 else 1
                pygame.draw.circle(
                    overlay, (*color, seg_alpha),
                    (int(tx_p - ox), int(ty_p - oy)), w,
                )

            # Soft glow halo behind the head — 3 concentric translucent
            # circles. Sits under the triangle so the arrow stays the
            # crisp shape but reads against any backdrop.
            halo_r_outer = 11
            for hr, ha_mult in ((halo_r_outer, 0.18), (8, 0.30), (5, 0.50)):
                ha = int(alpha * ha_mult)
                if ha < 1:
                    continue
                pygame.draw.circle(
                    overlay, (*color, ha),
                    (int(ax - ox), int(ay - oy)), hr,
                )

            # Arrow head triangle — pointing along (dx, dy); base perp.
            head_len = 14
            head_w = 10
            tip = (ax + math.cos(angle) * head_len * 0.5,
                   ay + math.sin(angle) * head_len * 0.5)
            base_left = (
                ax + math.cos(angle + 2.4) * head_w,
                ay + math.sin(angle + 2.4) * head_w,
            )
            base_right = (
                ax + math.cos(angle - 2.4) * head_w,
                ay + math.sin(angle - 2.4) * head_w,
            )
            local_pts = [
                (tip[0] - ox, tip[1] - oy),
                (base_left[0] - ox, base_left[1] - oy),
                (base_right[0] - ox, base_right[1] - oy),
            ]
            pygame.draw.polygon(overlay, (*color, alpha), local_pts)

            # Cluster count badge: small "×N" off the arrow base when
            # multiple targets clustered to this anchor. Placed on the
            # *inside* side (toward map centre) so it doesn't overlap
            # the trail.
            if a["count"] > 1:
                badge_dx = -math.cos(angle) * 14
                badge_dy = -math.sin(angle) * 14
                bx = int(ax + badge_dx - ox)
                by = int(ay + badge_dy - oy)
                badge_text = f"×{a['count']}"
                bsurf = self.fonts.label.render(
                    badge_text, True, (245, 248, 255),
                )
                bw, bh = bsurf.get_size()
                # Small rounded pill behind the text.
                pill = pygame.Rect(
                    bx - bw // 2 - 4, by - bh // 2 - 1, bw + 8, bh + 2,
                )
                pygame.draw.rect(
                    overlay,
                    (*_blend(color, (0, 0, 0), 0.55), 220),
                    pill, border_radius=pill.height // 2,
                )
                overlay.blit(bsurf, (pill.left + 4, pill.top + 1))

        surface.blit(overlay, rect.topleft)

    def _draw_spread_arcs(self, surface: pygame.Surface, game: Game) -> None:
        if not game.spread_edges:
            return
        map_rect = self.map_rect
        overlay = self._acquire_map_overlay(map_rect.size)
        arc_rgb = game.gaia.active.arc_color
        for edge in list(game.spread_edges):
            source = game.world.countries.get(edge.source_id)
            target = game.world.countries.get(edge.target_id)
            if source is None or target is None or edge.lifetime <= 0:
                continue
            sx, sy = game.world.transform_point(source.centroid, self.screen_size)
            tx, ty = game.world.transform_point(target.centroid, self.screen_size)
            sx -= map_rect.left
            sy -= map_rect.top
            tx -= map_rect.left
            ty -= map_rect.top
            dx, dy = tx - sx, ty - sy
            length = math.hypot(dx, dy)
            if length < 2.0:
                continue
            # Skip arcs whose chord crosses most of the screen (likely antimeridian wrap).
            if length > map_rect.width * 0.7:
                continue
            px, py = -dy / length, dx / length
            arch = min(80.0, length * 0.28)
            cx, cy = (sx + tx) / 2 + px * arch, (sy + ty) / 2 + py * arch

            progress = edge.age / edge.lifetime
            if progress >= 1.0:
                continue
            # Envelope: fade in during the first 10 % so the arc emerges
            # smoothly (was popping in at full alpha — sharp visual hit
            # when a new spread fires mid-turn), hold + fade out over
            # the remaining 90 % using the existing linear decay.
            if progress < 0.10:
                envelope = progress / 0.10
            else:
                envelope = 1.0 - progress  # full life remaining → fade out
            alpha = int(220 * envelope)
            if alpha <= 0:
                continue
            line_color = (*arc_rgb, alpha)

            samples = 22
            prev: tuple[float, float] | None = None
            for i in range(samples + 1):
                t = i / samples
                bx = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * tx
                by = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * ty
                if prev is not None:
                    # Tapered trail width — 1 px at the source, 3 px
                    # near the head. Reads as a comet trail (thin tail
                    # → fat leading edge) rather than a uniform line.
                    # The midpoint t is the average position of this
                    # segment along the arc.
                    mid_t = (i - 0.5) / samples
                    seg_w = max(1, int(1 + mid_t * 2))
                    pygame.draw.line(overlay, line_color, prev, (bx, by), seg_w)
                prev = (bx, by)

            # Comet head leading the arc. Soft glow halo around the
            # 4-px core so the head reads as a bright moving point
            # against busy country fills (was just a flat dot the eye
            # could lose on amber/coral terrain).
            t = progress
            hx = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t * t * tx
            hy = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t * t * ty
            head_alpha = max(0, int(255 * (1.0 - progress * 0.7)))
            head_core = _blend(arc_rgb, (255, 255, 255), 0.6)
            # Glow halo: three concentric circles at decreasing alpha
            # so the head looks like a luminous point, not a sticker.
            for halo_r, halo_a_mult in ((11, 0.18), (8, 0.30), (6, 0.55)):
                halo_a = int(head_alpha * halo_a_mult)
                if halo_a > 0:
                    pygame.draw.circle(
                        overlay, (*arc_rgb, halo_a),
                        (int(hx), int(hy)), halo_r,
                    )
            pygame.draw.circle(overlay, (*head_core, head_alpha), (int(hx), int(hy)), 4)
            pygame.draw.circle(
                overlay, (*arc_rgb, head_alpha), (int(hx), int(hy)), 6, 1
            )

            # Impact ring at the target end — expands + fades during the
            # last 35 % of the arc's lifetime so the spread "lands"
            # visibly on the target country instead of just fading out.
            # Touches a previously-untouched moment in gameplay: the
            # exact frame a catastrophe reaches a new country.
            if progress > 0.65:
                impact_t = (progress - 0.65) / 0.35  # 0 → 1
                ring_r = int(4 + impact_t * 18)
                ring_alpha = int(220 * (1.0 - impact_t))
                if ring_alpha > 4:
                    # Outer expanding ring.
                    pygame.draw.circle(
                        overlay, (*arc_rgb, ring_alpha),
                        (int(tx), int(ty)), ring_r, 2,
                    )
                    # Inner bright pip for the first half of the impact,
                    # so the eye locks onto the landing point even on
                    # the noisy country fills.
                    if impact_t < 0.5:
                        pip_alpha = int(255 * (1.0 - impact_t * 2))
                        pygame.draw.circle(
                            overlay, (*head_core, pip_alpha),
                            (int(tx), int(ty)), 3,
                        )
        surface.blit(overlay, map_rect.topleft)

    def _draw_floating_texts(self, surface: pygame.Surface, game: Game) -> None:
        """Rising +ÉN / status text over the map.

        Pop-in scale at birth (first 15 % of lifetime) gives the
        collection feedback a satisfying "+" punch instead of just
        appearing flat; the 4-direction shadow halo then keeps it
        readable on the patchy country fills as it rises.
        """
        if not game.floating_texts:
            return
        clip = surface.get_clip()
        surface.set_clip(self.map_rect)
        try:
            for ft in game.floating_texts:
                progress = ft.age / ft.lifetime
                if progress >= 1.0:
                    continue
                sx, sy = game.world.transform_point(ft.world_position, self.screen_size)
                rise = int(progress * 32)
                # Pop-in scale during the first 15 % of lifetime.
                # Ease-out cubic: starts small (0.6×), settles at 1.0×
                # by the end of the pop phase. Reads as a satisfying
                # rebound rather than a slow ramp.
                if progress < 0.15:
                    scale_t = progress / 0.15
                    scale = 0.6 + 0.4 * (1.0 - (1.0 - scale_t) ** 3)
                else:
                    scale = 1.0
                # Fade toward the panel/map background so we don't fight pygame's
                # surface-alpha quirks on per-pixel-alpha text surfaces.
                color = _blend(self.palette.background, ft.color, 1.0 - progress)
                shadow_color = _blend(
                    self.palette.background, (0, 0, 0), 1.0 - progress,
                )
                text = self.fonts.mono.render(ft.text, True, color)
                shadow = self.fonts.mono.render(ft.text, True, shadow_color)
                if scale != 1.0:
                    new_w = max(1, int(text.get_width() * scale))
                    new_h = max(1, int(text.get_height() * scale))
                    text = pygame.transform.scale(text, (new_w, new_h))
                    shadow = pygame.transform.scale(shadow, (new_w, new_h))
                tx = int(sx) - text.get_width() // 2
                ty = int(sy) - text.get_height() // 2 - rise
                # 8-direction radial shadow halo (was 4-direction
                # plus-cross). Same fix idiom shipped earlier this
                # session for ``_draw_text_centered``: the 4 cardinal
                # ghosts at 1 px land at distance 1.0; the 4 diagonal
                # ghosts land at distance √2 ≈ 1.41. Uniform alpha
                # across all 8 would over-emphasise the diagonal
                # axes; alpha-scaling diagonals by 1/√2 ≈ 0.707
                # matches the physical falloff so the halo reads as
                # round, not octagonal. Cardinals stay at full
                # shadow intensity; the diagonals fill the corner
                # gaps. Visibly matters for the "+5 ÉN" feedback over
                # patchy country fills (amber / coral land would
                # bleed through the prior plus-cross corners and the
                # text occasionally read as illegible).
                diag = shadow.copy()
                diag.set_alpha(int(255 * 0.707))
                for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    surface.blit(shadow, (tx + dx, ty + dy))
                for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                    surface.blit(diag, (tx + dx, ty + dy))
                surface.blit(text, (tx, ty))
        finally:
            surface.set_clip(clip)

    # ------------------------------------------------------------------ HUD

    def _draw_top_bar(self, surface: pygame.Surface, game: Game) -> None:
        w, _ = self.screen_size
        rect = pygame.Rect(0, 0, w, TOP_BAR_H)
        self._fill_panel(surface, rect, self.palette.surface)
        cat_color = game.gaia.active.arc_color
        # Catastrophe-tinted bottom edge: a 2 px solid line on the seam
        # for a crisp boundary, plus a 4 px alpha-falloff strip below
        # so the catastrophe accent visually dissolves into the map.
        # Replaces a flat 2 px line that ended too abruptly against
        # the deep-indigo backdrop.
        pygame.draw.line(surface, cat_color, (0, TOP_BAR_H), (w, TOP_BAR_H), 2)
        fade_h = 5
        fade = pygame.Surface((w, fade_h), pygame.SRCALPHA)
        for i in range(fade_h):
            a = int(110 * (1 - i / fade_h) ** 1.5)
            if a <= 0:
                continue
            pygame.draw.line(
                fade, (*cat_color, a),
                (0, i), (w, i),
            )
        surface.blit(fade, (0, TOP_BAR_H + 2))
        # Soft drop shadow below the bar for the "floating AppBar" effect.
        self._draw_edge_shadow(surface, y=TOP_BAR_H + 1, height=10)

        # Cluster background pills give visual grouping without heavy borders.
        # Each pill sits just inside the cluster's content region.
        cluster_y = 8
        cluster_h = TOP_BAR_H - 16
        # Left identity cluster (turn + catastrophe). Width is a guess that
        # fits the longest catastrophe label ("TERRE", "BRUTAL" etc.) at the
        # current font size — slight overshoot is harmless against the dark
        # surface.
        left_pill = pygame.Rect(PAD - 6, cluster_y, 200, cluster_h)
        self._draw_cluster_pill(surface, left_pill)

        # Left cluster: JOUR counter + element badge + catastrophe name.
        # "TOUR" was the board-game word for a tick of the simulation —
        # accurate but abstract. "JOUR" reads as time passing (the
        # planet's day-by-day descent), matches the reportage tone of
        # the doc-voice spine, and lands the player in the world
        # instead of in front of a board. Same 4-letter slot, plural
        # "jours" works in every other label site too.
        # JOUR value rendered with a soft catastrophe-tinted underbar
        # so the count reads as anchored progress (visible day-by-day)
        # instead of as a stray pair of stacked text lines that
        # competed with the catastrophe identity for attention.
        x = PAD
        # "JOUR" string + colour are constant; cached so the SDL_ttf raster
        # only runs once per run instead of every frame. ``turn_value`` is
        # dynamic (counts up) so it stays an uncached render.
        turn_label = self.cached_render(self.fonts.label, "JOUR", self.palette.text_label)
        turn_value = self.fonts.mono.render(str(game.turn), True, self.palette.text)
        surface.blit(turn_label, (x, 8))
        value_y = 8 + turn_label.get_height() + 1
        surface.blit(turn_value, (x, value_y))
        # Subtle catastrophe-tinted underline beneath the value (2 px
        # thick, ~80 % the width of the value), giving the counter a
        # "ticker" feel that connects it to the catastrophe identity
        # without dominating the bar.
        underline_w = max(8, int(turn_value.get_width() * 0.8))
        underline_y = value_y + turn_value.get_height() + 1
        pygame.draw.line(
            surface,
            _blend(cat_color, (255, 255, 255), 0.25),
            (x, underline_y), (x + underline_w, underline_y), 2,
        )
        x += max(turn_label.get_width(), turn_value.get_width()) + 14
        self._draw_top_divider(surface, x)
        x += 12

        # Element badge + catastrophe name — visual identity, no caption row.
        # Soft accent halo behind the disc so the catastrophe identity
        # has a focal-point glow that anchors the eye on the top bar
        # without raising overall ink weight (was a flat tinted disc
        # with no aura, easy to miss against the busy cluster pill).
        badge_r = 13
        badge_cx = x + badge_r
        badge_cy = TOP_BAR_H // 2
        halo = pygame.Surface(
            (badge_r * 4 + 4, badge_r * 4 + 4), pygame.SRCALPHA,
        )
        halo_cx = halo.get_width() // 2
        halo_cy = halo.get_height() // 2
        for hr_layer, hr_alpha in ((badge_r + 9, 26), (badge_r + 5, 52)):
            pygame.draw.circle(
                halo, (*cat_color, hr_alpha),
                (halo_cx, halo_cy), hr_layer,
            )
        surface.blit(
            halo, (badge_cx - halo_cx, badge_cy - halo_cy),
        )
        pygame.draw.circle(
            surface, _blend((10, 12, 18), cat_color, 0.4),
            (badge_cx, badge_cy), badge_r,
        )
        pygame.draw.circle(surface, cat_color, (badge_cx, badge_cy), badge_r, 2)
        self._draw_element_icon(
            surface, game.gaia.active.name,
            (badge_cx, badge_cy), badge_r - 3, cat_color,
        )
        x = badge_cx + badge_r + 8
        # Blend the catastrophe name 35 % toward white so it reads
        # consistently across every tint — Eau (60,140,230) raw on the
        # bar surface measured ≈5.6:1, just at WCAG AA for normal text.
        # Blending lifts it to a comfortable ≈8:1 while still reading
        # as the catastrophe identity colour (vs hard white which would
        # erase the tint cue).
        cat_name_color = _blend(cat_color, (255, 255, 255), 0.35)
        # Catastrophe name + tinted colour only change when the player
        # cycles the active catastrophe — cache by (name, colour) so the
        # render runs at most 5 times across the whole run instead of
        # once per frame.
        cat_name = self.cached_render(
            self.fonts.large, game.gaia.active.name.upper(), cat_name_color,
        )
        surface.blit(
            cat_name,
            (x, badge_cy - cat_name.get_height() // 2),
        )
        x += cat_name.get_width() + 12
        self._draw_top_divider(surface, x)

        # Speed buttons (just left of the balance bar). Hidden during the picker.
        if not game.awaiting_start:
            for speed, button_rect in speed_button_rects(self.config).items():
                self._draw_speed_button(
                    surface, button_rect, speed,
                    active=game.speed == speed,
                    accent=cat_color,
                )

        # Center: OBJECTIF bar. Shows the player's side-specific goal so the
        # win condition is always visible (educational + strategic anchor).
        # Bar bumped from 12 → 14 px so it has more visual presence inside
        # the cluster pill and the inset trough+gradient fill have room
        # to read as a channel rather than a thin strip.
        bar_w = 260
        bar_h = 14
        bar_x = (w - bar_w) // 2 + 60
        bar_y = TOP_BAR_H // 2 - bar_h // 2 + 6
        side = getattr(game, "player_side", "gaia")
        total_pop = sum(c.population for c in game.world.countries.values())
        total_dead = sum(c.dead for c in game.world.countries.values())
        equilibre = max(0.0, min(1.0, game.humans.global_progress))
        if side == "gaia":
            target = self.config.gameplay.defeat_mortality_ratio
            current = (total_dead / total_pop) if total_pop else 0.0
            progress = min(1.0, current / target) if target > 0 else 0.0
            # The HUD has cycled "MORTALITÉ" → "OBJECTIF · EFFONDREMENT"
            # → "DÉSÉQUILIBRE". Each step dropped one layer of cold
            # framing: the body-count KPI, then the imperative
            # "objective" wrapper. The label is now a pure *state name*
            # that pairs symmetrically with the Humanité side's
            # ÉQUILIBRE — same word root, opposite end-state of the
            # planet — and the bar fill already communicates the
            # progress, so the "OBJECTIF" preamble was redundant.
            obj_label = "DÉSÉQUILIBRE"
            # French typography: space before "%". This OBJECTIF
            # value is the most prominently displayed percentage in
            # the game — top bar, visible every frame of the
            # PLAYING phase. The previous "{x}% / {y}%" rendered as
            # "65%/65%" instead of the correct "65 % / 65 %".
            obj_value = f"{int(current * 100)} % / {int(target * 100)} %"
            # Player wants this to rise → tint red→amber→green is misleading;
            # use the catastrophe colour so it reads as the player's force.
            fill_color = cat_color
        else:
            target = self.config.gameplay.victory_threshold
            current = equilibre
            progress = min(1.0, current / target) if target > 0 else 0.0
            obj_label = "ÉQUILIBRE"
            obj_value = f"{int(current * 100)} % / {int(target * 100)} %"
            # Progress is "good" for humanity → green when close to target.
            fill_color = _progress_color(progress)
        # Backing cluster pill — the DÉSÉQUILIBRE/ÉQUILIBRE region was
        # the only bar-area cluster without a backing pill, so it
        # visually disconnected from the left identity cluster and the
        # right ?+audio+ÉVOLUTION cluster (both of which sit in their
        # own translucent pills). The pill anchors the bar + label +
        # value as one designed module instead of three floating bits
        # of chrome.
        center_pill_pad = 12
        center_pill = pygame.Rect(
            bar_x - center_pill_pad, cluster_y,
            bar_w + center_pill_pad * 2, cluster_h,
        )
        self._draw_cluster_pill(surface, center_pill)

        # Trough — inset channel treatment instead of a flat pill so the
        # bar reads as a groove the fill sits *in*, not a coloured strip
        # painted *on*. Three layers:
        #   1. Deep-shaded base fill (darker than the surrounding bar
        #      surface) so the trough looks recessed.
        #   2. Top-edge shadow stroke (1 px black at α 90) — sells the
        #      "inset" cue: light comes from above, so a recess casts a
        #      darker line on its top inner edge.
        #   3. Bottom-edge highlight stroke (1 px white at α 30) — the
        #      mirror cue: the inner bottom edge catches light.
        trough_color = _shade(self.palette.surface_overlay, 0.78)
        pygame.draw.rect(
            surface, trough_color,
            (bar_x, bar_y, bar_w, bar_h), border_radius=bar_h // 2,
        )
        # Inset edge strokes — drawn as 1 px arcs/lines on an SRCALPHA
        # layer so the rounded corners follow naturally.
        edge = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        pygame.draw.rect(
            edge, (0, 0, 0, 90),
            pygame.Rect(0, 0, bar_w, bar_h),
            1, border_radius=bar_h // 2,
        )
        # Bottom-edge highlight — paint a thin pill at the bottom and
        # mask against the trough corners so the highlight only shows
        # on the bottom inner edge, not the top.
        bot_hi = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        pygame.draw.line(
            bot_hi, (255, 255, 255, 30),
            (bar_h // 2, bar_h - 1),
            (bar_w - bar_h // 2, bar_h - 1),
        )
        edge.blit(bot_hi, (0, 0))
        surface.blit(edge, (bar_x, bar_y))
        fill_w = int(bar_w * progress)
        if fill_w > 0:
            # Fill — vertical gradient (top brighter, bottom darker) so
            # the coloured strip reads with shape rather than as a flat
            # painted swatch. Mask through a rounded-pill alpha so the
            # gradient respects the bar's radius and the right edge
            # cleanly trims at the leading edge.
            fill_layer = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
            top_c = _shade(fill_color, 1.18)
            bot_c = _shade(fill_color, 0.82)
            for py in range(bar_h):
                t = py / max(1, bar_h - 1)
                rr = int(top_c[0] * (1 - t) + bot_c[0] * t)
                gg = int(top_c[1] * (1 - t) + bot_c[1] * t)
                bb = int(top_c[2] * (1 - t) + bot_c[2] * t)
                pygame.draw.line(
                    fill_layer, (rr, gg, bb, 255),
                    (0, py), (fill_w, py),
                )
            # Mask to rounded corners (left side rounded, right side
            # square at the leading edge so it shows progress sharply).
            mask = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
            pygame.draw.rect(
                mask, (255, 255, 255, 255),
                pygame.Rect(0, 0, fill_w, bar_h),
                border_top_left_radius=bar_h // 2,
                border_bottom_left_radius=bar_h // 2,
                border_top_right_radius=(
                    bar_h // 2 if fill_w >= bar_w - 2 else 0
                ),
                border_bottom_right_radius=(
                    bar_h // 2 if fill_w >= bar_w - 2 else 0
                ),
            )
            fill_layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            # Subtle top-edge specular highlight on the fill — 1 px
            # near-white line at α 70 just below the top edge.
            pygame.draw.line(
                fill_layer, (255, 255, 255, 70),
                (bar_h // 2, 1),
                (max(bar_h // 2, fill_w - bar_h // 2), 1),
            )
            surface.blit(fill_layer, (bar_x, bar_y))
            # Leading-edge glow at the fill tip — soft halo + bright
            # 1 px line, so the bar reads as actively progressing
            # rather than a flat coloured stripe. Skipped when the bar
            # is full (fill_w >= bar_w) — no leading edge to highlight.
            if fill_w < bar_w:
                edge_x = bar_x + fill_w
                glow = pygame.Surface((20, bar_h + 10), pygame.SRCALPHA)
                for gr in range(10, 0, -1):
                    t = gr / 10
                    a = int(120 * (1 - t) ** 1.4)
                    if a < 1:
                        continue
                    pygame.draw.circle(
                        glow, (*fill_color, a),
                        (10, bar_h // 2 + 5), gr,
                    )
                surface.blit(glow, (edge_x - 10, bar_y - 5))
                # Crisp 1 px bright line at the exact leading edge.
                pygame.draw.line(
                    surface,
                    _blend(fill_color, (255, 255, 255), 0.45),
                    (edge_x, bar_y),
                    (edge_x, bar_y + bar_h),
                    1,
                )
        # Target tick — was a bright 2-px text-coloured stem cutting
        # vertically *through and outside* the bar plus a downward
        # chevron flag, both at full text-bright intensity. The stem
        # in particular read as a misplaced cursor: a hard bright
        # vertical slash through the coloured fill that competed with
        # the leading-edge glow for "where am I?" attention.
        #
        # Replaced by a *contained* target marker: a small upward-
        # pointing chevron below the bar at the goal position, in
        # ``text_label`` (dimmed white) rather than full text-bright,
        # so the target reads as a calm reference line instead of an
        # alert. The bar's own right edge already marks the goal
        # position visually; the chevron just gives the eye a tick
        # cue without painting a line through the fill.
        tick_x = bar_x + bar_w - 1
        flag_w = 4
        flag_h = 4
        flag_color = self.palette.text_label
        flag_pts = [
            (tick_x - flag_w, bar_y + bar_h + flag_h + 1),
            (tick_x + flag_w, bar_y + bar_h + flag_h + 1),
            (tick_x, bar_y + bar_h + 1),
        ]
        pygame.draw.polygon(surface, flag_color, flag_pts)

        # Label + value above the bar. Tightened spacing — value sits
        # 14 px above the bar (was 16) so the label-row + bar read as
        # one compact module inside the cluster pill rather than two
        # separated rows. Label sits flush-left, value flush-right.
        # obj_label is one of two literals ("DÉSÉQUILIBRE" / "ÉQUILIBRE")
        # depending on which side the player picked — bounded, cache hits.
        label = self.cached_render(self.fonts.label, obj_label, self.palette.text_label)
        surface.blit(label, (bar_x, bar_y - 14))
        pct = self.fonts.label.render(obj_value, True, self.palette.text)
        surface.blit(pct, (bar_x + bar_w - pct.get_width(), bar_y - 14))

        # Right meta cluster: pill behind ? + AUDIO + DNA-skill-tree button.
        help_rect = help_button_rect(self.config)
        audio_rect = audio_toggle_rect(self.config)
        dna_rect = evolution_dna_badge_rect(self.config)
        right_pill = pygame.Rect(
            help_rect.left - 10, cluster_y,
            (w - PAD) - (help_rect.left - 10), cluster_h,
        )
        self._draw_cluster_pill(surface, right_pill)

        self._draw_top_divider(surface, help_rect.left - 8)
        self._draw_help_button(surface, help_rect, active=game.help_open)
        self._draw_audio_toggle(surface, audio_rect, muted=game.audio_muted)
        self._draw_top_divider(surface, dna_rect.left - 6)
        self._draw_skill_tree_button(
            surface, dna_rect, active=game.evolution_open,
            accent=cat_color, catastrophe_name=game.gaia.active.name,
            energy=game.humans.evolution_points,
        )

    def _draw_top_divider(self, surface: pygame.Surface, x: int) -> None:
        """A thin vertical line that segments the top bar into widget groups.

        Was a flat 1-px line of ``ui_border_soft`` from y=12 to
        ``TOP_BAR_H-12`` — a hard top-and-bottom cut that read as
        a slash rather than a designed separator. Now the line is
        a 3-stop alpha gradient: faint at the ends, full opacity
        in the middle. The eye reads it as a soft beam between
        widget groups instead of a chopped hairline.

        Drawn 4× per frame on the top bar, so the cost stays in
        the budget — 28 px tall, 1 px wide = 28 line draws.
        """
        top_y = 12
        bot_y = TOP_BAR_H - 12
        height = bot_y - top_y
        if height < 6:
            return
        base = self.palette.ui_border_soft
        layer = pygame.Surface((1, height), pygame.SRCALPHA)
        for i in range(height):
            t = i / max(1, height - 1)
            # Smoothstep-ish profile: 0 at the ends, 1 in the middle.
            # Computed as sin²(π·t) which is exactly 0 at t=0 and
            # t=1 and 1 at t=0.5 — symmetric soft beam.
            envelope = math.sin(math.pi * t) ** 2
            alpha = int(220 * envelope)
            if alpha <= 0:
                continue
            layer.set_at((0, i), (*base, alpha))
        surface.blit(layer, (x, top_y))

    def _draw_cluster_pill(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        """Subtle background pill behind a top-bar cluster of widgets.

        Body + a soft 1 px top-edge highlight gives the pill a sense
        of elevation against the bar surface — was a flat translucent
        rect that looked like a smudge, now reads as a designed
        container resting on the bar.
        """
        pill = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            pill, (*self.palette.surface_deep[:3], 130),
            (0, 0, rect.width, rect.height),
            border_radius=rect.height // 2,
        )
        # Top-edge highlight — a thin curved arc along the upper half
        # of the pill in alpha-faded white. Standard Material elevation
        # cue without raising overall ink weight.
        highlight = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            highlight, (255, 255, 255, 24),
            (1, 1, rect.width - 2, max(1, rect.height // 2)),
            border_top_left_radius=rect.height // 2,
            border_top_right_radius=rect.height // 2,
        )
        pill.blit(highlight, (0, 0))
        # Hair-line bottom border so the pill has a defined lower edge.
        pygame.draw.line(
            pill, (255, 255, 255, 12),
            (rect.height // 2, rect.height - 1),
            (rect.width - rect.height // 2, rect.height - 1),
        )
        surface.blit(pill, rect.topleft)

    def _draw_help_button(
        self, surface: pygame.Surface, rect: pygame.Rect, active: bool
    ) -> None:
        hover = rect.collidepoint(pygame.mouse.get_pos())
        if active:
            # Was coral text on a neutral fill (≈5:1, borderline). Now
            # filled in a darkened accent with white text — matches the
            # speed-button / pill idiom and lifts contrast to ≈12:1.
            fill = _blend(self.palette.ui_accent, (0, 0, 0), 0.55)
            border = self.palette.ui_accent
            text_color = (255, 255, 255)
            if hover:
                # Hover-on-active lift. Without this, hovering an
                # active button gave zero affordance — the player
                # couldn't tell from visuals alone whether clicking
                # again would close the modal. 8 % white blend lifts
                # the fill enough to read as "armed" without losing
                # the active state's accent identity.
                fill = _blend(fill, (255, 255, 255), 0.08)
        elif hover:
            fill = self.palette.surface_elevated[:3]
            border = self.palette.ui_border
            text_color = self.palette.text
        else:
            fill = self.palette.surface_deep[:3]
            border = self.palette.ui_border_soft
            text_color = self.palette.text_label
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        # Gradient + edge strokes — shared button depth idiom so the
        # help / audio / speed buttons read as one set of tactile keys.
        self._apply_button_depth(surface, rect, fill, radius=6)
        pygame.draw.rect(surface, border, rect, 1, border_radius=6)
        if self.fonts.icons is not None:
            icon = self.fonts.icons.render(ICON_QUESTION, True, text_color)
            surface.blit(
                icon,
                (rect.centerx - icon.get_width() // 2,
                 rect.centery - icon.get_height() // 2),
            )
        else:
            text = self.fonts.label.render("?", True, text_color)
            surface.blit(
                text,
                (rect.centerx - text.get_width() // 2,
                 rect.centery - text.get_height() // 2),
            )

    def _draw_audio_toggle(
        self, surface: pygame.Surface, rect: pygame.Rect, muted: bool
    ) -> None:
        mouse_pos = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse_pos)
        if muted:
            # Same focus-state contrast fix as the help button: darkened
            # accent fill + white icon. Previously the muted state had a
            # coral-on-overlay text colour with ~5:1 contrast — borderline
            # WCAG AA. White on darkened accent measures ~12:1.
            fill = _blend(self.palette.ui_accent, (0, 0, 0), 0.55)
            border = self.palette.ui_accent
            text_color = (255, 255, 255)
            if hover:
                # Hover-on-muted lift — matches ``_draw_help_button``'s
                # active-hover treatment. Without this, hovering the
                # muted speaker showed zero affordance that clicking
                # would un-mute. 8 % white blend reads as "armed".
                fill = _blend(fill, (255, 255, 255), 0.08)
        else:
            fill = (
                self.palette.surface_elevated[:3]
                if hover else self.palette.surface_deep[:3]
            )
            border = self.palette.ui_border if hover else self.palette.ui_border_soft
            text_color = self.palette.text
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        # Gradient + edge strokes — shared button depth idiom.
        self._apply_button_depth(surface, rect, fill, radius=6)
        pygame.draw.rect(surface, border, rect, 1, border_radius=6)
        # Icon glyph if FontAwesome loaded; procedural speaker fallback
        # otherwise. The text fallback was just the word "AUDIO" / "MUET"
        # — readable but generic. A procedural speaker glyph reads as
        # an audio control whether or not the icon font ships.
        if self.fonts.icons is not None:
            glyph = ICON_VOLUME_OFF if muted else ICON_VOLUME_UP
            icon = self.fonts.icons.render(glyph, True, text_color)
            surface.blit(
                icon,
                (rect.centerx - icon.get_width() // 2,
                 rect.centery - icon.get_height() // 2),
            )
        else:
            self._draw_speaker_glyph(
                surface, rect.center, text_color, muted=muted,
            )

    def _draw_speaker_glyph(
        self,
        surface: pygame.Surface,
        center: tuple[int, int],
        color: tuple[int, int, int],
        *,
        muted: bool,
    ) -> None:
        """Procedural speaker icon — square body + cone + sound waves
        (or a × through it when muted). Drawn at a fixed ~14×12 px size."""
        cx, cy = center
        # Speaker body: small rectangle to the left + triangular cone.
        body = pygame.Rect(cx - 7, cy - 3, 4, 6)
        pygame.draw.rect(surface, color, body)
        cone = [
            (cx - 3, cy - 3),
            (cx + 1, cy - 6),
            (cx + 1, cy + 6),
            (cx - 3, cy + 3),
        ]
        pygame.draw.polygon(surface, color, cone)
        if muted:
            # Diagonal × overlay in the same colour.
            pygame.draw.line(
                surface, color, (cx + 2, cy - 5), (cx + 8, cy + 5), 2,
            )
            pygame.draw.line(
                surface, color, (cx + 2, cy + 5), (cx + 8, cy - 5), 2,
            )
        else:
            # Two sound-wave arcs radiating outward.
            for r, alpha_mult in ((4, 1.0), (7, 0.7)):
                arc_rect = pygame.Rect(cx + 1, cy - r, r * 2, r * 2)
                # pygame.draw.arc thickness is approximate; 2 px reads
                # at this size.
                pygame.draw.arc(
                    surface, color, arc_rect,
                    -math.pi / 3, math.pi / 3, 2,
                )

    def _draw_skill_tree_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        active: bool,
        accent: tuple[int, int, int],
        catastrophe_name: str,
        energy: int,
    ) -> None:
        """Top-bar pill that opens the skill tree.

        Layout: catastrophe element icon · "ÉVOLUTION" caption · energy count.
        Pulses softly when energy is unspent so it draws the player toward
        the next purchase.
        """
        mouse_pos = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse_pos)
        ticks = pygame.time.get_ticks()
        # Subtle pulse when unspent energy is sitting around.
        unspent_pulse = 0.5 + 0.5 * math.sin(ticks * 0.005) if energy > 0 else 0.0
        if active:
            fill = self.palette.surface_overlay[:3]
            border = accent
            border_w = 2
        else:
            fill = (
                self.palette.surface_elevated[:3]
                if hover else self.palette.surface_deep[:3]
            )
            border = _blend(self.palette.ui_border, accent, 0.35 + 0.4 * unspent_pulse)
            border_w = 1
        pygame.draw.rect(surface, fill, rect, border_radius=rect.height // 2)
        # Gradient + edge strokes — shares the button depth idiom with
        # the speed buttons, help, and audio toggle so the whole right
        # meta cluster reads as one consistent set of tactile chrome.
        self._apply_button_depth(
            surface, rect, fill, radius=rect.height // 2,
        )
        pygame.draw.rect(surface, border, rect, border_w, border_radius=rect.height // 2)

        # Element icon at the left side.
        icon_r = (rect.height // 2) - 4
        icon_cx = rect.left + 6 + icon_r
        icon_cy = rect.centery
        pygame.draw.circle(
            surface, _blend((10, 12, 18), accent, 0.4),
            (icon_cx, icon_cy), icon_r,
        )
        pygame.draw.circle(surface, accent, (icon_cx, icon_cy), icon_r, 2)
        self._draw_element_icon(
            surface, catastrophe_name, (icon_cx, icon_cy), icon_r - 3, accent,
        )

        # Caption + value on the right. Value reads as bright white (was
        # accent directly — on Eau/Feu that's ≈5-6:1 contrast on the dim
        # bar, soft for a number that updates every collection). The
        # catastrophe identity is already carried by the tinted icon
        # badge to the left, so the energy count can be neutral white
        # for maximum legibility on every run.
        cap_x = icon_cx + icon_r + 8
        caption = self.fonts.label.render(
            "ÉVOLUTION", True, self.palette.text_label,
        )
        value = self.fonts.mono.render(
            str(energy), True, self.palette.text,
        )
        surface.blit(
            caption,
            (cap_x, rect.centery - caption.get_height()),
        )
        surface.blit(
            value,
            (cap_x, rect.centery),
        )

    def _draw_pill(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        *,
        active: bool,
        tint: tuple[int, int, int],
        hover: bool,
    ) -> None:
        """Material-style indicator pill: tinted fill when active, dim otherwise.

        The shared button depth idiom layers gradient + top-highlight +
        bottom-shadow on every state so the pill reads as a tactile
        key — picker axis tabs and skill-tree axis tabs both flow
        through this helper.
        """
        radius = rect.height // 2
        if active:
            # Tinted fill darkened toward black so white text reads cleanly on
            # *any* catastrophe tint — Air (175,205,225) and Vie (120,220,130)
            # are too light to carry white text raw, so we always darken first.
            active_fill = _blend(tint, (0, 0, 0), 0.45)
            if hover:
                # Hover-on-active lift — matches the same treatment
                # already shipped on ``_draw_speed_button`` /
                # ``_draw_help_button`` / ``_draw_audio_toggle`` so
                # every "active button" surface speaks one hover
                # language. Without this, hovering an already-active
                # picker axis tab gave zero affordance that re-clicking
                # would do anything. 8 % white blend reads as "armed"
                # without losing the catastrophe-tint identity.
                active_fill = _blend(active_fill, (255, 255, 255), 0.08)
            pygame.draw.rect(surface, active_fill, rect, border_radius=radius)
            self._apply_button_depth(surface, rect, active_fill, radius=radius)
            # Crisp tint outline at full saturation so the active state still
            # reads as "this is the catastrophe's tab" while staying readable.
            pygame.draw.rect(surface, tint, rect, 1, border_radius=radius)
            text_color = (255, 255, 255)
        elif hover:
            hover_fill = self.palette.surface_elevated[:3]
            pygame.draw.rect(
                surface, hover_fill, rect, border_radius=radius,
            )
            self._apply_button_depth(surface, rect, hover_fill, radius=radius)
            pygame.draw.rect(
                surface, _blend(self.palette.surface_deep, tint, 0.5),
                rect, 1, border_radius=radius,
            )
            text_color = self.palette.text
        else:
            idle_fill = self.palette.surface_deep[:3]
            pygame.draw.rect(
                surface, idle_fill, rect, border_radius=radius,
            )
            self._apply_button_depth(surface, rect, idle_fill, radius=radius)
            # Brighter inactive text — was text_dim which read as washed out.
            text_color = self.palette.text_label
        text = self.fonts.label.render(label, True, text_color)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2,
             rect.centery - text.get_height() // 2),
        )

    def _draw_arrow_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        glyph: str,
        mouse_pos: tuple[int, int],
    ) -> None:
        hover = rect.collidepoint(mouse_pos)
        fill = (
            self.palette.surface_overlay[:3]
            if hover
            else self.palette.surface_elevated[:3]
        )
        pygame.draw.rect(surface, fill, rect, border_radius=rect.height // 2)
        # Gradient + edge strokes — shared chrome depth idiom so the
        # arrow buttons read as tactile keys rather than flat pills.
        self._apply_button_depth(
            surface, rect, fill, radius=rect.height // 2,
        )
        text = self.fonts.medium.render(
            glyph, True,
            self.palette.text if hover else self.palette.text_dim,
        )
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2,
             rect.centery - text.get_height() // 2),
        )

    def _apply_button_depth(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        base_fill: tuple[int, int, int],
        radius: int = 6,
    ) -> None:
        """Layer a vertical gradient + top/bottom edge strokes onto a button.

        Caller paints the base solid fill first (so the rounded-corner
        shape is established), then calls this helper to add depth,
        then paints the border on top. Same screen-surface idiom
        shipped on speed buttons / outro tiles / side cards, factored
        out so help-button, audio-toggle, and any future top-bar
        chrome share one visual language.
        """
        grad = pygame.Surface(rect.size, pygame.SRCALPHA)
        top_c = _shade(base_fill, 1.14)
        bot_c = _shade(base_fill, 0.88)
        for py in range(rect.height):
            t = py / max(1, rect.height - 1)
            rr = int(top_c[0] * (1 - t) + bot_c[0] * t)
            gg = int(top_c[1] * (1 - t) + bot_c[1] * t)
            bb = int(top_c[2] * (1 - t) + bot_c[2] * t)
            pygame.draw.line(grad, (rr, gg, bb, 255), (0, py), (rect.width, py))
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            mask, (255, 255, 255, 255),
            pygame.Rect(0, 0, rect.width, rect.height),
            border_radius=radius,
        )
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(grad, rect.topleft)
        # Edge strokes — asymmetric alphas (highlight 30 / shadow 70)
        # compensate for perception's logarithmic lightness response.
        edges = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.line(
            edges, (255, 255, 255, 30),
            (2, 1), (rect.width - 3, 1),
        )
        pygame.draw.line(
            edges, (0, 0, 0, 70),
            (2, rect.height - 2), (rect.width - 3, rect.height - 2),
        )
        surface.blit(edges, rect.topleft)

    def _draw_speed_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        speed: int,
        active: bool,
        accent: tuple[int, int, int] | None = None,
    ) -> None:
        """Speed selector button — gradient body + edge strokes via
        ``_apply_button_depth``. Active state keeps the cat-tint sheen
        patch so the "selected speed" cue still reads at a glance."""
        accent = accent or self.palette.ui_accent
        hover = rect.collidepoint(pygame.mouse.get_pos())
        if active:
            base_fill = _blend(accent, (0, 0, 0), 0.55)
            border = accent
            text_color = (255, 255, 255)
            if hover:
                # Hover-on-active lift — matches the same treatment on
                # ``_draw_help_button`` / ``_draw_audio_toggle`` so the
                # three top-bar button kinds share a hover language.
                # The sheen patch overlay below is independent of
                # hover, so without this the active speed button gave
                # no hover affordance — players couldn't tell that
                # re-clicking would (eg) pause from speed-1.
                base_fill = _blend(base_fill, (255, 255, 255), 0.08)
        elif hover:
            base_fill = self.palette.surface_elevated[:3]
            border = self.palette.ui_border
            text_color = self.palette.text
        else:
            base_fill = self.palette.surface_deep[:3]
            border = self.palette.ui_border_soft
            text_color = self.palette.text_label
        pygame.draw.rect(surface, base_fill, rect, border_radius=6)
        self._apply_button_depth(surface, rect, base_fill, radius=6)
        pygame.draw.rect(surface, border, rect, 2 if active else 1, border_radius=6)
        # Active speed keeps the cat-tint sheen patch on top of the
        # gradient so the "selected" affordance pops without losing
        # the new depth treatment underneath.
        if active:
            sheen = pygame.Surface(
                (rect.width - 4, max(2, rect.height // 3)), pygame.SRCALPHA
            )
            sheen.fill((*accent, 70))
            surface.blit(sheen, (rect.left + 2, rect.top + 2))
        label = SPEED_BUTTON_LABELS.get(speed, "?")
        text = self.fonts.label.render(label, True, text_color)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2),
        )

    def _build_minimap_surface(
        self, game: Game, size: tuple[int, int],
    ) -> pygame.Surface:
        """Pre-render the minimap base layer (background + country polygons).

        Equirectangular projection over -180..180 lon × -90..90 lat. Drawn at
        target resolution (240×120-ish) onto a fresh Surface so the cached
        result blits cheaply in subsequent frames.
        """
        w, h = size
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(
            out, self.palette.surface_deep[:3], (0, 0, w, h), border_radius=6,
        )

        # Equator + prime meridian guide lines, drawn *under* the
        # polygons so countries paint over them seamlessly. Helps the
        # player orient large-scale geography at a glance: "the country
        # I'm looking at sits south of the equator and west of the
        # prime meridian", without having to remember projection
        # boundaries. Very low contrast (≈ 35 alpha) so they read as
        # faint reference lines rather than a busy grid.
        grid_layer = pygame.Surface((w, h), pygame.SRCALPHA)
        eq_y = h // 2
        pm_x = w // 2
        pygame.draw.line(
            grid_layer, (200, 220, 245, 35),
            (2, eq_y), (w - 2, eq_y), 1,
        )
        pygame.draw.line(
            grid_layer, (200, 220, 245, 35),
            (pm_x, 2), (pm_x, h - 2), 1,
        )
        out.blit(grid_layer, (0, 0))

        sx_factor = w / 360.0
        sy_factor = h / 180.0
        for country in game.world.countries.values():
            color = _country_color(country, self.palette)
            for polygon in country.polygons:
                if len(polygon) < 3:
                    continue
                pts = [
                    (
                        int((p[0] + 180.0) * sx_factor),
                        int((90.0 - p[1]) * sy_factor),
                    )
                    for p in polygon
                ]
                if all(p == pts[0] for p in pts):
                    continue
                pygame.draw.polygon(out, color, pts)
        return out

    def _draw_minimap(self, surface: pygame.Surface, game: Game) -> None:
        """Cached mini world map + live viewport rect.

        The country polygons are rendered into a surface cached on the renderer
        and only refreshed every ``_minimap_refresh_interval_ms`` ms (so state
        changes track without re-drawing 239 polygons every frame).
        """
        mm = minimap_rect(self.config)
        cat_color = game.gaia.active.arc_color
        ticks = pygame.time.get_ticks()
        # Refresh the cache lazily.
        if (
            self._minimap_cache is None
            or ticks - self._minimap_last_refresh > self._minimap_refresh_interval_ms
        ):
            self._minimap_cache = self._build_minimap_surface(game, mm.size)
            self._minimap_last_refresh = ticks
        surface.blit(self._minimap_cache, mm.topleft)

        # Catastrophe-tinted border — previously a static
        # ``ui_border_soft`` (dim grey) that read as a flat box. Tinting
        # the border with a darkened cat_color joins the minimap to the
        # catastrophe identity carried by the rest of the chrome (the
        # right-panel left edge stripe, the news-ticker rail, the top-bar
        # cluster pill). Blended 55 % with the surface tone so it stays
        # subtle — accent, not focal element.
        border_color = _blend(self.palette.surface[:3], cat_color, 0.55)
        pygame.draw.rect(
            surface, border_color, mm, 1, border_radius=6,
        )

        # Corner accent brackets — small L-shaped strokes at the four
        # corners in the catastrophe colour. Reads as "instrument
        # framing" rather than a plain bordered rect, and gives the
        # minimap the same quiet-HUD feel as the top-bar cluster pills.
        # Inset by 3 px so the corner stays *inside* the rounded
        # border instead of overlapping it; arm length 8 px keeps the
        # bracket readable without dominating the panel.
        bracket_arm = 8
        bracket_inset = 3
        for corner_x, corner_y, dx, dy in (
            (mm.left + bracket_inset, mm.top + bracket_inset, 1, 1),
            (mm.right - bracket_inset - 1, mm.top + bracket_inset, -1, 1),
            (mm.left + bracket_inset, mm.bottom - bracket_inset - 1, 1, -1),
            (mm.right - bracket_inset - 1, mm.bottom - bracket_inset - 1, -1, -1),
        ):
            pygame.draw.line(
                surface, cat_color,
                (corner_x, corner_y),
                (corner_x + dx * bracket_arm, corner_y),
                2,
            )
            pygame.draw.line(
                surface, cat_color,
                (corner_x, corner_y),
                (corner_x, corner_y + dy * bracket_arm),
                2,
            )

        sx_factor = mm.width / 360.0
        sy_factor = mm.height / 180.0
        # Viewport rect — derived from world.scale + offset.
        # The visible world span = map_rect.width / scale (in world units).
        # Minimap is 360 lon × 180 lat across mm.width × mm.height pixels.
        map_w = self.map_rect.width
        map_h = self.map_rect.height
        # World coords visible in current viewport (compute from map corners).
        top_left = game.world.inverse_transform(
            (self.map_rect.left, self.map_rect.top), self.screen_size,
        )
        bot_right = game.world.inverse_transform(
            (self.map_rect.right, self.map_rect.bottom), self.screen_size,
        )
        # Map those world coords into minimap pixels (clamped).
        lx, ty = top_left
        rx, by = bot_right
        # Note: world Y is flipped vs latitude direction.
        view_left = mm.left + int((lx + 180.0) * sx_factor)
        view_right = mm.left + int((rx + 180.0) * sx_factor)
        view_top = mm.top + int((90.0 - ty) * sy_factor)
        view_bot = mm.top + int((90.0 - by) * sy_factor)
        view = pygame.Rect(
            min(view_left, view_right),
            min(view_top, view_bot),
            abs(view_right - view_left),
            abs(view_bot - view_top),
        )
        # Clamp to minimap.
        view.left = max(view.left, mm.left)
        view.top = max(view.top, mm.top)
        view.width = min(view.width, mm.right - view.left)
        view.height = min(view.height, mm.bottom - view.top)
        if view.width > 1 and view.height > 1:
            # Two-tone outline so the viewport rect reads against both
            # light continents (Sahara, Antarctica) AND dark ocean: a
            # dark halo one pixel out, then the bright stroke on top.
            # The previous single bright 1 px stroke was effectively
            # invisible over pale-tinted regions.
            halo = view.inflate(2, 2)
            pygame.draw.rect(
                surface, (12, 18, 28), halo, 1, border_radius=3,
            )
            pygame.draw.rect(
                surface, (245, 250, 255), view, 1, border_radius=2,
            )

    def _draw_right_panel(self, surface: pygame.Surface, game: Game) -> None:
        w, h = self.screen_size
        rect = pygame.Rect(w - RIGHT_PANEL_W, TOP_BAR_H, RIGHT_PANEL_W, h - TOP_BAR_H - NEWS_BAR_H)
        self._fill_panel(surface, rect, self.palette.surface)
        cat_color = game.gaia.active.arc_color
        # Catastrophe-tinted left edge stripe gives the run visual identity.
        pygame.draw.line(
            surface, cat_color, (rect.left, rect.top), (rect.left, rect.bottom), 2
        )

        # Mini-globe at the very top of the panel — situational awareness.
        self._draw_minimap(surface, game)
        mm = minimap_rect(self.config)

        x = rect.left + PAD
        y = mm.bottom + 12
        chart_w = RIGHT_PANEL_W - PAD * 2

        # ---- World hero stats ----
        # "BILAN MONDIAL" reads cleaner than the old "MONITEUR MONDIAL" and
        # matches the language used elsewhere ("foyer", "bascule"). Labels are
        # neutral so they fit fire / quake / wind catastrophes too, not just
        # disease vocabulary.
        y = self._draw_section_header(surface, "BILAN MONDIAL", x, y, accent=cat_color)
        total_pop = sum(c.population for c in game.world.countries.values())
        affected = sum(c.affected for c in game.world.countries.values())
        dead = sum(c.dead for c in game.world.countries.values())
        critical = sum(1 for c in game.world.countries.values() if c.state >= 0.5)
        affected_pct = (affected / total_pop * 100) if total_pop else 0.0
        dead_pct = (dead / total_pop * 100) if total_pop else 0.0
        balance = max(0.0, min(1.0, game.humans.global_progress))

        # Smart percentage: show 1-2 decimals when value is non-zero
        # but would round to 0 %, so the player sees "0,3 %" instead
        # of "0 %" next to a large absolute count like "22,91 M".
        # Anchor word changed from "pop. mondiale" (debug-flavoured
        # abbreviation) to "de l'humanité" — doc-voice register and
        # semantically accurate (the values are population fractions,
        # not territory). French typography: comma for decimals and
        # a non-breaking-friendly space before %.
        def _pct(value: float, raw_count: int) -> str:
            if raw_count == 0:
                return "0 % de l'humanité"
            if value < 1.0:
                return f"{value:.2f} % de l'humanité".replace(".", ",")
            if value < 10.0:
                return f"{value:.1f} % de l'humanité".replace(".", ",")
            return f"{value:.0f} % de l'humanité"

        y = self._draw_hero_stat(
            surface, x, y,
            value=_fmt_big(affected),
            label="TOUCHÉS",
            sub=_pct(affected_pct, affected),
            value_color=self.palette.affected,
        )
        y += GAP_SM
        y = self._draw_hero_stat(
            surface, x, y,
            value=_fmt_big(dead),
            label="DÉCÈS",
            sub=_pct(dead_pct, dead),
            value_color=self.palette.severe,
        )
        y += GAP_SM
        y = self._draw_hero_stat(
            surface, x, y,
            # French typography: space before "%". Visible every
            # frame as the hero number in the right panel.
            value=f"{int(balance * 100)} %",
            label="ÉQUILIBRE PLANÉTAIRE",
            sub=f"Jour {game.turn}",
            value_color=_progress_color(balance),
        )
        y += GAP

        # Compact secondary line: critiques + intensity (catastrophe info
        # collapsed into this row because the top-bar EVOLUTION pill already
        # surfaces the catastrophe identity + energy).
        cat = game.gaia.active
        diff_color = _difficulty_color(game.difficulty, self.palette)
        y = self._draw_two_col_row(
            surface,
            x, y, chart_w,
            (("CRITIQUES", str(critical), self.palette.text),
             ("INTENSITÉ", f"x{cat.intensity:.2f}", cat_color)),
        )
        y += GAP_SM
        y = self._draw_two_col_row(
            surface,
            x, y, chart_w,
            (("FOYERS", str(len(cat.active_points)), self.palette.text),
             ("DIFFICULTÉ", game.difficulty.label, diff_color)),
        )
        y += GAP_LG

        # FOYERS CRITIQUES leaderboard — flows naturally below ÉVOLUTIONS.
        # Auto-fit row count based on remaining vertical space. Skip the whole
        # section if there isn't enough room for the header + one row (the
        # player has the main map for critical-country awareness).
        ROW_H = 28
        ROW_GAP = 4
        section_header_h = self.fonts.label.get_height() + GAP
        if rect.bottom - PAD - y < section_header_h + ROW_H:
            game.leaderboard_rects = []
            return
        section_y = self._draw_section_header(
            surface, "FOYERS CRITIQUES", x, y, accent=cat_color
        )
        avail_h = max(0, rect.bottom - PAD - section_y)
        rows_n = max(1, min(3, (avail_h + ROW_GAP) // (ROW_H + ROW_GAP)))
        top_countries = sorted(
            (c for c in game.world.countries.values() if c.state > 0),
            key=lambda c: -c.state,
        )[:rows_n]
        # Reset and re-publish the leaderboard hit-test rects each frame.
        game.leaderboard_rects = []
        if not top_countries:
            # Single full-width empty-state card explaining the leaderboard.
            # Was a flat ``surface_deep`` rounded rect — a smudge of dim
            # colour with centred text. Now gets the chrome that the
            # leaderboard rows would carry, so the "waiting" state reads
            # as *the same slot* the rows will fill, not a generic blank:
            #   * Vertical gradient body + top-edge highlight + bottom-
            #     edge shadow via the shared button depth helper.
            #   * Faint catastrophe-tinted left-edge stripe at the same
            #     position the leaderboard row severity bar would
            #     occupy — visual continuity between "before data" and
            #     "with data".
            #   * Subtle pulse on the stripe alpha so the card reads as
            #     *attentive* rather than dormant.
            empty_h = rows_n * ROW_H + (rows_n - 1) * ROW_GAP
            empty_rect = pygame.Rect(x, section_y, chart_w, empty_h)
            base_fill = self.palette.surface_deep[:3]
            pygame.draw.rect(
                surface, base_fill, empty_rect, border_radius=4,
            )
            self._apply_button_depth(surface, empty_rect, base_fill, radius=4)
            # Catastrophe-tinted left stripe + soft pulse so the card
            # reads as actively scanning rather than empty chrome.
            pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.003)
            stripe_alpha = int(70 + 50 * pulse)
            stripe = pygame.Surface(
                (4, empty_rect.height - 4), pygame.SRCALPHA,
            )
            stripe.fill((*cat_color, stripe_alpha))
            surface.blit(stripe, (empty_rect.left, empty_rect.top + 2))
            # Hairline border on the empty card to keep its edges
            # defined against the sidebar gradient.
            pygame.draw.rect(
                surface, self.palette.ui_border_soft,
                empty_rect, 1, border_radius=4,
            )
            empty_label = self.fonts.label.render(
                "AUCUN FOYER CRITIQUE", True, self.palette.text_label,
            )
            empty_hint = self.fonts.small.render(
                # Was "Aucun pays au-dessus du seuil critique." — read
                # as a redundant restatement of the empty-state label
                # right above ("AUCUN FOYER CRITIQUE"). Replaced with
                # the explicit numeric threshold so the empty state
                # *teaches* what "critique" means instead of just
                # echoing the absence.
                "Seuil critique : 50 % de basculement.", True, self.palette.text_dim,
            )
            content_h = empty_label.get_height() + 2 + empty_hint.get_height()
            content_top = empty_rect.centery - content_h // 2
            surface.blit(
                empty_label,
                (empty_rect.centerx - empty_label.get_width() // 2, content_top),
            )
            surface.blit(
                empty_hint,
                (empty_rect.centerx - empty_hint.get_width() // 2,
                 content_top + empty_label.get_height() + 2),
            )
        else:
            for i in range(rows_n):
                row_y = section_y + i * (ROW_H + ROW_GAP)
                row_rect = pygame.Rect(x, row_y, chart_w, ROW_H)
                if i < len(top_countries):
                    country = top_countries[i]
                    self._draw_leaderboard_row(surface, row_rect, country, game)
                    game.leaderboard_rects.append((country.id, row_rect))
                else:
                    pygame.draw.rect(
                        surface, self.palette.surface_deep[:3], row_rect,
                        border_radius=4,
                    )
                    placeholder = self.fonts.small.render(
                        "—", True, self.palette.text_dim,
                    )
                    surface.blit(
                        placeholder,
                        (row_rect.centerx - placeholder.get_width() // 2,
                         row_rect.centery - placeholder.get_height() // 2),
                    )

    def _draw_section_header(
        self,
        surface: pygame.Surface,
        title: str,
        x: int,
        y: int,
        accent: tuple[int, int, int] | None = None,
    ) -> int:
        """Modern section header: shaded accent bar + uppercase label + fade rule.

        Was a flat 3-px vertical bar + title text. Used 3+ times per
        sidebar render, on every frame. Now reads as a deliberate
        section marker:

          * **Two-tone accent bar** — top half in the full accent
            tint, bottom half darkened 35 % toward black. Same trick
            shipped on the hero-stat 4-px bar so a thin vertical
            element still reads with weight.
          * **Fading horizontal rule** to the right of the title —
            short cat-tinted line with a quadratic falloff, anchoring
            the title row to a horizontal axis. Provides the structure
            of "label + rule" without the heavy "underline beneath"
            pattern the previous design rejected.
        """
        accent_color = accent or self.palette.ui_accent
        text_color = self.palette.text  # title text uses neutral white now
        # ``title`` is always a literal section name from the caller
        # (BILAN MONDIAL, FOYERS CRITIQUES, etc.) — the bounded set caches
        # cleanly and the call site fires 3-5× per frame.
        text = self.cached_render(self.fonts.label, title, text_color)
        bar_h = text.get_height()
        bar_w = 3
        # Two-tone vertical accent bar — top half full tint, bottom
        # half darkened toward black so the thin slab carries weight.
        top_half = pygame.Rect(x, y + 1, bar_w, max(1, (bar_h - 2) // 2))
        bot_half = pygame.Rect(
            x, top_half.bottom,
            bar_w, bar_h - 2 - top_half.height,
        )
        pygame.draw.rect(surface, accent_color, top_half)
        pygame.draw.rect(
            surface,
            _blend(accent_color, (0, 0, 0), 0.35),
            bot_half,
        )
        # Title text indented past the bar.
        title_x = x + bar_w + 8
        surface.blit(text, (title_x, y))
        # Horizontal accent rule fading right of the title — quadratic
        # falloff, peak at 130 α near the title, 0 α 80 px out. Sits
        # at the title's vertical baseline so it reads as an extension
        # of the underline rather than a separate decoration.
        rule_x = title_x + text.get_width() + 8
        rule_w = 80
        rule_y = y + bar_h - 3
        rule = pygame.Surface((rule_w, 1), pygame.SRCALPHA)
        for px in range(rule_w):
            t = px / max(1, rule_w - 1)
            a = int(130 * (1.0 - t) ** 2)
            if a <= 0:
                continue
            rule.set_at((px, 0), (*accent_color, a))
        surface.blit(rule, (rule_x, rule_y))
        return y + bar_h + GAP

    def _draw_leaderboard_row(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        country: Country,
        game: Game,
    ) -> None:
        """Leaderboard row with hover-lift + chevron affordance.

        The chevron + lift signals "click to focus" without needing a tooltip;
        animation slides up 2px on hover, the bg shifts to the elevated tone,
        and a `›` glyph appears at the right edge — all standard Material
        affordance hints for clickable list rows.
        """
        hover = rect.collidepoint(pygame.mouse.get_pos())
        is_selected = country.id == game.world.selected_country

        # Hover lift — render the row 2px higher so it visibly pops.
        draw_rect = rect.copy()
        if hover and not is_selected:
            draw_rect.y -= 2

        if is_selected:
            bg = self.palette.surface_overlay[:3]
        elif hover:
            bg = self.palette.surface_elevated[:3]
        else:
            bg = self.palette.surface_deep[:3]
        # Soft shadow under the lifted row for the elevation cue.
        # Was a flat ``(0, 0, 0)`` rect offset 2 px down — same hard-
        # edged-sliver pattern fixed on skill cards earlier this
        # session. Switch to the cached Pillow shadow so the hover
        # cue grades smoothly into the bg instead of cutting at a
        # cliff. Light elevation (blur=6, alpha=100) — rows are list
        # elements, not hero modals.
        if hover and not is_selected:
            self._draw_shadow(
                surface, draw_rect, blur=6, alpha=100, offset_y=2,
            )
        pygame.draw.rect(surface, bg, draw_rect, border_radius=4)

        bar_color = _country_color(country, self.palette)
        # Severity bar on the left edge — widens on the selected row so
        # "this country is in the info panel" reads at a glance even
        # in a column of 8 visually similar rows. The bg-shade-only cue
        # the row had before disappeared on darker catastrophe panels.
        bar_w = 6 if is_selected else 4
        pygame.draw.rect(
            surface, bar_color,
            (draw_rect.left, draw_rect.top + 2, bar_w, draw_rect.height - 4),
        )
        # Selected row also gets a 1 px accent outline so the focus
        # state survives even when the country happens to be SAIN (low
        # bar luminance) — colour-only cues fail in that case.
        if is_selected:
            pygame.draw.rect(
                surface, self.palette.selected_outline,
                draw_rect, 1, border_radius=4,
            )

        # Country name (clipped if too long; reserve room for chevron + state).
        name_str = self._fit_text(country.name, self.fonts.small, draw_rect.width - 84)
        name_text = self.fonts.small.render(name_str, True, self.palette.text)
        surface.blit(
            name_text,
            (draw_rect.left + bar_w + 8, draw_rect.top + 4),
        )

        # Per-day rate as small dim caption underneath name. "stable"
        # was misleading for a country sitting at 80 % state — it isn't
        # stable, it's just not deteriorating *today*. Show signed
        # motion when there is any, "—" when there isn't.
        rate = country.infection_rate()
        if rate > 0.0005:  # > 0.05 %/jour — meaningful upward motion
            rate_str = f"+{rate * 100:.1f} %/jour"
            rate_color = self.palette.severe
        elif rate < -0.0005:
            rate_str = f"{rate * 100:.1f} %/jour"
            rate_color = (110, 200, 130)
        elif country.state >= 0.5:
            # Critical country with no motion this turn — say so plainly.
            rate_str = "figé en zone critique"
            rate_color = self.palette.text_dim
        else:
            rate_str = "—"
            rate_color = self.palette.text_dim
        rate_text = self.fonts.label.render(rate_str, True, rate_color)
        surface.blit(
            rate_text,
            (draw_rect.left + bar_w + 8, draw_rect.top + 4 + name_text.get_height()),
        )

        # State percentage right-aligned. French typo: space before %.
        state_text = self.fonts.mono.render(
            f"{int(country.state * 100)} %", True, bar_color
        )
        state_x = draw_rect.right - state_text.get_width() - 18
        surface.blit(
            state_text,
            (state_x, draw_rect.centery - state_text.get_height() // 2),
        )

        # Chevron — clickable affordance, brighter on hover.
        chevron_color = (
            self.palette.text if hover else self.palette.text_dim
        )
        chevron = self.fonts.medium.render("›", True, chevron_color)
        surface.blit(
            chevron,
            (draw_rect.right - chevron.get_width() - 6,
             draw_rect.centery - chevron.get_height() // 2),
        )

    def _draw_two_col_row(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        width: int,
        cols: tuple[tuple[str, str, tuple[int, int, int]], ...],
    ) -> int:
        """Render label/value pairs in a stacked column (label above value).

        Was flat text-only — two label/value pairs floating against the
        sidebar bg with no chrome to group either cell. Now each cell
        sits in a subtle backing card (rounded rect, surface_deep at
        low alpha) with a value-coloured accent dot above the value
        and a 1-px hairline divider between the two columns. The
        backing pulls the row out of the wall-of-text and the dot ties
        each value visually to its semantic colour.
        """
        if not cols:
            return y
        col_w = width // max(1, len(cols))
        rendered: list[tuple[pygame.Surface, pygame.Surface, tuple[int, int, int]]] = []
        for label, value, color in cols:
            label_t = self.fonts.label.render(label, True, self.palette.text_label)
            value_t = self.fonts.mono.render(value, True, color)
            rendered.append((label_t, value_t, color))
        label_h = max(label_t.get_height() for label_t, _, _ in rendered)
        value_h = max(value_t.get_height() for _, value_t, _ in rendered)
        row_h = label_h + value_h + 2
        # Backing card spans the full row with a couple of pixels of
        # bleed top/bottom so the label sits inside it cleanly.
        card_pad_y = 6
        card_rect = pygame.Rect(x, y - 2, width, row_h + card_pad_y)
        card = pygame.Surface(card_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            card, (*self.palette.surface_deep[:3], 110),
            (0, 0, card_rect.width, card_rect.height),
            border_radius=6,
        )
        # Top-edge highlight stroke for subtle elevation against the
        # gradient sidebar bg.
        pygame.draw.line(
            card, (255, 255, 255, 18),
            (8, 0), (card_rect.width - 8, 0),
        )
        surface.blit(card, card_rect.topleft)
        # 1-px hairline divider between columns — sits between cells,
        # vertically centred inside the card with small top/bottom
        # padding so it reads as a separator, not a column edge.
        if len(cols) > 1:
            for i in range(1, len(cols)):
                div_x = x + i * col_w
                div_top = card_rect.top + 4
                div_bot = card_rect.bottom - 4
                div = pygame.Surface(
                    (1, div_bot - div_top), pygame.SRCALPHA,
                )
                # Vertical alpha envelope: 0 at the ends, peak in the
                # middle — same triangular fade idiom shipped on the
                # picker title accent so the divider tapers naturally
                # rather than cutting at hard top/bottom edges.
                for py in range(div_bot - div_top):
                    t = 1.0 - abs(py - (div_bot - div_top) / 2) / max(
                        1, (div_bot - div_top) / 2
                    )
                    a = int(70 * t ** 1.2)
                    if a <= 0:
                        continue
                    div.set_at((0, py), (255, 255, 255, a))
                surface.blit(div, (div_x, div_top))
        for i, (label_t, value_t, color) in enumerate(rendered):
            cx = x + i * col_w
            cw = col_w
            label_x = cx + (cw - label_t.get_width()) // 2
            value_x = cx + (cw - value_t.get_width()) // 2
            surface.blit(label_t, (label_x, y))
            surface.blit(value_t, (value_x, y + label_h + 2))
            # Tiny value-coloured accent dot to the left of the value —
            # ties the digits to their semantic colour even on the
            # darker catastrophes where the value text doesn't pop as
            # hard against the card backing.
            dot_x = value_x - 8
            dot_y = y + label_h + 2 + value_t.get_height() // 2
            pygame.draw.circle(surface, color, (dot_x, dot_y), 2)
        return y + row_h + card_pad_y + 2

    def _draw_hero_stat(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        value: str,
        label: str,
        sub: str,
        value_color: tuple[int, int, int],
    ) -> int:
        """Big number on top, '<LABEL> · <sub>' caption below.

        Drawn 3× per right-panel render (TOUCHÉS / DÉCÈS / ÉQUILIBRE
        PLANÉTAIRE). Was just hero font + caption with no visual link
        between the value and its colour — the eye had to pick out
        which-value-is-which-thing from the digits alone. Adds:

          * A **4-px-wide colour-coded accent bar** to the left of the
            value text, in ``value_color``. Visually pins each stat
            block to its semantic colour (severe-red for DÉCÈS,
            amber for TOUCHÉS, success-green for ÉQUILIBRE) so the
            three rows scan apart at a glance.
          * A **faint colour-tinted underline** below the value
            digits — barely-visible 1-px line at ~30 % alpha of the
            value colour. Anchors the value as a *measured quantity*
            rather than free-floating text.
        """
        # 4-px accent bar on the left, height matched to the value
        # text's actual rendered size. Sits 6 px to the left of the
        # value text so it doesn't push the layout.
        value_text = self.fonts.hero.render(value, True, value_color)
        bar_h = value_text.get_height()
        bar_rect = pygame.Rect(x - 8, y + 2, 3, max(8, bar_h - 4))
        # Two-tone bar: solid colour with a slightly darker bottom
        # half so it has a sense of weight rather than a flat slab.
        pygame.draw.rect(surface, value_color, bar_rect)
        pygame.draw.rect(
            surface, _blend(value_color, (0, 0, 0), 0.35),
            (bar_rect.left, bar_rect.centery, bar_rect.width,
             bar_rect.height - (bar_rect.centery - bar_rect.top)),
        )

        surface.blit(value_text, (x, y))

        # Tinted underline under the value digits.
        underline_y = y + value_text.get_height() - 3
        underline = pygame.Surface(
            (value_text.get_width(), 1), pygame.SRCALPHA,
        )
        underline.fill((*value_color, 90))
        surface.blit(underline, (x, underline_y))

        caption = self.fonts.label.render(
            f"{label} · {sub}", True, self.palette.text_dim
        )
        surface.blit(caption, (x, y + value_text.get_height() - 2))
        return y + value_text.get_height() + caption.get_height() + 2

    def _draw_stat_row(
        self,
        surface: pygame.Surface,
        label: str,
        value: str,
        x: int,
        y: int,
        value_color: tuple[int, int, int] | None = None,
    ) -> int:
        label_text = self.fonts.small.render(label, True, self.palette.text_label)
        surface.blit(label_text, (x, y))
        value_text = self.fonts.mono.render(
            value, True, value_color or self.palette.text
        )
        right_x = x + RIGHT_PANEL_W - 36 - value_text.get_width()
        surface.blit(value_text, (right_x, y - 3))
        return y + max(label_text.get_height(), value_text.get_height())

    def _draw_global_chart(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        width: int,
        height: int,
        game: Game,
    ) -> None:
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(surface, (12, 18, 28), rect, border_radius=3)
        pygame.draw.rect(surface, self.palette.ui_border, rect, 1, border_radius=3)

        infected = list(game.infected_history)
        dead = list(game.dead_history)
        if not infected and not dead:
            empty = self.cached_render(self.fonts.small, "— en attente —", self.palette.text_dim)
            surface.blit(
                empty,
                (rect.centerx - empty.get_width() // 2, rect.centery - empty.get_height() // 2),
            )
            return

        max_seen = max(
            (max(infected) if infected else 0.0),
            (max(dead) if dead else 0.0),
        )
        max_y = max(0.05, max_seen * 1.4)

        # Mid-grid line.
        mid_y = rect.top + rect.height // 2
        pygame.draw.line(
            surface, (24, 32, 46), (rect.left + 1, mid_y), (rect.right - 1, mid_y), 1
        )

        def project(series: list[float], color: tuple[int, int, int]) -> None:
            if not series:
                return
            denom = max(1, len(series) - 1)
            pts: list[tuple[int, int]] = []
            for i, v in enumerate(series):
                t = i / denom
                px = rect.left + 1 + int(t * (rect.width - 2))
                py = rect.bottom - 2 - int((v / max_y) * (rect.height - 4))
                pts.append((px, py))
            if len(pts) >= 2:
                pygame.draw.lines(surface, color, False, pts, 2)
            pygame.draw.circle(surface, color, pts[-1], 3)

        project(dead, self.palette.severe)
        project(infected, self.palette.affected)

        # Y-axis hint at top-left. French typo: space before %.
        scale = self.fonts.label.render(
            f"{int(max_y * 100)} %", True, self.palette.text_dim
        )
        surface.blit(scale, (rect.left + 4, rect.top + 2))

    def _draw_news_ticker(self, surface: pygame.Surface, game: Game) -> None:
        w, h = self.screen_size
        rect = pygame.Rect(0, h - NEWS_BAR_H, w, NEWS_BAR_H)
        # Drop shadow above the ticker (mirror of the top-bar shadow).
        self._draw_edge_shadow(surface, y=rect.top - 10, height=10, downward=False)
        self._fill_panel(surface, rect, self.palette.news_bg)
        cat_color = game.gaia.active.arc_color
        pygame.draw.line(surface, cat_color, (0, rect.top), (w, rect.top), 2)

        # Live alert badge — rounded pill in the catastrophe tint so it
        # stays cohesive with the top edge line + the rest of the catastrophe
        # branding. The previous flat coral red clashed with cool catastrophes
        # like Eau / Air.
        badge_w = 84
        badge_h = NEWS_BAR_H - 14
        badge_rect = pygame.Rect(rect.left + 12, rect.top + 7, badge_w, badge_h)
        # Was a flat black 1-px-down sliver under the badge — visible
        # as a hard cliff against the news bar. Soft Gaussian
        # ``_draw_shadow`` grades it into the bar's dark tone.
        # Very light elevation since the badge is a small element
        # *embedded* in a panel, not floating above one.
        self._draw_shadow(
            surface, badge_rect, blur=4, alpha=80, offset_y=1,
        )
        badge_color = _blend(cat_color, (0, 0, 0), 0.45)
        pygame.draw.rect(
            surface, badge_color, badge_rect, border_radius=badge_h // 2,
        )
        pygame.draw.rect(
            surface, cat_color, badge_rect, 1, border_radius=badge_h // 2,
        )
        # Pulsing dot — keeps the urgency colour cue.
        ticks = pygame.time.get_ticks()
        dot_pulse = 0.5 + 0.5 * math.sin(ticks * 0.006)
        dot_color = _blend(cat_color, (255, 255, 255), 0.3 + 0.7 * dot_pulse)
        dot_x = badge_rect.left + 12
        pygame.draw.circle(surface, dot_color, (dot_x, badge_rect.centery), 4)
        live = self.cached_render(self.fonts.label, "ALERTE", (255, 255, 255))
        surface.blit(
            live,
            (dot_x + 12,
             badge_rect.centery - live.get_height() // 2),
        )

        # Build the rolling strip from the news deque. Cache key
        # combines news items + cat_color: cycling catastrophes
        # re-tints the bullet separators baked into the strip, so the
        # cache must invalidate on either dimension.
        news_items = tuple(game.news)
        cache_key = (news_items, cat_color)
        if self._news_text_cache is None or self._news_text_cache[0] != cache_key:
            rendered = self._build_news_strip(news_items, cat_color)
            self._news_text_cache = (cache_key, rendered)
        rendered = self._news_text_cache[1]

        clip_rect = pygame.Rect(
            badge_rect.right + 14, rect.top, w - badge_rect.right - 30, NEWS_BAR_H
        )
        prev_clip = surface.get_clip()
        surface.set_clip(clip_rect)
        try:
            self._news_scroll_x -= 1.9  # faster scroll — was 1.2
            text_w = rendered.get_width()
            if -self._news_scroll_x > text_w + clip_rect.width:
                self._news_scroll_x = 0.0
            x = clip_rect.left + int(self._news_scroll_x) + clip_rect.width
            surface.blit(rendered, (x, rect.top + (NEWS_BAR_H - rendered.get_height()) // 2))
        finally:
            surface.set_clip(prev_clip)

        # Cat-tinted base rail — 2-px line at the bottom of the ticker
        # clip in the catastrophe colour. Gives the strip a physical
        # "track" feel: the rolling headlines ride along a coloured
        # rail, anchoring the catastrophe identity even when the text
        # passes through low-contrast headline content. Drawn in
        # clip-space (not on the scrolling strip) so it stays anchored
        # to the bar rather than rolling with the text. Painted *before*
        # the edge fades so the rail dissolves into the bar background
        # at the strip edges like the text does.
        rail_y = clip_rect.bottom - 5
        rail_layer = pygame.Surface(
            (clip_rect.width, 2), pygame.SRCALPHA,
        )
        rail_layer.fill((*cat_color, 90))
        surface.blit(rail_layer, (clip_rect.left, rail_y))

        # Soft edge fades on the rolling text so words don't hard-cut at
        # the clip boundaries. Two thin vertical gradient strips overlay
        # the ticker body in the news-bar background colour, opaque at
        # the edge and transparent toward the centre. Cheap pygame
        # draw — single Surface per side, cached implicitly by Python's
        # reuse-by-tuple in subsequent frames is not used here, but the
        # cost is ~32 line draws per frame which is trivial.
        self._draw_news_edge_fade(
            surface, clip_rect, side="left", width=28,
        )
        self._draw_news_edge_fade(
            surface, clip_rect, side="right", width=28,
        )

    def _build_news_strip(
        self,
        items: tuple[str, ...],
        cat_color: tuple[int, int, int],
    ) -> pygame.Surface:
        """Build the wide scrolling strip with cat-tinted bullet separators.

        Each item renders as its own Surface; between items a small
        filled circle (``cat_color``) acts as the visual delimiter, with
        a soft alpha halo for depth. Replaces the prior flat
        ``"  ◆  ".join(...)`` approach where every separator was a white
        diamond *glyph* rendered in the text colour — losing both the
        catastrophe identity and any clear visual break between items.

        Builds an SRCALPHA Surface sized to the joined content so the
        scroll-and-blit code in ``_draw_news_ticker`` doesn't need to
        change. Cached upstream keyed on ``(news_items, cat_color)`` so
        recomputation only happens when news changes or the player
        cycles catastrophes.
        """
        if not items:
            return self.fonts.medium.render("—", True, self.palette.text)
        item_surfaces = [
            self.fonts.medium.render(text, True, self.palette.text)
            for text in items
        ]
        bullet_r = 3
        halo_r = 6
        bullet_gap = 14
        bullet_block_w = bullet_gap * 2 + halo_r * 2
        total_w = (
            sum(s.get_width() for s in item_surfaces)
            + max(0, len(items) - 1) * bullet_block_w
        )
        max_text_h = max(s.get_height() for s in item_surfaces)
        # Strip height accommodates both the text and the bullet halo
        # (whichever is taller). +4 padding so the halo doesn't graze
        # the strip's vertical edges.
        strip_h = max(max_text_h, halo_r * 2 + 4)
        strip = pygame.Surface((total_w, strip_h), pygame.SRCALPHA)
        text_y = (strip_h - max_text_h) // 2
        x = 0
        for i, item_surf in enumerate(item_surfaces):
            strip.blit(item_surf, (x, text_y))
            x += item_surf.get_width()
            if i < len(item_surfaces) - 1:
                # Bullet centred in the gap between items.
                bx = x + bullet_gap + halo_r
                by = strip_h // 2
                # Soft halo behind the bullet — concentric SRCALPHA
                # circles with α growing inward (SRC_OVER blending
                # accumulates into a natural radial falloff).
                for r in range(halo_r, bullet_r, -1):
                    t = (halo_r - r) / max(1, halo_r - bullet_r - 1)
                    a = int(55 * t ** 0.9)
                    if a < 1:
                        continue
                    pygame.draw.circle(strip, (*cat_color, a), (bx, by), r)
                pygame.draw.circle(strip, cat_color, (bx, by), bullet_r)
                x += bullet_block_w
        return strip

    def _draw_news_edge_fade(
        self,
        surface: pygame.Surface,
        clip_rect: pygame.Rect,
        *,
        side: str,
        width: int,
    ) -> None:
        """Paint a horizontal alpha gradient strip at ``side`` of the ticker.

        Uses the news-bar background colour so the fade reads as the
        text "dissolving into" the bar instead of cutting at the clip.
        """
        bg = self.palette.news_bg
        fade = pygame.Surface((width, clip_rect.height), pygame.SRCALPHA)
        max_alpha = bg[3] if len(bg) == 4 else 245
        for x in range(width):
            # alpha fades from full at the outer edge to 0 toward the centre.
            if side == "left":
                t = 1.0 - (x / width)
            else:
                t = x / width
            a = int(max_alpha * (t ** 1.5))
            if a <= 0:
                continue
            pygame.draw.line(
                fade, (bg[0], bg[1], bg[2], a),
                (x, 0), (x, clip_rect.height),
            )
        if side == "left":
            surface.blit(fade, clip_rect.topleft)
        else:
            surface.blit(fade, (clip_rect.right - width, clip_rect.top))

    # --------------------------------------------------------- info panel

    def _draw_info_panel(self, surface: pygame.Surface, country: Country, game: "Game | None" = None) -> None:
        """Light dashboard card: catastrophe-color header strip + light body.

        Three sections: demographics rows, indicator bars (animated, color-graded),
        trend numbers + sparkline. Shadow + rounded corners for a card look.
        """
        panel_x = 16
        panel_y = TOP_BAR_H + 16
        rect = pygame.Rect(panel_x, panel_y, INFO_PANEL_W, INFO_PANEL_H)

        # Drop shadow + rounded card body.
        self._draw_shadow(surface, rect, blur=20, alpha=160)
        radius = 14
        pygame.draw.rect(surface, LIGHT_CARD_BG, rect, border_radius=radius)

        # Catastrophe-tinted side stripe along the body's left edge —
        # matches the idiom the right panel, news-ticker rail,
        # minimap brackets, and TENDANCE chips already use to carry
        # catastrophe identity into the chrome itself. Without this
        # the info panel was the only top-level surface in the game
        # with no catastrophe identity in its chrome. Sits BELOW the
        # header so the header's dark-tinted band can still bridge
        # the full panel width.
        base_tint = (
            game.gaia.active.arc_color if game is not None else self.palette.ui_accent
        )
        header_h = 60
        stripe_top = rect.top + header_h + 8
        stripe_bottom = rect.bottom - 12
        pygame.draw.rect(
            surface, base_tint,
            (rect.left + 4, stripe_top, 3, stripe_bottom - stripe_top),
            border_radius=2,
        )

        # Textured atmospheric overlay on the body — same warm-cool
        # gradient + fine film-grain idiom now shipped on the worldmap.
        # Scaled to the panel's body region (below the header) so the
        # otherwise flat ``LIGHT_CARD_BG`` reads as a material surface
        # with subtle ambient depth, not as a flat painted rectangle.
        # Cached per body-size; one blit per frame after first build.
        self._draw_info_panel_texture(
            surface,
            pygame.Rect(
                rect.left + 8, rect.top + header_h,
                rect.width - 16, rect.height - header_h - 8,
            ),
        )

        # Header strip — darkened catastrophe tint so white text reads cleanly
        # on top (light blue accent + white was poor contrast).
        header_color = _blend(base_tint, (0, 0, 0), 0.45)
        header_h = 60
        # Trick: draw a non-rounded fill, then re-overlay top corners with the card
        # bg to keep just the bottom flat — pygame can't selectively-round corners,
        # but a clip-style rounded top can be faked by drawing a rounded rect over
        # the full panel rect first, then a smaller solid rect for the body.
        header_surf = pygame.Surface((rect.width, header_h), pygame.SRCALPHA)
        pygame.draw.rect(
            header_surf, header_color,
            (0, 0, rect.width, header_h),
            border_radius=radius,
        )
        # Cover the bottom-rounded part of header so it blends into the body.
        pygame.draw.rect(
            header_surf, header_color,
            (0, header_h - radius, rect.width, radius),
        )
        # Vertical gradient inside the header — top +12 luminance,
        # bottom −12 — gives the band a "raised display surface" feel
        # rather than reading as a flat painted dark rectangle. The
        # gradient is drawn onto the header surface BEFORE the blit
        # so the rounded-corner mask catches the overlay.
        for gy in range(header_h):
            t = gy / max(1, header_h - 1)
            shift = int(12 * (1.0 - 2 * t))
            if shift > 0:
                pygame.draw.line(
                    header_surf, (255, 255, 255, min(255, shift * 3)),
                    (0, gy), (rect.width, gy),
                )
            elif shift < 0:
                pygame.draw.line(
                    header_surf, (0, 0, 0, min(255, -shift * 3)),
                    (0, gy), (rect.width, gy),
                )
        surface.blit(header_surf, (rect.left, rect.top))
        # 1-px top-edge highlight (inset 6 px on each side so it
        # doesn't crash into the rounded corners).
        pygame.draw.line(
            surface,
            _blend(header_color, (255, 255, 255), 0.25),
            (rect.left + 6, rect.top + 1),
            (rect.right - 6, rect.top + 1),
            1,
        )
        # 2-px catastrophe-tinted bottom-edge accent — uses the *full
        # saturation* base_tint (not the darkened header colour) so
        # it pops as a focal "lit edge" that bridges the header to
        # the body below. Same idiom the right panel's left-edge
        # stripe and the news-ticker rail use to carry catastrophe
        # identity into the chrome itself.
        pygame.draw.line(
            surface, base_tint,
            (rect.left + 8, rect.top + header_h - 1),
            (rect.right - 8, rect.top + header_h - 1),
            2,
        )

        # Auto-fit the country name so long French names like "République
        # dém. du Congo" or "Bosnie-Herzégovine" never spill past the panel
        # edge or under the close button. Progressive fallback: title (30pt
        # bold) → large (22pt) → medium (17pt) → ellipsized medium.
        close_btn = close_button_rect(self.config)
        title_max_w = close_btn.left - rect.left - 36
        title_label, title_font = self._fit_text_progressive(
            country.name, title_max_w,
            (self.fonts.title, self.fonts.large, self.fonts.medium),
        )
        title = title_font.render(title_label, True, LIGHT_HEADER_TEXT)
        surface.blit(title, (rect.left + 18, rect.top + (header_h - title.get_height()) // 2))

        # Close button (×) — translucent circle + white × glyph, matching the
        # impact card / skill tree style. The previous coral-red fill clashed
        # with the darkened catastrophe-tint header.
        close_rect = close_button_rect(self.config)
        close_hover = close_rect.collidepoint(pygame.mouse.get_pos())
        close_center = close_rect.center
        close_r = close_rect.width // 2
        close_layer = pygame.Surface(
            (close_r * 2, close_r * 2), pygame.SRCALPHA,
        )
        circle_alpha = 130 if close_hover else 70
        pygame.draw.circle(
            close_layer, (255, 255, 255, circle_alpha),
            (close_r, close_r), close_r,
        )
        surface.blit(
            close_layer,
            (close_center[0] - close_r, close_center[1] - close_r),
        )
        cx_close, cy_close = close_center
        pygame.draw.line(
            surface, (255, 255, 255),
            (cx_close - 5, cy_close - 5), (cx_close + 5, cy_close + 5), 2,
        )
        pygame.draw.line(
            surface, (255, 255, 255),
            (cx_close + 5, cy_close - 5), (cx_close - 5, cy_close + 5), 2,
        )

        # ---- Tab bar (3 sections) ----
        x = rect.left + PAD
        content_w = rect.width - PAD * 2
        tab_y = rect.top + header_h + 10
        tab_h = 32
        tab_labels = ("BILAN", "ÉQUILIBRE", "TENDANCE")
        active_tab = max(0, min(2, game.info_panel_tab)) if game else 0
        tab_rects = info_panel_tab_rects(self.config)
        accent = (
            game.gaia.active.arc_color if game is not None else self.palette.ui_accent
        )
        for i, label in enumerate(tab_labels):
            tab_rect = tab_rects[i]
            self._draw_info_panel_tab(
                surface, tab_rect, label,
                active=i == active_tab, accent=accent,
            )

        # ---- Tab content area ----
        y = tab_y + tab_h + 12
        if active_tab == 0:
            self._draw_info_tab_bilan(surface, x, y, content_w, country)
        elif active_tab == 1:
            self._draw_info_tab_equilibre(surface, x, y, content_w, country)
        else:
            self._draw_info_tab_tendance(surface, x, y, content_w, country)

    def _draw_info_panel_tab(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        *,
        active: bool,
        accent: tuple[int, int, int],
    ) -> None:
        """Pill-style tab inside the info panel with screen-surface depth.

        Active tab reads as a *pressed-in, lit pill*: darkened accent
        fill + subtle vertical gradient (top brighter, bottom darker)
        + 1-px top highlight + 1-px bottom shadow. The active pill
        looks like a backlit button that's currently pressed.

        Inactive tab reads as a *raised but dim pill*: flat
        ``LIGHT_TRACK`` fill + 1-px top highlight only (no bottom
        shadow, no gradient). Reads as "available but not the focus".

        Was flat colour-only pills — both states rendered as solid
        coloured rectangles with no depth cues, so the only thing
        distinguishing active from inactive was the fill colour.
        Players couldn't tell at a glance which tab they were on
        without parsing the text colour.
        """
        radius = rect.height // 2
        if active:
            tab_color = _blend(accent, (0, 0, 0), 0.40)
            pygame.draw.rect(surface, tab_color, rect, border_radius=radius)
            # Vertical gradient on the active tab — top +8, bottom -8.
            # Clipped to the rect so it can't bleed past the pill edges.
            prev_clip = surface.get_clip()
            surface.set_clip(rect)
            grad = pygame.Surface(rect.size, pygame.SRCALPHA)
            for gy in range(rect.height):
                t = gy / max(1, rect.height - 1)
                shift = int(8 * (1.0 - 2 * t))
                if shift > 0:
                    pygame.draw.line(
                        grad, (255, 255, 255, min(255, shift * 4)),
                        (0, gy), (rect.width, gy),
                    )
                elif shift < 0:
                    pygame.draw.line(
                        grad, (0, 0, 0, min(255, -shift * 4)),
                        (0, gy), (rect.width, gy),
                    )
            surface.blit(grad, rect.topleft)
            surface.set_clip(prev_clip)
            # Top-edge highlight (inset 4 px on each side so it
            # doesn't crash into the rounded ends of the pill).
            pygame.draw.line(
                surface,
                _blend(tab_color, (255, 255, 255), 0.30),
                (rect.left + 4, rect.top + 1),
                (rect.right - 4, rect.top + 1),
                1,
            )
            # Bottom-edge shadow.
            pygame.draw.line(
                surface,
                _blend(tab_color, (0, 0, 0), 0.45),
                (rect.left + 4, rect.bottom - 2),
                (rect.right - 4, rect.bottom - 2),
                1,
            )
            text_color = (255, 255, 255)
        else:
            pygame.draw.rect(
                surface, LIGHT_TRACK, rect, border_radius=radius,
            )
            # Inactive — top-edge highlight only (raised pill feel).
            pygame.draw.line(
                surface,
                _blend(LIGHT_TRACK, (255, 255, 255), 0.20),
                (rect.left + 4, rect.top + 1),
                (rect.right - 4, rect.top + 1),
                1,
            )
            text_color = self.palette.text_label
        text = self.fonts.label.render(label, True, text_color)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2,
             rect.centery - text.get_height() // 2),
        )

    def _draw_info_tab_bilan(
        self,
        surface: pygame.Surface,
        x: int, y: int, w: int,
        country: Country,
    ) -> None:
        """Tab 1 — BILAN. Demographics as 4 hero rows (icon + big number + caption)."""
        pop = max(country.population, 1)
        affected_pct = int(country.affected / pop * 100)
        dead_pct = int(country.dead / pop * 100)
        # "État sanitaire" suggested "health status" (high = good), but
        # country.state is the *damage* level (high = worse). Rename to
        # "GRAVITÉ" + colour-code by severity band so the value reads
        # correctly: 62 % gravité = 62 % damaged, not 62 % healthy.
        state_pct = int(country.state * 100)
        if country.state >= 0.5:
            gravity_color = LIGHT_DANGER
        elif country.state >= 0.2:
            gravity_color = LIGHT_WARNING
        else:
            gravity_color = LIGHT_SUCCESS
        # French typo for percentages: space before %. Visible every
        # frame of the open info panel — the BILAN tab is the most
        # frequently-read panel surface, so sloppy "62%" reads as a
        # debug stamp instead of a localised stat.
        rows = (
            ("Population", _fmt_big(country.population), LIGHT_CARD_TEXT, ""),
            ("Touchés",    _fmt_big(country.affected),   LIGHT_WARNING,   f"{affected_pct} %"),
            ("Décès",      _fmt_big(country.dead),       LIGHT_DANGER,    f"{dead_pct} %"),
            ("Gravité",    f"{state_pct} %",             gravity_color,   ""),
        )
        for label, value, color, suffix in rows:
            row_h = 44
            lbl = self.fonts.label.render(
                label.upper(), True, LIGHT_CARD_LABEL,
            )
            val = self.fonts.hero.render(value, True, color)
            surface.blit(lbl, (x + 4, y + 4))
            surface.blit(val, (x + 4, y + 4 + lbl.get_height() + 2))
            if suffix:
                pct = self.fonts.medium.render(suffix, True, color)
                surface.blit(
                    pct,
                    (x + w - pct.get_width() - 4,
                     y + 4 + lbl.get_height() + (val.get_height() - pct.get_height())),
                )
            # Bottom hairline.
            pygame.draw.line(
                surface, LIGHT_CARD_RULE,
                (x, y + row_h + 4),
                (x + w, y + row_h + 4),
                1,
            )
            y += row_h + 12

    def _draw_info_tab_equilibre(
        self,
        surface: pygame.Surface,
        x: int, y: int, w: int,
        country: Country,
    ) -> None:
        """Tab 2 — ÉQUILIBRE. Four indicator dials with name + percentage.

        Each indicator now sits in a **mini-tile** with severity-aware
        chrome — was a flat 2×2 grid of dials floating on the panel
        bg with no cell containment, so the four indicators read as
        "four detached widgets" instead of "four readouts on a panel".
        Each tile carries:

          * A subtle severity-washed background — the tile's overall
            tone reflects its indicator's severity (green wash for
            healthy, amber for mid, red for low).
          * A 3-px severity-tinted left-edge stripe — same idiom the
            TENDANCE chips, right panel, news-ticker rail, and
            minimap brackets use. Hi-contrast severity cue at the
            tile's leading edge.
          * A 1-px tile border at a darker shade of the severity
            colour — gives each tile a contained shape so the grid
            reads as four *cards* instead of four floating dials.

        Vibrance idiom matches the rest of the chrome — the dial,
        label, AND tile chrome all speak the same severity colour
        per indicator. No more grey panel with multi-coloured dials
        floating in space.
        """
        indicators = (
            ("Résilience\ntechnologique", country.resilience),
            ("Stabilité\nsociétale",      country.stability),
            ("Régénération\nécologique",  country.regeneration),
            ("Adaptation\névolutive",     country.adaptation),
        )
        # 2×2 grid of dials.
        cell_w = w // 2
        cell_h = 130
        for i, (label, value) in enumerate(indicators):
            col = i % 2
            row = i // 2
            cell_x = x + col * cell_w
            cell_y = y + row * cell_h
            cx = cell_x + cell_w // 2
            cy = cell_y + 38
            # Color grade — green high, amber mid, red low.
            v = max(0.0, min(1.0, value))
            if v >= 0.66:
                ind_color = LIGHT_SUCCESS
            elif v >= 0.33:
                ind_color = LIGHT_WARNING
            else:
                ind_color = LIGHT_DANGER
            # Mini-tile chrome — drawn BEFORE the dial so the dial /
            # label render on top of the tile bg. Inset 4 px from the
            # cell bounds so adjacent tiles have breathing room.
            tile_rect = pygame.Rect(
                cell_x + 4, cell_y + 4,
                cell_w - 8, cell_h - 8,
            )
            # Severity-washed bg — very subtle tint of the indicator
            # colour blended into the card bg (8 %). Just enough to
            # give the tile its own personality without making the
            # data hard to read.
            tile_bg = _blend(LIGHT_CARD_BG, ind_color, 0.08)
            pygame.draw.rect(surface, tile_bg, tile_rect, border_radius=8)
            # Gradient + edge-stroke depth — the four ÉQUILIBRE tiles
            # were flat severity-washed rects against the info panel's
            # light card bg. Now they pick up the same chrome family
            # depth (gradient mask + top-highlight + bottom-shadow) as
            # every other card-like surface. The dial + labels render
            # on top of the depth treatment, so the data stays clean
            # while the tile reads as a proper sub-card.
            self._apply_button_depth(surface, tile_rect, tile_bg, radius=8)
            # Severity-tinted border (35 % blend, darker than the
            # stripe so the stripe still reads as the focal accent).
            tile_border = _blend(LIGHT_CARD_BG, ind_color, 0.35)
            pygame.draw.rect(
                surface, tile_border, tile_rect, 1, border_radius=8,
            )
            # Left-edge severity stripe (3 px, 4 px inset top + bot
            # so the rounded corners stay unbroken).
            pygame.draw.rect(
                surface, ind_color,
                (tile_rect.left, tile_rect.top + 4, 3, tile_rect.height - 8),
                border_radius=2,
            )
            self._draw_indicator_dial(surface, cx, cy, 26, v, ind_color)
            # Two-line label below the dial.
            tline_y = cy + 32
            for line in label.split("\n"):
                t = self.fonts.label.render(line, True, LIGHT_CARD_LABEL)
                surface.blit(
                    t,
                    (cx - t.get_width() // 2, tline_y),
                )
                tline_y += t.get_height() + 1

    def _draw_indicator_dial(
        self,
        surface: pygame.Surface,
        cx: int, cy: int, r: int,
        value: float,
        color: tuple[int, int, int],
    ) -> None:
        """Procedural circular progress dial.

        Visual layers (was: dim ring + flat arc + centred % text — the
        most minimal helper in the chart family despite being drawn
        4× per country panel):

          1. **Track ring** (4 px, dim grey).
          2. **Calibration ticks** at 25 / 50 / 75 % — small radial
             pips on the track. Gives the eye a reference scale so
             the % reads at a glance without parsing the digits.
          3. **Filled arc as a sequence of small circles** instead of
             ``pygame.draw.arc`` — same technique as ``_draw_outro_donut``.
             pygame.draw.arc at width=4 on a 26 px radius had visible
             aliasing and gaps at certain end-angles; circle-stepping
             gives a crisp continuous arc at the same cost.
          4. **Leading-edge cap** at the arc tip — bright pip + soft
             halo so the eye locks onto where the value lands instead
             of having to trace the arc end. Skipped for ≥ 99 %.
          5. **Outer success halo** when value ≥ 0.70 — soft glow ring
             tinted with the indicator's colour, intensity scaling
             with how close to full. Reinforces that the indicator is
             healthy without changing the percentage.
          6. **Centred % text** (with French typography space).
        """
        # 1. Track ring.
        pygame.draw.circle(surface, LIGHT_TRACK, (cx, cy), r, 4)

        # 2. Calibration ticks at 25/50/75%.
        tick_color = _blend(LIGHT_TRACK, (0, 0, 0), 0.30)
        for t in (0.25, 0.50, 0.75):
            angle = -math.pi / 2 + t * 2 * math.pi
            outer_pt = (
                cx + math.cos(angle) * r,
                cy + math.sin(angle) * r,
            )
            inner_pt = (
                cx + math.cos(angle) * (r - 4),
                cy + math.sin(angle) * (r - 4),
            )
            pygame.draw.line(surface, tick_color, inner_pt, outer_pt, 1)

        # 3. Filled arc — circle-stepping for crisp quality.
        if value > 0.01:
            steps = max(8, int(72 * value))
            for k in range(steps):
                t = k / 72.0
                if t > value:
                    break
                angle = -math.pi / 2 + t * 2 * math.pi
                px = cx + int(math.cos(angle) * r)
                py = cy + int(math.sin(angle) * r)
                pygame.draw.circle(surface, color, (px, py), 2)
            # 4. Leading-edge cap (skipped at ~full).
            if value < 0.99:
                tip_angle = -math.pi / 2 + value * 2 * math.pi
                tx = cx + int(math.cos(tip_angle) * r)
                ty = cy + int(math.sin(tip_angle) * r)
                halo = pygame.Surface((18, 18), pygame.SRCALPHA)
                for hr in range(8, 0, -1):
                    a = int(85 * (1 - hr / 8) ** 1.6)
                    if a < 1:
                        continue
                    pygame.draw.circle(halo, (*color, a), (9, 9), hr)
                surface.blit(halo, (tx - 9, ty - 9))
                pygame.draw.circle(
                    surface, _blend(color, (255, 255, 255), 0.4),
                    (tx, ty), 3,
                )

        # 5. Outer success halo when value is healthy.
        if value >= 0.70:
            halo_alpha = int(55 * min(1.0, (value - 0.70) / 0.30))
            if halo_alpha > 2:
                outer = pygame.Surface(
                    (r * 2 + 12, r * 2 + 12), pygame.SRCALPHA,
                )
                for ring_r in (r + 5, r + 3):
                    pygame.draw.circle(
                        outer, (*color, halo_alpha),
                        (r + 6, r + 6), ring_r, 1,
                    )
                surface.blit(outer, (cx - r - 6, cy - r - 6))

        # 6. Centred % text. French typography: space before "%".
        pct = self.fonts.medium.render(
            f"{int(value * 100)} %", True, color,
        )
        surface.blit(
            pct,
            (cx - pct.get_width() // 2,
             cy - pct.get_height() // 2),
        )

    def _draw_info_tab_tendance(
        self,
        surface: pygame.Surface,
        x: int, y: int, w: int,
        country: Country,
    ) -> None:
        """Tab 3 — TENDANCE. Hero sparkline + 2 metric chips."""
        # Big sparkline at the top of the tab. Chart container gets
        # screen-like depth: a subtle vertical gradient (top brighter,
        # bottom darker — reads as a device-screen surface, not a
        # flat painted rect) plus top-edge highlight + bottom-edge
        # shadow strokes. Cheap: two extra blits over the existing
        # flat fill, both within the rounded corners thanks to
        # ``border_radius=10`` clipping on the gradient surface.
        chart_h = 110
        chart_rect = pygame.Rect(x, y, w, chart_h)
        # Base flat fill provides the rounded-corner shape.
        pygame.draw.rect(
            surface, LIGHT_TRACK, chart_rect, border_radius=10,
        )
        # Vertical gradient overlay — top 6 % brighter, bottom 6 %
        # darker — gives the container a "display panel" feel rather
        # than a painted rectangle.
        grad = pygame.Surface((chart_rect.width, chart_rect.height), pygame.SRCALPHA)
        for gy in range(chart_rect.height):
            t = gy / max(1, chart_rect.height - 1)  # 0 at top → 1 at bot
            # Linear interp from +20 brightness at top to -20 at bot.
            shift = int(20 * (1.0 - 2 * t))
            if shift > 0:
                pygame.draw.line(
                    grad, (255, 255, 255, min(255, shift * 2)),
                    (0, gy), (chart_rect.width, gy),
                )
            elif shift < 0:
                pygame.draw.line(
                    grad, (0, 0, 0, min(255, -shift * 2)),
                    (0, gy), (chart_rect.width, gy),
                )
        # Use the rounded-rect as a clip mask so the gradient doesn't
        # bleed past the rounded corners.
        prev_clip = surface.get_clip()
        surface.set_clip(chart_rect)
        surface.blit(grad, chart_rect.topleft)
        surface.set_clip(prev_clip)
        # Top-edge highlight stroke + bottom-edge shadow stroke —
        # 1 px each — completes the screen-surface illusion. Inset
        # 6 px on each side so they don't crash into the rounded
        # corners.
        pygame.draw.line(
            surface,
            _blend(LIGHT_TRACK, (255, 255, 255), 0.20),
            (chart_rect.left + 6, chart_rect.top + 1),
            (chart_rect.right - 6, chart_rect.top + 1),
            1,
        )
        pygame.draw.line(
            surface,
            _blend(LIGHT_TRACK, (0, 0, 0), 0.40),
            (chart_rect.left + 6, chart_rect.bottom - 2),
            (chart_rect.right - 6, chart_rect.bottom - 2),
            1,
        )
        self._draw_country_sparkline_light(
            surface, x + 6, y + 6, w - 12, chart_h - 12, country,
        )
        chart_label = self.fonts.label.render(
            "ÉTAT · 6 DERNIERS JOURS", True, LIGHT_CARD_LABEL,
        )
        surface.blit(chart_label, (x, y + chart_h + 8))
        y += chart_h + chart_label.get_height() + 16

        # Two big metric chips: rate + estimated collapse. "stable" used
        # to mean "infection rate ≤ 0" — but a country at 80 % state with
        # no motion this turn isn't stable, it's stuck in the danger
        # zone. Disambiguate by state.
        rate = country.infection_rate()
        rate_pct = rate * 100
        # French typography: comma decimal + space before %.
        if rate > 0:
            rate_str = f"+{rate_pct:.1f} %".replace(".", ",")
            rate_color = LIGHT_DANGER if rate_pct >= 5 else LIGHT_WARNING
        elif rate < -0.0005:
            rate_str = f"{rate_pct:.1f} %".replace(".", ",")
            rate_color = LIGHT_SUCCESS
        elif country.state >= 0.5:
            rate_str = "figé"
            rate_color = LIGHT_WARNING
        else:
            rate_str = "stable"
            rate_color = LIGHT_SUCCESS

        ttc = country.turns_to_collapse()
        if country.state >= 1.0:
            ttc_str = "effondré"
            ttc_color = LIGHT_DANGER
        elif ttc is None:
            ttc_str = "—"
            ttc_color = LIGHT_CARD_DIM
        else:
            # "~3t" was ambiguous (tours / tonnes / temps?). Spell it
            # out: "~3 jours" / "~1 jour". Reads correctly in French,
            # stays within the chip width thanks to fonts.large (22 pt),
            # and matches the JOUR HUD counter the player just glanced at.
            unit = "jour" if ttc == 1 else "jours"
            ttc_str = f"~{ttc} {unit}"
            ttc_color = (
                LIGHT_DANGER if ttc <= 5
                else LIGHT_WARNING if ttc <= 15
                else LIGHT_SUCCESS
            )
        chip_w = (w - 12) // 2
        chip_h = 56
        for i, (caption, value, color) in enumerate((
            ("PROPAGATION", rate_str, rate_color),
            ("EFFONDREMENT", ttc_str, ttc_color),
        )):
            chip = pygame.Rect(x + i * (chip_w + 12), y, chip_w, chip_h)
            # Chip bg now carries an 8 % severity wash + a 30 % border
            # in the matching severity colour — same idiom shipped on
            # the ÉQUILIBRE tab indicator tiles. The whole chip reads
            # as severity-flavoured instead of a flat ``LIGHT_TRACK``
            # rectangle with a single coloured stripe at the edge.
            chip_bg = _blend(LIGHT_TRACK, color, 0.08)
            chip_border = _blend(LIGHT_TRACK, color, 0.30)
            pygame.draw.rect(surface, chip_bg, chip, border_radius=10)
            # Gradient + edge-stroke depth — matches the ÉQUILIBRE tab
            # tiles on the sibling tab so the two chips here (rate +
            # turns-to-collapse) read as proper sub-cards rather than
            # flat severity-washed rects. Same chrome family idiom as
            # the rest of the cards-that-look-like-cards.
            self._apply_button_depth(surface, chip, chip_bg, radius=10)
            pygame.draw.rect(
                surface, chip_border, chip, 1, border_radius=10,
            )
            # Severity-tinted left-edge stripe (3 px). Mirrors the
            # idiom the right panel and news ticker already use to
            # carry identity / state colour into the panel chrome
            # itself. The stripe sits inside the rounded corners
            # (top inset 4 px, bottom inset 4 px) so the rounded
            # chip outline stays unbroken; colour matches the value's
            # severity exactly so the chip reads as a unit, not a
            # two-tone composition.
            pygame.draw.rect(
                surface, color,
                (chip.left, chip.top + 4, 3, chip_h - 8),
                border_radius=2,
            )
            cap = self.fonts.label.render(caption, True, LIGHT_CARD_LABEL)
            val = self.fonts.large.render(value, True, color)
            surface.blit(cap, (chip.left + 10, chip.top + 8))
            surface.blit(
                val,
                (chip.left + 10, chip.top + 10 + cap.get_height()),
            )

    def _draw_light_section_header(
        self,
        surface: pygame.Surface,
        x: int, y: int,
        title: str,
        content_w: int,
    ) -> int:
        text = self.fonts.label.render(title, True, LIGHT_CARD_LABEL)
        surface.blit(text, (x, y))
        rule_y = y + text.get_height() + 2
        pygame.draw.line(
            surface, LIGHT_CARD_RULE, (x, rule_y), (x + content_w, rule_y), 1,
        )
        return rule_y + 6

    def _draw_light_row(
        self,
        surface: pygame.Surface,
        x: int, y: int, width: int,
        label: str, value: str,
        value_color: tuple[int, int, int],
    ) -> int:
        label_text = self.fonts.small.render(label, True, LIGHT_CARD_DIM)
        value_text = self.fonts.mono.render(value, True, value_color)
        # Center-baseline alignment between label (smaller) and value (mono).
        label_y = y + max(0, (value_text.get_height() - label_text.get_height()) // 2)
        surface.blit(label_text, (x, label_y))
        surface.blit(value_text, (x + width - value_text.get_width(), y))
        return y + max(label_text.get_height(), value_text.get_height()) + 4

    def _draw_light_indicator(
        self,
        surface: pygame.Surface,
        x: int, y: int, width: int,
        label: str, value: float,
    ) -> int:
        label_text = self.fonts.small.render(label, True, LIGHT_CARD_TEXT)
        surface.blit(label_text, (x, y))
        # Right-side percentage in the indicator color so the eye lands on it.
        value_color = self._indicator_color(value)
        # French typo: space before %.
        pct_text = self.fonts.mono.render(
            f"{int(value * 100)} %", True, value_color,
        )
        surface.blit(pct_text, (x + width - pct_text.get_width(), y - 1))
        bar_y = y + label_text.get_height() + 4
        bar_h = 10
        self._draw_indicator_bar_v2(
            surface, x, bar_y, width, bar_h, value, value_color,
        )
        return bar_y + bar_h + 8

    def _draw_country_sparkline_light(
        self,
        surface: pygame.Surface,
        x: int, y: int, width: int, height: int,
        country: Country,
    ) -> None:
        rect = pygame.Rect(x, y, width, height)
        pygame.draw.rect(surface, LIGHT_TRACK, rect, border_radius=4)

        history = list(country.state_history)
        if len(history) < 2:
            # Two-tier empty state. Zero samples (the very first turn,
            # before any history is captured) shows the generic wait
            # message. One sample renders the lone reading as a dot at
            # its correct y-coord — feels like the chart is *starting*
            # rather than empty, and the player sees their current
            # severity colour immediately instead of a placeholder.
            if len(history) == 0:
                empty = self.fonts.small.render(
                    "historique à partir du jour 2", True, LIGHT_CARD_DIM,
                )
                surface.blit(
                    empty,
                    (rect.centerx - empty.get_width() // 2,
                     rect.centery - empty.get_height() // 2),
                )
                return
            # Single-sample path: dot only, anchored on the right edge.
            v = history[0]
            px = rect.right - 4
            py = rect.bottom - 3 - int(
                max(0.0, min(1.0, v)) * (rect.height - 6)
            )
            dot_color = self._indicator_color(1.0 - country.state)
            pygame.draw.circle(surface, dot_color, (px, py), 3)
            pygame.draw.circle(surface, (255, 255, 255), (px, py), 3, 1)
            return

        denom = max(1, len(history) - 1)
        pts: list[tuple[int, int]] = []
        for i, v in enumerate(history):
            t = i / denom
            px = rect.left + 3 + int(t * (rect.width - 6))
            py = rect.bottom - 3 - int(max(0.0, min(1.0, v)) * (rect.height - 6))
            pts.append((px, py))
        line_color = self._indicator_color(1.0 - country.state)  # inverted: high state = bad

        # Vertical day-tick guides at each interior sample's x-coord —
        # 1 px, very dim, drawn behind everything else. Reads the chart
        # as a time-series (each gap = one day) rather than an abstract
        # wiggle. Skipped at the endpoints (which get their own
        # treatment) and when there's too little horizontal room for
        # the ticks to read as distinct (e.g. on the narrowest panel
        # widths where the chart shrinks below a usable gap).
        if len(pts) >= 3 and (pts[1][0] - pts[0][0]) >= 6:
            for px, _py in pts[1:-1]:
                pygame.draw.line(
                    surface, LIGHT_CARD_RULE,
                    (px, rect.top + 4), (px, rect.bottom - 4), 1,
                )

        # Dashed 50 % reference line behind the chart — turns the thin
        # stroke into something readable as a *chart* rather than a
        # disconnected wiggle. Skipped when the chart is so short the
        # dashes wouldn't render distinctly.
        mid_y = rect.bottom - 3 - int(0.5 * (rect.height - 6))
        if rect.width >= 40:
            dash_x = rect.left + 4
            dash_end = rect.right - 4
            while dash_x < dash_end:
                dash_to = min(dash_x + 4, dash_end)
                pygame.draw.line(
                    surface, LIGHT_CARD_RULE,
                    (dash_x, mid_y), (dash_to, mid_y), 1,
                )
                dash_x += 7

        # Translucent area fill — gives the sparkline weight at a
        # glance. Drawn on an SRCALPHA layer in chart-local coords so
        # the rounded corners of LIGHT_TRACK below stay clean. The
        # fill keeps a single colour (the *current* severity, same as
        # the country fill on the map) — that single-colour wash
        # anchors the "this is now" reading; the line above tells the
        # *history* story in its per-segment colours.
        fill = pygame.Surface(rect.size, pygame.SRCALPHA)
        poly = (
            [(p[0] - rect.left, p[1] - rect.top) for p in pts]
            + [(pts[-1][0] - rect.left, rect.height - 3),
               (pts[0][0]  - rect.left, rect.height - 3)]
        )
        pygame.draw.polygon(fill, (*line_color, 55), poly)
        surface.blit(fill, rect.topleft)

        # Per-segment line colour. Each segment between samples i and
        # i+1 uses the *average severity* at that interval, so the
        # stroke traces a colour journey across the past days instead
        # of being a single flat tone. Same blue-grey → amber → coral
        # → wine ramp as the country fill on the map, so the chart
        # speaks the player's existing visual vocabulary. A country
        # that *was* fine and *just* tipped reads very differently
        # from one that has been critical all week — the line's
        # colour history tells the descent story (or the recovery).
        for i in range(len(pts) - 1):
            avg = (history[i] + history[i + 1]) * 0.5
            seg_color = self._indicator_color(1.0 - avg)
            pygame.draw.line(surface, seg_color, pts[i], pts[i + 1], 2)

        # Endpoint emphasis — "you are here" cue. Soft radial halo
        # (concentric filled circles with alpha increasing as r
        # shrinks, so SRC_OVER accumulates into a natural radial
        # falloff with a bright core and smooth outer fade) + filled
        # dot + thin 1-px white ring. The ring picks the dot out
        # against the line's local colour so the live-state position
        # reads instantly, not just as "another sample".
        end_x, end_y = pts[-1]
        halo_r = 7
        halo = pygame.Surface(
            (halo_r * 2 + 4, halo_r * 2 + 4), pygame.SRCALPHA,
        )
        hcx = halo_r + 2
        hcy = halo_r + 2
        for r in range(halo_r, 2, -1):
            t = (halo_r - r) / max(1, halo_r - 3)  # 0 outer → 1 inner
            a = int(48 * t ** 0.8)
            if a < 1:
                continue
            pygame.draw.circle(halo, (*line_color, a), (hcx, hcy), r)
        surface.blit(halo, (end_x - hcx, end_y - hcy))
        pygame.draw.circle(surface, line_color, (end_x, end_y), 3)
        pygame.draw.circle(surface, (255, 255, 255), (end_x, end_y), 3, 1)

    @staticmethod
    def _indicator_color(value: float) -> tuple[int, int, int]:
        """Map a 0..1 indicator to success / warning / danger colors (light theme)."""
        if value >= 0.70:
            return LIGHT_SUCCESS
        if value >= 0.40:
            return LIGHT_WARNING
        return LIGHT_DANGER

    def _draw_indicator_bar_v2(
        self,
        surface: pygame.Surface,
        x: int,
        y: int,
        width: int,
        height: int,
        value: float,
        color: tuple[int, int, int],
        track_color: tuple[int, int, int] = LIGHT_TRACK,
    ) -> None:
        """Animated progress bar: brightness-gradient fill + rounded corners."""
        radius = max(2, height // 2)
        pygame.draw.rect(surface, track_color, (x, y, width, height), border_radius=radius)
        clamped = max(0.0, min(1.0, value))
        fill_w = max(0, min(width, int(width * clamped)))
        # Visible-minimum lift: a non-zero value that rounds to 1-3 px
        # used to early-return at ``fill_w < 4`` — so a bar at 0.5 %
        # rendered identically to a bar at 0 %. Now any positive value
        # is forced to at least ``2 × radius`` (one pill diameter) so
        # the player sees *some* fill, capped to the bar width so a
        # tiny bar doesn't overflow. Strict zero still returns early
        # (no fill drawn, just the empty track).
        if clamped <= 0.0:
            return
        fill_w = max(fill_w, min(width, 2 * radius))
        fill_surf = pygame.Surface((fill_w, height), pygame.SRCALPHA)
        for i in range(fill_w):
            brightness = int(math.sin((i / max(1, width)) * math.pi) * 24)
            c = (
                max(0, min(255, color[0] + brightness)),
                max(0, min(255, color[1] + brightness)),
                max(0, min(255, color[2] + brightness)),
            )
            pygame.draw.line(fill_surf, c, (i, 0), (i, height))
        mask = pygame.Surface((fill_w, height), pygame.SRCALPHA)
        pygame.draw.rect(
            mask, (255, 255, 255, 255),
            (0, 0, fill_w, height), border_radius=radius,
        )
        fill_surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(fill_surf, (x, y))

    # ------------------------------------------------------ evolution

    def _draw_evolution_overlay(self, surface: pygame.Surface, game: Game) -> None:
        """Catalog-driven skill tree (replaces the old humanity evolution tree)."""
        w, h = self.screen_size
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 210))
        surface.blit(overlay, (0, 0))

        cat_color = game.gaia.active.arc_color
        self._update_evo_particles(w, h)
        self._draw_evo_particles(surface, cat_color)

        panel_rect = evolution_panel_rect(self.config)
        self._draw_shadow(surface, panel_rect, blur=26, alpha=190)
        self._fill_panel(surface, panel_rect, self.palette.surface_elevated)
        pygame.draw.rect(
            surface, cat_color, (panel_rect.left, panel_rect.top, panel_rect.width, 3)
        )

        # Header: title + ENERGY counter on the right. Wording depends on
        # which side the player picked at picker step -1.
        side = getattr(game, "player_side", "gaia")
        if side == "humanite":
            title_label = f"CONTRE-MESURES — {game.gaia.active.name.upper()}"
            sub_label = "Dépensez vos ressources pour atténuer la catastrophe."
        else:
            title_label = f"ÉVOLUTION — {game.gaia.active.name.upper()}"
            # Was "Configurez le scénario : faites évoluer la catastrophe
            # simulée." — "Configurez le scénario" read as an engine-side
            # technical instruction, breaking the GAIA-antagonist framing
            # the rest of the UI carries. Reworded as a direct call to
            # action in the same voice as the HUMANITÉ subtitle above.
            sub_label = "Renforcez chaque axe pour amplifier la catastrophe."
        title = self.fonts.title.render(title_label, True, self.palette.text)
        surface.blit(title, (panel_rect.left + 24, panel_rect.top + 16))
        sub = self.fonts.label.render(
            sub_label, True, self.palette.text_label,
        )
        surface.blit(sub, (panel_rect.left + 24, panel_rect.top + 16 + title.get_height() + 4))

        energy_label = self.fonts.label.render(
            "ÉNERGIE DISPONIBLE", True, self.palette.text_label,
        )
        energy_value = self.fonts.mono.render(
            str(game.humans.evolution_points), True, cat_color,
        )
        # Shift the energy block left so the × close button has room.
        energy_right = panel_rect.right - 24 - 36
        surface.blit(
            energy_label,
            (energy_right - energy_label.get_width(), panel_rect.top + 16),
        )
        surface.blit(
            energy_value,
            (energy_right - energy_value.get_width(),
             panel_rect.top + 16 + energy_label.get_height() + 4),
        )

        # Explicit × close button at the top-right corner. Players were
        # closing this panel via the keyboard binding (E) or by clicking
        # outside, both of which assume knowledge. The × is an obvious
        # affordance for everyone.
        close_rect = skill_tree_close_button_rect(self.config)
        close_hover = close_rect.collidepoint(pygame.mouse.get_pos())
        pygame.draw.circle(
            surface,
            self.palette.surface_overlay[:3] if close_hover else self.palette.surface[:3],
            close_rect.center, 14,
        )
        pygame.draw.circle(
            surface,
            cat_color if close_hover else self.palette.ui_border,
            close_rect.center, 14, 1,
        )
        cx_close, cy_close = close_rect.center
        x_color = self.palette.text if close_hover else self.palette.text_label
        pygame.draw.line(surface, x_color, (cx_close - 5, cy_close - 5), (cx_close + 5, cy_close + 5), 2)
        pygame.draw.line(surface, x_color, (cx_close + 5, cy_close - 5), (cx_close - 5, cy_close + 5), 2)

        # Axis tabs (4 pills) with progress counters (X/9 for this axis's 9 cards).
        active_axis = skill_tree_active_axis(game)
        mouse_pos = pygame.mouse.get_pos()
        for axis_name, tab_rect in skill_tree_axis_tab_rects(self.config).items():
            axis_skills = skill_tree_skills_for_axis(game, axis_name)
            owned = sum(
                1 for _t, sk in axis_skills
                if game.purchased_skills.get(sk.id, 0) > 0
            )
            label = (
                f"{SKILL_TREE_AXIS_LABELS.get(axis_name, axis_name)}  "
                f"{owned}/{len(axis_skills)}"
            )
            self._draw_pill(
                surface, tab_rect, label,
                active=axis_name == active_axis,
                tint=cat_color,
                hover=tab_rect.collidepoint(mouse_pos),
            )

        # Column headers (Fondations / Amplification / Transformation).
        # Each tier becomes a *grouped column*: a banner header on top of a
        # subtle cat-tinted background band that spans all 3 cards. That
        # way the 9 cards read as "3 ordered tier columns" instead of "9
        # loose tiles with floating labels above".
        cards = skill_tree_card_rects(self.config)
        if cards:
            # Per-tier deepening — the further along the ladder, the warmer
            # the column tint (subtle, alpha-staged) so progression is felt.
            band_alphas = (10, 14, 18)
            stripe_alphas = (90, 120, 150)
            banner_blends = (0.32, 0.42, 0.55)
            # Column band stretches from the top of the header band down to
            # the bottom of the last card row (cards[6..8] are the last row).
            last_row_bottom = max(cards[6].bottom, cards[7].bottom, cards[8].bottom)
            for c, label in enumerate(SKILL_TIER_LABELS):
                col_rect = cards[c]
                # ----- (1) Subtle column background band behind the 3 cards.
                band_top = col_rect.top - 32  # banner header sits inside this
                band_bottom = last_row_bottom + 6
                band_left = col_rect.left - 6
                band_right = col_rect.right + 6
                band_w = band_right - band_left
                band_h = band_bottom - band_top
                col_band = pygame.Surface((band_w, band_h), pygame.SRCALPHA)
                col_band.fill((*cat_color, band_alphas[c]))
                # Mask to rounded corners (top wider for banner, bottom rounded).
                mask = pygame.Surface((band_w, band_h), pygame.SRCALPHA)
                pygame.draw.rect(
                    mask, (255, 255, 255, 255),
                    pygame.Rect(0, 0, band_w, band_h),
                    border_radius=10,
                )
                col_band.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
                surface.blit(col_band, (band_left, band_top))
                # Left accent stripe — tier identity carrier on the column.
                stripe = pygame.Surface((2, band_h - 12), pygame.SRCALPHA)
                stripe.fill((*cat_color, stripe_alphas[c]))
                surface.blit(stripe, (band_left + 4, band_top + 6))

                # ----- (2) Banner header — cat-tinted rounded rect containing
                # the tier badge + label. Anchors the column header in place
                # of the previous floating "[1] LABEL  ────" treatment.
                banner_h = 24
                banner_rect = pygame.Rect(
                    col_rect.left, col_rect.top - banner_h - 6,
                    col_rect.width, banner_h,
                )
                banner_fill = _blend(
                    self.palette.surface_deep, cat_color, banner_blends[c],
                )
                pygame.draw.rect(
                    surface, banner_fill, banner_rect, border_radius=6,
                )
                # Top highlight stroke on the banner — depth.
                hi = pygame.Surface((banner_rect.width, banner_rect.height), pygame.SRCALPHA)
                pygame.draw.rect(
                    hi, (255, 255, 255, 38),
                    pygame.Rect(0, 0, banner_rect.width, banner_rect.height),
                    1, border_radius=6,
                )
                surface.blit(hi, banner_rect.topleft)

                # Tier badge — number pip on the left inside the banner.
                badge_size = 16
                num_text = self.fonts.label.render(
                    str(c + 1), True, self.palette.text,
                )
                label_text = self.fonts.label.render(
                    label, True, self.palette.text_label,
                )
                group_w = badge_size + 8 + label_text.get_width()
                group_x = banner_rect.centerx - group_w // 2
                badge_rect = pygame.Rect(
                    group_x,
                    banner_rect.centery - badge_size // 2,
                    badge_size, badge_size,
                )
                pygame.draw.rect(
                    surface, cat_color, badge_rect, border_radius=4,
                )
                surface.blit(
                    num_text,
                    (badge_rect.centerx - num_text.get_width() // 2,
                     badge_rect.centery - num_text.get_height() // 2),
                )
                # Label to the right of the badge — text colour bumped on the
                # banner for legibility against the warmer fill.
                surface.blit(
                    label_text,
                    (badge_rect.right + 8,
                     banner_rect.centery - label_text.get_height() // 2),
                )

        # 3×3 skill cards for the active axis.
        skills_for_axis = skill_tree_skills_for_axis(game, active_axis)
        # Detect level-ups since last frame → spawn burst at the card center.
        # Skipped on the first overlay open so pre-existing levels don't fire.
        if self._overlay_was_open:
            for idx, (_tier, sk) in enumerate(skills_for_axis):
                if idx >= len(cards):
                    break
                current = game.purchased_skills.get(sk.id, 0)
                previous = self._last_purchased_levels.get(sk.id, 0)
                if current > previous:
                    self.burst_at(cards[idx].centerx, cards[idx].centery, cat_color, count=10)
        # Sync snapshot + flag for next frame.
        self._last_purchased_levels = dict(game.purchased_skills)
        self._overlay_was_open = True
        # First pass: gather state for each card so we can find the recommended
        # (cheapest unowned + affordable + unlocked) before rendering.
        from gaia_ultimatum.models.game import SKILL_COST_MULTIPLIER
        card_states: list[dict] = []
        for idx, (_tier_label, skill) in enumerate(skills_for_axis):
            if idx >= len(cards):
                break
            current_level = game.purchased_skills.get(skill.id, 0)
            max_level = len(skill.levels)
            # Display the *effective* cost (JSON × SKILL_COST_MULTIPLIER)
            # so the price the player sees matches the price the purchase
            # path actually charges.
            next_cost = (
                max(1, int(round(skill.levels[current_level].cost * SKILL_COST_MULTIPLIER)))
                if current_level < max_level
                else None
            )
            affordable = (
                next_cost is not None
                and game.humans.evolution_points >= next_cost
            )
            unlocked = game.is_skill_unlocked(skill)
            card_states.append({
                "idx": idx,
                "skill": skill,
                "current_level": current_level,
                "max_level": max_level,
                "next_cost": next_cost,
                "affordable": affordable,
                "unlocked": unlocked,
            })

        # Cheapest unowned, affordable, unlocked card → the recommended-next pulse.
        recommended_idx: int | None = None
        cheapest_cost = float("inf")
        for st in card_states:
            if (
                st["current_level"] == 0
                and st["unlocked"]
                and st["affordable"]
                and st["next_cost"] is not None
                and st["next_cost"] < cheapest_cost
            ):
                cheapest_cost = st["next_cost"]
                recommended_idx = st["idx"]

        hovered_skill: Skill | None = None
        for st in card_states:
            card_rect = cards[st["idx"]]
            skill = st["skill"]
            hover = card_rect.collidepoint(mouse_pos)
            if hover:
                hovered_skill = skill
            selected = game.selected_skill_id == skill.id
            self._draw_skill_card(
                surface, card_rect, skill,
                current_level=st["current_level"],
                max_level=st["max_level"],
                next_cost=st["next_cost"],
                affordable=st["affordable"],
                unlocked=st["unlocked"],
                hover=hover,
                selected=selected,
                recommended=st["idx"] == recommended_idx,
                accent=cat_color,
                catastrophe_name=game.gaia.active.name,
            )

        # Detail panel — persistent, populated by selected_skill_id (or hovered fallback).
        detail_rect = skill_tree_detail_panel_rect(self.config)
        selected_skill = (
            game.skill_catalog.find_skill(game.selected_skill_id)
            if game.selected_skill_id
            else None
        )
        # If nothing selected, fall back to hover preview so the panel never feels dead.
        display_skill = selected_skill or hovered_skill
        self._draw_skill_detail_panel(
            surface, detail_rect, game, display_skill, cat_color,
            is_selected=display_skill is selected_skill and selected_skill is not None,
        )

    @staticmethod
    def _fit_text(text: str, font: pygame.font.Font, max_width: int) -> str:
        """Return ``text`` trimmed with an ellipsis when it would exceed max_width."""
        if font.size(text)[0] <= max_width:
            return text
        ellipsis = "…"
        # Binary-searchish: shrink one char at a time until it fits.
        for end in range(len(text) - 1, 0, -1):
            candidate = text[:end].rstrip() + ellipsis
            if font.size(candidate)[0] <= max_width:
                return candidate
        return ellipsis

    def _fit_text_progressive(
        self,
        text: str,
        max_width: int,
        candidates: tuple[pygame.font.Font, ...],
    ) -> tuple[str, pygame.font.Font]:
        """Pick the largest font from ``candidates`` that fits ``text`` whole.

        Falls back to ellipsising the last (smallest) font when nothing fits.
        Used by labels like skill names and country headers where shrinking
        is preferable to truncation — long French names (e.g. "République
        dém. du Congo", "Bosnie-Herzégovine") no longer get clipped to "..."
        when there's space for the full string at a smaller size.
        """
        for font in candidates:
            if font.size(text)[0] <= max_width:
                return text, font
        smallest = candidates[-1]
        return Renderer._fit_text(text, smallest, max_width), smallest

    @staticmethod
    def _wrap_text(
        text: str,
        font: pygame.font.Font,
        max_width: int,
        max_lines: int = 2,
    ) -> list[str]:
        """Greedy word-wrap into at most ``max_lines`` lines (last line ellipsizes)."""
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if font.size(candidate)[0] <= max_width:
                current = candidate
                continue
            if current:
                lines.append(current)
            current = word
            if len(lines) == max_lines - 1:
                break
        if current and len(lines) < max_lines:
            lines.append(current)
        # If we hit the cap mid-stream, ellipsize the last line.
        if len(lines) == max_lines:
            consumed = sum(len(line.split()) for line in lines)
            if consumed < len(words):
                last = " ".join(lines[-1].split() + words[consumed:])
                lines[-1] = Renderer._fit_text(last, font, max_width)
        return lines

    def _draw_skill_card(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        skill: Skill,
        *,
        current_level: int,
        max_level: int,
        next_cost: int | None,
        affordable: bool,
        unlocked: bool,
        hover: bool,
        selected: bool,
        recommended: bool,
        accent: tuple[int, int, int],
        catastrophe_name: str = "",
    ) -> None:
        """5-state skill card matching the modern mobile pattern.

        State precedence (highest → lowest): MAXED → LOCKED → OWNED-LEVELABLE
        (current_level > 0 < max) → AFFORDABLE-UNOWNED → UNAFFORDABLE.
        """
        is_max = current_level >= max_level
        is_locked = (not unlocked) and current_level == 0
        is_owned = current_level > 0 and not is_max
        is_affordable_unowned = (
            current_level == 0 and unlocked and affordable and next_cost is not None
        )

        # Recommended-next pulse — only on UNOWNED-AFFORDABLE cards (Genshin pattern,
        # one node max per axis selected by the renderer-level cheapest-affordable cache).
        if recommended and is_affordable_unowned:
            ticks = pygame.time.get_ticks()
            pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
            ring_alpha = int(60 + 80 * pulse)
            ring_w = rect.width + 12
            ring_h = rect.height + 12
            ring = pygame.Surface((ring_w, ring_h), pygame.SRCALPHA)
            pygame.draw.rect(
                ring, (*accent, ring_alpha),
                (0, 0, ring_w, ring_h),
                3, border_radius=14,
            )
            surface.blit(ring, (rect.left - 6, rect.top - 6))

        # Drop shadow (skipped for locked — they don't elevate).
        # Was a flat ``pygame.draw.rect((0, 0, 0), shadow_offset_down)``
        # producing a 4-px hard-edged solid-black sliver — read as a
        # cliff against the tree backdrop, not as soft material depth.
        # Every other elevated panel in the renderer (impact card,
        # settings overlay, pause confirm, outro tiles, picker cards,
        # skill detail panel) uses ``_draw_shadow``: a Pillow Gaussian-
        # blurred shadow cached per ``(w, h, blur, alpha)`` tuple via
        # ``_drop_shadow``. Cost is one Pillow filter at first render of
        # a given card size, then a pure blit on every subsequent frame
        # — cheaper than the hand-rolled rect once the cache fills.
        # ``blur=10`` / ``alpha=130`` is mid-elevation (cards sit between
        # a flat tile and a hero modal); ``offset_y=4`` preserves the
        # same downward bias as the prior shadow so the visual centre
        # of gravity reads identically.
        if not is_locked:
            self._draw_shadow(
                surface, rect, blur=10, alpha=130, offset_y=4,
            )

        # Pick visual style per state.
        if is_max:
            fill = (24, 50, 42)
            border = (110, 220, 150)
            badge_text = "MAÎTRISÉ ✓"
            badge_color = (110, 220, 150)
            name_color = self.palette.text
            border_w = 2
        elif is_locked:
            fill = (22, 26, 36)
            border = (72, 82, 102)
            badge_text = "VERROUILLÉ"
            # Brighter name on locked so it reads cleanly against the dark fill.
            badge_color = self.palette.text_label
            name_color = (210, 218, 232)
            border_w = 1
        elif is_owned:
            fill = _blend(self.palette.surface_deep, accent, 0.20)
            border = accent if (hover or selected) else _blend(self.palette.surface_deep, accent, 0.55)
            badge_text = f"NIV. {current_level + 1} — {next_cost} ÉN"
            badge_color = accent if affordable else self.palette.text_dim
            name_color = self.palette.text
            border_w = 2 if (hover or selected) else 1
        elif is_affordable_unowned:
            fill = (
                self.palette.surface_overlay[:3]
                if (hover or selected) else self.palette.surface_elevated[:3]
            )
            border = accent
            badge_text = f"+ {next_cost} ÉN"
            badge_color = accent
            name_color = self.palette.text
            border_w = 2 if (hover or selected) else 1
        else:  # UNAFFORDABLE
            fill = self.palette.surface_deep[:3]
            border = _blend(self.palette.surface_deep, accent, 0.25)
            badge_text = f"{next_cost} ÉN" if next_cost is not None else "—"
            badge_color = LIGHT_DANGER
            # Brighter than text_dim so the name still reads clearly when the
            # player can't yet afford the skill — they need to see what it is.
            name_color = self.palette.text_label
            border_w = 1

        pygame.draw.rect(surface, fill, rect, border_radius=10)
        # Gradient + edge-stroke depth — the skill cards are the most-
        # interacted-with surface in the skill tree screen, but their
        # body was flat while every other tactile chrome surface had
        # picked up the gradient + top-highlight + bottom-shadow
        # treatment. Now each of the 5 card states (max / locked /
        # owned / affordable / unaffordable) reads with the same
        # depth language as the buttons, settings rows, sidebar
        # two-col, and outro tiles. The drop shadow underneath, the
        # 5-state fill, the border, and the recommended-next pulse
        # ring are all unchanged — depth slots in between fill and
        # border in the existing render order.
        self._apply_button_depth(surface, rect, fill, radius=10)
        pygame.draw.rect(surface, border, rect, border_w, border_radius=10)

        # Selection ring (drawn after fill, before content, so it doesn't hide pips).
        if selected:
            sel_ring = pygame.Surface((rect.width + 6, rect.height + 6), pygame.SRCALPHA)
            pygame.draw.rect(
                sel_ring, (*self.palette.text, 200),
                (0, 0, rect.width + 6, rect.height + 6),
                2, border_radius=12,
            )
            surface.blit(sel_ring, (rect.left - 3, rect.top - 3))

        # Element badge — small disc on the left with the catastrophe icon.
        # Colour reflects state: filled tint for owned/maxed, ring-only for
        # affordable, very dim for locked. Gives every card a visual anchor.
        icon_r = 14
        icon_cx = rect.left + 12 + icon_r
        icon_cy = rect.top + 12 + icon_r
        if is_locked:
            ring_color = (52, 60, 76)
            icon_color = (70, 80, 96)
            inner_color = _blend((10, 12, 18), ring_color, 0.4)
        elif is_max:
            ring_color = (110, 220, 150)
            icon_color = (180, 240, 200)
            inner_color = _blend((10, 12, 18), ring_color, 0.6)
        elif is_owned:
            ring_color = accent
            icon_color = accent
            inner_color = _blend((10, 12, 18), accent, 0.6)
        else:
            ring_color = accent
            icon_color = accent
            inner_color = _blend((10, 12, 18), accent, 0.35)
        pygame.draw.circle(surface, inner_color, (icon_cx, icon_cy), icon_r)
        pygame.draw.circle(
            surface, ring_color, (icon_cx, icon_cy), icon_r,
            2 if (selected or hover) else 1,
        )
        if is_locked:
            # Padlock inside the element badge so locked state is communicated
            # with the same anchor every card uses — no collision with the
            # skill name on short cards.
            self._draw_padlock(
                surface, (icon_cx, icon_cy), icon_r - 4, icon_color,
            )
        elif catastrophe_name:
            self._draw_element_icon(
                surface, catastrophe_name,
                (icon_cx, icon_cy), icon_r - 5, icon_color,
            )

        # Title (right of the icon). Auto-fitted with progressive font
        # fallback (medium → small → ellipsized small) so long skill names
        # shrink rather than truncating with "..." when they don't fit at
        # the default font size.
        # Pip strip lives on the same row at the right edge; reserve its
        # width + an 8 px gap so the title can't bleed under the pips.
        # 28 French skill names overflowed at medium font when the pip
        # footprint wasn't reserved (e.g. "Effondrement de la Régulation
        # Climatique", "Production Pharmaceutique Continue") — they
        # rendered at medium and clipped the pips on the right.
        pip_r = 4
        pip_gap = 4
        total_pip_w = max_level * (pip_r * 2) + (max_level - 1) * pip_gap
        text_x = icon_cx + icon_r + 8
        title_max_w = rect.right - text_x - 14 - total_pip_w - 8
        fitted_name, fitted_font = self._fit_text_progressive(
            skill.name, title_max_w,
            (self.fonts.medium, self.fonts.small),
        )
        text = fitted_font.render(fitted_name, True, name_color)
        surface.blit(text, (text_x, rect.top + 14))

        # Level pips — circular this time, along the right edge.
        pip_x = rect.right - 14 - total_pip_w + pip_r
        pip_y = rect.top + 14 + pip_r
        for i in range(max_level):
            cx = pip_x + i * (pip_r * 2 + pip_gap)
            if i < current_level:
                fill_color = accent if not is_locked else (60, 70, 84)
                pygame.draw.circle(surface, fill_color, (cx, pip_y), pip_r)
            else:
                pygame.draw.circle(surface, (50, 58, 72), (cx, pip_y), pip_r, 1)

        # State / cost badge — always at the bottom-center now that locked
        # state is communicated via a padlock inside the element badge slot
        # (no overlap possible with the skill name above).
        badge = self.fonts.label.render(badge_text, True, badge_color)
        surface.blit(
            badge,
            (rect.centerx - badge.get_width() // 2,
             rect.bottom - badge.get_height() - 10),
        )

    def _draw_skill_detail_panel(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        game: Game,
        skill: Skill | None,
        accent: tuple[int, int, int],
        is_selected: bool,
    ) -> None:
        """Persistent detail panel: name + pips + before/after diff + impacts + AMÉLIORER."""
        # Background card.
        pygame.draw.rect(surface, self.palette.surface_deep[:3], rect, border_radius=10)
        # Catastrophe-tinted left edge to tie it to the rest of the chrome.
        pygame.draw.rect(
            surface, accent,
            (rect.left, rect.top + 10, 3, rect.height - 20),
        )
        pygame.draw.rect(surface, self.palette.ui_border_soft, rect, 1, border_radius=10)

        if skill is None:
            # Visual-first placeholder: big tinted element icon centred, then
            # a single line of hint text below. Gives the empty detail panel
            # presence instead of a lonely sentence.
            icon_r = 22
            icx = rect.centerx
            icy = rect.centery - 18
            pygame.draw.circle(
                surface, _blend((10, 12, 18), accent, 0.5),
                (icx, icy), icon_r,
            )
            pygame.draw.circle(surface, accent, (icx, icy), icon_r, 2)
            self._draw_element_icon(
                surface, game.gaia.active.name,
                (icx, icy), icon_r - 6, accent,
            )
            hint = self.fonts.medium.render(
                "Cliquez une compétence pour découvrir ses impacts.",
                True, self.palette.text_label,
            )
            surface.blit(
                hint,
                (rect.centerx - hint.get_width() // 2,
                 icy + icon_r + 14),
            )
            return

        from gaia_ultimatum.models.game import SKILL_COST_MULTIPLIER
        current_level = game.purchased_skills.get(skill.id, 0)
        max_level = len(skill.levels)
        is_max = current_level >= max_level
        unlocked = game.is_skill_unlocked(skill)
        next_cost = (
            max(1, int(round(skill.levels[current_level].cost * SKILL_COST_MULTIPLIER)))
            if not is_max else None
        )
        affordable = (
            next_cost is not None and game.humans.evolution_points >= next_cost
        )
        can_purchase = unlocked and affordable and not is_max

        # ---- Header strip (title + pips + AMÉLIORER button).
        # Was a magic ``240`` — the original coupled value back when the
        # button itself was 240 wide. ``SKILL_TREE_ACTION_BTN_W`` got
        # bumped to 264 to stop the affordable "AMÉLIORER · +{cost} ÉN"
        # label from ellipsising, but this local was missed. Symptom:
        # the content reservation (tabs, IMPACTS column, skill name
        # right-edge) all extended 24 px past where the actual 264-wide
        # button starts, so the button's left edge visually overlapped
        # into the content column — read as the button "overflowing".
        # Single-source the constant so any future width tweak stays
        # in lockstep across both call sites.
        button_w = SKILL_TREE_ACTION_BTN_W
        text_x = rect.left + 18
        text_w = rect.width - button_w - 36 - 18

        # Was ``fonts.title`` (~30 px) — shrunk to ``fonts.large`` so the
        # header takes less vertical space and the tab + content rows
        # below get more breathing room within the 168-px detail panel.
        name = self.fonts.large.render(skill.name, True, self.palette.text)
        surface.blit(name, (text_x, rect.top + 14))
        if is_selected:
            pygame.draw.circle(
                surface, accent,
                (text_x + name.get_width() + 14,
                 rect.top + 14 + name.get_height() // 2),
                4,
            )
        # Pip strip right under the title.
        pip_y = rect.top + 14 + name.get_height() + 8
        for i in range(max_level):
            color = accent if i < current_level else (50, 58, 72)
            pygame.draw.rect(
                surface, color,
                (text_x + i * 12, pip_y, 9, 9),
                0 if i < current_level else 1,
                border_radius=2,
            )

        # ---- Tab bar — APERÇU / IMPACTS / NIVEAUX.
        active_tab = max(0, min(2, getattr(game, "skill_detail_tab", 0)))
        for i, tab_rect in enumerate(skill_detail_tab_rects(self.config)):
            tab_labels = ("APERÇU", "IMPACTS", "NIVEAUX")
            self._draw_skill_detail_tab(
                surface, tab_rect, tab_labels[i],
                active=i == active_tab, accent=accent,
            )

        # ---- Tab content area.
        # Was ``pip_y + 30`` — anchored to the pip strip with a guessed
        # 30 px tab offset, which actually fell *inside* the tab band
        # (overlap). Now anchored to the actual tab bottom + 8 px so
        # content sits cleanly under the tabs regardless of font tweaks.
        first_tab = skill_detail_tab_rects(self.config)[0]
        content_top = first_tab.bottom + 8
        content_left = text_x
        content_right = rect.left + rect.width - button_w - 36
        content_w = content_right - content_left
        # Thread the game ref + visible bottom down to any tab that
        # needs scroll (APERÇU description, IMPACTS row list). The
        # tab functions are too deep in the call graph to plumb
        # through positional params without a wider refactor;
        # ``self`` attrs keep the change contained.
        self._skill_detail_game = game
        # Bottom of the scrollable region — leaves ~24 px for the
        # bottom rounded corner of the panel + breathing room.
        self._skill_detail_visible_bottom = rect.bottom - 24
        if active_tab == 0:
            self._draw_skill_tab_apercu(
                surface, skill, current_level, max_level,
                content_left, content_top, content_w, accent,
            )
        elif active_tab == 1:
            self._draw_skill_tab_impacts(
                surface, skill, current_level, max_level,
                content_left, content_top, content_w, accent,
            )
        else:
            self._draw_skill_tab_niveaux(
                surface, skill, current_level, max_level,
                content_left, content_top, content_w, accent,
            )

        # ---- Right column: AMÉLIORER button (always visible across tabs).
        btn_h = 56
        btn_rect = skill_tree_action_button_rect(self.config)
        if is_max:
            self._draw_action_button(
                surface, btn_rect,
                label="MAÎTRISÉ ✓",
                primary=False, hover=False,
            )
        elif not unlocked:
            self._draw_action_button(
                surface, btn_rect,
                label="VERROUILLÉ",
                primary=False, hover=False,
            )
        elif not affordable:
            # Was ``f"+{next_cost} ÉN  (manque)"`` with a double space
            # before the parenthesis — same double-space typo a prior
            # refinement fixed on the affordable sibling's label
            # ("AMÉLIORER  +X ÉN" → "AMÉLIORER · +X ÉN") but missed
            # here. Aligning the unaffordable label with the same
            # middle-dot pattern: parallel structure (cost · state for
            # unaffordable, action · cost for affordable), uppercase
            # state token to match other status labels (VERROUILLÉ,
            # MAÎTRISÉ), no parenthetical clutter.
            self._draw_action_button(
                surface, btn_rect,
                label=f"+{next_cost} ÉN · MANQUE",
                primary=False,
                hover=False,
            )
        else:
            mouse_pos = pygame.mouse.get_pos()
            hover = btn_rect.collidepoint(mouse_pos)
            self._draw_chunky_button(
                surface, btn_rect,
                # Middle-dot separator — was a double-space "AMÉLIORER
                # +{cost} ÉN" that read as a typo at small font sizes.
                # Mirrors the "PASSER · ÉCHAP" cinematic skip pill pattern.
                label=f"AMÉLIORER · +{next_cost} ÉN",
                primary=True,
                hover=hover,
                font=self.fonts.large,
            )

        # Right-click hint (only meaningful when current_level > 0).
        if current_level > 0:
            hint = self.fonts.label.render(
                "Clic droit pour rembourser un niveau",
                True, self.palette.text_dim,
            )
            surface.blit(
                hint,
                (btn_rect.centerx - hint.get_width() // 2,
                 btn_rect.bottom + 8),
            )

    def _draw_skill_detail_tab(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        *,
        active: bool,
        accent: tuple[int, int, int],
    ) -> None:
        """Pill-style tab inside the skill detail panel."""
        if active:
            # Darken accent so white text reads with proper contrast.
            tab_color = _blend(accent, (0, 0, 0), 0.40)
            pygame.draw.rect(surface, tab_color, rect, border_radius=rect.height // 2)
            text_color = (255, 255, 255)
        else:
            pygame.draw.rect(
                surface, self.palette.surface[:3], rect,
                border_radius=rect.height // 2,
            )
            pygame.draw.rect(
                surface,
                _blend(self.palette.surface_deep, accent, 0.35),
                rect, 1, border_radius=rect.height // 2,
            )
            text_color = self.palette.text_label
        text = self.fonts.label.render(label, True, text_color)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2,
             rect.centery - text.get_height() // 2),
        )

    def _draw_skill_tab_apercu(
        self,
        surface: pygame.Surface,
        skill: Skill,
        current_level: int,
        max_level: int,
        x: int, y: int, w: int,
        accent: tuple[int, int, int],
    ) -> None:
        """Tab 1 — diff card LEFT, EFFET description RIGHT (side-by-side).

        Was a vertical stack (diff card full-width on top, EFFET below)
        which combined badly with the 200-px panel height: after the
        title row + pip strip + tab bar (≈ 90 px) and the 80-px diff
        card (≈ 90 px including gap), only ~20 px remained for the
        EFFET label + description. The scrollable region's
        ``visible_h`` clamped to its 40-px minimum and the clip rect
        extended *below* the panel bottom, causing text to render
        into the chrome underneath. The side-by-side layout gives
        EFFET the FULL content-area height (≈ 100 px visible band)
        and the diff card stays as a compact left-column summary —
        wide enough for the before→after numbers, narrow enough to
        leave the description a real reading width.

        When the skill has no before→after diff (no numerical effect
        to compare), the EFFET section takes the full content width
        for an even more readable wrap.
        """
        diff_parts = self._before_after_parts(skill, current_level)
        # Column split: diff card on the left, description on the
        # right. Tuned to keep before→after numbers legible without
        # squeezing the description below ~22 chars/line.
        DIFF_CARD_W = 240
        COL_GAP = 16
        content_x = x  # starting x for EFFET section
        content_w = w  # starting w for EFFET section
        diff_top = y   # starting y for both columns
        if diff_parts is not None:
            metric_name, before_str, after_str = diff_parts
            # Compact card — was 80 px tall full-width; now 76 px tall
            # in a 240-px column. Vertical layout inside the card
            # stays similar (caption + before/arrow/after) but the
            # values centre within the narrower box.
            card_h = 76
            card_w = min(DIFF_CARD_W, w - 100)  # never starve EFFET
            card = pygame.Rect(x, y, card_w, card_h)
            pygame.draw.rect(
                surface, self.palette.surface_deep[:3], card,
                border_radius=10,
            )
            pygame.draw.rect(
                surface, _blend(self.palette.surface_deep, accent, 0.45),
                card, 1, border_radius=10,
            )
            # Caption strip at the top of the diff card.
            cap = self.fonts.label.render(
                metric_name.upper(), True, self.palette.text_label,
            )
            # Truncate metric name to card width if needed.
            cap = self.fonts.label.render(
                self._fit_text(metric_name.upper(), self.fonts.label, card_w - 28),
                True, self.palette.text_label,
            )
            surface.blit(cap, (card.left + 14, card.top + 8))
            # Before / arrow / after layout inside the narrower card.
            # Use ``large`` for both before AND after when the card
            # is narrow — ``hero`` would overflow on long values.
            after_font = self.fonts.large
            before_t = self.fonts.medium.render(
                before_str, True, self.palette.text_dim,
            )
            after_t = after_font.render(after_str, True, accent)
            arrow_w = 24
            mid = card.centery + 10
            # Right-align after_t inside the card.
            after_x = card.right - 12 - after_t.get_width()
            arrow_right = after_x - 6
            arrow_left = arrow_right - arrow_w
            before_x = arrow_left - 6 - before_t.get_width()
            # If before_str is too wide to fit in the card, drop it
            # entirely — the after value alone still communicates
            # the post-purchase state.
            if before_x >= card.left + 10:
                surface.blit(
                    before_t,
                    (before_x, mid - before_t.get_height() // 2),
                )
                # Arrow only when before is visible.
                ay = mid
                pygame.draw.line(
                    surface, accent,
                    (arrow_left, ay), (arrow_right - 5, ay),
                    2,
                )
                pygame.draw.polygon(
                    surface, accent,
                    [(arrow_right, ay),
                     (arrow_right - 7, ay - 4),
                     (arrow_right - 7, ay + 4)],
                )
            surface.blit(after_t, (after_x, mid - after_t.get_height() // 2))
            # Shift EFFET section to start to the right of the card.
            content_x = card.right + COL_GAP
            content_w = (x + w) - content_x
        # EFFET section. When diff_parts is None, content_x/content_w
        # stay at the full width; otherwise they're sized to the
        # right column. ``y`` stays at the column top so EFFET starts
        # at the same height as the diff card and uses the FULL
        # remaining vertical space — no longer competes for the 20-px
        # leftover after a vertically-stacked diff card.
        x = content_x
        w = content_w
        y = diff_top
        if skill.description:
            head = self.fonts.label.render(
                "EFFET", True, accent,
            )
            surface.blit(head, (x, y))
            y += head.get_height() + 4
            # ---- Scrollable description block ----
            scroll_top = y
            # Visible region: from here to ~36 px above the panel
            # bottom (room for the bottom rounded corner + breathing
            # room). ``rect`` isn't in scope here, so the visible
            # bottom is captured upstream and passed via a renderer
            # attr set by ``_draw_skill_detail_panel``.
            visible_bottom = getattr(
                self, "_skill_detail_visible_bottom", scroll_top + 200,
            )
            visible_h = max(40, visible_bottom - scroll_top)
            # Save existing clip; restore after the scrolled blits so
            # downstream rendering (right-column button) doesn't
            # inherit the description's narrow clip.
            prev_clip = surface.get_clip()
            game_ref = getattr(self, "_skill_detail_game", None)
            scroll_off = 0
            if game_ref is not None:
                scroll_off = max(0, int(getattr(
                    game_ref, "skill_detail_scroll", 0,
                )))
            surface.set_clip(pygame.Rect(x, scroll_top, w + 14, visible_h))
            # Internal y starts above the visible region by the scroll
            # offset. Negative starts mean some content scrolled past
            # the top; the clip hides it.
            inner_y = scroll_top - scroll_off
            for line in self._wrap_text(
                skill.description, self.fonts.small, w, max_lines=16,
            ):
                t = self.fonts.small.render(
                    line, True, self.palette.text,
                )
                surface.blit(t, (x, inner_y))
                inner_y += t.get_height() + 1
            # Pick the first impact description from the *current*
            # level (or level 0 if untouched) — the JSON's per-
            # indicator explanation, which carries the educational
            # context. Prefixed with a thin tint chevron so it reads
            # as the "real-world consequence" continuation of the
            # EFFET section.
            target_level = max(0, min(current_level, max_level - 1))
            if 0 <= target_level < len(skill.levels):
                impacts = skill.levels[target_level].impact_descriptions
                if impacts:
                    first_desc = next(iter(impacts.values()))
                    if first_desc:
                        inner_y += 4
                        # Small chevron "›" (single angle quote,
                        # well-supported by Inter).
                        chev = self.fonts.label.render("›", True, accent)
                        surface.blit(chev, (x, inner_y))
                        chev_w = chev.get_width() + 4
                        for line in self._wrap_text(
                            first_desc, self.fonts.small,
                            w - chev_w, max_lines=16,
                        ):
                            t = self.fonts.small.render(
                                line, True, self.palette.text_label,
                            )
                            surface.blit(t, (x + chev_w, inner_y))
                            inner_y += t.get_height() + 1
            # Restore clip + capture content height for the input
            # handler's scroll-bound clamping next frame.
            surface.set_clip(prev_clip)
            content_h = (inner_y + scroll_off) - scroll_top
            if game_ref is not None:
                game_ref.skill_detail_content_h = content_h
                game_ref.skill_detail_visible_h = visible_h
                # Clamp the scroll if the player wheeled past the
                # end (e.g. content shrank when they switched to a
                # shorter-described skill before the input handler
                # had a chance to reset).
                max_scroll = max(0, content_h - visible_h)
                if game_ref.skill_detail_scroll > max_scroll:
                    game_ref.skill_detail_scroll = max_scroll
            # Scrollbar — only when content actually overflows.
            # Widened from 3 px to 6 px (previously hard-to-click thin
            # sliver) and the geometry is stashed on game state so the
            # input handler can hit-test clicks + drags. The
            # ``hit_pad`` extends the clickable area 4 px on each side
            # of the visible bar so the player can land a click in
            # the *vicinity* of the bar without needing pixel-precise
            # aim — same idiom the orb hit-test uses for its hit
            # radius.
            if content_h > visible_h:
                bar_x = x + w + 6
                track_top = scroll_top
                track_h = visible_h
                BAR_W = 6
                HIT_PAD = 4
                # Track (dim, behind the thumb).
                pygame.draw.rect(
                    surface,
                    _blend(self.palette.surface_deep[:3], accent, 0.30),
                    (bar_x, track_top, BAR_W, track_h),
                    border_radius=3,
                )
                # Thumb sized to visible_h / content_h fraction.
                thumb_h = max(20, int(track_h * visible_h / content_h))
                thumb_y_max = track_h - thumb_h
                thumb_progress = (
                    min(1.0, scroll_off / max(1, content_h - visible_h))
                )
                thumb_y = track_top + int(thumb_progress * thumb_y_max)
                pygame.draw.rect(
                    surface, accent,
                    (bar_x, thumb_y, BAR_W, thumb_h),
                    border_radius=3,
                )
                # Stash the hit-test rect (track + pad) on game so the
                # input handler can route clicks here without re-doing
                # the panel layout math.
                if game_ref is not None:
                    game_ref.skill_detail_scrollbar = (
                        bar_x - HIT_PAD,
                        track_top,
                        BAR_W + HIT_PAD * 2,
                        track_h,
                    )
            else:
                # No overflow → clear the stashed rect so a stale value
                # from a previous skill's long description doesn't keep
                # eating clicks in the same screen region.
                if game_ref is not None:
                    game_ref.skill_detail_scrollbar = None

    def _draw_skill_tab_impacts(
        self,
        surface: pygame.Surface,
        skill: Skill,
        current_level: int,
        max_level: int,
        x: int, y: int, w: int,
        accent: tuple[int, int, int],
    ) -> None:
        """Tab 2 — environmental impacts as a vertically-stacked,
        scrollable list of rows.

        Was a 2×2 grid of 56-px-tall mini-tiles where each description
        got hard-truncated by ``_fit_text`` to a single line — JSON
        descriptions are typically 80-150 chars, so the educational
        text was always ellipsized to ~30 chars and the *point* of the
        tab (showing the per-indicator real-world effect) collapsed
        into "first 4 words…". Tile height (56 px) couldn't hold more
        than one line; tile width (~230 px) couldn't hold long lines.

        New layout: vertical stack, one row per indicator. Each row:
          - Icon badge top-left
          - Indicator name (small caps) at top, next to icon
          - Description wrapped over multiple lines below the name
            with ``_wrap_text(max_lines=4)`` — never truncated below
            4 lines of small text per indicator
        Total content can easily exceed the 100-px visible band so
        the same scroll mechanism as APERÇU is reused: clipped region
        + scroll-offset blit + scrollbar drawn on the right when
        content overflows + scrollbar geometry stashed on game state
        for the input handler's click+drag routing.

        Switching tabs already resets ``skill_detail_scroll`` to 0 in
        the input handler, so opening IMPACTS always lands the player
        at the top of the list.
        """
        target_level = (
            skill.levels[current_level] if current_level < max_level
            else skill.levels[-1]
        )
        game_ref = getattr(self, "_skill_detail_game", None)
        if not target_level.impact_descriptions:
            t = self.fonts.medium.render(
                "Aucun impact détaillé pour ce palier.",
                True, self.palette.text_label,
            )
            surface.blit(t, (x, y))
            # Empty state has no overflow — clear the scrollbar state
            # so a stale rect from a previous skill doesn't keep
            # eating clicks here.
            if game_ref is not None:
                game_ref.skill_detail_content_h = 0
                game_ref.skill_detail_visible_h = 0
                game_ref.skill_detail_scrollbar = None
            return

        items = list(target_level.impact_descriptions.items())

        # ---- Scrollable region setup (mirrors APERÇU). ----
        scroll_top = y
        visible_bottom = getattr(
            self, "_skill_detail_visible_bottom", scroll_top + 200,
        )
        visible_h = max(40, visible_bottom - scroll_top)
        prev_clip = surface.get_clip()
        scroll_off = 0
        if game_ref is not None:
            scroll_off = max(0, int(getattr(
                game_ref, "skill_detail_scroll", 0,
            )))
        # Clip width includes the scrollbar's hit pad so the bar can
        # render inside the clip without being chopped off.
        surface.set_clip(pygame.Rect(x, scroll_top, w + 14, visible_h))

        inner_y = scroll_top - scroll_off
        icon_r = 12  # smaller than the prior 14 — keeps each row compact
        ROW_GAP = 10
        for indicator, desc in items:
            row_top = inner_y
            icon_cx = x + 8 + icon_r
            icon_cy = row_top + 10 + icon_r
            # Indicator icon — circular badge on the left.
            pygame.draw.circle(
                surface, _blend((10, 12, 18), accent, 0.5),
                (icon_cx, icon_cy), icon_r,
            )
            pygame.draw.circle(
                surface, accent, (icon_cx, icon_cy), icon_r, 2,
            )
            self._draw_indicator_glyph(
                surface, indicator,
                (icon_cx, icon_cy), icon_r - 4, accent,
            )
            # Name + multi-line description to the right of the icon.
            text_x = icon_cx + icon_r + 8
            text_w_inner = (x + w) - text_x
            short_name = self._indicator_short(indicator)
            name_t = self.fonts.label.render(
                short_name.upper(), True, accent,
            )
            surface.blit(name_t, (text_x, row_top + 6))
            line_y = row_top + 6 + name_t.get_height() + 3
            for line in self._wrap_text(
                desc, self.fonts.small, text_w_inner, max_lines=4,
            ):
                t = self.fonts.small.render(
                    line, True, self.palette.text,
                )
                surface.blit(t, (text_x, line_y))
                line_y += t.get_height() + 1
            # Thin separator hairline at the bottom of each row except
            # the last — gives the list visual rhythm without the heavy
            # tile borders of the prior 2×2 grid.
            row_bottom = max(line_y, icon_cy + icon_r) + 2
            pygame.draw.line(
                surface,
                _blend(self.palette.surface_deep[:3], accent, 0.20),
                (x, row_bottom),
                (x + w, row_bottom),
                1,
            )
            inner_y = row_bottom + ROW_GAP

        # ---- Restore clip + capture content height. ----
        surface.set_clip(prev_clip)
        content_h = (inner_y + scroll_off) - scroll_top
        if game_ref is not None:
            game_ref.skill_detail_content_h = content_h
            game_ref.skill_detail_visible_h = visible_h
            max_scroll = max(0, content_h - visible_h)
            if game_ref.skill_detail_scroll > max_scroll:
                game_ref.skill_detail_scroll = max_scroll

        # ---- Scrollbar (same idiom + cliclable hit-area as APERÇU). ----
        if content_h > visible_h:
            bar_x = x + w + 6
            track_top = scroll_top
            track_h = visible_h
            BAR_W = 6
            HIT_PAD = 4
            pygame.draw.rect(
                surface,
                _blend(self.palette.surface_deep[:3], accent, 0.30),
                (bar_x, track_top, BAR_W, track_h),
                border_radius=3,
            )
            thumb_h = max(20, int(track_h * visible_h / content_h))
            thumb_y_max = track_h - thumb_h
            thumb_progress = (
                min(1.0, scroll_off / max(1, content_h - visible_h))
            )
            thumb_y = track_top + int(thumb_progress * thumb_y_max)
            pygame.draw.rect(
                surface, accent,
                (bar_x, thumb_y, BAR_W, thumb_h),
                border_radius=3,
            )
            if game_ref is not None:
                game_ref.skill_detail_scrollbar = (
                    bar_x - HIT_PAD, track_top,
                    BAR_W + HIT_PAD * 2, track_h,
                )
        else:
            if game_ref is not None:
                game_ref.skill_detail_scrollbar = None

    @staticmethod
    def _indicator_short(indicator: str) -> str:
        """Tighten verbose indicator names for tile labels."""
        return {
            "Resilience Technologique": "Tech.",
            "Stabilite Societale":      "Société",
            "Regeneration Ecologique":  "Écologie",
            "Adaptation Evolutive":     "Évolution",
        }.get(indicator, indicator)

    def _draw_indicator_glyph(
        self,
        surface: pygame.Surface,
        indicator: str,
        center: tuple[int, int],
        r: int,
        color: tuple[int, int, int],
    ) -> None:
        """Procedural glyph per indicator (gear / people / leaf / DNA).

        Each glyph reads at the impact card's 12 px radius AND the info-
        panel ÉQUILIBRE tab's 26 px dials. Refinements over the first
        draft:

          * **Gear** now has 6 radial teeth (was 4) so the silhouette
            reads as a cog, not a cross-in-circle. Tooth tips also
            extend further (r+3 vs r+1) so they're not just nubs.
          * **Society** now has a small arc connecting the two heads —
            signals "community / network" rather than "two strangers".
            Matches the "stabilité sociétale" indicator name (which is
            about social *cohesion*, not just population).
          * **Leaf** is now a proper asymmetric teardrop with two
            quadratic Bézier curves instead of a 4-corner diamond.
            Two side veins branch off the central spine for the kind
            of leaf-shape that reads instantly even at thumbnail size.
          * **DNA** keeps the two S-curves but gains four horizontal
            rungs at the crossing points — reads as the base-pair
            ladder, not just "two parallel waves".
        """
        cx, cy = center
        thick = max(2, r // 3)
        if "Technologique" in indicator:
            # Gear cog — circle with 6 radial teeth at hexagonal spacing.
            # Was 4 teeth (cardinals only); reading at 12 px the result
            # looked like a circled cross. Six teeth gives the silhouette
            # an unambiguous cog shape.
            pygame.draw.circle(surface, color, (cx, cy), r, thick)
            tooth_outer = r + 3
            tooth_inner = r - 1
            for k in range(6):
                ang = math.pi * 2 * k / 6
                ex = int(cx + math.cos(ang) * tooth_outer)
                ey = int(cy + math.sin(ang) * tooth_outer)
                ix = int(cx + math.cos(ang) * tooth_inner)
                iy = int(cy + math.sin(ang) * tooth_inner)
                pygame.draw.line(surface, color, (ix, iy), (ex, ey), thick)
            # Centre dot — gives the gear a hub instead of a hollow.
            pygame.draw.circle(surface, color, (cx, cy), max(1, r // 4))
        elif "Societale" in indicator:
            # Two-figure silhouette + an arc above the heads connecting
            # them. The arc reads as "community / interaction" — turns
            # the icon from "two strangers" into "two people in a
            # relationship", which matches what *stabilité sociétale*
            # actually measures (social cohesion, not headcount).
            head_y = cy - r // 3
            head_r = thick
            shoulder_y = cy - r // 8
            foot_y = cy + r // 2
            for x_off in (-r // 2, r // 2):
                pygame.draw.circle(
                    surface, color, (cx + x_off, head_y), head_r,
                )
                pygame.draw.line(
                    surface, color,
                    (cx + x_off, shoulder_y),
                    (cx + x_off, foot_y),
                    thick,
                )
            # Connecting arc over the heads — thin so it reads as a
            # link, not a third element competing for attention.
            arc_top_y = head_y - head_r - 4
            arc_left = cx - r // 2
            arc_right = cx + r // 2
            arc_steps = 14
            arc_prev = None
            for i in range(arc_steps + 1):
                t = i / arc_steps
                ax = arc_left + int(t * (arc_right - arc_left))
                # Inverted parabola — dips down at the centre by ~3 px.
                ay = arc_top_y + int((1 - 4 * (t - 0.5) ** 2) * 3) - 1
                if arc_prev is not None:
                    pygame.draw.line(
                        surface, color, arc_prev, (ax, ay), max(1, thick - 1),
                    )
                arc_prev = (ax, ay)
        elif "Ecologique" in indicator:
            # Leaf — proper asymmetric teardrop with two side veins.
            # Built from two quadratic Bézier curves meeting at the tip
            # and base, then a centre spine + two angled side veins
            # branching off the spine. The previous diamond polygon
            # (4 sharp corners, vertical-only vein) read as a kite or
            # rhombus glyph, not a plant.
            tip = (cx, cy - r)
            base = (cx + r // 4, cy + r)  # slight rightward tilt
            # Control points push the curves outward to create the
            # convex sides of the leaf.
            ctrl_left = (cx - r * 4 // 5, cy + r // 6)
            ctrl_right = (cx + r * 4 // 5, cy - r // 4)
            steps = 22
            left_pts = []
            right_pts = []
            for i in range(steps + 1):
                t = i / steps
                # Left side: tip → ctrl_left → base
                lx = (1 - t) ** 2 * tip[0] + 2 * (1 - t) * t * ctrl_left[0] + t * t * base[0]
                ly = (1 - t) ** 2 * tip[1] + 2 * (1 - t) * t * ctrl_left[1] + t * t * base[1]
                left_pts.append((int(lx), int(ly)))
                # Right side: tip → ctrl_right → base
                rx = (1 - t) ** 2 * tip[0] + 2 * (1 - t) * t * ctrl_right[0] + t * t * base[0]
                ry = (1 - t) ** 2 * tip[1] + 2 * (1 - t) * t * ctrl_right[1] + t * t * base[1]
                right_pts.append((int(rx), int(ry)))
            pygame.draw.polygon(
                surface, color, left_pts + list(reversed(right_pts)), thick,
            )
            # Centre spine.
            pygame.draw.line(surface, color, tip, base, max(1, thick - 1))
            # Two side veins, branching from the spine at ~1/3 and 2/3
            # of its length, angled toward the leaf edge.
            mid1 = (
                (tip[0] * 2 + base[0]) // 3,
                (tip[1] * 2 + base[1]) // 3,
            )
            mid2 = (
                (tip[0] + base[0] * 2) // 3,
                (tip[1] + base[1] * 2) // 3,
            )
            # Pick a point on the leaf edge near each midpoint.
            edge1_left = left_pts[len(left_pts) // 3]
            edge1_right = right_pts[len(right_pts) // 3]
            edge2_left = left_pts[2 * len(left_pts) // 3]
            edge2_right = right_pts[2 * len(right_pts) // 3]
            for spine_pt, edge_pt in (
                (mid1, edge1_left), (mid1, edge1_right),
                (mid2, edge2_left), (mid2, edge2_right),
            ):
                pygame.draw.line(
                    surface, color, spine_pt, edge_pt, max(1, thick - 2),
                )
        elif "Evolutive" in indicator or "evolutive" in indicator.lower():
            # DNA double-helix — two S-curves + horizontal "rungs" at
            # the crossing points so the result reads as a base-pair
            # ladder instead of two unrelated sine waves.
            steps = 12
            curves = {}
            for direction in (1, -1):
                pts = []
                for s in range(steps + 1):
                    t = s / steps
                    py = cy - r + int(t * 2 * r)
                    px = cx + int(direction * math.sin(t * math.pi * 2) * r * 0.7)
                    pts.append((px, py))
                pygame.draw.lines(surface, color, False, pts, thick)
                curves[direction] = pts
            # Horizontal rungs at the t-values where the two helices
            # cross (sin = 0 at t = 0, 0.5, 1.0). Skip the endpoints to
            # avoid drawing nubs at the tips of the glyph.
            rung_color = _blend(color, (0, 0, 0), 0.25)
            for rung_t in (0.25, 0.50, 0.75):
                idx = int(rung_t * steps)
                if 0 < idx < steps:
                    left = curves[-1][idx]
                    right = curves[1][idx]
                    pygame.draw.line(
                        surface, rung_color, left, right, max(1, thick - 1),
                    )
        else:
            # Fallback — small dot.
            pygame.draw.circle(surface, color, (cx, cy), thick)

    def _draw_skill_tab_niveaux(
        self,
        surface: pygame.Surface,
        skill: Skill,
        current_level: int,
        max_level: int,
        x: int, y: int, w: int,
        accent: tuple[int, int, int],
    ) -> None:
        """Tab 3 — visual level path: connected hexagonal nodes with state-aware fills.

        Each node represents one level. A connecting line traces from one to
        the next so the progression reads as a journey rather than a row of
        disconnected cells.
        """
        cap = self.fonts.label.render(
            "PARCOURS DE PROGRESSION", True, self.palette.text_label,
        )
        surface.blit(cap, (x, y))
        # Tightened vertical rhythm — was cap+14 / node_r=24 / label+6, which
        # totalled ~96 px and pushed the cost labels past the bottom of the
        # 168-px detail panel. Shrunk nodes (radius 24 → 14), trimmed the
        # caption gap (14 → 6), and pulled labels closer to the node (6 → 4)
        # so the full path fits within the ~68 px content band.
        y += cap.get_height() + 6
        # Lay out N nodes evenly across the width, joined by a track line.
        node_r = 14
        track_y = y + node_r
        if max_level == 1:
            xs = [x + w // 2]
        else:
            step = (w - node_r * 2) // (max_level - 1)
            xs = [x + node_r + i * step for i in range(max_level)]
        # Draw track line behind nodes — segmented so owned portion is brighter.
        for i in range(max_level - 1):
            seg_color = (
                accent if i < current_level
                else _blend(self.palette.surface_deep, accent, 0.4)
            )
            pygame.draw.line(
                surface, seg_color,
                (xs[i] + node_r - 2, track_y),
                (xs[i + 1] - node_r + 2, track_y),
                3 if i < current_level else 2,
            )
        # Nodes.
        for i, cx in enumerate(xs):
            owned = i < current_level
            current = i == current_level
            if owned:
                fill = accent
                border = accent
                num_color = (250, 252, 255)
                glow = True
            elif current:
                fill = _blend(self.palette.surface_elevated, accent, 0.18)
                border = accent
                num_color = (250, 252, 255)
                glow = True
            else:
                fill = self.palette.surface_deep[:3]
                border = _blend(self.palette.surface_deep, accent, 0.3)
                num_color = self.palette.text_label
                glow = False
            # Subtle pulse glow around the current target node.
            # Glow radius pulled in (node_r+6 → node_r+4) to match the
            # smaller node footprint.
            if current:
                pulse = 0.5 + 0.5 * math.sin(pygame.time.get_ticks() * 0.005)
                glow_r = node_r + 4 + int(2 * pulse)
                glow_surf = pygame.Surface(
                    (glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA,
                )
                pygame.draw.circle(
                    glow_surf, (*accent, int(80 + 60 * pulse)),
                    (glow_r + 2, glow_r + 2), glow_r, 2,
                )
                surface.blit(
                    glow_surf,
                    (cx - glow_r - 2, track_y - glow_r - 2),
                )
            pygame.draw.circle(surface, fill, (cx, track_y), node_r)
            pygame.draw.circle(
                surface, border, (cx, track_y), node_r,
                2 if (owned or current) else 1,
            )
            if owned:
                # Centred checkmark glyph drawn from two strokes.
                self._draw_check(surface, (cx, track_y), node_r // 2, num_color)
            else:
                # ``medium`` (was ``large``) — fits the smaller node radius
                # without the glyph spilling outside the circle.
                num = self.fonts.medium.render(str(i + 1), True, num_color)
                surface.blit(
                    num,
                    (cx - num.get_width() // 2, track_y - num.get_height() // 2),
                )
            # Cost / status beneath the node.
            if owned:
                under = "ACQUIS"
                under_color = accent
            elif current:
                under = f"{skill.levels[i].cost} ÉN"
                under_color = self.palette.text
            else:
                under = f"{skill.levels[i].cost} ÉN"
                under_color = self.palette.text_label
            under_t = self.fonts.label.render(under, True, under_color)
            surface.blit(
                under_t,
                (cx - under_t.get_width() // 2, track_y + node_r + 4),
            )

    @staticmethod
    def _draw_check(
        surface: pygame.Surface,
        center: tuple[int, int],
        r: int,
        color: tuple[int, int, int],
    ) -> None:
        """Two-stroke procedural checkmark inside a circular node.

        Was three line segments at constant width 3 — readable on a
        clean surface but the joints jaggy at the bend point, and the
        white stroke could vanish against a near-white evolution node
        fill. Now stroked in two passes:

          1. **Dark halo underlay** at width 5 — gives the check a
             1-px outline so it reads against any fill colour.
          2. **Coloured stroke** at width 3 (original) on top.

        Plus a small filled circle at the bend joint to soften the
        angle — the previous polyline had a visible kink there at
        zoom-in / hi-DPI rendering.
        """
        cx, cy = center
        pts = [
            (cx - r, cy + r // 4),
            (cx - r // 4, cy + r),
            (cx + r, cy - r // 2),
        ]
        # Dark halo underlay so the check is legible against any fill.
        # Black tinted toward the foreground colour keeps it from
        # reading as pure black on coloured backdrops.
        halo_color = (10, 12, 18)
        pygame.draw.lines(surface, halo_color, False, pts, 5)
        # Original coloured stroke on top.
        pygame.draw.lines(surface, color, False, pts, 3)
        # Joint smoother — small filled circle at the bend so the
        # 100°-ish angle doesn't show a hard corner. Coloured to
        # match the stroke so it disappears into the line.
        pygame.draw.circle(surface, color, pts[1], 2)

    def _before_after_diff(self, skill: Skill, current_level: int) -> str:
        """Build a "Rayon 10 km → 20 km" diff string for the first effect.

        Returns "" when there's no meaningful diff to show (no effects, max level,
        or only one level defined).
        """
        parts = self._before_after_parts(skill, current_level)
        if parts is None:
            return ""
        key, before_str, after_str = parts
        if not before_str:
            return f"{key} : {after_str}"
        return f"{key} : {before_str} → {after_str}"

    def _before_after_parts(
        self, skill: Skill, current_level: int,
    ) -> tuple[str, str, str] | None:
        """Return (metric_name, before, after) for the first effect's diff.

        Used by the APERÇU tab to render before/after as separate visual
        blocks. Returns None when there's nothing to show.
        """
        max_level = len(skill.levels)
        if max_level == 0 or current_level >= max_level:
            return None
        next_level = skill.levels[current_level]
        if not next_level.effects:
            return None
        key = next(iter(next_level.effects))
        next_value = next_level.effects[key]
        if current_level == 0:
            return (key, "", str(next_value))
        prev_value = skill.levels[current_level - 1].effects.get(key, "?")
        return (key, str(prev_value), str(next_value))

    def _draw_skill_tooltip(
        self,
        surface: pygame.Surface,
        panel_rect: pygame.Rect,
        y: int,
        height: int,
        game: Game,
        skill: Skill | None,
        accent: tuple[int, int, int],
    ) -> None:
        if skill is None:
            hint = self.fonts.small.render(
                "Survolez une compétence pour voir ses effets — clic pour faire évoluer la catastrophe.",
                True, self.palette.text_dim,
            )
            surface.blit(
                hint,
                (panel_rect.centerx - hint.get_width() // 2,
                 y + height // 2 - hint.get_height() // 2),
            )
            return
        # Skill flavor + first impact description.
        x = panel_rect.left + 24
        name = self.fonts.medium.render(skill.name, True, self.palette.text)
        surface.blit(name, (x, y))
        flavor_text = self._fit_text(
            skill.description, self.fonts.small, panel_rect.width - 48,
        )
        flavor = self.fonts.small.render(flavor_text, True, self.palette.text_dim)
        surface.blit(flavor, (x, y + name.get_height() + 2))
        # Pull the next-level impact description for one indicator.
        current_level = game.purchased_skills.get(skill.id, 0)
        target_level = skill.levels[current_level] if current_level < len(skill.levels) else (
            skill.levels[-1] if skill.levels else None
        )
        if target_level and target_level.impact_descriptions:
            indicator, desc = next(iter(target_level.impact_descriptions.items()))
            impact = self.fonts.small.render(
                self._fit_text(
                    f"{indicator}: {desc}", self.fonts.small, panel_rect.width - 48,
                ),
                True, accent,
            )
            surface.blit(
                impact, (x, y + name.get_height() + 2 + flavor.get_height() + 4),
            )

    def _draw_evolution_node(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        node_name: str,
        cost: int,
        purchased: bool,
        unlocked: bool,
        affordable: bool,
        hovered: bool,
        tier: int = 0,
        accent: tuple[int, int, int] | None = None,
    ) -> None:
        accent = accent or self.palette.ui_accent
        if purchased:
            fill = (24, 50, 42)
            border = (90, 200, 140)
            name_color = self.palette.text
            cost_color = (90, 200, 140)
            cost_label = "ACQUIS"
            tier_dot = (90, 200, 140)
        elif not unlocked:
            fill = (18, 22, 30)
            border = (52, 60, 74)
            name_color = self.palette.text_dim
            cost_color = self.palette.text_dim
            cost_label = "VERROUILLÉ"
            tier_dot = (60, 70, 85)
        elif not affordable:
            fill = (28, 24, 32)
            border = _blend(self.palette.surface_deep, accent, 0.35)
            name_color = self.palette.text_dim
            cost_color = self.palette.text_dim
            cost_label = f"{cost} ADN"
            tier_dot = _blend(self.palette.surface_deep, accent, 0.45)
        else:
            fill = (
                self.palette.surface_overlay[:3]
                if hovered
                else self.palette.surface_elevated[:3]
            )
            border = accent if hovered else _blend(self.palette.surface_deep, accent, 0.5)
            name_color = self.palette.text
            cost_color = accent
            cost_label = f"{cost} ADN"
            tier_dot = accent

        # Drop shadow for elevation. Soft Pillow Gaussian (cached)
        # replaces the prior flat 3-px-down solid-black rect —
        # cards now grade smoothly into the panel they sit on
        # instead of reading as paper cutouts on cardboard.
        self._draw_shadow(surface, rect, blur=10, alpha=130, offset_y=3)
        pygame.draw.rect(surface, fill, rect, border_radius=8)
        pygame.draw.rect(surface, border, rect, 2 if hovered else 1, border_radius=8)

        # Tier indicator: small dots top-left showing the tier (0..3).
        dot_y = rect.top + 8
        dot_size = 4
        dot_gap = 3
        for i in range(4):
            dx = rect.left + 8 + i * (dot_size + dot_gap)
            color = tier_dot if i <= tier else (40, 46, 56)
            pygame.draw.circle(surface, color, (dx + dot_size // 2, dot_y + dot_size // 2), dot_size // 2 + 1)

        # Name (centered, up to 2 lines, wrapped).
        name_lines = _wrap(node_name, 18)[:2]
        name_block_h = sum(self.fonts.small.size(l)[1] for l in name_lines) + (len(name_lines) - 1) * 2
        name_y = rect.top + 22 + (rect.height - 22 - 18 - name_block_h) // 2
        for line in name_lines:
            text = self.fonts.small.render(line, True, name_color)
            surface.blit(
                text,
                (rect.centerx - text.get_width() // 2, name_y),
            )
            name_y += text.get_height() + 2

        # Cost / state label centered at the bottom.
        cost_text = self.fonts.label.render(cost_label, True, cost_color)
        surface.blit(
            cost_text,
            (rect.centerx - cost_text.get_width() // 2, rect.bottom - cost_text.get_height() - 8),
        )

    # ----------------------------------------------------------- title

    def _draw_title_screen(
        self,
        surface: pygame.Surface,
        reduce_motion: bool = False,
        last_run: dict | None = None,
    ) -> None:
        w, h = self.screen_size

        # ---- Vertical gradient backdrop (cached). ----
        bg = self._gradient_surface(
            w, h, (45, 45, 65, 255), (16, 16, 24, 255)
        )
        surface.blit(bg, (0, 0))

        # ---- Procedural Earth rising from below the horizon. ----
        self._draw_title_planet(surface)

        # ---- Ambient particle field (skipped when reduce-motion is on). ----
        if not reduce_motion:
            self._update_title_particles(w, h)
            self._draw_title_particles(surface)

        # ---- Cinematic intro envelopes — title drifts in from above, then
        # subtitle, then buttons cascade up. Times are relative to the moment
        # the player landed on the TITLE phase (so the cinematic also fires
        # on every restart-to-title, not only on first launch).
        elapsed_ms = pygame.time.get_ticks() - self._phase_transition_start_ms
        if reduce_motion:
            title_drift = 0
            title_alpha = 255
            sub_drift = 0
            sub_alpha = 255
        else:
            title_intro_t = min(1.0, max(0.0, elapsed_ms / 700))
            title_drift = int((1.0 - title_intro_t) * -28)
            title_alpha = int(255 * (title_intro_t ** 0.6))
            sub_intro_t = min(1.0, max(0.0, (elapsed_ms - 350) / 550))
            sub_drift = int((1.0 - sub_intro_t) * -14)
            sub_alpha = int(255 * (sub_intro_t ** 0.6))

        # ---- Title with sin-bob + blue glow ghost. ----
        ticks = pygame.time.get_ticks()
        bob = math.sin(ticks / 600) * 8
        title_y = int(h // 2 - 220 + bob + title_drift)

        glow = self.fonts.giant.render("TERRE VIVANTE", True, (90, 110, 220))
        # Title text uses ``palette.text`` rather than the hardcoded
        # ``(245, 248, 255)`` literal it had — the value is identical
        # today, but routing through the palette ties the title text
        # to the same source of truth the dashboard and overlays read
        # so any future tonal shift on the primary text colour lands
        # on the title in lockstep. Glow stays hardcoded — that
        # cool-blue tone is the title's own visual identity, not part
        # of the text-colour family.
        title = self.fonts.giant.render("TERRE VIVANTE", True, self.palette.text)
        # 8-direction radial halo (was 4-direction plus-cross — same
        # bug fixed earlier this session on ``_draw_text_centered``
        # and ``_draw_floating_texts``). Diagonals get alpha scaled
        # by 1/sqrt(2) ≈ 0.707 to match the inverse-distance falloff
        # (cardinals at 1.0 px, diagonals at √2 ≈ 1.41 px). Produces
        # a properly round halo instead of leaving visible empty
        # diagonals around the giant title text — the first
        # impression the player gets when launching the game.
        diag_glow = glow.copy()
        diag_glow.set_alpha(int(255 * 0.707))
        if title_alpha < 255:
            comp = pygame.Surface(
                (title.get_width() + 4, title.get_height() + 4),
                pygame.SRCALPHA,
            )
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                comp.blit(glow, (2 + dx, 2 + dy))
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                comp.blit(diag_glow, (2 + dx, 2 + dy))
            comp.blit(title, (2, 2))
            comp.set_alpha(title_alpha)
            surface.blit(
                comp, ((w - title.get_width()) // 2 - 2, title_y - 2),
            )
        else:
            glow_pos = ((w - glow.get_width()) // 2, title_y + 2)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                surface.blit(glow, (glow_pos[0] + dx, glow_pos[1] + dy))
            for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
                surface.blit(diag_glow, (glow_pos[0] + dx, glow_pos[1] + dy))
            surface.blit(title, ((w - title.get_width()) // 2, title_y))

        # Subtitle is the player's very first reading. Was "Simulez.
        # Observez. Comprenez la bascule planétaire." — three
        # imperatives at the player + one alarm noun (la bascule).
        # The new line is the spine of the source pedagogy doc
        # (faits_planete.txt): comprendre la catastrophe, s'émerveiller
        # du vivant qu'elle traverse, agir pour ce qui peut être tenu.
        # Infinitives, not imperatives — a philosophy, not a directive.
        subtitle = self.fonts.medium.render(
            "Comprendre la planète. S'émerveiller du vivant. Agir.",
            True,
            (185, 195, 225),
        )
        if sub_alpha < 255:
            subtitle.set_alpha(sub_alpha)
        surface.blit(
            subtitle,
            ((w - subtitle.get_width()) // 2,
             title_y + title.get_height() + 14 + sub_drift),
        )

        # The "DERNIÈRE PARTIE" card used to live here, mixed with the
        # JOUER / QUITTER buttons. It's been moved off the title — recap
        # belongs to the outro screen, which already shows the same data
        # for the run that just ended. Keeping the title menu pure.

        # ---- Chunky buttons with shadow + border + glossy highlight. ----
        # Buttons cascade in last so the eye lands on title → tagline → action.
        if reduce_motion:
            btn_alpha = 255
        else:
            btn_intro_t = min(1.0, max(0.0, (elapsed_ms - 600) / 500))
            btn_alpha = int(255 * (btn_intro_t ** 0.6))
        rects = title_button_rects(self.config)
        mouse_pos = pygame.mouse.get_pos()
        if btn_alpha < 255:
            # Draw to an offscreen layer so we can set alpha on the full pair.
            layer = pygame.Surface(self.screen_size, pygame.SRCALPHA)
            self._draw_chunky_button(
                layer, rects["play"], label="JOUER", primary=True,
                hover=rects["play"].collidepoint(mouse_pos),
            )
            self._draw_chunky_button(
                layer, rects["quit"], label="QUITTER", primary=False,
                hover=rects["quit"].collidepoint(mouse_pos),
            )
            layer.set_alpha(btn_alpha)
            surface.blit(layer, (0, 0))
        else:
            self._draw_chunky_button(
                surface, rects["play"], label="JOUER", primary=True,
                hover=rects["play"].collidepoint(mouse_pos),
            )
            self._draw_chunky_button(
                surface, rects["quit"], label="QUITTER", primary=False,
                hover=rects["quit"].collidepoint(mouse_pos),
            )

        # ---- Footer: version + hint. ----
        version = self.fonts.small.render(f"v{__version__}", True, (140, 150, 175))
        surface.blit(version, (w - version.get_width() - 16, h - version.get_height() - 12))
        # Title-screen footer hint. Aligned with the rest of the codebase's
        # shortcut idiom — middle-dot separator + "pour" preposition,
        # matching the pause overlay ("ESPACE pour reprendre · ÉCHAP pour
        # le menu"), the help footer ("H · ÉCHAP POUR FERMER"), and the
        # cinematic skip pill ("PASSER · ÉCHAP"). Was the lone "KEY: action"
        # colon-form holdout with a 4-space separator, which read as a
        # typewriter line rather than a UI hint.
        hint = self.fonts.small.render(
            "ENTRÉE pour jouer · ÉCHAP pour quitter",
            True,
            (140, 150, 175),
        )
        surface.blit(hint, ((w - hint.get_width()) // 2, h - hint.get_height() - 12))

    def _update_title_particles(self, w: int, h: int) -> None:
        """Spawn / advance / prune ambient drifting particles."""
        if random.random() < 0.18 and len(self._title_particles) < 90:
            lifetime = random.randint(140, 280)
            self._title_particles.append(
                {
                    "x": random.uniform(0.0, w),
                    "y": random.uniform(0.0, h),
                    "vx": (random.random() * 2.0 - 1.0) * 0.55,
                    "vy": (random.random() * 2.0 - 1.0) * 0.55 - 0.18,
                    "lifetime": lifetime,
                    "max_lifetime": lifetime,
                    "size": random.randint(1, 3),
                }
            )
        survivors: list[dict] = []
        for p in self._title_particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["lifetime"] -= 1
            if p["lifetime"] > 0 and 0 <= p["x"] < w and 0 <= p["y"] < h:
                survivors.append(p)
        self._title_particles = survivors

    def _draw_title_particles(self, surface: pygame.Surface) -> None:
        # Brightness envelope: trapezoidal ramp instead of pure
        # linear fade-out. Newborn particles used to pop in at full
        # brightness (the spawn point flickered visibly because the
        # uniform-x/y spawn could land mid-screen), then linearly
        # fade as they aged. Envelope: 0→1 over the first 15 % of
        # life, hold at 1 through 70 %, 1→0 over the last 30 %. The
        # backdrop-blend trick still does the actual alpha work since
        # pygame.draw.circle has no per-call alpha.
        for p in self._title_particles:
            age = 1.0 - p["lifetime"] / max(1, p["max_lifetime"])
            if age < 0.15:
                brightness = age / 0.15
            elif age > 0.70:
                brightness = max(0.0, (1.0 - age) / 0.30)
            else:
                brightness = 1.0
            color = _blend((16, 16, 24), (140, 160, 230), brightness)
            pygame.draw.circle(
                surface, color, (int(p["x"]), int(p["y"])), p["size"]
            )

    def _draw_padlock(
        self,
        surface: pygame.Surface,
        center: tuple[int, int],
        r: int,
        color: tuple[int, int, int],
    ) -> None:
        """Procedural padlock — shackle arc on top of a rounded body.

        Used in the skill-tree badge slot to communicate locked state.
        ``r`` is the icon's bounding half-extent (matches the element-icon
        helper's signature so the two are interchangeable per card state).
        """
        cx, cy = center
        body_w = r * 2
        body_h = max(8, int(r * 1.2))
        body = pygame.Rect(cx - body_w // 2, cy - body_h // 2 + 2, body_w, body_h)
        pygame.draw.rect(surface, color, body, border_radius=2)
        # Shackle arc above the body.
        arc_w = int(body_w * 0.75)
        arc_h = int(body_h * 1.4)
        arc_rect = pygame.Rect(cx - arc_w // 2, body.top - arc_h + 4, arc_w, arc_h)
        pygame.draw.arc(surface, color, arc_rect, 0.2, math.pi - 0.2, 2)
        # Keyhole dot in the body's center.
        pygame.draw.circle(surface, (16, 18, 24), (cx, body.centery + 1), 2)

    def _draw_element_icon(
        self,
        surface: pygame.Surface,
        name: str,
        center: tuple[int, int],
        radius: int,
        color: tuple[int, int, int],
    ) -> None:
        """Procedural glyph for each catastrophe element (Eau/Feu/Terre/Air/Vie).

        Draws into the given (cx, cy) with ``radius`` as the bounding-circle
        half-width. ``color`` controls both fill and stroke. Falls back to the
        first letter of the name if the element isn't recognised.
        """
        cx, cy = center
        r = radius
        thick = max(2, r // 4)

        if name == "Eau":
            # Three wave lines — bottom one widest, all stacked.
            for i, y_off in enumerate((-r // 2, 0, r // 2)):
                span = r - i * 2
                y = cy + y_off
                pts = [
                    (cx - span, y),
                    (cx - span // 3, y - thick),
                    (cx + span // 3, y + thick),
                    (cx + span, y),
                ]
                pygame.draw.lines(surface, color, False, pts, thick)
        elif name == "Feu":
            # Flame: pointed teardrop with inner notch.
            outer = [
                (cx, cy - r),
                (cx + r * 3 // 4, cy),
                (cx + r // 2, cy + r * 3 // 4),
                (cx - r // 2, cy + r * 3 // 4),
                (cx - r * 3 // 4, cy),
                (cx - r // 4, cy - r // 4),
                (cx + r // 6, cy - r // 2),
            ]
            pygame.draw.polygon(surface, color, outer, thick)
        elif name == "Terre":
            # Two overlapping mountain peaks.
            big = [(cx - r, cy + r // 2),
                   (cx - r // 6, cy - r // 2),
                   (cx + r // 2, cy + r // 2)]
            small = [(cx, cy + r // 2),
                     (cx + r // 3, cy - r // 6),
                     (cx + r, cy + r // 2)]
            pygame.draw.polygon(surface, color, big, thick)
            pygame.draw.polygon(surface, color, small, thick)
        elif name == "Air":
            # Two horizontal S-curves stacked — reads as wind streams.
            steps = 18
            for amp_y, base_y in ((r // 2, -r // 2), (r // 3, r // 4)):
                pts = []
                for s in range(steps + 1):
                    t = s / steps
                    px = cx - r + int(t * 2 * r)
                    py = cy + base_y + int(math.sin(t * math.pi * 2) * amp_y // 2)
                    pts.append((px, py))
                pygame.draw.lines(surface, color, False, pts, thick)
        elif name == "Vie":
            # Twin DNA-style curves crossing twice.
            steps = 16
            for direction in (1, -1):
                pts: list[tuple[int, int]] = []
                for s in range(steps + 1):
                    t = s / steps
                    py = cy - r + int(t * (2 * r))
                    px = cx + int(direction * math.sin(t * math.pi * 2) * r * 0.7)
                    pts.append((px, py))
                pygame.draw.lines(surface, color, False, pts, thick)
        else:
            glyph = self.fonts.label.render(name[0].upper(), True, color)
            surface.blit(
                glyph,
                (cx - glyph.get_width() // 2,
                 cy - glyph.get_height() // 2),
            )

    def _draw_title_planet(self, surface: pygame.Surface) -> None:
        """Procedural Earth rising from below the horizon on the title screen.

        Cached after first build because every layer is static — the planet
        sits behind the title text and serves as the anchoring "art" of the
        landing screen. Continents are rasterised onto a sub-surface that is
        masked by the planet disc so green polygons can never poke past the
        sphere's silhouette ("Earth overflowing from its circle").
        """
        w, h = self.screen_size
        cached = getattr(self, "_title_planet_cache", None)
        if cached is not None and cached.get_size() == (w, h):
            surface.blit(cached, (0, 0))
            return

        planet = pygame.Surface((w, h), pygame.SRCALPHA)
        cx = w // 2
        # Sized so the visible arc sits *below* the JOUER / QUITTER button
        # stack (button bottom ≈ y = h//2 + 30 + 48 + 14 + 48 ≈ 460 on the
        # default 640 h canvas). cy = h + 200, R = 360 puts the arc top at
        # y ≈ 480 — a clean ~20 px gap below the buttons instead of a
        # 140 px overlap.
        cy = h + 200
        R = 360

        # ---- Soft atmospheric halo around the planet. ----
        for i in range(60, 0, -2):
            alpha = int(85 * (i / 60) ** 3)
            tint = _blend((25, 70, 115), (130, 195, 240), (60 - i) / 60)
            pygame.draw.circle(
                planet, (*tint, alpha),
                (cx, cy), R + i * 2,
            )

        # ---- Planet body: radial gradient. Brightened so the disc actually
        # reads against the deep-indigo title backdrop (previously the
        # gradient hit (6,18,40) at centre which was darker than the
        # background, making the disc look like a hole instead of a planet).
        light_x = cx - R // 3
        light_y = cy - R // 2
        for r in range(R, 0, -1):
            t = 1 - (r / R)
            base = _blend((20, 50, 90), (75, 145, 205), t * 0.95 + 0.05)
            pygame.draw.circle(planet, (*base, 255), (cx, cy), r)

        # ---- Continents: rasterised onto a transparent sub-surface, then
        # alpha-multiplied by a disc mask so they can never escape the
        # planet's silhouette. Polygons themselves are inset from the
        # rim a little so the clipping rarely has to fire — the mask is
        # belt-and-braces.
        continents_layer = pygame.Surface((w, h), pygame.SRCALPHA)
        # Polygons are expressed as fractions of R so they scale with the
        # planet — previously they were hard-coded for R=460 and broke
        # when the disc shrank to fit the title-screen layout.
        continents_fractional: list[list[tuple[float, float]]] = [
            # "Africa-ish" — central south mass.
            [(0.11, -0.87), (0.23, -0.80), (0.30, -0.69), (0.27, -0.55),
             (0.16, -0.46), (0.07, -0.53), (0.02, -0.65), (0.05, -0.77)],
            # "Eurasia-ish" — wide arc to the right (rim points pulled in).
            [(-0.24, -0.93), (-0.07, -0.96), (0.13, -0.93), (0.33, -0.88),
             (0.47, -0.80), (0.43, -0.71), (0.24, -0.74), (0.07, -0.77),
             (-0.17, -0.84), (-0.25, -0.88)],
            # "Americas-ish" — left band.
            [(-0.62, -0.85), (-0.52, -0.76), (-0.48, -0.62), (-0.51, -0.48),
             (-0.60, -0.42), (-0.70, -0.52), (-0.68, -0.68), (-0.65, -0.80)],
            # Island specks.
            [(0.49, -0.54), (0.57, -0.52), (0.54, -0.46), (0.48, -0.48)],
            [(-0.30, -0.53), (-0.23, -0.51), (-0.21, -0.45), (-0.28, -0.47)],
        ]
        for poly in continents_fractional:
            pts = [(cx + int(dx * R), cy + int(dy * R)) for dx, dy in poly]
            pygame.draw.polygon(continents_layer, (78, 130, 100, 245), pts)
            # Subtle darker edge so the landmass has a coastline cue.
            pygame.draw.polygon(continents_layer, (45, 85, 65, 200), pts, 1)
        # Build the disc mask once.
        mask = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.circle(mask, (255, 255, 255, 255), (cx, cy), R - 2)
        # Multiply continents alpha by the mask — any pixel outside the
        # disc gets its alpha multiplied by 0 and disappears.
        continents_layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        planet.blit(continents_layer, (0, 0))

        # ---- Light glaze: soft white-cyan bloom over the lit quadrant. ----
        glaze = pygame.Surface((R, R), pygame.SRCALPHA)
        for i in range(R // 2, 0, -2):
            alpha = int(55 * (1 - i / (R / 2)) ** 2)
            pygame.draw.circle(
                glaze, (220, 240, 255, alpha),
                (R // 2, R // 2), i,
            )
        # Position the glaze so its centre is offset toward upper-left.
        gx, gy = light_x - R // 2, light_y - R // 2
        # Mask the glaze too so it doesn't bloom outside the disc.
        glaze.blit(
            mask,
            (-gx, -gy),
            special_flags=pygame.BLEND_RGBA_MULT,
        )
        planet.blit(glaze, (gx, gy))

        # ---- Subtle outer edge ring to seat the sphere. ----
        pygame.draw.circle(planet, (170, 215, 245, 110), (cx, cy), R, 2)

        self._title_planet_cache = planet
        surface.blit(planet, (0, 0))

    def _picker_origin_vignette_cache(
        self, size: tuple[int, int],
    ) -> pygame.Surface:
        """Cached radial-vignette dim for the picker step-2 map overlay.

        Centre at alpha ≈ 50, corners at alpha ≈ 130 — emphasises the
        middle of the map (where the player is looking for an origin
        country) while still letting the world read through. Rebuilt
        if the canvas size changes between calls.
        """
        cached = getattr(self, "_picker_vignette_cache", None)
        if cached is not None and cached.get_size() == size:
            return cached
        w, h = size
        out = pygame.Surface((w, h), pygame.SRCALPHA)
        # Start with the base centre alpha, then layer concentric rings
        # of darker alpha so the corners come out heaviest.
        out.fill((0, 0, 0, 50))
        cx, cy = w // 2, h // 2
        max_r = int(math.hypot(cx, cy))
        # Draw rings from outermost inward; outer rings stack the
        # darkest alpha so the corners feel weighty without affecting
        # the centre where the rings don't reach.
        for r in range(max_r, max_r // 2, -10):
            t = (r - max_r // 2) / (max_r - max_r // 2)
            extra_alpha = int(80 * t)
            if extra_alpha <= 0:
                continue
            pygame.draw.circle(
                out, (0, 0, 0, extra_alpha), (cx, cy), r, 10,
            )
        self._picker_vignette_cache = out
        return out

    def burst_at(self, x: int, y: int, color: tuple[int, int, int], count: int = 8) -> None:
        """Spawn a small short-lived particle burst at (x, y) — used on purchase."""
        for _ in range(count):
            angle = random.uniform(0, 2 * math.pi)
            speed = random.uniform(1.2, 2.6)
            lifetime = random.randint(20, 36)
            self._evo_particles.append({
                "x": float(x),
                "y": float(y),
                "vx": math.cos(angle) * speed,
                "vy": math.sin(angle) * speed - 0.4,
                "lifetime": lifetime,
                "max_lifetime": lifetime,
                "size": random.randint(2, 3),
                "tint": color,
            })

    def _update_evo_particles(self, w: int, h: int) -> None:
        """Spawn / advance / prune the evolution overlay's ambient particles."""
        # Tuned down from 70/22% — was visually noisy: dozens of bright dots
        # floating across the skill tree. 18 cap + 6% spawn keeps the
        # ambience without dominating the foreground content.
        if random.random() < 0.06 and len(self._evo_particles) < 18:
            lifetime = random.randint(240, 420)
            self._evo_particles.append({
                "x": random.uniform(0.0, w),
                "y": random.uniform(0.0, h),
                "vx": (random.random() * 2.0 - 1.0) * 0.25,
                "vy": -random.uniform(0.08, 0.32),
                "lifetime": lifetime,
                "max_lifetime": lifetime,
                "size": random.randint(1, 2),
            })
        survivors: list[dict] = []
        for p in self._evo_particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["lifetime"] -= 1
            if p["lifetime"] > 0 and -10 <= p["x"] < w + 10 and -10 <= p["y"] < h + 10:
                survivors.append(p)
        self._evo_particles = survivors

    def _draw_evo_particles(
        self, surface: pygame.Surface, tint: tuple[int, int, int]
    ) -> None:
        """Evolution-overlay particle effects.

        Previously a flat ``pygame.draw.circle`` per particle with the
        colour blended toward the background. That works against a pure
        dark backdrop (the original target), but the evolution overlay
        now renders on top of the lit panel — the "fade toward
        background" trick produced muddy grey particles instead of
        glowing motes.

        Now each particle gets:
          1. A soft outer halo (2 concentric translucent circles) that
             carries the catastrophe tint without depending on the
             backdrop colour.
          2. A bright core sized to the particle's nominal size.
          3. True per-pixel alpha via an SRCALPHA scratch surface, so
             the fade-out at end-of-life is actually transparent
             instead of "blended toward dark grey".
        """
        if not self._evo_particles:
            return
        for p in self._evo_particles:
            ratio = p["lifetime"] / max(1, p["max_lifetime"])
            if ratio <= 0.0:
                continue
            particle_tint = p.get("tint", tint)
            size = max(1, int(p["size"]))
            # Halo extends 3 px beyond the core so even tiny particles
            # still read as glowing dots, not pixels.
            halo_r = size + 3
            scratch = pygame.Surface(
                (halo_r * 2 + 2, halo_r * 2 + 2), pygame.SRCALPHA,
            )
            cxs, cys = halo_r + 1, halo_r + 1
            # Two halo layers — outer faint, inner brighter — both
            # tinted, both fading with the particle's lifetime ratio.
            for r, a_mult in ((halo_r, 0.20), (halo_r - 2, 0.45)):
                a = int(255 * ratio * a_mult)
                if a < 1:
                    continue
                pygame.draw.circle(
                    scratch, (*particle_tint, a), (cxs, cys), r,
                )
            # Bright core — particle_tint pushed toward white so the
            # centre stays luminous even as the halo fades.
            core_color = _blend(particle_tint, (255, 255, 255), 0.45)
            core_alpha = int(255 * ratio)
            if core_alpha > 0:
                pygame.draw.circle(
                    scratch, (*core_color, core_alpha), (cxs, cys), size,
                )
            surface.blit(
                scratch, (int(p["x"]) - cxs, int(p["y"]) - cys),
            )

    def _draw_chunky_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        label: str,
        primary: bool,
        hover: bool,
        font: pygame.font.Font | None = None,
        tint: tuple[int, int, int] | None = None,
    ) -> None:
        """Title-screen button: shadow under, fill, accent border, glossy strip.

        ``tint`` paints a primary button in a caller-supplied accent
        (catastrophe colour for the LANCER button) instead of the default
        cobalt blue, so the button can broadcast *which* element the
        player is about to commit to.
        """
        # Drop shadow underneath — soft Pillow Gaussian via the cached
        # helper. Strong elevation (blur=12, alpha=150, offset=5):
        # chunky buttons are the most visually-prominent CTAs in the
        # game (LANCER, AMÉLIORER, REPRENDRE) and earn full material
        # depth instead of the prior flat 5-px-down sliver of solid
        # black.
        self._draw_shadow(surface, rect, blur=12, alpha=150, offset_y=5)

        if primary and tint is not None:
            base = (18, 22, 32)
            bg = _blend(base, tint, 0.55 if hover else 0.38)
            border = _blend(tint, (255, 255, 255), 0.20)
            text_color = (255, 255, 255)
        elif primary:
            bg = (60, 80, 130) if hover else (40, 50, 90)
            border = (120, 140, 240)
            text_color = (255, 255, 255)
        else:
            bg = (60, 60, 70) if hover else (40, 40, 50)
            border = (110, 120, 150)
            text_color = (235, 240, 250)
        # Hover halo on primary buttons — a soft glow ring announces "clickable".
        if primary and hover:
            glow = pygame.Surface(
                (rect.width + 10, rect.height + 10), pygame.SRCALPHA,
            )
            pygame.draw.rect(
                glow, (*border, 90),
                (0, 0, rect.width + 10, rect.height + 10),
                4, border_radius=16,
            )
            surface.blit(glow, (rect.left - 5, rect.top - 5))
        # Flat fill provides the rounded-corner shape.
        pygame.draw.rect(surface, bg, rect, border_radius=14)
        # Vertical gradient overlay — top +15 luminance, bottom −15 —
        # gives the button real tactile depth instead of reading as a
        # flat coloured rect. Clipped to the rect so it can't bleed
        # past the rounded corners. Same depth idiom shipped on the
        # info-panel tab pills, help-modal key pills, and ÉQUILIBRE
        # tiles — every elevated chrome surface in the codebase now
        # speaks the same gradient language.
        prev_clip = surface.get_clip()
        surface.set_clip(rect)
        grad = pygame.Surface(rect.size, pygame.SRCALPHA)
        for gy in range(rect.height):
            t = gy / max(1, rect.height - 1)
            shift = int(15 * (1.0 - 2 * t))
            if shift > 0:
                pygame.draw.line(
                    grad, (255, 255, 255, min(255, shift * 3)),
                    (0, gy), (rect.width, gy),
                )
            elif shift < 0:
                pygame.draw.line(
                    grad, (0, 0, 0, min(255, -shift * 3)),
                    (0, gy), (rect.width, gy),
                )
        surface.blit(grad, rect.topleft)
        surface.set_clip(prev_clip)
        pygame.draw.rect(surface, border, rect, 2, border_radius=14)

        # Glossy highlight strip across the top quarter — now with
        # *alpha falloff* (brightest at the top of the strip, fading
        # to 0 at the bottom). Was a flat-alpha rectangle which read
        # as a "lighter coloured stripe" rather than as a *glass
        # reflection*. The cubic falloff gives the strip a polished
        # gloss-on-curved-surface feel matching real raised buttons.
        gloss_h = max(2, rect.height // 4)
        gloss = pygame.Surface((rect.width - 6, gloss_h), pygame.SRCALPHA)
        gloss_peak = 42 if hover else 30
        for gy in range(gloss_h):
            t = gy / max(1, gloss_h - 1)
            a = int(gloss_peak * (1.0 - t) ** 1.4)
            if a < 1:
                continue
            pygame.draw.line(
                gloss, (255, 255, 255, a),
                (0, gy), (rect.width - 6, gy),
            )
        surface.blit(gloss, (rect.left + 3, rect.top + 3))
        # Bottom-edge shadow stroke — 1 px line at 45 % black blend,
        # inset 6 px so it doesn't crash the rounded corners. Anchors
        # the button visually as a *raised* element with a clear lit
        # top and shadowed bottom.
        pygame.draw.line(
            surface,
            _blend(bg, (0, 0, 0), 0.45),
            (rect.left + 6, rect.bottom - 3),
            (rect.right - 6, rect.bottom - 3),
            1,
        )

        # Auto-shrink: title font first, fall back to large/medium if it
        # would spill past the button. Callers can also force a font.
        use_font = font or self.fonts.title
        fit = self._fit_text(label, use_font, rect.width - 24)
        if fit != label and font is None:
            # Bumped down to medium when the title font would have ellipsised.
            use_font = self.fonts.medium
            fit = self._fit_text(label, use_font, rect.width - 16)
        text = use_font.render(fit, True, text_color)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2,
             rect.centery - text.get_height() // 2),
        )

    # ----------------------------------------------------------- pause

    def _draw_pause_overlay(self, surface: pygame.Surface, game: Game) -> None:
        """Pause notice card — same design language as the rest of the panels.

        Drop shadow + rounded corners + catastrophe-tint accent stripe on
        top, pause glyph badge on the left, action hints on the right. This
        is the lightweight "you're paused" notice — the full action menu
        (RECOMMENCER / MENU / QUITTER) lives behind ESC and is drawn by
        ``_draw_pause_menu``.
        """
        map_rect = self.map_rect
        dim = pygame.Surface(map_rect.size, pygame.SRCALPHA)
        dim.fill((0, 0, 0, 80))
        surface.blit(dim, map_rect.topleft)

        cat_color = game.gaia.active.arc_color
        ticks = pygame.time.get_ticks()
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.004)
        accent = _blend(cat_color, (0, 0, 0), 0.2 + 0.1 * pulse)

        # Card width widened (was 340) so the hint string
        # "ESPACE pour reprendre · ÉCHAP pour le menu" doesn't overflow
        # the right edge. Astuce row removed (was a scrolling ticker —
        # added visual noise on a screen the player visits mostly to
        # take a break). Height returns to the original 112 px.
        card_w, card_h = 440, 112
        radius = 14
        card = pygame.Rect(
            map_rect.centerx - card_w // 2,
            map_rect.centery - card_h // 2,
            card_w, card_h,
        )

        # Drop shadow + rounded card body.
        self._draw_shadow(surface, card, blur=18, alpha=170)
        card_surf = pygame.Surface(card.size, pygame.SRCALPHA)
        pygame.draw.rect(
            card_surf, (*self.palette.surface_elevated[:3], 248),
            (0, 0, card_w, card_h),
            border_radius=radius,
        )
        # Smooth top-edge highlight + bottom-edge shadow (replaces the
        # half-panel rect that left a visible midline on tall cards).
        self._fade_card_highlight(
            card_surf, card_w, card_h, radius,
            peak_lowlight_alpha=22,
        )
        surface.blit(card_surf, card.topleft)

        # Top accent stripe in the catastrophe tint (darkened so it reads on
        # any catastrophe colour). Pulses softly with the existing pulse.
        accent_strip = pygame.Surface((card_w, 3), pygame.SRCALPHA)
        pygame.draw.rect(
            accent_strip, (*accent, 255),
            (0, 0, card_w, 3),
            border_top_left_radius=radius,
            border_top_right_radius=radius,
        )
        surface.blit(accent_strip, card.topleft)
        pygame.draw.rect(
            surface, self.palette.ui_border_soft, card, 1, border_radius=radius,
        )

        # Pause glyph badge — two vertical bars in a tinted circle, on a
        # soft catastrophe-colour halo. Halo matches the top-bar
        # element-badge idiom so the pause card uses the same elevation
        # treatment as the rest of the HUD (was a flat tinted disc
        # with no aura).
        badge_r = 22
        badge_cx = card.left + 28 + badge_r
        badge_cy = card.centery + 4
        halo = pygame.Surface(
            (badge_r * 4 + 4, badge_r * 4 + 4), pygame.SRCALPHA,
        )
        halo_cx_local = halo.get_width() // 2
        halo_cy_local = halo.get_height() // 2
        for hr_layer, hr_alpha in ((badge_r + 14, 22), (badge_r + 8, 50)):
            pygame.draw.circle(
                halo, (*cat_color, hr_alpha),
                (halo_cx_local, halo_cy_local), hr_layer,
            )
        surface.blit(
            halo, (badge_cx - halo_cx_local, badge_cy - halo_cy_local),
        )
        pygame.draw.circle(
            surface, _blend((10, 12, 18), cat_color, 0.45),
            (badge_cx, badge_cy), badge_r,
        )
        pygame.draw.circle(
            surface, cat_color, (badge_cx, badge_cy), badge_r, 2,
        )
        bar_w, bar_h = 4, 18
        gap = 4
        bar_y = badge_cy - bar_h // 2
        pygame.draw.rect(
            surface, (245, 248, 255),
            (badge_cx - bar_w - gap // 2, bar_y, bar_w, bar_h),
            border_radius=1,
        )
        pygame.draw.rect(
            surface, (245, 248, 255),
            (badge_cx + gap // 2, bar_y, bar_w, bar_h),
            border_radius=1,
        )

        # Text column on the right.
        text_x = badge_cx + badge_r + 14
        # Section tag above title — anchors the design idiom from the dashboard.
        tag = self.fonts.label.render(
            "SCÉNARIO", True, self.palette.text_label,
        )
        surface.blit(tag, (text_x, card.top + 16))
        title_text = self.fonts.title.render(
            "EN PAUSE", True, self.palette.text,
        )
        surface.blit(title_text, (text_x, card.top + 16 + tag.get_height() + 2))
        # Defensive fit — guarantees the hint sits inside the card even if
        # the chosen font happens to render wider on a particular system.
        hint_max_w = card.right - text_x - 16
        hint_str = self._fit_text(
            "ESPACE pour reprendre · ÉCHAP pour le menu",
            self.fonts.small, hint_max_w,
        )
        hint = self.fonts.small.render(
            hint_str, True, self.palette.text_dim,
        )
        hint_y = card.top + 16 + tag.get_height() + 2 + title_text.get_height() + 4
        surface.blit(hint, (text_x, hint_y))

        # Astuce ticker removed — the rotating tip / scrolling ticker
        # added visual weight on a screen the player visits *to take a
        # break*. The hint line above ("ESPACE pour reprendre · ÉCHAP
        # pour le menu") already carries everything they need at this
        # moment. Educational tips live in the news ticker during play.

    # ------------------------------------------------------- tooltip

    def _draw_country_tooltip(self, surface: pygame.Surface, game: Game) -> None:
        """Three-line hover tooltip for the world map.

        Row 1: country name.
        Row 2: state colour dot + "Sain/Exposé/Critique [%] · N habitants".
        Row 3 (educational): archetype label + vulnerability chip showing
        the per-country multiplier against the currently active
        catastrophe — e.g. hovering Bangladesh during Eau reveals "Delta
        tropical · ×1,50 EAU" in amber, while hovering Iceland during
        Feu reveals "Polaire · isolé · ×0,55 FEU" in sage. Player learns
        *why* their next decision should target this country, not just
        that the country is in trouble.
        """
        from gaia_ultimatum.models.country_profiles import display_label_for

        country = game.world.countries.get(game.hovered_country or "")
        if country is None:
            return
        pad_x = 11
        pad_y = 9
        radius = 7
        cat_color = game.gaia.active.arc_color
        active_cat_name = game.gaia.active.name

        # Status band — softened palette so SAIN doesn't read as a neon
        # stamp. State percentage is appended only when there's actual
        # damage; "SAIN 0%" was redundant noise.
        if country.state >= 0.5:
            band_label = "Critique"
            band_color = self.palette.severe
        elif country.state >= 0.2:
            band_label = "Exposé"
            band_color = SOFT_WARNING
        else:
            band_label = "Sain"
            band_color = SOFT_SUCCESS

        # Compact population (e.g. 1.4 G, 68 M, 320 K, < 1 K).
        pop = country.population
        if pop >= 1_000_000_000:
            pop_str = f"{pop / 1_000_000_000:.1f} G".replace(".", ",")
        elif pop >= 1_000_000:
            pop_str = f"{pop / 1_000_000:.0f} M"
        elif pop >= 1_000:
            pop_str = f"{pop / 1_000:.0f} k"
        else:
            pop_str = str(pop)

        # Status caption: "Sain · 68 M habitants" / "Exposé 35 % ·
        # 68 M habitants" / "Critique 72 % · 4,2 % perdus".
        # The death-rate branch previously rendered as
        # "Critique 72 % · −4.2% pop." — a leading minus + dot
        # decimal + abbreviation, three inconsistencies with the
        # sibling "habitants" templates. "X % perdus" reads as
        # natural French ("4.2 % lost"), drops the redundant minus
        # (the noun *perdus* already implies loss), and uses comma
        # decimals like the rest of the localised UI.
        state_pct = int(country.state * 100)
        if country.state < 0.05:
            status_str = f"{band_label} · {pop_str} habitants"
        elif country.dead > 0:
            lost_pct = (country.dead / max(1, country.population + country.dead)) * 100
            lost_str = f"{lost_pct:.1f}".replace(".", ",")
            status_str = f"{band_label} {state_pct} % · {lost_str} % perdus"
        else:
            status_str = f"{band_label} {state_pct} % · {pop_str} habitants"

        # Vulnerability against the active catastrophe — 1.0 is neutral,
        # >1 is more vulnerable, <1 is more resilient. Bucketed into 4
        # severity bands so the colour communicates the strategic stake
        # at a glance.
        vuln = country.vulnerability.get(active_cat_name, 1.0)
        if vuln >= 1.30:
            vuln_label = "Très exposée"
            vuln_color = self.palette.severe
        elif vuln >= 1.10:
            vuln_label = "Exposée"
            vuln_color = SOFT_WARNING
        elif vuln <= 0.90:
            vuln_label = "Résiliente"
            vuln_color = SOFT_SUCCESS
        else:
            vuln_label = "Neutre"
            vuln_color = self.palette.text_dim

        archetype_str = display_label_for(country.profile_name)
        # Format vulnerability multiplier with French decimal style.
        vuln_str = f"×{vuln:.2f}".replace(".", ",").rstrip("0").rstrip(",")
        if vuln_str == "×1":
            vuln_str = "×1,00"  # keep two-digit precision so the chip
                                # doesn't look like an unfinished string
        edu_str = f"{archetype_str} · {active_cat_name.upper()} {vuln_str}"

        name_text = self.fonts.medium.render(
            country.name, True, self.palette.text,
        )
        status_text = self.fonts.small.render(
            status_str, True, self.palette.text_label,
        )
        edu_text = self.fonts.small.render(
            edu_str, True, vuln_color,
        )

        # Layout: dot (8 px) + 6 px gap + text on row 2. Row 3 mirrors
        # the dot position with a tiny chevron so the eye reads it as a
        # related fact, not a separate widget.
        dot_r = 4
        dot_gap = 8
        edu_indent = dot_r * 2 + dot_gap  # align row 3 with row 2 text
        content_w = max(
            name_text.get_width(),
            dot_r * 2 + dot_gap + status_text.get_width(),
            edu_indent + edu_text.get_width(),
        )
        w = content_w + pad_x * 2
        # Three text rows separated by 4 px gaps.
        h = (
            pad_y
            + name_text.get_height() + 4
            + max(status_text.get_height(), dot_r * 2) + 4
            + edu_text.get_height()
            + pad_y
        )

        mx, my = pygame.mouse.get_pos()
        x = mx + 18
        y = my + 18
        # Clamp inside the *currently visible* map area so the tooltip
        # never overlaps a panel edge. ``self.map_rect.right`` already
        # reflects whether the right panel is collapsed (the map widens
        # to the screen edge in that mode), so the tooltip can use the
        # full visible width instead of an unconditional
        # ``screen_width - RIGHT_PANEL_W`` reserve that left a 296 px
        # dead zone on the right when the sidebar was hidden.
        max_x = self.map_rect.right - 4
        max_y = self.config.display.height - NEWS_BAR_H - 4
        if x + w > max_x:
            x = mx - 18 - w
        if y + h > max_y:
            y = my - 18 - h
        x = max(4, x)
        y = max(TOP_BAR_H + 4, y)
        rect = pygame.Rect(x, y, w, h)

        # Drop shadow + rounded translucent card.
        self._draw_shadow(surface, rect, blur=12, alpha=150)
        card = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            card, (*self.palette.surface_elevated[:3], 240),
            (0, 0, rect.width, rect.height),
            border_radius=radius,
        )
        # Smooth top-edge highlight + bottom-edge shadow for depth.
        self._fade_card_highlight(
            card, rect.width, rect.height, radius,
            peak_alpha=10, peak_lowlight_alpha=18,
        )
        surface.blit(card, rect.topleft)
        # Catastrophe-tint left-edge bar (vertical accent — keeps the card
        # tied to the active catastrophe identity without a heavy top
        # stripe on such a small surface).
        edge_color = _blend(cat_color, (0, 0, 0), 0.25)
        pygame.draw.rect(
            surface, edge_color,
            (rect.left, rect.top, 3, rect.height),
            border_top_left_radius=radius,
            border_bottom_left_radius=radius,
        )
        pygame.draw.rect(
            surface, self.palette.ui_border_soft,
            rect, 1, border_radius=radius,
        )

        # Top row — name.
        surface.blit(
            name_text,
            (rect.left + pad_x + 2, rect.top + pad_y),
        )

        # Middle row — colour dot + status caption.
        row_y = rect.top + pad_y + name_text.get_height() + 4
        dot_cy = row_y + status_text.get_height() // 2
        dot_cx = rect.left + pad_x + 2 + dot_r
        pygame.draw.circle(surface, band_color, (dot_cx, dot_cy), dot_r)
        # Soft halo around the dot so SAIN's sage-green still pops without
        # screaming.
        halo = pygame.Surface((dot_r * 4, dot_r * 4), pygame.SRCALPHA)
        pygame.draw.circle(
            halo, (*band_color, 70), (dot_r * 2, dot_r * 2), dot_r * 2,
        )
        surface.blit(halo, (dot_cx - dot_r * 2, dot_cy - dot_r * 2))
        pygame.draw.circle(surface, band_color, (dot_cx, dot_cy), dot_r)
        surface.blit(
            status_text,
            (dot_cx + dot_r + dot_gap, row_y),
        )

        # Bottom row — vulnerability + archetype. Aligned with the
        # status text column. Small tinted square bullet matches the
        # section-header bullet idiom used elsewhere.
        edu_y = row_y + max(status_text.get_height(), dot_r * 2) + 4
        pygame.draw.rect(
            surface, vuln_color,
            (rect.left + pad_x + 2, edu_y + 4, 3, edu_text.get_height() - 6),
        )
        surface.blit(
            edu_text,
            (rect.left + pad_x + 2 + edu_indent, edu_y),
        )
        # Tiny one-word severity tag at the far right of the row so the
        # bar gives a colour cue *and* a literal word.
        vuln_tag = self.fonts.label.render(
            vuln_label.upper(), True, vuln_color,
        )
        tag_x = rect.right - pad_x - vuln_tag.get_width()
        if tag_x > rect.left + pad_x + edu_indent + edu_text.get_width() + 10:
            surface.blit(vuln_tag, (tag_x, edu_y + 1))

    # ------------------------------------------------------- milestones

    def _draw_milestone_banners(self, surface: pygame.Surface, game: Game) -> None:
        """Central auto-fading notification stack — visual-first redesign.

        Layout per banner (440 × 80):

            [ icon ]  TAG               × close
                      Title text wrapped
                      onto up to 2 lines

        - Severity badge on the left (44 px circle with a procedural icon).
        - Tag label + wrapped title in the middle column.
        - ``×`` button on the right corner — players can dismiss
          immediately instead of waiting for the auto-fade.

        Severity styles:
          ``trophy``   — UI accent coral, label "TROPHÉE", star icon.
          ``warning``  — amber, label "ALERTE", exclamation icon.
          ``critical`` — severe red, label "CRITIQUE", skull-like glyph.
        """
        if not game.milestone_banners:
            return
        rects = milestone_banner_rects(self.config, len(game.milestone_banners))
        if not rects:
            return

        severity_styles = {
            "trophy":   (self.palette.ui_accent[:3],     "TROPHÉE",  "star"),
            # SOFT_WARNING is the same amber the country tooltip status
            # band and the outro population row use. Was a near-twin
            # literal ``(220, 160, 70)`` — 5-unit deltas on G/B, below
            # the perception threshold. Routing through the named
            # constant ties the milestone banner's "ALERTE" tone to the
            # rest of the soft-status family so any future tonal shift
            # stays cohesive.
            "warning":  (SOFT_WARNING,                   "ALERTE",   "warn"),
            "critical": (self.palette.severe[:3],        "CRITIQUE", "skull"),
        }

        banners = list(game.milestone_banners)
        mouse_pos = pygame.mouse.get_pos()
        for i, banner in enumerate(banners):
            if i >= len(rects):
                break
            base_rect = rects[i]
            progress = banner.age / banner.lifetime
            if progress < 0.08:
                envelope = progress / 0.08
            elif progress < 0.82:
                envelope = 1.0
            else:
                envelope = max(0.0, 1.0 - (progress - 0.82) / 0.18)
            if envelope <= 0:
                continue
            slide = int(20 * (1.0 - envelope))
            rect = base_rect.move(0, -slide)

            severity = getattr(banner, "severity", "trophy")
            accent_rgb, tag_label, icon_kind = severity_styles.get(
                severity, severity_styles["trophy"],
            )

            # Birth halo — accent-colour glow expanding outward.
            if progress < 0.15:
                halo_t = progress / 0.15
                halo_radius = int(28 + halo_t * 52)
                halo_alpha = int(120 * (1.0 - halo_t))
                if halo_alpha > 4:
                    halo = pygame.Surface(
                        (rect.width + halo_radius * 2,
                         rect.height + halo_radius * 2),
                        pygame.SRCALPHA,
                    )
                    for step in range(halo_radius, 0, -4):
                        s = step / halo_radius
                        a = int(halo_alpha * (1 - s) ** 1.5)
                        if a < 1:
                            continue
                        pygame.draw.rect(
                            halo, (*accent_rgb, a),
                            pygame.Rect(
                                halo_radius - step,
                                halo_radius - step,
                                rect.width + step * 2,
                                rect.height + step * 2,
                            ),
                            1, border_radius=8 + step,
                        )
                    surface.blit(
                        halo, (rect.left - halo_radius, rect.top - halo_radius),
                    )

            # Body with rounded corners.
            bg = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                bg, (*self.palette.ui_panel[:3],
                     int(self.palette.ui_panel[3] * envelope)),
                (0, 0, rect.width, rect.height),
                border_radius=10,
            )
            # Vertical gradient overlay on the body — top +14 luminance,
            # bottom −14 — gives the banner real screen-surface depth
            # instead of reading as a flat coloured rect. Drawn on a
            # separate surface, then masked via the rounded-rect shape
            # (BLEND_RGBA_MULT) so the gradient respects the corners.
            # Alpha scales with the autofade envelope so the gradient
            # fades in/out with the banner.
            grad = pygame.Surface(rect.size, pygame.SRCALPHA)
            for gy in range(rect.height):
                t = gy / max(1, rect.height - 1)
                shift = int(14 * (1.0 - 2 * t))
                if shift > 0:
                    a = min(255, int(shift * 3 * envelope))
                    if a >= 1:
                        pygame.draw.line(
                            grad, (255, 255, 255, a),
                            (0, gy), (rect.width, gy),
                        )
                elif shift < 0:
                    a = min(255, int(-shift * 3 * envelope))
                    if a >= 1:
                        pygame.draw.line(
                            grad, (0, 0, 0, a),
                            (0, gy), (rect.width, gy),
                        )
            # Mask the gradient to the rounded-rect shape so it doesn't
            # leak into the transparent corners.
            mask = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                mask, (255, 255, 255, 255),
                (0, 0, rect.width, rect.height),
                border_radius=10,
            )
            grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            bg.blit(grad, (0, 0))
            surface.blit(bg, rect.topleft)
            border_color = _blend(self.palette.background, accent_rgb, envelope)
            pygame.draw.rect(surface, border_color, rect, 1, border_radius=10)
            # Top-edge highlight + bottom-edge shadow strokes (1 px
            # each, inset 8 px to avoid the rounded corners). Same
            # idiom shipped on TENDANCE chart container, info panel
            # header, and pause menu buttons — the banner now speaks
            # the same depth language. Envelope-aware so they fade
            # with the rest of the banner.
            hl_color = (
                255, 255, 255,
                int(60 * envelope),
            )
            sh_color = (
                0, 0, 0,
                int(80 * envelope),
            )
            if hl_color[3] >= 1:
                hl_layer = pygame.Surface(
                    (rect.width - 16, 1), pygame.SRCALPHA,
                )
                hl_layer.fill(hl_color)
                surface.blit(hl_layer, (rect.left + 8, rect.top + 1))
            if sh_color[3] >= 1:
                sh_layer = pygame.Surface(
                    (rect.width - 16, 1), pygame.SRCALPHA,
                )
                sh_layer.fill(sh_color)
                surface.blit(sh_layer, (rect.left + 8, rect.bottom - 2))
            # Left accent stripe.
            pygame.draw.rect(
                surface, border_color,
                (rect.left, rect.top + 6, 4, rect.height - 12),
                border_radius=2,
            )

            # Severity icon badge.
            badge_r = 22
            badge_cx = rect.left + 16 + badge_r
            badge_cy = rect.top + rect.height // 2
            pygame.draw.circle(
                surface, _blend((10, 12, 18), accent_rgb, 0.45),
                (badge_cx, badge_cy), badge_r,
            )
            pygame.draw.circle(
                surface, border_color,
                (badge_cx, badge_cy), badge_r, 2,
            )
            self._draw_milestone_icon(
                surface, icon_kind, (badge_cx, badge_cy), badge_r - 6,
                color=(245, 248, 255),
            )

            # Text column.
            text_x = badge_cx + badge_r + 14
            close_rect = milestone_banner_close_rect(
                rect, touch_mode=self.config.display.touch_mode,
            )
            text_right = close_rect.left - 12
            text_max_w = max(80, text_right - text_x)

            label_color = _blend(
                self.palette.background, self.palette.text_label, envelope,
            )
            label = self.fonts.label.render(tag_label, True, label_color)
            surface.blit(label, (text_x, rect.top + 10))

            title_color = _blend(
                self.palette.background, self.palette.text, envelope,
            )
            title_y = rect.top + 10 + label.get_height() + 2
            # Wrap up to 2 lines so long messages stay fully readable
            # instead of getting ellipsised. Falls back to smaller font
            # only when even 2 wrapped lines won't fit.
            wrapped = self._wrap_text(
                banner.title, self.fonts.medium, text_max_w, max_lines=2,
            )
            line_h = self.fonts.medium.get_height()
            if title_y + line_h * len(wrapped) > rect.bottom - 6:
                # Re-wrap with the smaller font when we ran out of vertical
                # space — gives the player every chance to read the full
                # message before it auto-fades.
                wrapped = self._wrap_text(
                    banner.title, self.fonts.small, text_max_w, max_lines=2,
                )
                font = self.fonts.small
                line_h = font.get_height()
            else:
                font = self.fonts.medium
            for line in wrapped:
                t = font.render(line, True, title_color)
                surface.blit(t, (text_x, title_y))
                title_y += line_h + 1

            # × close button. Hover highlight when the cursor is over it.
            close_hover = close_rect.collidepoint(mouse_pos)
            close_color = _blend(
                self.palette.background,
                (245, 248, 255) if close_hover else self.palette.text_label,
                envelope,
            )
            if close_hover:
                pygame.draw.rect(
                    surface, (*accent_rgb, int(45 * envelope)),
                    close_rect, border_radius=4,
                )
            cw = close_rect
            pad = 5
            pygame.draw.line(
                surface, close_color,
                (cw.left + pad, cw.top + pad),
                (cw.right - pad, cw.bottom - pad),
                2,
            )
            pygame.draw.line(
                surface, close_color,
                (cw.right - pad, cw.top + pad),
                (cw.left + pad, cw.bottom - pad),
                2,
            )

    def _draw_milestone_icon(
        self,
        surface: pygame.Surface,
        kind: str,
        center: tuple[int, int],
        r: int,
        *,
        color: tuple[int, int, int],
    ) -> None:
        """Procedural icon for the milestone-banner severity badge.

        Each kind got a small richness pass:

          * **star** — was a flat 5-point polygon; now polygon + a tiny
            bright centre pip so it reads as a *shining* star, not just
            a yellow shape.
          * **warn** — was a hairline triangle outline + bang. Now a
            translucent-fill triangle underneath the outline so the
            badge reads as a filled hazard sign, with the bang +
            terminal pip layered on top.
          * **skull** — was a circle outline + two eye dots + a flat
            horizontal mouth bar. Now the bar carries three small
            vertical teeth pips so it reads as a clenched-jaw skull
            (more menacing for the "critical" milestone tier) instead
            of a plain "—" line.
        """
        cx, cy = center
        if kind == "star":
            # Filled star polygon (unchanged baseline).
            pts: list[tuple[int, int]] = []
            for i in range(10):
                radius = r if i % 2 == 0 else r // 2
                angle = -math.pi / 2 + i * math.pi / 5
                pts.append((
                    cx + int(math.cos(angle) * radius),
                    cy + int(math.sin(angle) * radius),
                ))
            pygame.draw.polygon(surface, color, pts)
            # Bright centre pip — pushes the star's heart toward white
            # so it reads as a luminous celestial body, not a flat
            # die-cut shape. Sized small so it doesn't obscure the
            # spike geometry.
            pip_color = _blend(color, (255, 255, 255), 0.75)
            pygame.draw.circle(surface, pip_color, (cx, cy), max(1, r // 5))
        elif kind == "warn":
            # Translucent fill underneath the outline — the triangle
            # reads as a hazard sign with a body, not a wire-frame.
            triangle = [
                (cx, cy - r),
                (cx - r, cy + r - 1),
                (cx + r, cy + r - 1),
            ]
            fill_layer = pygame.Surface(
                (r * 2 + 4, r * 2 + 4), pygame.SRCALPHA,
            )
            local_pts = [(p[0] - (cx - r - 2), p[1] - (cy - r - 2)) for p in triangle]
            pygame.draw.polygon(fill_layer, (*color, 70), local_pts)
            surface.blit(fill_layer, (cx - r - 2, cy - r - 2))
            # Outline + exclamation bar + terminal pip on top.
            pygame.draw.polygon(surface, color, triangle, 2)
            pygame.draw.line(
                surface, color,
                (cx, cy - r // 3),
                (cx, cy + r // 3),
                2,
            )
            pygame.draw.circle(surface, color, (cx, cy + r // 2 + 1), 1)
        elif kind == "skull":
            # Circle + eye dots (unchanged baseline).
            pygame.draw.circle(surface, color, (cx, cy), r, 2)
            eye_dx = r // 2
            pygame.draw.circle(surface, color, (cx - eye_dx, cy - 1), 2)
            pygame.draw.circle(surface, color, (cx + eye_dx, cy - 1), 2)
            # Clenched-jaw mouth: horizontal bar plus three small
            # vertical teeth pips. Was just a flat "—" line which
            # read as decorative; the teeth give the icon a
            # critical-severity character.
            mouth_y = cy + r // 2
            mouth_left = cx - r // 2
            mouth_right = cx + r // 2
            pygame.draw.line(
                surface, color,
                (mouth_left, mouth_y), (mouth_right, mouth_y), 2,
            )
            tooth_h = max(2, r // 6)
            for tooth_x in (
                mouth_left + (mouth_right - mouth_left) // 4,
                cx,
                mouth_right - (mouth_right - mouth_left) // 4,
            ):
                pygame.draw.line(
                    surface, color,
                    (tooth_x, mouth_y),
                    (tooth_x, mouth_y + tooth_h),
                    1,
                )
        else:
            glyph = self.fonts.label.render(
                kind[:1].upper(), True, color,
            )
            surface.blit(
                glyph,
                (cx - glyph.get_width() // 2,
                 cy - glyph.get_height() // 2),
            )

    # ----------------------------------------------------------- flash

    def _draw_flash(self, surface: pygame.Surface, game: Game) -> None:
        """Cinematic "foyer initial" intro: dim overlay + radial bloom + giant
        element badge + animated ripple rings + title and subtitle."""
        if game.disable_flash:
            return
        flash = game.flash
        if flash is None:
            return
        w, h = self.screen_size
        progress = min(1.0, flash.age / flash.lifetime)
        # Three-phase envelope: fade in, hold, fade out.
        if progress < 0.25:
            envelope = progress / 0.25
        elif progress < 0.65:
            envelope = 1.0
        else:
            envelope = max(0.0, 1.0 - (progress - 0.65) / 0.35)
        if envelope <= 0:
            return

        overlay_alpha = int(220 * envelope)
        overlay = pygame.Surface((w, h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, overlay_alpha))
        surface.blit(overlay, (0, 0))

        cx, cy = w // 2, h // 2 - 16

        # Catastrophe-tint radial bloom behind everything.
        bloom_r = int(min(w, h) * 0.6 * envelope)
        bloom = pygame.Surface((bloom_r * 2, bloom_r * 2), pygame.SRCALPHA)
        for r in range(bloom_r, 0, -3):
            t = r / bloom_r
            alpha = int(50 * (1 - t) ** 1.8 * envelope)
            if alpha < 1:
                continue
            pygame.draw.circle(bloom, (*flash.color, alpha), (bloom_r, bloom_r), r)
        surface.blit(bloom, (cx - bloom_r, cy - bloom_r))

        # Animated ripple rings emanating from the badge — driven by age so
        # they grow over the flash's lifetime.
        for i in range(3):
            ring_progress = (progress + i * 0.33) % 1.0
            if ring_progress > 0.8:
                continue
            ring_r = int(70 + ring_progress * 220)
            ring_alpha = int(140 * (1 - ring_progress) * envelope)
            if ring_alpha < 1:
                continue
            ring_layer = pygame.Surface(
                (ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA,
            )
            pygame.draw.circle(
                ring_layer, (*flash.color, ring_alpha),
                (ring_r + 2, ring_r + 2), ring_r, 2,
            )
            surface.blit(ring_layer, (cx - ring_r - 2, cy - ring_r - 2))

        # Hero element badge — big disc + element glyph.
        badge_r = 64
        # Slight scale-in pop during fade-in for a "landing impact" feel.
        scale = 0.6 + 0.4 * min(1.0, progress * 3.5)
        badge_r_scaled = int(badge_r * scale)
        pygame.draw.circle(
            surface, _blend((10, 12, 18), flash.color, 0.55),
            (cx, cy - 26), badge_r_scaled,
        )
        pygame.draw.circle(
            surface, flash.color, (cx, cy - 26), badge_r_scaled, 4,
        )
        # Inner icon (using the active catastrophe glyph).
        self._draw_element_icon(
            surface, game.gaia.active.name,
            (cx, cy - 26), int(badge_r_scaled * 0.55), flash.color,
        )

        # Title under the badge.
        title_color = _blend(self.palette.background, (255, 255, 255), envelope)
        title = self.fonts.giant.render(flash.text, True, title_color)
        title_y = cy + badge_r - 4
        # Catastrophe-tint glow ghost behind the title.
        glow = self.fonts.giant.render(
            flash.text, True, _blend(self.palette.background, flash.color, envelope),
        )
        glow_pos = ((w - glow.get_width()) // 2, title_y + 2)
        for off in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            surface.blit(glow, (glow_pos[0] + off[0], glow_pos[1] + off[1]))
        surface.blit(title, ((w - title.get_width()) // 2, title_y))

        # Subtitle: "FOYER INITIAL : COUNTRY" — small caps, dim accent.
        sub_color = _blend(
            self.palette.background, self.palette.text_label, envelope,
        )
        subtitle = self.fonts.label.render(flash.subtitle, True, sub_color)
        surface.blit(
            subtitle,
            ((w - subtitle.get_width()) // 2,
             title_y + title.get_height() + 8),
        )

    # ------------------------------------------------------- settings

    def _draw_settings_overlay(self, surface: pygame.Surface, game: Game) -> None:
        """Centered tabbed settings modal — audio + accessibility.

        Rounded translucent card matching the help-modal / impact-card
        idiom. Previously the panel had sharp corners + a flat gradient
        which read as legacy next to the redesigned panes.
        """
        w, h = self.screen_size
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 210))
        surface.blit(dim, (0, 0))

        panel = settings_panel_rect(self.config)
        radius = 14
        self._draw_shadow(surface, panel, blur=24, alpha=190)
        # Rounded translucent card body with a smooth top-edge highlight.
        # Previously a half-panel rect overlay gave the card a visible
        # midpoint colour band ("weird two-tone background") on the taller
        # settings panel. Now the highlight fades smoothly to transparent.
        body = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(
            body, (*self.palette.surface_elevated[:3], 248),
            (0, 0, panel.width, panel.height), border_radius=radius,
        )
        self._fade_card_highlight(
            body, panel.width, panel.height, radius,
            peak_lowlight_alpha=22,
        )
        surface.blit(body, panel.topleft)
        pygame.draw.rect(
            surface, self.palette.ui_border_soft,
            panel, 1, border_radius=radius,
        )
        # Top accent stripe — rounded top corners only, matching help modal.
        accent_strip = pygame.Surface((panel.width, 3), pygame.SRCALPHA)
        pygame.draw.rect(
            accent_strip, (*self.palette.ui_accent, 255),
            (0, 0, panel.width, 3),
            border_top_left_radius=radius,
            border_top_right_radius=radius,
        )
        surface.blit(accent_strip, panel.topleft)

        # Header — tag + title + short accent underline under the
        # title. The underline anchors the header section as a
        # defined block against the tabs below (was just floating
        # text with no boundary). Matches the picker title accent
        # underline idiom — same design vocabulary across modals.
        tag = self.fonts.label.render(
            "RÉGLAGES", True, self.palette.text_label,
        )
        surface.blit(tag, (panel.left + 24, panel.top + 16))
        title = self.fonts.title.render(
            "PARAMÈTRES", True, self.palette.text,
        )
        title_x = panel.left + 24
        title_y = panel.top + 16 + tag.get_height() + 2
        surface.blit(title, (title_x, title_y))
        # Short accent underline — sized to ~50 % of the title width,
        # left-aligned with the title. Catastrophe-agnostic accent
        # since this modal is global (opens from title / pause / play).
        underline_w = max(60, title.get_width() // 2)
        underline_y = title_y + title.get_height() + 4
        accent_strip = pygame.Surface((underline_w, 2), pygame.SRCALPHA)
        for px in range(underline_w):
            # Falloff: full alpha at the left, fading to 0 at the right
            # — gives the line a "ticker" direction reading.
            t = 1.0 - (px / underline_w)
            a = int(220 * (t ** 1.2))
            if a <= 0:
                continue
            pygame.draw.line(
                accent_strip, (*self.palette.ui_accent, a),
                (px, 0), (px, 1),
            )
        surface.blit(accent_strip, (title_x, underline_y))

        # Close × — translucent white disc + white × glyph, matching the
        # info-panel / impact-card / skill-tree style. (Was a saturated red
        # disc which clashed with the dim panel and broke design consistency.)
        close = settings_close_rect(self.config)
        mouse_pos = pygame.mouse.get_pos()
        hover_close = close.collidepoint(mouse_pos)
        close_r = close.width // 2
        close_layer = pygame.Surface(
            (close_r * 2, close_r * 2), pygame.SRCALPHA,
        )
        circle_alpha = 130 if hover_close else 70
        pygame.draw.circle(
            close_layer, (255, 255, 255, circle_alpha),
            (close_r, close_r), close_r,
        )
        # Stroke alpha matches the tutorial overlay and help modal
        # close buttons (180/100). Was 200/120 here only — a lone
        # one-off brighter ring with no corresponding semantic
        # difference. All three modals sit on the same
        # ``surface_elevated`` card body, so the close affordance
        # should read with the same visual weight.
        pygame.draw.circle(
            close_layer, (255, 255, 255, 180 if hover_close else 100),
            (close_r, close_r), close_r, 1,
        )
        surface.blit(
            close_layer, (close.centerx - close_r, close.centery - close_r),
        )
        cx_close, cy_close = close.center
        x_color = (255, 255, 255)
        pygame.draw.line(
            surface, x_color,
            (cx_close - 5, cy_close - 5), (cx_close + 5, cy_close + 5), 2,
        )
        pygame.draw.line(
            surface, x_color,
            (cx_close + 5, cy_close - 5), (cx_close - 5, cy_close + 5), 2,
        )

        # Tabs.
        tab_rects = settings_tab_rects(self.config)
        tab_labels = {"audio": "AUDIO", "accessibility": "ACCESSIBILITÉ"}
        for key, rect in tab_rects.items():
            self._draw_pill(
                surface, rect, tab_labels[key],
                active=game.settings_tab == key,
                tint=self.palette.ui_accent,
                hover=rect.collidepoint(mouse_pos),
            )

        # Tab content.
        toggles = settings_toggle_rects(self.config)
        if game.settings_tab == "audio":
            self._draw_settings_row(
                surface, panel, 0, "Couper le son",
                "Bascule instantanée (raccourci M).",
                toggles["mute"], game.audio_muted,
            )
        else:
            self._draw_settings_row(
                surface, panel, 0, "Réduire les animations",
                "Désactive particules ambiantes et pulsations du titre.",
                toggles["reduce_motion"], game.reduce_motion,
            )
            self._draw_settings_row(
                surface, panel, 1, "Désactiver l'écran d'émergence",
                "Ignore le flash plein écran au lancement du scénario.",
                toggles["disable_flash"], game.disable_flash,
            )
            self._draw_settings_row(
                surface, panel, 2, "Contraste élevé",
                "Renforce les contours et les couleurs d'alerte.",
                toggles["high_contrast"], game.high_contrast,
            )

        hint = self.fonts.label.render(
            "ÉCHAP POUR FERMER · RÉGLAGES SAUVEGARDÉS AUTOMATIQUEMENT",
            True, self.palette.text_dim,
        )
        surface.blit(
            hint,
            (panel.centerx - hint.get_width() // 2,
             panel.bottom - hint.get_height() - 14),
        )

    def _draw_settings_row(
        self,
        surface: pygame.Surface,
        panel: pygame.Rect,
        index: int,
        label: str,
        description: str,
        toggle_rect: pygame.Rect,
        on: bool,
    ) -> None:
        """Single row: label + description on the left, toggle on the right.

        The label/desc block is *vertically centred* on the 56 px row so it
        aligns with the toggle's centerline. Previously the label sat at
        row_y while the toggle floated mid-row, giving a misaligned look
        in the ACCESSIBILITÉ tab where rows stack tightly.
        """
        row_h = 56
        row_y = panel.top + 130 + index * row_h
        x = panel.left + 24
        # ---- Row backing card ----
        # Was floating text + toggle with no chrome between rows. Now
        # each row sits in a subtle deep-surface card so the panel
        # reads as a structured form instead of a list of strings:
        #   * Deep-surface translucent fill so the row is darker than
        #     the panel body it sits in (visual hierarchy).
        #   * Top-edge highlight stroke (1 px white α 26) — the same
        #     screen-surface depth idiom shipped on every elevated
        #     chrome surface.
        #   * Bottom-edge shadow stroke (1 px black α 60) — completes
        #     the raised-card cue.
        #   * Hairline border (ui_border_soft) for crisp definition.
        row_card_x = panel.left + 16
        row_card_w = panel.width - 32
        row_card = pygame.Rect(
            row_card_x, row_y + 2, row_card_w, row_h - 4,
        )
        card_layer = pygame.Surface(row_card.size, pygame.SRCALPHA)
        pygame.draw.rect(
            card_layer, (*self.palette.surface_deep[:3], 130),
            (0, 0, row_card.width, row_card.height),
            border_radius=8,
        )
        # Top-edge highlight + bottom-edge shadow strokes.
        pygame.draw.line(
            card_layer, (255, 255, 255, 26),
            (10, 1), (row_card.width - 10, 1),
        )
        pygame.draw.line(
            card_layer, (0, 0, 0, 60),
            (10, row_card.height - 2),
            (row_card.width - 10, row_card.height - 2),
        )
        surface.blit(card_layer, row_card.topleft)
        pygame.draw.rect(
            surface, self.palette.ui_border_soft,
            row_card, 1, border_radius=8,
        )
        # Auto-fit the description so long French strings don't bleed under
        # the toggle pill on the right edge of the panel.
        desc_max_w = toggle_rect.left - x - 16
        label_text = self.fonts.medium.render(label, True, self.palette.text)
        desc_fit = self._fit_text(description, self.fonts.small, desc_max_w)
        desc = self.fonts.small.render(desc_fit, True, self.palette.text_dim)
        # Vertical centring of the label + desc as a block.
        block_h = label_text.get_height() + 2 + desc.get_height()
        block_top = row_y + (row_h - block_h) // 2
        surface.blit(label_text, (x, block_top))
        surface.blit(desc, (x, block_top + label_text.get_height() + 2))
        # Toggle pill: green ON / dark OFF, with knob. The OFF track was
        # `surface_overlay (52, 62, 88)` on the panel's `surface_elevated
        # (38, 46, 68)` — only 1.5:1 luminance ratio, so the track
        # nearly disappeared into the panel and players had to read the
        # knob position to tell on/off. Darkening the OFF track to
        # `(18, 22, 34)` (clearly darker than the panel, ≈2.2:1 ratio
        # the *other* direction) gives the toggle a visible "depression"
        # — the control reads as a slot the knob slides in, not a flat
        # smudge of similar tones.
        track_color = (
            LIGHT_SUCCESS if on else (18, 22, 34)
        )
        pygame.draw.rect(
            surface, track_color, toggle_rect,
            border_radius=toggle_rect.height // 2,
        )
        # Inset shadow at the top of the track — 1 px line at black
        # α 100, inset 4 px so it doesn't crash the rounded ends.
        # Reads as a *depression* (the knob slides in a slot), not a
        # flat coloured pill. Same idiom physical toggle switches use
        # — the track is inset into the housing, the knob sits in
        # the track. Without this the toggle reads as paint, not as
        # a moulded control. Skipped on the ON state because the
        # bright green track already carries enough visual weight.
        if not on:
            inset_shadow = pygame.Surface(
                (toggle_rect.width - 8, 1), pygame.SRCALPHA,
            )
            inset_shadow.fill((0, 0, 0, 100))
            surface.blit(
                inset_shadow,
                (toggle_rect.left + 4, toggle_rect.top + 1),
            )
        # Thin border so OFF state still reads as a control, not a void.
        pygame.draw.rect(
            surface,
            (110, 220, 150) if on else self.palette.ui_border,
            toggle_rect, 1,
            border_radius=toggle_rect.height // 2,
        )
        knob_r = toggle_rect.height // 2 - 4
        knob_x = (
            toggle_rect.right - knob_r - 4 if on
            else toggle_rect.left + knob_r + 4
        )
        knob_cy = toggle_rect.centery
        # Drop shadow under the knob — cast onto the track. Offset
        # 2 px down + 1 px right. Built on a separate SRCALPHA layer
        # because ``pygame.draw.circle`` on the live surface ignores
        # the colour's alpha channel — the layer approach lets the
        # shadow blend properly with the track underneath. Adds
        # material depth: the knob sits *on top of* the track
        # surface, not painted *into* it.
        knob_shadow_layer = pygame.Surface(
            (knob_r * 2 + 4, knob_r * 2 + 4), pygame.SRCALPHA,
        )
        pygame.draw.circle(
            knob_shadow_layer, (0, 0, 0, 100),
            (knob_r + 2, knob_r + 2), knob_r,
        )
        surface.blit(
            knob_shadow_layer,
            (knob_x + 1 - (knob_r + 2), knob_cy + 2 - (knob_r + 2)),
        )
        # Knob body — flat white-grey base.
        pygame.draw.circle(
            surface, (245, 245, 250),
            (knob_x, knob_cy), knob_r,
        )
        # Specular highlight — small near-white pip at the upper-left
        # quadrant of the knob. Reads as light falling from above,
        # giving the knob a 3D sphere feel rather than a flat disc.
        # Same idiom used on the orb collection points + impact card
        # element badge — every circular interactive element in the
        # codebase now carries a specular highlight.
        if knob_r >= 4:
            hl_r = max(1, knob_r // 3)
            hl_offset = max(1, knob_r // 3)
            pygame.draw.circle(
                surface, (255, 255, 255),
                (knob_x - hl_offset, knob_cy - hl_offset),
                hl_r,
            )
        # Subtle bottom shadow ring on the knob itself — 1 px dark
        # ring at the very bottom edge. Anchors the knob visually
        # without adding heavy chrome.
        if knob_r >= 5:
            pygame.draw.circle(
                surface, (200, 200, 210),
                (knob_x, knob_cy), knob_r, 1,
            )

    # ------------------------------------------------------- pause menu

    def _draw_pause_menu(self, surface: pygame.Surface, game: Game) -> None:
        """Centered pause menu — three button clusters (REPRISE / ACTIONS /
        FIN DE SESSION) with section labels and grouped spacing. Title lives
        at the top of the screen so it never clashes with the first section
        label (which now sits just above the REPRENDRE button)."""
        w, h = self.screen_size
        cat_color = game.gaia.active.arc_color
        # Dim the underlying gameplay 60% so the menu has clear focus.
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        surface.blit(dim, (0, 0))
        # Textured atmospheric overlay — same warm-cool gradient +
        # film-grain idiom shipped on the picker, info panel, and
        # worldmap. Reuses the picker cache (same screen size, same
        # seed) so cost is one blit per frame. Grades the dim out of
        # flatness without obscuring the menu chrome.
        self._draw_picker_texture_overlay(surface, (w, h))
        # Soft radial vignette focused on screen centre — corners
        # darker so the eye lands on the menu without being pulled
        # toward the dim's outer edges. Cached at the screen size.
        self._draw_pause_vignette(surface, (w, h))

        # Compute the menu's top y so the title hovers cleanly above the
        # first section label without overlapping it.
        rects = pause_menu_button_rects(self.config)
        menu_top = rects["resume"].top
        title = self.fonts.giant.render(
            "PAUSE", True, self.palette.text,
        )
        # Title sits 20 px above the first section label — tighter than
        # the previous 36 px so the title + button stack read as one
        # contained dialog inside the wrapping panel card.
        title_y = max(36, menu_top - title.get_height() - 28)
        title_x = (w - title.get_width()) // 2

        # ---- Panel card (NEW) — wraps title + section labels + button
        # stack so the menu reads as a focused dialog rather than a
        # column of buttons floating over the dim. Sized to contain
        # the title at the top and the QUITTER button at the bottom
        # with 24 px padding inside each edge.
        card_pad_x = 40
        card_pad_top = 22
        card_pad_bottom = 28
        bottom_btn = rects["quit"]
        # Section labels for "REPRISE" / "ACTIONS" / "FIN DE SESSION"
        # sit ~12 px to the LEFT of the buttons (the catastrophe-tinted
        # leading dot extends to rect.left - 8 - dot_r). Card padding
        # on the left needs to clear that, so card_left sits 12 px
        # further left than the buttons.
        card_left = rects["resume"].left - 12 - card_pad_x
        card_right = rects["resume"].right + card_pad_x
        card_top = title_y - card_pad_top
        card_bottom = bottom_btn.bottom + card_pad_bottom
        card_rect = pygame.Rect(
            card_left, card_top,
            card_right - card_left,
            card_bottom - card_top,
        )
        # Drop shadow — strong elevation since this is a modal-class
        # dialog interrupting gameplay. Matches the help modal weight.
        self._draw_shadow(surface, card_rect, blur=22, alpha=190, offset_y=6)
        # Body fill with the standard panel gradient (top brighter,
        # bottom darker) so the card has subtle shape.
        self._fill_panel(surface, card_rect, self.palette.surface_elevated)
        # Catastrophe-tinted top stripe — 3 px, full width, anchors
        # the card to the active catastrophe identity (same idiom on
        # info panel, help modal, pause confirm).
        pygame.draw.rect(
            surface, cat_color,
            (card_rect.left, card_rect.top, card_rect.width, 3),
        )
        # Soft top-edge highlight + bottom-edge shadow strokes —
        # screen-surface depth idiom (asymmetric α 38 / α 80 to
        # compensate for perception's logarithmic lightness response).
        depth = pygame.Surface(card_rect.size, pygame.SRCALPHA)
        pygame.draw.line(
            depth, (255, 255, 255, 38),
            (12, 4), (card_rect.width - 12, 4),
        )
        pygame.draw.line(
            depth, (0, 0, 0, 80),
            (12, card_rect.height - 2),
            (card_rect.width - 12, card_rect.height - 2),
        )
        surface.blit(depth, card_rect.topleft)
        # Hairline border for crisp definition.
        pygame.draw.rect(
            surface, self.palette.ui_border_soft,
            card_rect, 1, border_radius=0,
        )

        surface.blit(title, (title_x, title_y))
        # Catastrophe-tinted underline beneath the title — same idiom
        # the help modal + settings overlay titles use to carry
        # identity into chrome. Sits 4 px below the baseline,
        # 1/3 the title width, with a left-to-right alpha falloff
        # so it reads as a *lit accent* rather than a hard bar.
        underline_w = max(60, title.get_width() // 3)
        underline_x = title_x + (title.get_width() - underline_w) // 2
        underline_y = title_y + title.get_height() + 4
        underline = pygame.Surface((underline_w, 2), pygame.SRCALPHA)
        for px in range(underline_w):
            # Symmetric falloff — brightest in the middle, fading at
            # both ends. Reads as a polished accent stripe, not a
            # flat coloured rect.
            t = abs(px - underline_w / 2) / (underline_w / 2)
            a = int(220 * (1.0 - t) ** 1.2)
            if a <= 0:
                continue
            pygame.draw.line(
                underline, (*cat_color, a), (px, 0), (px, 1),
            )
        surface.blit(underline, (underline_x, underline_y))

        # Buttons.
        rects = pause_menu_button_rects(self.config)
        mouse_pos = pygame.mouse.get_pos()
        labels = {
            "resume":   ("REPRENDRE",     True),
            "restart":  ("RECOMMENCER",   False),
            "settings": ("PARAMÈTRES",    False),
            "help":     ("AIDE",          False),
            # Was "REVENIR AU MENU" — but ``abandon_run`` routes to the
            # picker, not the title screen, so the label named the
            # wrong destination. "ABANDONNER" matches the action verb
            # (the method, the news ticker line, the confirm question),
            # and the section label "FIN DE SESSION" + the modal
            # explain string already establish that this ends the
            # *scenario*, not the game.
            "abandon":  ("ABANDONNER", False),
            "quit":     ("QUITTER LE JEU",  False),
        }
        # Section labels drawn above the group-leading button so the menu
        # reads as three intentional clusters instead of a flat stack.
        section_titles = {
            "resume":   "REPRISE",
            "restart":  "ACTIONS",
            "abandon":  "FIN DE SESSION",
        }
        # Destructive ones get a red outline to discourage mis-click.
        destructive = {"abandon", "quit"}
        for key, rect in rects.items():
            section = section_titles.get(key)
            if section is not None:
                section_text = self.fonts.label.render(
                    section, True, self.palette.text_label,
                )
                section_y = rect.top - section_text.get_height() - 2
                # Catastrophe-tinted leading dot — same idiom the
                # news ticker bullets use to mark each section. The
                # dot sits 3 px to the left of the section text, at
                # the same baseline. Reads as a *lit accent* that
                # categorises each section visually before the eye
                # even parses the label.
                dot_r = 3
                dot_cx = rect.left - 8 - dot_r
                dot_cy = section_y + section_text.get_height() // 2
                # Soft halo behind the dot — radial alpha falloff.
                halo_r = 5
                halo = pygame.Surface(
                    (halo_r * 2 + 2, halo_r * 2 + 2), pygame.SRCALPHA,
                )
                for r in range(halo_r, dot_r, -1):
                    t = (halo_r - r) / max(1, halo_r - dot_r - 1)
                    a = int(50 * t ** 0.9)
                    if a < 1:
                        continue
                    pygame.draw.circle(
                        halo, (*cat_color, a),
                        (halo_r + 1, halo_r + 1), r,
                    )
                surface.blit(halo, (dot_cx - halo_r - 1, dot_cy - halo_r - 1))
                pygame.draw.circle(
                    surface, cat_color, (dot_cx, dot_cy), dot_r,
                )
                surface.blit(
                    section_text,
                    (rect.left, section_y),
                )
            label, primary = labels[key]
            hover = rect.collidepoint(mouse_pos)
            if key in destructive:
                self._draw_destructive_button(surface, rect, label, hover=hover)
            else:
                self._draw_chunky_button(
                    surface, rect, label=label, primary=primary, hover=hover,
                )

        # Confirmation modal — sits over the pause menu when a destructive
        # action is in flight.
        if game.pause_confirm:
            self._draw_pause_confirm(surface, game)

    def _draw_destructive_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        hover: bool,
    ) -> None:
        """Red-outlined chunky button for irreversible actions (abandon, quit).

        Font auto-shrinks from title → large → medium when the label doesn't
        fit; previously CONFIRMER overflowed the 160 px confirm button.

        Previously the button leaned on colour alone (red outline +
        dark red fill + red text) to communicate "destructive". On a
        screen where every other red element is also danger-tinted
        (severe state, milestone CRITIQUE), the button didn't earn
        the extra weight its consequences (erase the run) warranted.
        Layered three additional cues:

          1. **Inner-edge red glow** when hovering — a soft red-tinted
             halo just inside the rect border, growing with hover.
             Reads as the button "lighting up dangerous" on pointer
             contact, not just changing fill.
          2. **Diagonal warning hatch** on hover at low alpha. Matches
             the universal yellow-and-black caution-tape vocabulary
             (rendered in severe red here for catastrophe-tint
             consistency). Inactive (non-hover) state stays clean so
             the button still reads as a normal element until the
             player is committing.
          3. **Caution-triangle glyph** at the left edge of the
             button — a small filled severe-coloured triangle with a
             white "!" inside. Communicates the action class
             *visually*, not just textually. Sized to the button's
             height so it scales with the auto-shrunk text.
        """
        # Soft Pillow Gaussian shadow for the destructive button —
        # mid elevation (blur=10, alpha=130, offset=4) matches the
        # weight of a "this action is irreversible" CTA: heavier than
        # a list row, lighter than the chunky primary CTAs.
        self._draw_shadow(surface, rect, blur=10, alpha=130, offset_y=4)
        fill = (60, 22, 28) if hover else (38, 18, 22)
        pygame.draw.rect(surface, fill, rect, border_radius=12)
        # Vertical gradient overlay — same depth idiom as the chunky
        # button. Top +12 luminance / bottom −12 (slightly subtler
        # than chunky's ±15 because the destructive button already
        # carries strong colour from the dark-red fill). Reads as a
        # *raised tactile button* instead of a flat dark-red rect.
        prev_clip = surface.get_clip()
        surface.set_clip(rect)
        grad = pygame.Surface(rect.size, pygame.SRCALPHA)
        for gy in range(rect.height):
            t = gy / max(1, rect.height - 1)
            shift = int(12 * (1.0 - 2 * t))
            if shift > 0:
                pygame.draw.line(
                    grad, (255, 255, 255, min(255, shift * 3)),
                    (0, gy), (rect.width, gy),
                )
            elif shift < 0:
                pygame.draw.line(
                    grad, (0, 0, 0, min(255, -shift * 3)),
                    (0, gy), (rect.width, gy),
                )
        surface.blit(grad, rect.topleft)
        surface.set_clip(prev_clip)

        # 1. Inner-edge red glow on hover.
        if hover:
            glow = pygame.Surface(rect.size, pygame.SRCALPHA)
            for inset in range(3, 0, -1):
                alpha = int(70 * (1 - inset / 3) ** 1.4) + 30
                pygame.draw.rect(
                    glow, (*self.palette.severe, alpha),
                    (inset, inset, rect.width - inset * 2,
                     rect.height - inset * 2),
                    1, border_radius=12 - inset,
                )
            surface.blit(glow, rect.topleft)

            # 2. Diagonal caution hatch — low-alpha severe-red stripes.
            hatch = pygame.Surface(
                (rect.width - 6, rect.height - 6), pygame.SRCALPHA,
            )
            step = 10
            hatch_color = (*self.palette.severe, 22)
            for offset in range(-rect.height, rect.width + rect.height, step):
                pygame.draw.line(
                    hatch, hatch_color,
                    (offset, 0), (offset + rect.height, rect.height - 6),
                    2,
                )
            # Clip the hatch to the rounded rect via a mask blit.
            mask = pygame.Surface(
                (rect.width - 6, rect.height - 6), pygame.SRCALPHA,
            )
            pygame.draw.rect(
                mask, (255, 255, 255, 255),
                (0, 0, rect.width - 6, rect.height - 6),
                border_radius=9,
            )
            hatch.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            surface.blit(hatch, (rect.left + 3, rect.top + 3))

        pygame.draw.rect(surface, self.palette.severe, rect, 2, border_radius=12)

        # 3. Caution-triangle glyph at the left edge.
        glyph_h = min(rect.height - 16, 22)
        glyph_cx = rect.left + 18
        glyph_cy = rect.centery
        glyph_top = glyph_cy - glyph_h // 2
        glyph_pts = [
            (glyph_cx, glyph_top),
            (glyph_cx - glyph_h // 2, glyph_top + glyph_h),
            (glyph_cx + glyph_h // 2, glyph_top + glyph_h),
        ]
        pygame.draw.polygon(surface, self.palette.severe, glyph_pts)
        pygame.draw.polygon(
            surface, _blend(self.palette.severe, (0, 0, 0), 0.45),
            glyph_pts, 1,
        )
        # White "!" inside the triangle — high-contrast cue.
        bang = self.fonts.label.render("!", True, (255, 255, 255))
        surface.blit(
            bang,
            (glyph_cx - bang.get_width() // 2,
             glyph_cy - bang.get_height() // 2 + 1),
        )

        max_w = rect.width - 20
        use_font = self.fonts.title
        if use_font.size(label)[0] > max_w:
            use_font = self.fonts.large
            if use_font.size(label)[0] > max_w:
                use_font = self.fonts.medium
        text = use_font.render(label, True, self.palette.severe)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2,
             rect.centery - text.get_height() // 2),
        )

    def _draw_pause_confirm(self, surface: pygame.Surface, game: Game) -> None:
        """Yes/No confirm panel layered over the pause menu."""
        w, h = self.screen_size
        # Full opaque dim so the pause menu disappears entirely behind the
        # confirm — previously it bled through and made the dialog unreadable.
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 235))
        surface.blit(dim, (0, 0))
        if game.pause_confirm == "abandon":
            # Question used to be "Revenir au menu principal ?" — but
            # ``abandon_run`` routes to ``Phase.PICKER`` (the selection
            # screen), not TITLE. The explain string was fixed earlier
            # to name the actual destination; the question stayed
            # behind, so the modal asked "back to menu" then dropped
            # the player on the picker. "Abandonner le scénario ?"
            # mirrors the action verb (``abandon_run``, news ticker
            # "Retour au choix de scénario"), and matches the parallel
            # "Recommencer le scénario ?" right below — three confirm
            # questions now use three distinct action verbs (abandon /
            # recommencer / quitter) instead of two overlapping ones.
            question = "Abandonner le scénario ?"
            explain = (
                "Votre progression sera perdue. Vous reviendrez à l'écran de sélection."
            )
        elif game.pause_confirm == "restart":
            # "Simulation" / "partie" were the legacy vocabulary;
            # this session standardised on "scénario" (news ticker,
            # outcome lines, abandon ticker) so the confirm modal
            # now speaks the same word the rest of the UI does.
            question = "Recommencer le scénario ?"
            explain = (
                "Un nouveau scénario démarrera depuis la sélection."
                " La progression actuelle sera perdue."
            )
        else:
            question = "Quitter le jeu ?"
            explain = "Cette session se terminera immédiatement."
        rects = pause_confirm_button_rects(self.config)
        title_font = self.fonts.title
        sub_font = self.fonts.medium
        title_h = title_font.get_height()
        sub_lines = self._wrap_text(explain, sub_font, w - 120, max_lines=2)
        sub_h = sum(sub_font.get_height() + 2 for _ in sub_lines)
        # Sized panel that contains warning icon + question + explanation +
        # buttons — keeps the eye anchored in one focused card.
        btn = rects["confirm"]
        panel_w = 520
        panel_h = 70 + title_h + 8 + sub_h + 28 + btn.height + 28
        panel = pygame.Rect(
            (w - panel_w) // 2, (h - panel_h) // 2 - 10, panel_w, panel_h,
        )
        self._draw_shadow(surface, panel, blur=24, alpha=200)
        self._fill_panel(surface, panel, self.palette.surface_elevated)
        pygame.draw.rect(
            surface, self.palette.severe,
            (panel.left, panel.top, panel.width, 3),
        )
        # Warning triangle glyph at the top of the panel. Filled severe
        # body + dark "!" inside — industry-standard destructive-action
        # affordance, much more visually committed than the previous
        # hairline-stroked outline + same-colour bang (which read as
        # decorative more than alarming).
        cx = panel.centerx
        cy = panel.top + 38
        warn = [(cx, cy - 16), (cx + 18, cy + 13), (cx - 18, cy + 13)]
        # Soft halo behind the triangle so it pops on the elevated panel.
        halo = pygame.Surface((48, 44), pygame.SRCALPHA)
        for hr in range(20, 0, -2):
            ha = int(50 * (1 - hr / 20) ** 1.6)
            if ha < 1:
                continue
            pygame.draw.circle(
                halo, (*self.palette.severe, ha), (24, 22), hr,
            )
        surface.blit(halo, (cx - 24, cy - 22))
        # Filled body + crisp darker stroke for definition on bright fills.
        pygame.draw.polygon(surface, self.palette.severe, warn)
        pygame.draw.polygon(
            surface, _blend(self.palette.severe, (0, 0, 0), 0.45),
            warn, 2,
        )
        # White "!" inside the filled triangle — high-contrast danger glyph.
        bang = self.fonts.medium.render("!", True, (255, 255, 255))
        surface.blit(
            bang,
            (cx - bang.get_width() // 2,
             cy - bang.get_height() // 2 + 3),
        )

        title = title_font.render(question, True, self.palette.text)
        surface.blit(
            title,
            (panel.centerx - title.get_width() // 2, panel.top + 70),
        )
        sub_y = panel.top + 70 + title_h + 8
        for line in sub_lines:
            t = sub_font.render(line, True, self.palette.text_label)
            surface.blit(
                t, (panel.centerx - t.get_width() // 2, sub_y),
            )
            sub_y += t.get_height() + 2

        mouse_pos = pygame.mouse.get_pos()
        self._draw_destructive_button(
            surface, rects["confirm"], "CONFIRMER",
            hover=rects["confirm"].collidepoint(mouse_pos),
        )
        self._draw_chunky_button(
            surface, rects["cancel"], label="ANNULER",
            primary=False, hover=rects["cancel"].collidepoint(mouse_pos),
        )

    # ------------------------------------------------------- loading bridge

    def _draw_loading_bridge(self, surface: pygame.Surface, game: Game) -> None:
        """500 ms picker→playing bridge: catastrophe name + progress bar + fact.

        Cinematic intro for the simulation: aurora bloom in the catastrophe
        tint behind the title, title fades up + drifts down, progress bar has
        a glowing leading edge that pulses with motion.

        Duration matches ``LOADING_BRIDGE_FRAMES = 30`` at 60 fps. (The
        docstring read "600 ms" historically — a stale value from when
        the bridge constant was 36 frames. The dataclass docstring on
        ``LoadingBridge`` was updated when the constant changed; this
        renderer docstring drifted out of sync.)
        """
        bridge = game.loading_bridge
        if bridge is None:
            return
        w, h = self.screen_size
        # Heavy dim — bridge takes the screen for its full duration.
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 220))
        surface.blit(dim, (0, 0))

        progress = min(1.0, bridge.age / bridge.lifetime)
        reduce_motion = game.reduce_motion

        # Soft aurora bloom behind the title in the catastrophe tint. Pulses
        # subtly with progress so the screen feels alive even while loading.
        if not reduce_motion:
            bloom_pulse = 0.6 + 0.4 * math.sin(
                pygame.time.get_ticks() * 0.003
            )
            bloom_r = int(280 * bloom_pulse)
            bloom = pygame.Surface(
                (bloom_r * 2, bloom_r * 2), pygame.SRCALPHA,
            )
            for r in range(bloom_r, 0, -4):
                t = r / bloom_r
                a = int(45 * (1 - t) ** 1.8)
                if a < 1:
                    continue
                pygame.draw.circle(
                    bloom, (*bridge.accent, a), (bloom_r, bloom_r), r,
                )
            surface.blit(
                bloom, (w // 2 - bloom_r, h // 2 - 60 - bloom_r),
            )

        # Title envelope — fades in + drifts down during first 30% of bridge.
        if reduce_motion:
            title_alpha = 255
            title_drift = 0
        else:
            title_intro_t = min(1.0, progress / 0.30)
            title_alpha = int(255 * (title_intro_t ** 0.6))
            title_drift = int((1.0 - title_intro_t) * -18)

        # Catastrophe label.
        label = self.fonts.label.render(
            "INITIALISATION DU SCÉNARIO", True, self.palette.text_dim,
        )
        if title_alpha < 255:
            label.set_alpha(title_alpha)
        surface.blit(
            label,
            ((w - label.get_width()) // 2, h // 2 - 120 + title_drift),
        )
        # Darken light tints so the giant title carries enough contrast on the
        # dim. Air / Vie titles were washing out at full saturation.
        title_color = _blend(bridge.accent, (255, 255, 255), 0.10)
        title = self.fonts.giant.render(
            bridge.catastrophe_name.upper(), True, title_color,
        )
        if title_alpha < 255:
            title.set_alpha(title_alpha)
        surface.blit(
            title,
            ((w - title.get_width()) // 2, h // 2 - 80 + title_drift),
        )

        # Progress bar — inset trough + gradient fill + leading-edge glow.
        # Same depth idiom shipped on the main DÉSÉQUILIBRE / ÉQUILIBRE
        # bar so the loading bridge reads as part of the same visual
        # language. Was a flat trough + flat fill that read as a
        # painted swatch; now reads as a coloured substance flowing
        # along a recessed channel.
        bar_w = 440
        bar_h = 8
        bar_x = (w - bar_w) // 2
        bar_y = h // 2 + 20
        trough_color = _shade(self.palette.surface_overlay, 0.78)
        pygame.draw.rect(
            surface, trough_color,
            (bar_x, bar_y, bar_w, bar_h),
            border_radius=bar_h // 2,
        )
        # Inset edge strokes — top inner shadow + bottom inner highlight.
        edge = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        pygame.draw.rect(
            edge, (0, 0, 0, 90),
            pygame.Rect(0, 0, bar_w, bar_h),
            1, border_radius=bar_h // 2,
        )
        bot_hi = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
        pygame.draw.line(
            bot_hi, (255, 255, 255, 30),
            (bar_h // 2, bar_h - 1),
            (bar_w - bar_h // 2, bar_h - 1),
        )
        edge.blit(bot_hi, (0, 0))
        surface.blit(edge, (bar_x, bar_y))
        fill_w = int(bar_w * progress)
        if fill_w > 0:
            # Fill — vertical gradient (top brighter, bottom darker),
            # masked through a rounded-pill alpha so the gradient
            # respects the bar radius while the right edge trims
            # sharply at the leading edge.
            fill_layer = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
            top_c = _shade(bridge.accent, 1.18)
            bot_c = _shade(bridge.accent, 0.82)
            for py in range(bar_h):
                t = py / max(1, bar_h - 1)
                rr = int(top_c[0] * (1 - t) + bot_c[0] * t)
                gg = int(top_c[1] * (1 - t) + bot_c[1] * t)
                bb = int(top_c[2] * (1 - t) + bot_c[2] * t)
                pygame.draw.line(
                    fill_layer, (rr, gg, bb, 255),
                    (0, py), (fill_w, py),
                )
            mask = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
            pygame.draw.rect(
                mask, (255, 255, 255, 255),
                pygame.Rect(0, 0, fill_w, bar_h),
                border_top_left_radius=bar_h // 2,
                border_bottom_left_radius=bar_h // 2,
                border_top_right_radius=(
                    bar_h // 2 if fill_w >= bar_w - 2 else 0
                ),
                border_bottom_right_radius=(
                    bar_h // 2 if fill_w >= bar_w - 2 else 0
                ),
            )
            fill_layer.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            # Subtle 1-px specular highlight on top of the fill.
            pygame.draw.line(
                fill_layer, (255, 255, 255, 70),
                (bar_h // 2, 1),
                (max(bar_h // 2, fill_w - bar_h // 2), 1),
            )
            surface.blit(fill_layer, (bar_x, bar_y))
            # Leading-edge glow — soft halo at the bar tip suggests "in flight".
            if not reduce_motion and fill_w < bar_w:
                glow_layer = pygame.Surface((40, 40), pygame.SRCALPHA)
                for gr in range(20, 0, -2):
                    t = gr / 20
                    a = int(130 * (1 - t) ** 1.6)
                    if a < 1:
                        continue
                    pygame.draw.circle(
                        glow_layer, (*bridge.accent, a), (20, 20), gr,
                    )
                surface.blit(
                    glow_layer,
                    (bar_x + fill_w - 20, bar_y + bar_h // 2 - 20),
                )

        # Educational fact below the bar — wrapped in a translucent
        # callout card so it reads as a deliberate "did you know"
        # surface rather than floating text on the dim. Card carries
        # the same depth idiom (gradient + edge strokes) as the rest
        # of the chrome family, plus a left-edge catastrophe-tint
        # stripe so the fact ties visually to the run's identity.
        if bridge.fact:
            # Pre-wrap the fact to size the card.
            fact_lines = self._wrap_text(
                bridge.fact, self.fonts.medium, w - 280, max_lines=3,
            )
            label_h = self.fonts.label.get_height()
            line_h = self.fonts.medium.get_height() + 2
            card_inner_h = label_h + 6 + line_h * len(fact_lines)
            card_pad_x = 28
            card_pad_y = 14
            card_w = min(w - 80, max(420, w - 280 + card_pad_x * 2))
            card_h = card_inner_h + card_pad_y * 2
            card_top = bar_y + bar_h + 24
            card_rect = pygame.Rect(
                (w - card_w) // 2, card_top, card_w, card_h,
            )
            # Soft shadow underneath so the card lifts off the dim bg.
            self._draw_shadow(
                surface, card_rect, blur=14, alpha=120,
            )
            # Body — translucent ``surface_elevated`` with the same
            # depth treatment used everywhere else (gradient mask +
            # top-highlight + bottom-shadow). Slight transparency
            # (α 220) lets the aurora bloom bleed through subtly.
            body = pygame.Surface(card_rect.size, pygame.SRCALPHA)
            pygame.draw.rect(
                body, (*self.palette.surface_elevated[:3], 220),
                (0, 0, card_rect.width, card_rect.height),
                border_radius=10,
            )
            surface.blit(body, card_rect.topleft)
            self._apply_button_depth(
                surface, card_rect, self.palette.surface_elevated[:3],
                radius=10,
            )
            # Left-edge catastrophe-tint stripe — 3 px, slightly inset
            # vertically so the rounded corners stay clean.
            pygame.draw.rect(
                surface, bridge.accent,
                (card_rect.left, card_rect.top + 10,
                 3, card_rect.height - 20),
            )
            # Hairline border for crisp edges.
            pygame.draw.rect(
                surface, _blend(self.palette.surface_deep, bridge.accent, 0.45),
                card_rect, 1, border_radius=10,
            )
            # Label inside the card.
            fact_label = self.fonts.label.render(
                "LE SAVIEZ-VOUS ?",
                True, _blend(bridge.accent, (255, 255, 255), 0.45),
            )
            label_x = card_rect.centerx - fact_label.get_width() // 2
            label_y = card_rect.top + card_pad_y
            surface.blit(fact_label, (label_x, label_y))
            # Body text.
            fact_y = label_y + label_h + 6
            for line in fact_lines:
                rendered = self.fonts.medium.render(
                    line, True, self.palette.text,
                )
                surface.blit(
                    rendered,
                    ((w - rendered.get_width()) // 2, fact_y),
                )
                fact_y += rendered.get_height() + 2

    # ----------------------------------------------------- impact card

    def _draw_impact_card(self, surface: pygame.Surface, game: Game) -> None:
        card = game.impact_card
        if card is None:
            return
        w, h = self.screen_size
        progress = card.age / card.lifetime
        # 3-phase envelope: fade in / hold / fade out.
        if progress < 0.10:
            envelope = progress / 0.10
        elif progress < 0.85:
            envelope = 1.0
        else:
            envelope = max(0.0, 1.0 - (progress - 0.85) / 0.15)
        if envelope <= 0:
            return

        card_w = 540
        # Fixed-height card with a 2×2 impact grid; layout is predictable.
        card_h = 320
        slide = int(40 * (1.0 - envelope))
        rect = pygame.Rect((w - card_w) // 2, (h - card_h) // 2 + slide, card_w, card_h)

        self._draw_shadow(surface, rect, blur=24, alpha=int(180 * envelope))
        body = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
        pygame.draw.rect(
            body, (*self.palette.surface_elevated[:3], int(245 * envelope)),
            (0, 0, card_w, card_h), border_radius=14,
        )
        surface.blit(body, rect.topleft)
        pygame.draw.rect(
            surface, _blend(self.palette.surface_deep, card.accent, 0.55),
            rect, 1, border_radius=14,
        )

        # Header strip — catastrophe-tint band with element badge + name.
        header_h = 76
        header_surf = pygame.Surface((card_w, header_h), pygame.SRCALPHA)
        pygame.draw.rect(
            header_surf, (*_blend(card.accent, (0, 0, 0), 0.35), int(255 * envelope)),
            (0, 0, card_w, header_h),
            border_top_left_radius=14, border_top_right_radius=14,
        )
        surface.blit(header_surf, rect.topleft)
        # Element badge on the left of the header.
        badge_r = 22
        bcx = rect.left + 20 + badge_r
        bcy = rect.top + header_h // 2
        pygame.draw.circle(surface, _blend((10, 12, 18), card.accent, 0.45), (bcx, bcy), badge_r)
        pygame.draw.circle(surface, card.accent, (bcx, bcy), badge_r, 2)
        self._draw_element_icon(
            surface, game.gaia.active.name, (bcx, bcy), badge_r - 7, card.accent,
        )
        # Tag + skill name to the right of the badge.
        # ``card.skill_axis`` is the JSON-id form (no accents:
        # "Intensite" / "Portee" / "Duree" / "Impact Ecologique").
        # Naively uppercasing produced "INTENSITE" / "PORTEE" /
        # "DUREE" / "IMPACT ECOLOGIQUE" on every skill purchase —
        # a French-accent regression visible every single time the
        # impact card fired. The codebase already has
        # ``SKILL_TREE_AXIS_LABELS`` (used by the skill-tree axis
        # tabs and outro IMPACTS rows) which carries the properly-
        # accented uppercase form; route the tag through that map
        # so the impact card speaks the same vocabulary.
        axis_display = SKILL_TREE_AXIS_LABELS.get(
            card.skill_axis, card.skill_axis.upper(),
        )
        tag = self.fonts.label.render(
            f"NOUVEL IMPACT · {axis_display} · NIV. {card.level}",
            True, (255, 255, 255),
        )
        surface.blit(tag, (bcx + badge_r + 12, rect.top + 14))
        name_max_w = rect.right - (bcx + badge_r + 12) - 56  # leave space for ×
        fitted_name, fitted_font = self._fit_text_progressive(
            card.skill_name, name_max_w,
            (self.fonts.title, self.fonts.large, self.fonts.medium),
        )
        name = fitted_font.render(fitted_name, True, (255, 255, 255))
        surface.blit(name, (bcx + badge_r + 12, rect.top + 14 + tag.get_height() + 2))

        # Explicit × close button at the top-right of the header so the player
        # never wonders how to dismiss the card. Drawn on an SRCALPHA layer so
        # the circle stays translucent against the tinted header.
        close_rect = pygame.Rect(rect.right - 38, rect.top + 14, 26, 26)
        close_hover = close_rect.collidepoint(pygame.mouse.get_pos())
        close_layer = pygame.Surface((26, 26), pygame.SRCALPHA)
        circle_alpha = int((120 if close_hover else 60) * envelope)
        pygame.draw.circle(
            close_layer, (255, 255, 255, circle_alpha), (13, 13), 13,
        )
        surface.blit(close_layer, close_rect.topleft)
        cx, cy = close_rect.center
        pygame.draw.line(surface, (255, 255, 255), (cx - 5, cy - 5), (cx + 5, cy + 5), 2)
        pygame.draw.line(surface, (255, 255, 255), (cx + 5, cy - 5), (cx - 5, cy + 5), 2)

        # Hero "key effect" line — the first effect (usually the most readable
        # one like "Rayon d'action : 20 km").
        body_x = rect.left + 22
        body_y = rect.top + header_h + 14
        if card.effects:
            k, v = next(iter(card.effects.items()))
            key_t = self.fonts.label.render(
                k.upper(), True, self.palette.text_label,
            )
            val_t = self.fonts.hero.render(str(v), True, card.accent)
            surface.blit(key_t, (body_x, body_y))
            surface.blit(
                val_t, (body_x, body_y + key_t.get_height() + 2),
            )
        # Smaller effects on the right (if any beyond the first).
        if len(card.effects) > 1:
            secondary_x = rect.left + card_w - 220
            sy = body_y
            for k, v in list(card.effects.items())[1:3]:
                kt = self.fonts.label.render(k.upper(), True, self.palette.text_label)
                vt = self.fonts.medium.render(str(v), True, self.palette.text)
                surface.blit(kt, (secondary_x, sy))
                surface.blit(vt, (secondary_x + kt.get_width() + 8, sy - 2))
                sy += kt.get_height() + 4

        # Impact grid — 2×2 mini-cards with iconic indicator glyph.
        grid_top = body_y + 68
        items = list(card.impact_descriptions.items())[:4]
        if items:
            section = self.fonts.label.render(
                "IMPACT ENVIRONNEMENTAL", True, self.palette.text_label,
            )
            surface.blit(section, (body_x, grid_top - section.get_height() - 6))
            cell_w = (card_w - 56) // 2
            cell_h = 54
            cell_gap = 10
            for i, (indicator, desc) in enumerate(items):
                col = i % 2
                row = i // 2
                cx0 = body_x + col * (cell_w + cell_gap)
                cy0 = grid_top + row * (cell_h + cell_gap)
                cell = pygame.Rect(cx0, cy0, cell_w, cell_h)
                cell_fill = self.palette.surface_deep[:3]
                pygame.draw.rect(
                    surface, cell_fill, cell, border_radius=8,
                )
                # Gradient + edge strokes — same depth idiom shipped on
                # every other tactile chrome surface (button family,
                # tooltip card, settings rows, sidebar two-col, empty
                # state card). Was a flat ``surface_deep`` body that
                # read as a smudge of dim colour against the impact
                # card's tinted header; now the four cells read as
                # proper sub-cards inside the parent card, picking up
                # the same gradient + top-highlight + bottom-shadow
                # depth treatment as the rest of the chrome family.
                self._apply_button_depth(
                    surface, cell, cell_fill, radius=8,
                )
                pygame.draw.rect(
                    surface, _blend(self.palette.surface_deep, card.accent, 0.4),
                    cell, 1, border_radius=8,
                )
                icon_r = 12
                icx = cell.left + 12 + icon_r
                icy = cell.centery
                pygame.draw.circle(
                    surface, _blend((10, 12, 18), card.accent, 0.5),
                    (icx, icy), icon_r,
                )
                pygame.draw.circle(surface, card.accent, (icx, icy), icon_r, 2)
                self._draw_indicator_glyph(
                    surface, indicator, (icx, icy), icon_r - 4, card.accent,
                )
                short = self._indicator_short(indicator)
                ind_t = self.fonts.label.render(short.upper(), True, card.accent)
                surface.blit(
                    ind_t, (icx + icon_r + 8, cell.top + 8),
                )
                desc_t = self.fonts.small.render(
                    self._fit_text(desc, self.fonts.small, cell_w - 60),
                    True, self.palette.text,
                )
                surface.blit(
                    desc_t,
                    (icx + icon_r + 8,
                     cell.top + 8 + ind_t.get_height() + 1),
                )

        # Footer hint pinned to the bottom — explicit + concise.
        hint = self.fonts.label.render(
            "× POUR FERMER", True, self.palette.text_dim,
        )
        surface.blit(
            hint,
            (rect.centerx - hint.get_width() // 2,
             rect.bottom - hint.get_height() - 12),
        )

    # ----------------------------------------------------------- tutorial
    # "How to play" overlay: a discrete chip at the top-left of the
    # map opens a 4-slide procedural cinematic (rôle / carte /
    # évolution / objectif). Manual click-through; closing returns
    # to PLAYING without affecting simulation state.

    def _draw_tutorial_button(self, surface: pygame.Surface, game: Game) -> None:
        """Discrete chip with a play-triangle glyph + 'TUTORIEL' label.

        Sits at the top-left of the map area (not the top bar, so it
        reads as an in-world affordance rather than a control-pane
        button). Before first use, the catastrophe-tinted border pulses
        softly so a new player notices; after ``tutorial_seen`` is set,
        the pulse stops and the chip stays available without drawing
        the eye.

        Gating layers (most specific first):

        * Phase / modal gating — never visible outside PLAYING, or
          while another modal is up (tutorial/evolution/help/pause/
          settings/cinematic).
        * **Focus gating** — temporarily hidden when the player is
          actively reading something else: the country info panel
          (a click-selected country pulled the panel open) or the
          expanded sidebar (the player opened the right-panel
          drawer). The chip competing for attention with the surface
          the player just opened reads as chrome noise; it reappears
          the moment they close the focused surface.
        * **Veteran gating** — after ``TUTORIAL_VETERAN_TURN`` days
          of playing, the chip permanently disappears for the rest
          of the run. By that point the player has either opened
          the tutorial or learned the loop by playing; either way
          the chip is no longer an onboarding affordance, just
          clutter. The Help modal (``H``) still surfaces the same
          info via the keyboard shortcut for anyone who needs it
          mid-late game.
        """
        if game.phase is not Phase.PLAYING:
            return
        if game.tutorial_open or game.evolution_open or game.help_open:
            return
        if game.pause_menu_open or game.settings_open:
            return
        if game.cinematic_playing:
            return
        # Focus gating — temporarily yield to other reading surfaces.
        if getattr(game, "info_panel_visible", False):
            return
        if not getattr(game, "sidebar_collapsed", True):
            return
        # Veteran gating — newcomer affordance, retires after the
        # onboarding window. 20 days ≈ first third of a typical run.
        TUTORIAL_VETERAN_TURN = 20
        if game.turn >= TUTORIAL_VETERAN_TURN:
            return
        rect = tutorial_button_rect(self.config)
        mouse_pos = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse_pos)
        cat_color = game.gaia.active.arc_color
        # Soft halo before first use — a one-time invitation, not a
        # permanent attention grabber.
        if not game.tutorial_seen:
            ticks = pygame.time.get_ticks()
            pulse = 0.5 + 0.5 * math.sin(ticks * 0.004)
            halo_alpha = int(70 + 60 * pulse)
            halo = pygame.Surface(
                (rect.width + 12, rect.height + 12), pygame.SRCALPHA,
            )
            pygame.draw.rect(
                halo, (*cat_color, halo_alpha),
                (0, 0, rect.width + 12, rect.height + 12),
                2, border_radius=10,
            )
            surface.blit(halo, (rect.left - 6, rect.top - 6))
        # Body — dark surface with a soft tint blend that warms on hover.
        # The same gradient + edge stroke depth treatment used elsewhere
        # in the top-bar chrome carries onto this in-world chip so it
        # reads as a tactile control rather than a flat tinted slab.
        base = (16, 20, 30)
        bg = _blend(base, cat_color, 0.35 if hover else 0.18)
        border = _blend(cat_color, (255, 255, 255), 0.20)
        pygame.draw.rect(surface, bg, rect, border_radius=8)
        self._apply_button_depth(surface, rect, bg, radius=8)
        pygame.draw.rect(surface, border, rect, 1, border_radius=8)
        # Play-triangle glyph — universal "start" affordance.
        tri_cx = rect.left + 14
        tri_cy = rect.centery
        tri_r = 6
        pygame.draw.polygon(
            surface, (245, 250, 255),
            [(tri_cx - tri_r // 2, tri_cy - tri_r),
             (tri_cx - tri_r // 2, tri_cy + tri_r),
             (tri_cx + tri_r, tri_cy)],
        )
        # Label.
        label = self.fonts.label.render(
            "TUTORIEL", True, (245, 250, 255),
        )
        surface.blit(
            label,
            (tri_cx + tri_r + 10, rect.centery - label.get_height() // 2),
        )

    def _draw_tutorial_overlay(self, surface: pygame.Surface, game: Game) -> None:
        """4-slide procedural cinematic: rôle / carte / évolution / objectif.

        Matches the help-modal design language (dim backdrop + rounded
        translucent card + accent stripe + close ×) so the tutorial
        feels native, not bolted on. The slide area carries a small
        procedural diagram on the left and a 2-line caption on the
        right. Progress dots at the bottom show which slide is active.
        """
        w, h = self.screen_size
        # Dim the underlying gameplay so the modal owns focus, matching
        # the help-modal alpha (210) for consistency.
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 210))
        surface.blit(dim, (0, 0))

        modal_w, modal_h = 560, 340
        modal = pygame.Rect(
            (w - modal_w) // 2, (h - modal_h) // 2, modal_w, modal_h,
        )
        radius = 14
        self._draw_shadow(surface, modal, blur=22, alpha=190)
        card = pygame.Surface(modal.size, pygame.SRCALPHA)
        pygame.draw.rect(
            card, (*self.palette.surface_elevated[:3], 248),
            (0, 0, modal_w, modal_h), border_radius=radius,
        )
        self._fade_card_highlight(
            card, modal_w, modal_h, radius,
            peak_alpha=12, peak_lowlight_alpha=20,
        )
        surface.blit(card, modal.topleft)
        pygame.draw.rect(
            surface, self.palette.ui_border_soft,
            modal, 1, border_radius=radius,
        )
        # Top accent stripe — catastrophe tint so the tutorial picks
        # up the run's identity (vs the catastrophe-agnostic help modal
        # which uses ui_accent).
        cat_color = game.gaia.active.arc_color
        accent_strip = pygame.Surface((modal_w, 3), pygame.SRCALPHA)
        pygame.draw.rect(
            accent_strip, (*cat_color, 255),
            (0, 0, modal_w, 3),
            border_top_left_radius=radius,
            border_top_right_radius=radius,
        )
        surface.blit(accent_strip, modal.topleft)

        # Header tag + title + close ×.
        tag = self.fonts.label.render(
            "AIDE · DÉCOUVERTE", True, self.palette.text_label,
        )
        surface.blit(tag, (modal.left + 24, modal.top + 18))
        title = self.fonts.title.render(
            "COMMENT JOUER", True, self.palette.text,
        )
        title_y = modal.top + 18 + tag.get_height() + 2
        surface.blit(title, (modal.left + 24, title_y))
        # Underline matching the help / settings / picker pattern.
        underline_w = max(60, title.get_width() // 2)
        underline_y = title_y + title.get_height() + 4
        underline = pygame.Surface((underline_w, 2), pygame.SRCALPHA)
        for px in range(underline_w):
            t = 1.0 - (px / underline_w)
            a = int(220 * (t ** 1.2))
            if a <= 0:
                continue
            pygame.draw.line(
                underline, (*cat_color, a), (px, 0), (px, 1),
            )
        surface.blit(underline, (modal.left + 24, underline_y))

        # Close × at top-right.
        close_rect = pygame.Rect(modal.right - 40, modal.top + 16, 28, 28)
        close_hover = close_rect.collidepoint(pygame.mouse.get_pos())
        close_r = close_rect.width // 2
        close_layer = pygame.Surface(
            (close_r * 2, close_r * 2), pygame.SRCALPHA,
        )
        pygame.draw.circle(
            close_layer, (255, 255, 255, 130 if close_hover else 70),
            (close_r, close_r), close_r,
        )
        pygame.draw.circle(
            close_layer, (255, 255, 255, 180 if close_hover else 100),
            (close_r, close_r), close_r, 1,
        )
        surface.blit(
            close_layer,
            (close_rect.centerx - close_r, close_rect.centery - close_r),
        )
        cx_, cy_ = close_rect.center
        pygame.draw.line(surface, (255, 255, 255), (cx_ - 6, cy_ - 6), (cx_ + 6, cy_ + 6), 2)
        pygame.draw.line(surface, (255, 255, 255), (cx_ + 6, cy_ - 6), (cx_ - 6, cy_ + 6), 2)

        # Slide body — left: procedural diagram (156×156), right: caption.
        # Bumped 140 → 156 because slide 0's "HUMANITÉ" label (72 px at
        # fonts.label) was overflowing the 68-px-per-label budget when
        # centred at cx ± 36 in the previous 140-wide box; and slide
        # 2's tier-label row "FOND. AMPL. TRANS." (141 px) was
        # overflowing the 130 px centred budget. At 156 the per-label
        # budget for slide 0 grows to 84 px (12 px breath for HUMANITÉ),
        # and the centred-row budget for slide 2 grows to 146 px (5 px
        # breath for the tier label). Caption column tightens from
        # 336 → 320 px in lockstep — still wider than the widest wrapped
        # caption line measured at 310 px in the earlier audit, so the
        # 2-line wrap envelope on the captions stays unbroken.
        slide_top = underline_y + 28
        slide_h = 160
        diagram_size = 156
        diagram_rect = pygame.Rect(
            modal.left + 32, slide_top, diagram_size, diagram_size,
        )
        caption_left = diagram_rect.right + 28
        caption_w = modal.right - caption_left - 24

        step = max(0, min(TUTORIAL_SLIDE_COUNT - 1, game.tutorial_step))
        # Slide 4's title + caption mirror the HUD label the player
        # actually sees at the top centre — DÉSÉQUILIBRE for Gaïa,
        # ÉQUILIBRE for Humanité — so the tutorial points at the same
        # word the bar carries. Generic "OBJECTIF" no longer appears
        # on the HUD, so referencing it here would send the player
        # hunting for a label that doesn't exist.
        side = getattr(game, "player_side", "gaia")
        hud_label = "DÉSÉQUILIBRE" if side == "gaia" else "ÉQUILIBRE"
        # Side-aware role line. Was the hedging "Vous incarnez la
        # planète ou l'humanité." for both sides — but the tutorial
        # only opens with ``awaiting_start = False`` (i.e. after the
        # player committed to a side at the picker), so the "ou"
        # clause was wishy-washy at point of read. Slide 4 already
        # uses the same side-aware pattern for ``hud_label``;
        # bringing slide 1 in line.
        role_line = (
            "Vous incarnez la planète."
            if side == "gaia"
            else "Vous incarnez l'humanité."
        )
        SLIDES = (
            ("VOTRE RÔLE",
             role_line,
             "L'autre côté joue automatiquement."),
            ("LA CARTE",
             "La catastrophe se propage de pays en pays.",
             "Cliquez un pays pour voir ses indicateurs."),
            ("ÉVOLUTION",
             # Was "Touche E ouvre votre arbre d'évolution." — the
             # "Touche E ouvre" construction reads anglicised ("Key E
             # opens"). Drop the noun-marker for the key, matching the
             # help modal's "E : Évolution" pattern where keys appear
             # as bare letters.
             "E ouvre l'arbre d'évolution.",
             # Was "Investissez vos points en compétences." — "points"
             # was the only place in the player-facing French where the
             # currency was called something other than "ÉN" / "énergie".
             # The HUD labels it "ÉNERGIE DISPONIBLE", buttons cost
             # "+12 ÉN", orb collection floats read "+5 ÉN", milestones
             # award "+10 ÉN". The tutorial should speak the same
             # vocabulary the rest of the game speaks.
             "Investissez votre énergie dans des compétences."),
            (hud_label,
             f"En haut au centre, la jauge de {hud_label}.",
             "Remplissez-la pour gagner."),
        )
        slide_title, line1, line2 = SLIDES[step]
        self._draw_tutorial_diagram(
            surface, diagram_rect, step, cat_color, game,
        )
        # Caption: small SLIDE TITLE label + two text lines, each
        # word-wrapped so longer captions like "La catastrophe se
        # propage de pays en pays." (359 px) and "Investissez votre
        # énergie dans des compétences." (399 px) don't overflow the
        # 336 px caption column. Was a single ``render(line, ...)``
        # call per line — the surface produced was as wide as the
        # text and bled past the modal's right edge.
        sub_tag = self.fonts.label.render(
            slide_title, True, _blend(cat_color, (255, 255, 255), 0.35),
        )
        surface.blit(sub_tag, (caption_left, slide_top + 6))
        line_y = slide_top + 6 + sub_tag.get_height() + 14
        # Each caption line wraps to at most 2 sub-lines. The 4-slide
        # corpus fits in 1-2 sub-lines per line at the medium font's
        # 17 pt size on the 336 px column, leaving the layout balanced
        # against the 140 px diagram on the left.
        for sub_line in self._wrap_text(
            line1, self.fonts.medium, caption_w, max_lines=2,
        ):
            surf = self.fonts.medium.render(sub_line, True, self.palette.text)
            surface.blit(surf, (caption_left, line_y))
            line_y += surf.get_height() + 2
        # Small extra gap between the two lines to keep the
        # primary/dim visual hierarchy readable when one or both wrap.
        line_y += 4
        for sub_line in self._wrap_text(
            line2, self.fonts.medium, caption_w, max_lines=2,
        ):
            surf = self.fonts.medium.render(
                sub_line, True, self.palette.text_dim,
            )
            surface.blit(surf, (caption_left, line_y))
            line_y += surf.get_height() + 2

        # Progress dots — TUTORIAL_SLIDE_COUNT pips just above the buttons.
        dots_y = modal.bottom - 78
        dot_r = 4
        dot_spacing = 18
        dots_total_w = (TUTORIAL_SLIDE_COUNT - 1) * dot_spacing
        dots_left = modal.centerx - dots_total_w // 2
        inactive_color = _blend(self.palette.surface_deep, cat_color, 0.55)
        for i in range(TUTORIAL_SLIDE_COUNT):
            dx = dots_left + i * dot_spacing
            color = cat_color if i == step else inactive_color
            pygame.draw.circle(surface, color, (dx, dots_y), dot_r)
            if i == step:
                pygame.draw.circle(
                    surface, self.palette.text, (dx, dots_y), dot_r + 3, 1,
                )

        # Nav buttons.
        nav = tutorial_overlay_button_rects(self.config)
        mouse_pos = pygame.mouse.get_pos()
        self._draw_chunky_button(
            surface, nav["skip"],
            label="PASSER", primary=False,
            hover=nav["skip"].collidepoint(mouse_pos),
            font=self.fonts.medium,
        )
        next_label = "COMMENCER" if step == TUTORIAL_SLIDE_COUNT - 1 else "SUIVANT"
        self._draw_chunky_button(
            surface, nav["next"],
            label=next_label, primary=True,
            hover=nav["next"].collidepoint(mouse_pos),
            font=self.fonts.medium,
            tint=cat_color,
        )

    def _draw_tutorial_diagram(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        step: int,
        cat_color: tuple[int, int, int],
        game: Game,
    ) -> None:
        """Per-slide procedural illustration. Pure visual cue for each
        concept — no text. Drawn into ``rect`` (140×140 by default).

        Step 0 (VOTRE RÔLE): two facing glyphs — wave (GAIA) + shield
            (HUMANITÉ), thin dividing line between them.
        Step 1 (LA CARTE): simplified globe disc + pulse rings expanding
            from a centred marker.
        Step 2 (ÉVOLUTION): three tier dots (Fondations → Amplification →
            Transformation) connected by arrows.
        Step 3 (OBJECTIF): progress bar with a chevron target tick and a
            fill that completes to the tick.
        """
        # Soft tinted backplate so the diagram has its own little stage.
        plate_fill = _blend(self.palette.surface_deep[:3], cat_color, 0.10)
        plate = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            plate, (*plate_fill, 220),
            (0, 0, rect.width, rect.height), border_radius=10,
        )
        surface.blit(plate, rect.topleft)
        # Gradient + edge-stroke depth — same idiom as every other
        # tactile card. The tutorial backplate now reads as a proper
        # sub-card inside the tutorial modal rather than a flat tinted
        # rectangle. Cat-tinted border drawn last so it frames the
        # depth treatment.
        self._apply_button_depth(surface, rect, plate_fill, radius=10)
        pygame.draw.rect(
            surface, _blend(cat_color, (255, 255, 255), 0.15),
            rect, 1, border_radius=10,
        )

        cx, cy = rect.centerx, rect.centery
        gaia_tint = (220, 110, 80)
        humanite_tint = (110, 200, 230)

        if step == 0:
            # Two facing glyphs + dividing line.
            divider_y_top = rect.top + 18
            divider_y_bot = rect.bottom - 18
            divider_x = cx
            for y in range(divider_y_top, divider_y_bot, 6):
                pygame.draw.line(
                    surface, _blend(self.palette.surface_overlay[:3], (255, 255, 255), 0.3),
                    (divider_x, y), (divider_x, y + 3), 1,
                )
            # Left side: GAIA wave glyph in the gaia tint.
            self._draw_side_glyph(
                surface, "wave", (cx - 36, cy), 18, gaia_tint,
            )
            # Right side: HUMANITÉ shield glyph in the humanité tint.
            self._draw_side_glyph(
                surface, "shield", (cx + 36, cy), 18, humanite_tint,
            )
            # Side labels under each. "GAIA" was mythological; "PLANÈTE"
            # reads as concrete + educational, matches the doc-voice
            # spine ("Comprendre, s'émerveiller, agir") and the established
            # "Terre Vivante" title.
            g_lab = self.fonts.label.render("PLANÈTE", True, gaia_tint)
            h_lab = self.fonts.label.render("HUMANITÉ", True, humanite_tint)
            surface.blit(g_lab, (cx - 36 - g_lab.get_width() // 2, cy + 32))
            surface.blit(h_lab, (cx + 36 - h_lab.get_width() // 2, cy + 32))

        elif step == 1:
            # Simplified globe + pulse rings from a marker.
            globe_r = 42
            pygame.draw.circle(
                surface, _blend(self.palette.surface_deep[:3], (75, 145, 205), 0.85),
                (cx, cy), globe_r,
            )
            pygame.draw.circle(
                surface, _blend(cat_color, (255, 255, 255), 0.25),
                (cx, cy), globe_r, 1,
            )
            # A couple of stylised continents.
            for poly_fr in (
                [(-0.25, -0.45), (0.05, -0.55), (0.10, -0.25), (-0.20, -0.20)],
                [(0.20, 0.10), (0.55, 0.05), (0.45, 0.40), (0.15, 0.35)],
                [(-0.55, 0.10), (-0.30, 0.20), (-0.35, 0.45), (-0.55, 0.40)],
            ):
                pts = [(cx + int(dx * globe_r), cy + int(dy * globe_r)) for dx, dy in poly_fr]
                pygame.draw.polygon(surface, (78, 130, 100), pts)
            # Pulse rings around a marker (top of globe).
            ticks = pygame.time.get_ticks()
            pulse = (ticks % 1500) / 1500.0
            mark_x = cx + 8
            mark_y = cy - 16
            for k, t_off in enumerate((0.0, 0.33, 0.66)):
                t = (pulse + t_off) % 1.0
                r = int(8 + t * 22)
                alpha = int(180 * (1.0 - t))
                if alpha <= 0:
                    continue
                ring = pygame.Surface((r * 2 + 4, r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(
                    ring, (*cat_color, alpha), (r + 2, r + 2), r, 1,
                )
                surface.blit(ring, (mark_x - r - 2, mark_y - r - 2))
            pygame.draw.circle(surface, cat_color, (mark_x, mark_y), 4)
            pygame.draw.circle(surface, (255, 255, 255), (mark_x, mark_y), 2)

        elif step == 2:
            # Three tier dots connected by arrows.
            dot_r = 8
            dot_spacing = 38
            start_x = cx - dot_spacing
            colours = (
                _blend(cat_color, (255, 255, 255), 0.10),
                _blend(cat_color, (255, 255, 255), 0.25),
                _blend(cat_color, (255, 255, 255), 0.45),
            )
            labels = ("F", "A", "T")
            for i in range(3):
                dx = start_x + i * dot_spacing
                pygame.draw.circle(surface, colours[i], (dx, cy), dot_r)
                pygame.draw.circle(surface, (255, 255, 255), (dx, cy), dot_r, 1)
                ltr = self.fonts.label.render(
                    labels[i], True, _blend(cat_color, (0, 0, 0), 0.55),
                )
                surface.blit(
                    ltr, (dx - ltr.get_width() // 2, cy - ltr.get_height() // 2),
                )
                if i < 2:
                    arr_x1 = dx + dot_r + 2
                    arr_x2 = start_x + (i + 1) * dot_spacing - dot_r - 2
                    pygame.draw.line(
                        surface, _blend(cat_color, (255, 255, 255), 0.30),
                        (arr_x1, cy), (arr_x2, cy), 2,
                    )
                    # Arrow head.
                    pygame.draw.polygon(
                        surface, _blend(cat_color, (255, 255, 255), 0.30),
                        [(arr_x2, cy - 3), (arr_x2 + 4, cy), (arr_x2, cy + 3)],
                    )
            # Tier labels under the dots. Matches the canonical
            # ``SKILL_TIER_LABELS_SHORT`` form ("FOND.", "AMPL.",
            # "TRANS.") with single-space joins — the previous
            # ``"FOND.  AMPLI.  TRANS."`` had inconsistent abbreviation
            # ("AMPLI" vs canonical "AMPL.") and double-space joins
            # that pushed the row to 153 px (overflowed the 146-px
            # centred budget in the 156-wide diagram by 7 px and the
            # 130-px budget in the previous 140-wide diagram by 23 px).
            tier_label = self.fonts.label.render(
                " ".join(SKILL_TIER_LABELS_SHORT),
                True, self.palette.text_dim,
            )
            surface.blit(
                tier_label,
                (cx - tier_label.get_width() // 2, cy + dot_r + 14),
            )

        elif step == 3:
            # Progress bar — looping fill demo so the diagram *moves*,
            # matching the real ÉQUILIBRE / DÉSÉQUILIBRE bar in the
            # top HUD (which has an animated fill, leading-edge glow,
            # and chevron target tick). Was a static "full bar"
            # snapshot; the player saw
            # the END of a goal rather than the *process* of working
            # toward one. The cycle: 2.5 s fill 0 → 100 % with ease-out
            # cubic (deliberate progression), 1.5 s hold at full, then
            # restart. Total 4 s loop.
            bar_w = 100
            bar_h = 12
            bar_x = cx - bar_w // 2
            bar_y = cy - bar_h // 2
            if game.reduce_motion:
                # Static full bar — same as the original static design.
                progress = 1.0
            else:
                cycle_ms = 4000
                fill_phase_ms = 2500
                ticks_mod = pygame.time.get_ticks() % cycle_ms
                if ticks_mod < fill_phase_ms:
                    t = ticks_mod / fill_phase_ms
                    progress = 1.0 - (1.0 - t) ** 3  # ease-out cubic
                else:
                    progress = 1.0
            pygame.draw.rect(
                surface, self.palette.surface_overlay[:3],
                (bar_x, bar_y, bar_w, bar_h), border_radius=bar_h // 2,
            )
            fill_w = int(bar_w * progress)
            if fill_w > 0:
                pygame.draw.rect(
                    surface, cat_color,
                    (bar_x, bar_y, fill_w, bar_h), border_radius=bar_h // 2,
                )
                # Leading-edge glow + bright 1-px line at the tip —
                # same idiom as the real ÉQUILIBRE / DÉSÉQUILIBRE bar
                # in the HUD. Only painted mid-fill (skipped at 100 %
                # since there's no leading edge then).
                if fill_w < bar_w and not game.reduce_motion:
                    edge_x = bar_x + fill_w
                    glow = pygame.Surface((20, bar_h + 10), pygame.SRCALPHA)
                    for gr in range(10, 0, -1):
                        gt = gr / 10
                        a = int(120 * (1 - gt) ** 1.4)
                        if a < 1:
                            continue
                        pygame.draw.circle(
                            glow, (*cat_color, a),
                            (10, bar_h // 2 + 5), gr,
                        )
                    surface.blit(glow, (edge_x - 10, bar_y - 5))
                    pygame.draw.line(
                        surface,
                        _blend(cat_color, (255, 255, 255), 0.45),
                        (edge_x, bar_y),
                        (edge_x, bar_y + bar_h),
                        1,
                    )
            # Target chevron + stem at the right end.
            tick_x = bar_x + bar_w - 1
            pygame.draw.line(
                surface, self.palette.text,
                (tick_x, bar_y - 2), (tick_x, bar_y + bar_h + 2), 2,
            )
            flag_h = 6
            flag_w = 5
            flag_pts = [
                (tick_x - flag_w, bar_y - flag_h - 2),
                (tick_x + flag_w, bar_y - flag_h - 2),
                (tick_x, bar_y - 2),
            ]
            pygame.draw.polygon(surface, self.palette.text, flag_pts)
            # Caption above the bar — mirrors the HUD's state label
            # (DÉSÉQUILIBRE for Gaïa, ÉQUILIBRE for Humanité). Matching
            # the real HUD word lets the player connect this diagram
            # to the bar at the top of the screen at a glance.
            side = getattr(game, "player_side", "gaia")
            hud_label = "DÉSÉQUILIBRE" if side == "gaia" else "ÉQUILIBRE"
            cap = self.fonts.label.render(
                hud_label, True, _blend(cat_color, (255, 255, 255), 0.40),
            )
            surface.blit(
                cap, (cx - cap.get_width() // 2, bar_y - 22),
            )

    # ----------------------------------------------------------- help

    def _draw_help_modal(self, surface: pygame.Surface) -> None:
        """Visual-first shortcut reference — 3 themed section cards.

        Replaces the previous flat 10-row key/desc list. Each section is its
        own translucent card with a procedural glyph badge (▶ simulation /
        ✥ navigation / ◳ interface), a section title, and 3–4 compact key
        rows. The layout reads as three intentional clusters instead of a
        long scroll of shortcuts.
        """
        w, h = self.screen_size
        dim = pygame.Surface((w, h), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 210))
        surface.blit(dim, (0, 0))

        # Three sections — title, glyph kind, rows of (key, label).
        sections: tuple[tuple[str, str, tuple[tuple[str, str], ...]], ...] = (
            (
                "SCÉNARIO", "play",
                (
                    ("Espace",    "Pause / reprise"),
                    ("1 · 2 · 3", "Vitesse"),
                    ("R",         "Recommencer"),
                ),
            ),
            (
                "NAVIGATION", "compass",
                (
                    # "Déplacer la carte" was 112 px in a 93 px column —
                    # bled under the next column. The arrow-keys pill
                    # already implies movement so "Déplacement" is
                    # unambiguous, and 87 px leaves comfortable breath.
                    ("Flèches", "Déplacement"),
                    ("+  −",    "Zoom"),
                    # Was "Sidebar" — the only non-French word in the
                    # help modal's ten shortcut descriptions, sitting
                    # next to all-French neighbours. "Panneau" matches
                    # the code's own ``_draw_right_panel`` vocabulary
                    # and is the natural French term for the dashboard.
                    ("Tab",     "Panneau"),
                ),
            ),
            (
                "INTERFACE", "grid",
                (
                    ("E",     "Évolution"),
                    ("M",     "Couper le son"),
                    ("H",     "Cet écran"),
                    ("Échap", "Fermer / menu"),
                ),
            ),
        )

        modal_w = 660
        modal_h = 380
        modal = pygame.Rect(
            (w - modal_w) // 2, (h - modal_h) // 2, modal_w, modal_h,
        )
        radius = 14
        self._draw_shadow(surface, modal, blur=24, alpha=190)
        # Rounded translucent card body, matching the impact-card / tooltip
        # design vocabulary instead of a flat panel.
        card = pygame.Surface(modal.size, pygame.SRCALPHA)
        pygame.draw.rect(
            card, (*self.palette.surface_elevated[:3], 248),
            (0, 0, modal_w, modal_h), border_radius=radius,
        )
        self._fade_card_highlight(
            card, modal_w, modal_h, radius,
            peak_alpha=12, peak_lowlight_alpha=20,
        )
        surface.blit(card, modal.topleft)
        pygame.draw.rect(
            surface, self.palette.ui_border_soft,
            modal, 1, border_radius=radius,
        )
        # Top accent stripe — neutral ui_accent here since this modal is
        # catastrophe-agnostic (opens from the title / pause / playing).
        accent_strip = pygame.Surface((modal_w, 3), pygame.SRCALPHA)
        pygame.draw.rect(
            accent_strip, (*self.palette.ui_accent, 255),
            (0, 0, modal_w, 3),
            border_top_left_radius=radius,
            border_top_right_radius=radius,
        )
        surface.blit(accent_strip, modal.topleft)

        # Header: section tag + title + close ×.
        tag = self.fonts.label.render(
            "AIDE", True, self.palette.text_label,
        )
        surface.blit(tag, (modal.left + 24, modal.top + 18))
        title = self.fonts.title.render(
            "RACCOURCIS", True, self.palette.text,
        )
        title_x = modal.left + 24
        title_y = modal.top + 18 + tag.get_height() + 2
        surface.blit(title, (title_x, title_y))
        # Accent underline — matches settings + picker title pattern so
        # all three centred modals share the same design vocabulary.
        underline_w = max(60, title.get_width() // 2)
        underline_y = title_y + title.get_height() + 4
        accent_strip = pygame.Surface((underline_w, 2), pygame.SRCALPHA)
        for px in range(underline_w):
            t = 1.0 - (px / underline_w)
            a = int(220 * (t ** 1.2))
            if a <= 0:
                continue
            pygame.draw.line(
                accent_strip, (*self.palette.ui_accent, a),
                (px, 0), (px, 1),
            )
        surface.blit(accent_strip, (title_x, underline_y))
        sub = self.fonts.small.render(
            "Tout ce qu'il faut pour piloter le scénario.",
            True, self.palette.text_dim,
        )
        surface.blit(
            sub,
            (modal.left + 24,
             underline_y + 8),
        )

        # × close button at top-right, matching the rest of the close design.
        close_rect = pygame.Rect(modal.right - 40, modal.top + 16, 28, 28)
        close_hover = close_rect.collidepoint(pygame.mouse.get_pos())
        close_r = close_rect.width // 2
        close_layer = pygame.Surface(
            (close_r * 2, close_r * 2), pygame.SRCALPHA,
        )
        pygame.draw.circle(
            close_layer, (255, 255, 255, 130 if close_hover else 70),
            (close_r, close_r), close_r,
        )
        pygame.draw.circle(
            close_layer, (255, 255, 255, 180 if close_hover else 100),
            (close_r, close_r), close_r, 1,
        )
        surface.blit(
            close_layer,
            (close_rect.centerx - close_r, close_rect.centery - close_r),
        )
        cx, cy = close_rect.center
        x_color = (255, 255, 255)
        pygame.draw.line(surface, x_color, (cx - 6, cy - 6), (cx + 6, cy + 6), 2)
        pygame.draw.line(surface, x_color, (cx + 6, cy - 6), (cx - 6, cy + 6), 2)

        # Section cards — 3 columns, equal width, gap = 14. Each
        # section gets a *distinct* accent colour: warm amber for
        # SIMULATION (action), cool blue for NAVIGATION (movement),
        # sage green for INTERFACE (utility). Previously all three
        # used the neutral ``ui_accent``, so the cards read as
        # "three identical containers"; now they're visually
        # categorised at a glance.
        section_top = modal.top + 110
        section_bot = modal.bottom - 56
        section_h = section_bot - section_top
        gap = 14
        col_w = (modal_w - 24 * 2 - gap * 2) // 3
        section_accents = (
            LIGHT_WARNING,              # SIMULATION — warm amber (action)
            self.palette.ui_highlight,  # NAVIGATION — cool blue
            (110, 200, 130),            # INTERFACE — sage green (utility,
                                        # intentionally distinct from
                                        # LIGHT_SUCCESS so the three help
                                        # sections read as three colours,
                                        # not "warning + cool + success")
        )
        for i, (section_title, glyph, rows) in enumerate(sections):
            col_x = modal.left + 24 + i * (col_w + gap)
            section_rect = pygame.Rect(col_x, section_top, col_w, section_h)
            self._draw_help_section(
                surface, section_rect, section_title, glyph, rows,
                accent=section_accents[i],
            )

        # Footer hint.
        hint = self.fonts.label.render(
            "H · ÉCHAP POUR FERMER", True, self.palette.text_dim,
        )
        surface.blit(
            hint,
            (modal.centerx - hint.get_width() // 2,
             modal.bottom - hint.get_height() - 18),
        )

    def _draw_help_section(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        title: str,
        glyph: str,
        rows: tuple[tuple[str, str], ...],
        *,
        accent: tuple[int, int, int] | None = None,
    ) -> None:
        """Single section card inside the help modal.

        Refinements over the prior flat design:

        * **Per-section accent** (passed in by the caller, one of
          warm/cool/sage) replaces the previous shared ``ui_accent``.
          The badge ring, top accent stripe, key pill highlights, and
          section title underline all draw from this colour so each
          section card has its own *visual identity* rather than
          reading as "three identical containers in three columns".
        * **Card body screen-surface depth** — subtle vertical
          gradient (top brighter, bottom darker) + 1-px top
          highlight + 1-px bottom shadow. Same idiom shipped on the
          TENDANCE chart container and info panel header — gives the
          card a "raised display surface" feel instead of a flat
          painted rounded rect.
        * **Top accent stripe** in the section's tint (2 px,
          inset 4 px from the rounded corners) — same colour-stripe
          idiom the right panel + news ticker + minimap brackets
          already use to carry identity into the chrome.
        * **3D key pills** — vertical gradient + top highlight +
          bottom shadow on each key pill. Reads as a *physical
          keyboard key* (the player's mental model — these *are*
          keyboard shortcuts) instead of a flat label-with-border.
        """
        if accent is None:
            accent = self.palette.ui_accent

        # Translucent card body.
        body = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            body, (*self.palette.surface_deep[:3], 200),
            (0, 0, rect.width, rect.height), border_radius=10,
        )
        # Vertical gradient overlay inside the card.
        for gy in range(rect.height):
            t = gy / max(1, rect.height - 1)
            shift = int(12 * (1.0 - 2 * t))
            if shift > 0:
                pygame.draw.line(
                    body, (255, 255, 255, min(255, shift * 2)),
                    (0, gy), (rect.width, gy),
                )
            elif shift < 0:
                pygame.draw.line(
                    body, (0, 0, 0, min(255, -shift * 2)),
                    (0, gy), (rect.width, gy),
                )
        surface.blit(body, rect.topleft)
        # Border tinted with the section accent (35 % blend) instead of
        # the neutral ui_border_soft — keeps the section's identity
        # readable even at the edges.
        pygame.draw.rect(
            surface, _blend(self.palette.surface_deep[:3], accent, 0.35),
            rect, 1, border_radius=10,
        )
        # Top accent stripe — 2 px in the section's tint, inset 4 px
        # so the rounded corners stay clean. ``border_radius`` is
        # omitted here: pygame's rect-rounding on a 2-px-tall stripe
        # collapses the draw to nothing on some backends (the radius
        # is taller than half the rect height, so the rounded corners
        # eat the entire fill). A flat 2-px stripe inset 4 px is
        # already crisp enough.
        pygame.draw.rect(
            surface, accent,
            (rect.left + 4, rect.top + 1, rect.width - 8, 2),
        )
        # 1-px top-edge highlight stroke just below the accent stripe.
        pygame.draw.line(
            surface,
            _blend(self.palette.surface_deep[:3], (255, 255, 255), 0.20),
            (rect.left + 6, rect.top + 4),
            (rect.right - 6, rect.top + 4),
            1,
        )
        # 1-px bottom-edge shadow stroke.
        pygame.draw.line(
            surface,
            _blend(self.palette.surface_deep[:3], (0, 0, 0), 0.50),
            (rect.left + 6, rect.bottom - 2),
            (rect.right - 6, rect.bottom - 2),
            1,
        )

        # Glyph badge — top-left, section-accent-tinted circle + glyph.
        badge_r = 18
        badge_cx = rect.left + 18 + badge_r
        badge_cy = rect.top + 18 + badge_r
        pygame.draw.circle(
            surface, _blend((10, 12, 18), accent, 0.45),
            (badge_cx, badge_cy), badge_r,
        )
        pygame.draw.circle(
            surface, accent, (badge_cx, badge_cy), badge_r, 2,
        )
        self._draw_help_glyph(surface, glyph, (badge_cx, badge_cy), badge_r - 4)

        # Section title to the right of the badge.
        title_text = self.fonts.label.render(
            title, True, self.palette.text,
        )
        surface.blit(
            title_text,
            (badge_cx + badge_r + 10,
             badge_cy - title_text.get_height() // 2),
        )

        # Rows below the badge.
        row_y = badge_cy + badge_r + 14
        row_h = self.fonts.small.get_height() + 8
        for key, desc in rows:
            # Key pill — small rounded rect rendered as a 3D
            # keyboard key. Layers: flat fill → vertical gradient
            # (top brighter, bottom darker) → top-edge highlight →
            # bottom-edge shadow → accent-tinted border. The eye
            # reads it as a physical keycap rather than a flat label.
            key_text = self.fonts.label.render(
                key, True, self.palette.text,
            )
            pill_w = key_text.get_width() + 14
            pill_h = key_text.get_height() + 6
            pill = pygame.Rect(rect.left + 18, row_y, pill_w, pill_h)
            pygame.draw.rect(
                surface, self.palette.surface_overlay[:3], pill,
                border_radius=pill_h // 2,
            )
            # Vertical gradient on the pill — clipped to the pill rect.
            prev_clip = surface.get_clip()
            surface.set_clip(pill)
            grad = pygame.Surface(pill.size, pygame.SRCALPHA)
            for gy in range(pill_h):
                t = gy / max(1, pill_h - 1)
                shift = int(20 * (1.0 - 2 * t))
                if shift > 0:
                    pygame.draw.line(
                        grad, (255, 255, 255, min(255, shift * 3)),
                        (0, gy), (pill_w, gy),
                    )
                elif shift < 0:
                    pygame.draw.line(
                        grad, (0, 0, 0, min(255, -shift * 3)),
                        (0, gy), (pill_w, gy),
                    )
            surface.blit(grad, pill.topleft)
            surface.set_clip(prev_clip)
            # Top highlight stroke + bottom shadow stroke on the pill —
            # 1 px each, inset 3 px so they don't crash the rounded ends.
            pygame.draw.line(
                surface,
                _blend(self.palette.surface_overlay[:3], (255, 255, 255), 0.45),
                (pill.left + 3, pill.top + 1),
                (pill.right - 3, pill.top + 1),
                1,
            )
            pygame.draw.line(
                surface,
                _blend(self.palette.surface_overlay[:3], (0, 0, 0), 0.55),
                (pill.left + 3, pill.bottom - 2),
                (pill.right - 3, pill.bottom - 2),
                1,
            )
            # Section-accent-tinted border (was neutral ui_border).
            pygame.draw.rect(
                surface,
                _blend(self.palette.ui_border, accent, 0.40),
                pill, 1, border_radius=pill_h // 2,
            )
            surface.blit(
                key_text,
                (pill.centerx - key_text.get_width() // 2,
                 pill.centery - key_text.get_height() // 2),
            )
            # Description to the right of the pill.
            desc_text = self.fonts.small.render(
                desc, True, self.palette.text_label,
            )
            surface.blit(
                desc_text,
                (pill.right + 10,
                 pill.centery - desc_text.get_height() // 2),
            )
            row_y += row_h + 4

    def _draw_help_glyph(
        self,
        surface: pygame.Surface,
        kind: str,
        center: tuple[int, int],
        r: int,
    ) -> None:
        """Procedural section icon, matching the in-game element-glyph idiom."""
        cx, cy = center
        color = (245, 248, 255)
        if kind == "play":
            # Triangle pointing right.
            pts = [
                (cx - r // 2, cy - r),
                (cx + r, cy),
                (cx - r // 2, cy + r),
            ]
            pygame.draw.polygon(surface, color, pts)
        elif kind == "compass":
            # Compass-rose diamond with a filled North marker — was a
            # generic 4-arrow cross that read as "directional pad", not
            # "compass". The diamond + accented north pip gives the
            # glyph a real compass-rose silhouette: the player reads
            # NAVIGATION immediately instead of decoding 4 ambiguous
            # arrows.
            arm = r
            diamond = [
                (cx, cy - arm),  # N
                (cx + arm, cy),  # E
                (cx, cy + arm),  # S
                (cx - arm, cy),  # W
            ]
            pygame.draw.polygon(surface, color, diamond, 2)
            # Inner diamond — secondary cross at half-arm, gives the
            # rose its layered look.
            inner = [
                (cx, cy - arm // 2),
                (cx + arm // 2, cy),
                (cx, cy + arm // 2),
                (cx - arm // 2, cy),
            ]
            pygame.draw.polygon(surface, color, inner, 1)
            # North marker — small filled triangle pointing up, sits at
            # the top apex so the player can tell which way is north
            # (the whole point of a compass).
            n_triangle = [
                (cx, cy - arm),
                (cx - 3, cy - arm + 6),
                (cx + 3, cy - arm + 6),
            ]
            pygame.draw.polygon(surface, color, n_triangle)
            # Centre pip.
            pygame.draw.circle(surface, color, (cx, cy), 2)
        elif kind == "grid":
            # Stylised game-UI layout: map area (wide left rect) +
            # right sidebar (narrow filled rect). Was a generic 2×2
            # grid of squares which had nothing to do with "interface"
            # — now the icon literally depicts THIS game's HUD shape
            # (map on the left, dashboard panel on the right), so a
            # player reading the INTERFACE section knows the keybinds
            # below act on the surfaces they're looking at.
            map_w = int(r * 1.4)
            side_w = max(3, int(r * 0.45))
            gap = 1
            total_w = map_w + gap + side_w
            total_h = int(r * 1.4)
            left = cx - total_w // 2
            top = cy - total_h // 2
            # Outer frame — full HUD bounds.
            pygame.draw.rect(
                surface, color,
                (left, top, total_w, total_h), 1, border_radius=2,
            )
            # Map area — empty rect (the world map).
            pygame.draw.rect(
                surface, color,
                (left, top, map_w, total_h), 1,
            )
            # Sidebar — filled rect (the dashboard panel).
            pygame.draw.rect(
                surface, color,
                (left + map_w + gap, top, side_w, total_h),
            )
        else:
            glyph = self.fonts.label.render(kind[:1].upper(), True, color)
            surface.blit(
                glyph,
                (cx - glyph.get_width() // 2,
                 cy - glyph.get_height() // 2),
            )

    # ---------------------------------------------------------- picker

    def _draw_intro_picker(self, surface: pygame.Surface, game: Game) -> None:
        """4-step wizard for scenario setup.

        Step -1 — Choose your side (GAIA / HUMANITÉ).
        Step  0 — Choose a catastrophe (5 cards, map hidden).
        Step  1 — Choose a difficulty (3 cards, map hidden).
        Step  2 — Choose an origin country (map foregrounded, LANCER button).
        """
        w, h = self.screen_size
        step = max(-1, min(2, game.picker_step))
        mouse_pos = pygame.mouse.get_pos()
        cat_color = game.gaia.active.arc_color

        # ---- Vignette: full dim on cards-focused steps, lighter on the
        # origin step so the map underneath is the click target.
        map_rect = self.map_rect
        if step == 2:
            # Vignette dim instead of a flat alpha fill — corners are
            # darker than the centre, so the player's eye is pulled
            # toward the middle of the map where "pick an origin"
            # actually happens. Cached on the renderer because the
            # size is stable; only paints once on first picker step-2
            # entry per session.
            dim = self._picker_origin_vignette_cache(map_rect.size)
            surface.blit(dim, map_rect.topleft)
        else:
            dim = pygame.Surface((w, h), pygame.SRCALPHA)
            dim.fill((6, 10, 20, 230))
            surface.blit(dim, (0, 0))
            # Textured atmospheric overlay — same warm-cool gradient +
            # film-grain idiom shipped on the worldmap and info panel,
            # tuned to picker scale (α 9-10 for the gradient, between
            # the worldmap's 10-12 and the info panel's 7-8). Sits
            # *after* the dim flat fill but *before* the aurora bloom,
            # so the catastrophe-tinted bloom paints on top of a
            # textured backdrop rather than a flat one — the aurora
            # itself reads as more dimensional, and the unbloomed
            # corners of the screen no longer register as "dead flat
            # rectangle". Cached per screen size.
            self._draw_picker_texture_overlay(surface, (w, h))
            # Soft radial bloom in the active accent. Side step uses a neutral
            # cyan/coral split visualised below.
            if step >= 0:
                self._draw_picker_aurora(surface, cat_color)

        # ---- Step indicator + title at the top of every step.
        step_titles = ("CÔTÉ", "CATASTROPHE", "DIFFICULTÉ", "ORIGINE")
        side = getattr(game, "player_side", "gaia")
        step_taglines = (
            "Quel camp incarnez-vous dans le scénario ?",
            (
                # GAIA orchestrates the force; HUMANITÉ defends against
                # one. The previous fixed "Quelle force planétaire
                # allez-vous simuler ?" spoke the GAIA voice for both
                # sides — a HUMANITÉ player was asked which catastrophe
                # they would *simulate*, when they're picking which one
                # to defend against. Side-aware now, mirroring the
                # existing split on the DIFFICULTÉ tagline below.
                "Contre quelle force planétaire vous défendrez-vous ?"
                if side == "humanite"
                else "Quelle force planétaire allez-vous simuler ?"
            ),
            (
                # HUMANITÉ player picks how strong the threat will be;
                # GAIA player picks how prepared the targets will be.
                # "Quelle résistance pour vos cibles ?" was grammatically
                # truncated — the verb is missing. Restored to the full
                # form so the question reads as a complete sentence.
                "Quelle est la puissance de la catastrophe simulée ?"
                if side == "humanite"
                else "Quelle résistance opposeront vos cibles ?"
            ),
            (
                # GAIA "places" the first foyer (active orchestration);
                # HUMANITÉ "sees it start" somewhere (passive observer
                # of where the threat lands). Was a single
                # "Où placez-vous le premier foyer ?" — the active-verb
                # ``placez-vous`` only fits the GAIA side. HUMANITÉ
                # picks where the simulation will start but the framing
                # should be observational, not authorial.
                "Où démarrera le premier foyer ?"
                if side == "humanite"
                else "Où placez-vous le premier foyer ?"
            ),
        )
        # Brief catastrophe-tint shockwave at picker entry — quick visual cue
        # that the briefing has loaded. Only fires on the first ~700 ms.
        if not game.reduce_motion:
            elapsed_ms_picker = (
                pygame.time.get_ticks() - self._phase_transition_start_ms
            )
            picker_intro_t = min(1.0, max(0.0, elapsed_ms_picker / 700))
            if picker_intro_t < 1.0:
                ring_r = int(picker_intro_t * max(w, h) * 0.55)
                ring_alpha = int(130 * (1.0 - picker_intro_t))
                if ring_alpha > 4:
                    ring_layer = pygame.Surface(
                        (ring_r * 2 + 6, ring_r * 2 + 6), pygame.SRCALPHA,
                    )
                    pygame.draw.circle(
                        ring_layer, (*cat_color, ring_alpha),
                        (ring_r + 3, ring_r + 3), ring_r, 3,
                    )
                    surface.blit(
                        ring_layer,
                        (w // 2 - ring_r - 3, h // 2 - ring_r - 3),
                    )
        # Stepper draws 4 dots — shift indices by 1 so -1 → 0.
        self._draw_picker_stepper(surface, step + 1, step_titles, cat_color)
        idx = step + 1
        # Editorial header: hero title flush-left, tagline left-aligned below,
        # short catastrophe-tinted accent rule under both. Replaces the
        # previous all-centred stack which funnelled every element through
        # the canvas centreline and competed visually with the centred
        # content cards below.
        title_x = 48
        title_y = 40
        title = self.fonts.title.render(step_titles[idx], True, self.palette.text)
        surface.blit(title, (title_x, title_y))
        tag = self.fonts.medium.render(
            step_taglines[idx], True, self.palette.text_dim,
        )
        tag_y = title_y + title.get_height() + 4
        surface.blit(tag, (title_x, tag_y))
        # Left-aligned catastrophe-tinted accent rule under the tagline —
        # starts flush with the title at full intensity and fades out to
        # the right. Anchors the header block to its left edge.
        accent_y = tag_y + tag.get_height() + 8
        accent_w = max(96, title.get_width() // 2)
        accent_strip = pygame.Surface((accent_w, 2), pygame.SRCALPHA)
        for px in range(accent_w):
            # Asymmetric envelope — full alpha on the left, smooth fade out
            # to the right. Quadratic falloff (1−t)² reads as "starts solid,
            # tapers gracefully" rather than a uniform bar.
            t = px / accent_w
            a = int(220 * (1.0 - t) ** 2)
            if a <= 0:
                continue
            pygame.draw.line(
                accent_strip, (*cat_color, a),
                (px, 0), (px, 1),
            )
        surface.blit(accent_strip, (title_x, accent_y))
        # Step counter on the right — small monochrome "N / 4" that
        # balances the left-aligned hero text and gives the header a
        # second visual anchor. Doubles as a redundant location cue
        # alongside the stepper dots up top.
        total_steps = len(step_titles)
        counter_text = self.fonts.label.render(
            f"ÉTAPE {idx + 1} / {total_steps}",
            True, self.palette.text_label,
        )
        counter_x = w - 48 - counter_text.get_width()
        # Vertically aligned with the title baseline — sits just under it
        # so the right column reads as a header element, not a floating chip.
        counter_y = title_y + title.get_height() - counter_text.get_height() - 2
        surface.blit(counter_text, (counter_x, counter_y))

        # ---- Step content.
        if step == -1:
            self._draw_picker_step_side(surface, game, mouse_pos)
        elif step == 0:
            self._draw_picker_step_catastrophe(surface, game, mouse_pos)
        elif step == 1:
            self._draw_picker_step_difficulty(surface, game, mouse_pos)
        else:
            self._draw_picker_step_origin(surface, game, mouse_pos)

        # ---- Navigation footer (PRÉCÉDENT / SUIVANT or LANCER).
        self._draw_picker_nav(surface, game, mouse_pos)

    def _draw_sidebar_toggle(
        self, surface: pygame.Surface, game: Game,
    ) -> None:
        """Chevron pill on the inner edge of the right panel.

        Layered build (was: plain rounded rect + 2 px chevron — minimal,
        and the only persistent map-edge control that didn't pick up
        the run's catastrophe-colour identity):

          1. **Soft catastrophe-tinted halo on hover** — same idiom as
             the OBJECTIF bar leading edge and the speed-button accent.
             Signals interactivity *and* roots the control in the run's
             identity, so the player's eye treats it as part of the
             HUD instead of a neutral chrome control.
          2. **Tinted border on hover** — accent-blended border so the
             pill matches the OBJECTIF / speed / LANCER pattern of
             "neutral → catastrophe-tint on hover/active".
          3. **Thicker chevron** (2 px → 3 px) — the direction cue
             reads cleanly at the icon's small size; a 2 px line in a
             22 px pill was visually thin against the panel-edge halo.
        """
        collapsed = game.sidebar_collapsed
        rect = sidebar_toggle_rect(self.config, collapsed)
        mouse_pos = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse_pos)
        cat_color = game.gaia.active.arc_color

        # 1. Soft halo behind the pill on hover.
        if hover:
            halo_pad = 6
            halo = pygame.Surface(
                (rect.width + halo_pad * 2, rect.height + halo_pad * 2),
                pygame.SRCALPHA,
            )
            for i in range(halo_pad, 0, -1):
                t = i / halo_pad
                alpha = int(60 * (1 - t) ** 1.6)
                if alpha < 1:
                    continue
                pygame.draw.rect(
                    halo, (*cat_color, alpha),
                    (halo_pad - i, halo_pad - i,
                     rect.width + i * 2, rect.height + i * 2),
                    2, border_radius=11 + (halo_pad - i),
                )
            surface.blit(halo, (rect.left - halo_pad, rect.top - halo_pad))

        # 2. Pill body + tinted border on hover.
        fill = (
            self.palette.surface_elevated[:3]
            if hover else self.palette.surface[:3]
        )
        pygame.draw.rect(surface, fill, rect, border_radius=11)
        border_color = (
            _blend(self.palette.ui_border, cat_color, 0.45)
            if hover else self.palette.ui_border_soft
        )
        pygame.draw.rect(surface, border_color, rect, 1, border_radius=11)

        # 3. Chevron — thickened from 2 px to 3 px. Points right when
        # collapsed (open), left when open (close).
        cx, cy = rect.centerx, rect.centery
        arm = 4
        if collapsed:
            pts = [(cx - 2, cy - arm), (cx + 3, cy), (cx - 2, cy + arm)]
        else:
            pts = [(cx + 2, cy - arm), (cx - 3, cy), (cx + 2, cy + arm)]
        pygame.draw.lines(
            surface,
            self.palette.text if hover else self.palette.text_label,
            False, pts, 3,
        )

    def _draw_recenter_button(
        self, surface: pygame.Surface, game: Game,
    ) -> None:
        """Discrete "fit to screen" pill at the bottom-left of the map.

        Same low-contrast idiom as ``_draw_sidebar_toggle``:
        soft surface fill + thin border, both lifted on hover with
        the active catastrophe's tint. Icon is a square frame with a
        centre dot — universally read as "recentre / fit view" and
        small enough not to compete with map content. Tap resets
        zoom + pan so the player can recover from a stuck deep-zoom
        in one click instead of pinch-zooming back to overview.
        """
        rect = recenter_map_button_rect(self.config)
        mouse_pos = pygame.mouse.get_pos()
        hover = rect.collidepoint(mouse_pos)
        cat_color = game.gaia.active.arc_color

        fill = (
            self.palette.surface_elevated[:3]
            if hover else self.palette.surface[:3]
        )
        # Round-rect body, same radius family as the sidebar pill so
        # the two map-edge controls feel like siblings.
        pygame.draw.rect(surface, fill, rect, border_radius=6)
        border_color = (
            _blend(self.palette.ui_border, cat_color, 0.45)
            if hover else self.palette.ui_border_soft
        )
        pygame.draw.rect(surface, border_color, rect, 1, border_radius=6)

        # Icon — outer frame (corner brackets) + centre dot. Reads as
        # "snap viewport back to centre" even without a label.
        glyph_color = self.palette.text if hover else self.palette.text_label
        cx, cy = rect.centerx, rect.centery
        arm = max(4, rect.width // 5)
        inset = max(3, rect.width // 6)
        # Four corner brackets — small L-shapes pointing inward.
        for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            x = cx + dx * (rect.width // 2 - inset)
            y = cy + dy * (rect.height // 2 - inset)
            pygame.draw.line(surface, glyph_color, (x, y), (x - dx * arm, y), 2)
            pygame.draw.line(surface, glyph_color, (x, y), (x, y - dy * arm), 2)
        # Centre dot.
        pygame.draw.circle(surface, glyph_color, (cx, cy), 2)

    def _draw_pause_vignette(
        self, surface: pygame.Surface, size: tuple[int, int],
    ) -> None:
        """Soft radial vignette for the pause menu — corners darker.

        Focuses the eye on the centered menu by gently darkening the
        screen's outer edges. The vignette is purely additive black
        with a smooth radial alpha falloff — no colour shift, no
        contrast crush. Subtle (max α 50 at the corner extremes).
        Cached per screen size.
        """
        cached = getattr(self, "_pause_vignette_cache", None)
        if cached is None or cached.get_size() != size:
            cached = self._build_pause_vignette(*size)
            self._pause_vignette_cache = cached
        surface.blit(cached, (0, 0))

    def _build_pause_vignette(
        self, w: int, h: int,
    ) -> pygame.Surface:
        """Pre-render the radial vignette layer."""
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        cx, cy = w // 2, h // 2
        # Corner distance from centre — the vignette reaches max α
        # at this radius. Beyond ~60 % of corner distance, alpha
        # ramps up from 0 to the max so the inner 60 % of the screen
        # area stays untouched (where the menu lives).
        max_r = math.hypot(cx, cy)
        inner_r = int(max_r * 0.55)
        # Draw concentric expanding annuli at increasing alpha.
        # 4 px steps keep the falloff smooth without the cost of
        # per-pixel computation.
        for r in range(max_r_int := int(max_r), inner_r, -4):
            t = (r - inner_r) / max(1, max_r - inner_r)
            a = int(50 * t ** 1.6)
            if a < 1:
                continue
            pygame.draw.circle(layer, (0, 0, 0, a), (cx, cy), r, 4)
        return layer

    def _draw_picker_texture_overlay(
        self, surface: pygame.Surface, size: tuple[int, int],
    ) -> None:
        """Textured atmospheric overlay for the picker background.

        Mirrors the worldmap / info-panel idiom but tuned to picker
        scale — a hero menu screen between gameplay (worldmap, where
        α 10-12 is appropriate) and the data-dense info panel (α
        7-8). The picker's role is to *land the player on a choice*,
        so the texture is prominent enough to give the bg material
        feel (the dim fill alone reads as paint), but stays under
        the threshold where it would compete with the catastrophe
        aurora bloom that paints on top. α 9 for the warm tint
        (top), α 8 for the cool tint (bottom), 4 % grain coverage
        at α 7.

        Cached per screen size — re-used on every picker render
        (4 steps × many frames).
        """
        cached = getattr(self, "_picker_texture_cache", None)
        if cached is None or cached.get_size() != size:
            cached = self._build_picker_texture_overlay(*size)
            self._picker_texture_cache = cached
        surface.blit(cached, (0, 0))

    def _build_picker_texture_overlay(
        self, w: int, h: int,
    ) -> pygame.Surface:
        """Pre-render the warm-cool gradient + grain layer for the picker."""
        import random as _random
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        mid = h // 2
        for y in range(h):
            if y < mid:
                t = 1.0 - (y / max(1, mid))
                a = int(9 * (t ** 1.2))
                if a >= 1:
                    pygame.draw.line(
                        layer, (240, 200, 160, a), (0, y), (w, y),
                    )
            else:
                t = (y - mid) / max(1, h - mid)
                a = int(8 * (t ** 1.2))
                if a >= 1:
                    pygame.draw.line(
                        layer, (120, 160, 220, a), (0, y), (w, y),
                    )
        # Grain — α 7 (between worldmap's 8 and info panel's 7).
        # Distinct seed (2028) so the picker's grain doesn't align
        # with the worldmap (2026) or info panel (2027) — each
        # screen has its own stable noise field.
        rng = _random.Random(2028)
        n_grains = int(w * h * 0.04)
        for _ in range(n_grains):
            x = rng.randint(0, w - 1)
            y = rng.randint(0, h - 1)
            if rng.random() < 0.5:
                layer.set_at((x, y), (255, 255, 255, 7))
            else:
                layer.set_at((x, y), (0, 0, 0, 7))
        return layer

    def _draw_info_panel_texture(
        self, surface: pygame.Surface, body_rect: pygame.Rect,
    ) -> None:
        """Textured atmospheric overlay on the info panel body.

        Mirrors the worldmap's idiom (warm-cool gradient + film grain)
        scaled to the panel size. Cached per-size — for a single
        ``INFO_PANEL_W × INFO_PANEL_H`` panel this means one cached
        surface total, one blit per frame. The texture is *subtler*
        than the map's (lower α throughout) because the panel is a
        UI surface, not a hero render target — too much grain would
        compete with the data.
        """
        key = (body_rect.width, body_rect.height)
        cached = getattr(self, "_info_panel_texture_cache", None)
        if cached is None or cached.get_size() != key:
            cached = self._build_info_panel_texture(*key)
            self._info_panel_texture_cache = cached
        surface.blit(cached, body_rect.topleft)

    def _build_info_panel_texture(
        self, w: int, h: int,
    ) -> pygame.Surface:
        """Pre-render the gradient + grain layer for an info panel body."""
        import random as _random
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        # Vertical warm-cool gradient — lower α than the worldmap so
        # the panel doesn't shift its overall hue noticeably; the
        # gradient is there to break the flatness, not to recolour.
        mid = h // 2
        for y in range(h):
            if y < mid:
                t = 1.0 - (y / max(1, mid))
                a = int(8 * (t ** 1.2))
                if a >= 1:
                    pygame.draw.line(
                        layer, (240, 200, 160, a), (0, y), (w, y),
                    )
            else:
                t = (y - mid) / max(1, h - mid)
                a = int(7 * (t ** 1.2))
                if a >= 1:
                    pygame.draw.line(
                        layer, (120, 160, 220, a), (0, y), (w, y),
                    )
        # Fine grain — same 4 % coverage / α 6-8 as the worldmap.
        # Deterministic seed so the noise is stable across frames
        # (film-grain feels like a material property, not animated).
        # Distinct seed from the worldmap so the patterns don't
        # accidentally align if the panel ever sits over the map.
        rng = _random.Random(2027)
        n_grains = int(w * h * 0.04)
        for _ in range(n_grains):
            x = rng.randint(0, w - 1)
            y = rng.randint(0, h - 1)
            if rng.random() < 0.5:
                layer.set_at((x, y), (255, 255, 255, 7))
            else:
                layer.set_at((x, y), (0, 0, 0, 7))
        return layer

    def _draw_map_texture_overlay(self, surface: pygame.Surface) -> None:
        """Textured atmospheric overlay (warm-cool gradient + film grain).

        Cached once on first call; per-frame cost is a single blit of
        an SRCALPHA layer the size of ``map_rect``. Two stacked
        contributions on the same surface:

        * **Warm-cool vertical gradient** — subtle warm orange tint at
          top (~α 12) fading through neutral mid, to subtle cool
          blue tint at bottom (~α 10). Earth-from-space tonal
          scheme: warm equatorial band → cool polar regions. Adds
          colour-temperature variation across the map without
          obliterating individual country fills.
        * **Film-grain noise** — ~4 % coverage of single-pixel
          white/black grains at α 6-8. Gives the otherwise-flat
          country colour areas apparent material *texture* — they
          read as "land surfaces with grain" instead of as "flat
          coloured polygons". Same idiom AAA game maps use to make
          flat tile palettes look modern.

        Layered AFTER countries (so it grades them) but BEFORE
        spread arcs / orbs / floating texts (so it doesn't dim the
        gameplay-focus elements).
        """
        cached = getattr(self, "_map_texture_cache", None)
        if cached is None or cached.get_size() != self.map_rect.size:
            cached = self._build_map_texture_overlay(
                self.map_rect.width, self.map_rect.height,
            )
            self._map_texture_cache = cached
        surface.blit(cached, self.map_rect.topleft)

    def _build_map_texture_overlay(
        self, w: int, h: int,
    ) -> pygame.Surface:
        """Pre-render the gradient + grain layer."""
        import random as _random
        layer = pygame.Surface((w, h), pygame.SRCALPHA)
        # Vertical warm-cool gradient. Top warm (sunlit equatorial
        # tone) → transparent at middle → bottom cool (polar shadow
        # tone). Alphas are deliberately low so the gradient grades
        # rather than tints.
        mid = h // 2
        for y in range(h):
            if y < mid:
                t = 1.0 - (y / max(1, mid))  # 1 at top → 0 at middle
                a = int(12 * (t ** 1.2))
                if a >= 1:
                    pygame.draw.line(
                        layer, (240, 200, 160, a), (0, y), (w, y),
                    )
            else:
                t = (y - mid) / max(1, h - mid)  # 0 at middle → 1 at bottom
                a = int(10 * (t ** 1.2))
                if a >= 1:
                    pygame.draw.line(
                        layer, (120, 160, 220, a), (0, y), (w, y),
                    )
        # Film-grain noise. Deterministic seed so the texture is
        # stable across runs (otherwise the noise would shimmer
        # frame-to-frame if regenerated, which is the opposite of
        # what we want — film grain should feel like a *property
        # of the material*, not animated noise).
        rng = _random.Random(2026)
        n_grains = int(w * h * 0.04)
        for _ in range(n_grains):
            x = rng.randint(0, w - 1)
            y = rng.randint(0, h - 1)
            if rng.random() < 0.5:
                layer.set_at((x, y), (255, 255, 255, 8))
            else:
                layer.set_at((x, y), (0, 0, 0, 8))
        return layer

    def _draw_picker_aurora(
        self,
        surface: pygame.Surface,
        tint: tuple[int, int, int],
    ) -> None:
        """Soft radial bloom in the active catastrophe colour behind the cards.

        Built from a single radial-alpha gradient surface that blends with
        normal alpha (not BLEND_RGB_ADD — that saturates instantly). Centred
        horizontally, slightly above middle to sit behind the card row.
        """
        w, h = self.screen_size
        cx = w // 2
        cy = int(h * 0.42)
        max_r = int(min(w, h) * 0.55)
        aurora = pygame.Surface((max_r * 2, max_r * 2), pygame.SRCALPHA)
        # Paint outermost first with low alpha, inner rings slightly stronger
        # but always capped so the brightest centre is ~alpha 35.
        for i in range(max_r, 0, -3):
            t = i / max_r
            alpha = int(55 * (1 - t) ** 1.8)
            if alpha < 1:
                continue
            pygame.draw.circle(
                aurora, (*tint, alpha), (max_r, max_r), i,
            )
        surface.blit(aurora, (cx - max_r, cy - max_r))

    def _draw_picker_stepper(
        self,
        surface: pygame.Surface,
        step: int,
        labels: tuple[str, ...],
        accent: tuple[int, int, int],
    ) -> None:
        """N-dot progress indicator at the very top of the picker.

        Inactive dots/lines used to render in ``ui_border_soft``
        (lum ≈ 0.05) which was nearly invisible against the dim picker
        overlay — the player could see where they were but not how many
        steps remained. Inactive state now uses a darkened blend of the
        accent (≈ 4× brighter than before) so the full progress path
        is legible end-to-end while staying visually subordinate to the
        active state.

        ``labels`` (CÔTÉ / CATASTROPHE / DIFFICULTÉ / ORIGINE) was a
        dead parameter — passed in by every caller but never rendered.
        The active step's label now appears as a centred caption under
        its dot so the player has a "you are here" anchor that names
        the moment instead of just an indexed pip. Centred on the
        active dot specifically (not on the row centre) so the label
        moves left-to-right as the player advances, reinforcing the
        sense of progression.
        """
        w = self.screen_size[0]
        spacing = 40
        dot_r = 5
        total_w = (len(labels) - 1) * spacing
        cx = (w - total_w) // 2
        y = 14
        inactive_color = _blend(self.palette.surface_deep, accent, 0.55)
        active_x: int | None = None
        for i, label in enumerate(labels):
            done = i < step
            current = i == step
            x = cx + i * spacing
            if i > 0:
                pygame.draw.line(
                    surface,
                    accent if done or current else inactive_color,
                    (x - spacing + dot_r + 2, y),
                    (x - dot_r - 2, y),
                    2,
                )
            color = accent if (done or current) else inactive_color
            pygame.draw.circle(surface, color, (x, y), dot_r)
            if current:
                pygame.draw.circle(
                    surface, self.palette.text, (x, y), dot_r + 3, 2,
                )
                active_x = x

        # Active-step caption — small uppercase label centred under the
        # current dot. ``text_label`` brightness keeps it subordinate to
        # the row title shown in the body content (catastrophe names /
        # difficulty cards / etc.), so the stepper caption reads as
        # navigation orientation, not a hero element.
        if active_x is not None and 0 <= step < len(labels):
            caption = self.fonts.label.render(
                labels[step], True, self.palette.text_label,
            )
            cap_x = active_x - caption.get_width() // 2
            # Clamp to screen edges so the leftmost / rightmost step's
            # caption stays inside the canvas at small window sizes.
            cap_x = max(4, min(w - caption.get_width() - 4, cap_x))
            surface.blit(caption, (cap_x, y + dot_r + 6))

    def _draw_picker_step_side(
        self,
        surface: pygame.Surface,
        game: Game,
        mouse_pos: tuple[int, int],
    ) -> None:
        """Step -1 — choose between playing Gaia (catastrophe) or Humanité
        (countermeasures). Two big hero cards centred in the screen."""
        cards = picker_side_card_rects(self.config)
        active_side = getattr(game, "player_side", "gaia")
        side_specs = (
            # Sub-text lists the *full set* of axes/indicators each side
            # actually controls. Previously: GAIA mentioned only 3 of 4
            # axes (omitting Durée), and HUMANITÉ mentioned only 2 of 4
            # indicators (omitting Stabilité + Régénération) — players
            # picked a side based on an incomplete spec sheet.
            # Headlines reframed from oppositional ("Renforcez" /
            # "Atténuez la catastrophe") to generative — each side
            # *gives voice to* something the planet already has. GAIA
            # speaks through its forces; HUMANITÉ grows its capacity
            # to coexist. Mirrors the source doc's "comprendre /
            # s'émerveiller / agir" framing where the two sides are
            # complementary movements of the same simulation, not
            # adversaries. Sub-text (spec sheet) unchanged so the
            # picker still works as a choice tool.
            # Internal key stays "gaia" (player_side enum / Python token);
            # display label switches to "PLANÈTE" for the picker card.
            ("gaia", "PLANÈTE", (220, 110, 80), "wave",
             "Faites parler la planète.",
             "Faites monter intensité, portée, durée et impact écologique."),
            ("humanite", "HUMANITÉ", (110, 200, 230), "shield",
             "Faites grandir la résilience.",
             "Renforcez résilience, stabilité, régénération et adaptation."),
        )
        for (key, label, tint, glyph, headline, sub), card_rect in zip(
            side_specs, cards,
        ):
            self._draw_side_card(
                surface, card_rect, label, tint, glyph, headline, sub,
                active=key == active_side,
                hover=card_rect.collidepoint(mouse_pos),
            )

    def _draw_side_card(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        tint: tuple[int, int, int],
        glyph: str,
        headline: str,
        sub: str,
        *,
        active: bool,
        hover: bool,
    ) -> None:
        """Hero side card: big glyph + LABEL + headline + sub."""
        self._draw_shadow(surface, rect, blur=16, alpha=160 if active else 100)
        # Matching focus glow + thicker border so the "selected side"
        # is obviously different from "the other option".
        if active:
            ticks = pygame.time.get_ticks()
            pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
            glow_alpha = int(80 + 70 * pulse)
            glow_pad = 8
            glow = pygame.Surface(
                (rect.width + glow_pad * 2, rect.height + glow_pad * 2),
                pygame.SRCALPHA,
            )
            pygame.draw.rect(
                glow, (*tint, glow_alpha),
                (0, 0, rect.width + glow_pad * 2, rect.height + glow_pad * 2),
                3, border_radius=14 + glow_pad,
            )
            surface.blit(glow, (rect.left - glow_pad, rect.top - glow_pad))
        if active:
            fill = self.palette.surface_overlay[:3]
            border = tint
            border_w = 3
        else:
            fill = (
                self.palette.surface_elevated[:3]
                if hover else self.palette.surface_deep[:3]
            )
            border = _blend(self.palette.surface_deep, tint, 0.5 if hover else 0.2)
            border_w = 1
        pygame.draw.rect(surface, fill, rect, border_radius=14)
        # Vertical gradient overlay on the body — top +14 / bottom −14
        # luminance, clipped to the rounded corners via a BLEND_RGBA_MULT
        # mask so the gradient respects the 14-px radius. Gives the
        # card material depth that the radial wash alone couldn't
        # provide (the wash is a *spotlight*, the gradient is a
        # *surface*). Same depth idiom shipped on milestone banner
        # bodies, outro tiles, ÉQUILIBRE tiles, TENDANCE chips, and
        # pause-menu buttons.
        grad = pygame.Surface(rect.size, pygame.SRCALPHA)
        for gy in range(rect.height):
            tt = gy / max(1, rect.height - 1)
            shift = int(14 * (1.0 - 2 * tt))
            if shift > 0:
                pygame.draw.line(
                    grad, (255, 255, 255, min(255, shift * 3)),
                    (0, gy), (rect.width, gy),
                )
            elif shift < 0:
                pygame.draw.line(
                    grad, (0, 0, 0, min(255, -shift * 3)),
                    (0, gy), (rect.width, gy),
                )
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            mask, (255, 255, 255, 255),
            (0, 0, rect.width, rect.height), border_radius=14,
        )
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(grad, rect.topleft)
        pygame.draw.rect(surface, border, rect, border_w, border_radius=14)
        # Top-edge highlight + bottom-edge shadow strokes (1 px each,
        # inset 8 px to avoid the rounded corners). Same idiom used
        # on every elevated card in the codebase. Stronger lowlight
        # alpha than highlight matches the perceptual asymmetry
        # (the eye sees dark gradients more weakly than light ones).
        hl_layer = pygame.Surface(
            (rect.width - 16, 1), pygame.SRCALPHA,
        )
        hl_layer.fill((255, 255, 255, 55))
        surface.blit(hl_layer, (rect.left + 8, rect.top + 1))
        sh_layer = pygame.Surface(
            (rect.width - 16, 1), pygame.SRCALPHA,
        )
        sh_layer.fill((0, 0, 0, 80))
        surface.blit(sh_layer, (rect.left + 8, rect.bottom - 2))

        # Radial tint wash — draws on top of the gradient + edge
        # strokes so the side identity colour reads through the
        # surface depth rather than competing with it.
        wash = pygame.Surface(rect.size, pygame.SRCALPHA)
        max_r = int(min(rect.width, rect.height) * 0.55)
        wcx, wcy = rect.width // 2, int(rect.height * 0.38)
        for i in range(max_r, 0, -2):
            t = i / max_r
            a = int(55 * (1 - t) ** 1.6) if active else int(22 * (1 - t) ** 1.6)
            if a < 1:
                continue
            pygame.draw.circle(wash, (*tint, a), (wcx, wcy), i)
        surface.blit(wash, rect.topleft)

        # Big procedural glyph in a tinted disc.
        icon_r = min(rect.width, rect.height) // 4
        icx, icy = rect.centerx, rect.top + 30 + icon_r
        pygame.draw.circle(
            surface, _blend((10, 12, 18), tint, 0.45), (icx, icy), icon_r,
        )
        pygame.draw.circle(surface, tint, (icx, icy), icon_r, 3 if active else 2)
        self._draw_side_glyph(surface, glyph, (icx, icy), icon_r - 8, tint)

        # Label.
        name_color = self.palette.text if active else _blend(
            self.palette.text_label, tint, 0.25,
        )
        name = self.fonts.title.render(label, True, name_color)
        surface.blit(
            name, (rect.centerx - name.get_width() // 2, icy + icon_r + 12),
        )

        # Headline + sub. Side tint blended 35 % toward white when
        # active so both Gaia (warm coral, ≈6.6:1 raw on surface_overlay
        # — borderline AA) and Humanité (cyan, ≈12:1) read at a
        # consistent comfortable level (~10:1 / ~14:1 respectively).
        # Inactive cards keep the raw tint so the active state lifts
        # visibly when chosen.
        headline_color = (
            _blend(tint, (255, 255, 255), 0.35) if active else tint
        )
        hl = self.fonts.medium.render(headline, True, headline_color)
        surface.blit(
            hl, (rect.centerx - hl.get_width() // 2,
                 icy + icon_r + 12 + name.get_height() + 6),
        )
        sub_y = icy + icon_r + 12 + name.get_height() + 6 + hl.get_height() + 4
        for line in self._wrap_text(sub, self.fonts.small, rect.width - 28, max_lines=2):
            t = self.fonts.small.render(line, True, self.palette.text_label)
            surface.blit(
                t,
                (rect.centerx - t.get_width() // 2, sub_y),
            )
            sub_y += t.get_height() + 1

        if active:
            pygame.draw.circle(
                surface, tint, (rect.centerx, rect.bottom - 14), 4,
            )

    @staticmethod
    def _draw_side_glyph(
        surface: pygame.Surface,
        kind: str,
        center: tuple[int, int],
        r: int,
        color: tuple[int, int, int],
    ) -> None:
        """Procedural glyph for the side cards (wave for Planète, shield for Humanité)."""
        cx, cy = center
        thick = max(2, r // 4)
        if kind == "shield":
            pts = [
                (cx, cy - r),
                (cx + r, cy - r // 3),
                (cx + r * 3 // 5, cy + r),
                (cx, cy + r * 5 // 4),
                (cx - r * 3 // 5, cy + r),
                (cx - r, cy - r // 3),
            ]
            pygame.draw.polygon(surface, color, pts, thick)
            # Inner check mark.
            check = [
                (cx - r // 2, cy + r // 8),
                (cx - r // 8, cy + r // 2),
                (cx + r // 2, cy - r // 3),
            ]
            pygame.draw.lines(surface, color, False, check, thick)
        else:  # default: wave
            for i, y_off in enumerate((-r // 2, 0, r // 2)):
                span = r - i * 2
                y = cy + y_off
                pts = [
                    (cx - span, y),
                    (cx - span // 3, y - thick),
                    (cx + span // 3, y + thick),
                    (cx + span, y),
                ]
                pygame.draw.lines(surface, color, False, pts, thick)

    def _draw_picker_step_catastrophe(
        self,
        surface: pygame.Surface,
        game: Game,
        mouse_pos: tuple[int, int],
    ) -> None:
        cards = picker_pill_rects(self.config)
        active_cat = game.gaia.active.name
        for name, card_rect in cards["catastrophe"]:
            cat = next(
                (c for c in game.gaia.catastrophes if c.name == name), None
            )
            tint = cat.arc_color if cat else self.palette.ui_accent
            self._draw_catastrophe_card(
                surface, card_rect, name, tint,
                active=name == active_cat,
                hover=card_rect.collidepoint(mouse_pos),
                catastrophe=cat,
            )
        # Detail panel below the cards — tagline + spread stats + keywords
        # for the active catastrophe. Replaces all the per-card text.
        self._draw_catastrophe_detail(surface, game)

    def _draw_catastrophe_detail(
        self, surface: pygame.Surface, game: Game,
    ) -> None:
        """One focused detail panel for the active catastrophe.

        Sits below the card row. Renders the tagline (large), three stat bars
        side-by-side, and the keyword chips. Visual-first: lots of breathing
        space, no walls of label/value text inside the cards.
        """
        w, h = self.screen_size
        cat = game.gaia.active
        tint = cat.arc_color
        # Panel rect: full width minus margins, below the cards. Height 150
        # (was 130) so a 2-line wrapped tagline + 3 stat rows + the new
        # science-reference line all fit without overlap.
        cards_bottom = PICKER_CARDS_TOP + PICKER_CARD_H
        panel = pygame.Rect(40, cards_bottom + 24, w - 80, 150)
        # Backdrop with a tint stripe on the left.
        self._fill_panel(surface, panel, self.palette.surface)
        pygame.draw.line(
            surface, tint,
            (panel.left, panel.top),
            (panel.left, panel.bottom),
            3,
        )

        # Reserve the right column's width based on what the chips
        # actually need so the tagline column shrinks just enough to
        # avoid the right-anchored keywords stamping over the second
        # tagline line. Previously the right column was a hard-coded
        # 280 px allocation while keywords rendered at medium font
        # were 272–391 px wide for Feu/Terre/Air/Vie — the chips
        # extended into the tagline column and overlapped wrapped
        # second lines. Switching to small font for the keyword strip
        # (max 320 for "CYCLONES · COURANTS-JETS · SUBMERSIONS") plus
        # a content-driven right column makes the layout adapt instead
        # of clashing.
        chips_text = self.fonts.label.render(
            "VOUS DÉCOUVRIREZ", True, self.palette.text_label,
        )
        keywords = CATASTROPHE_LEARN.get(cat.name, "")
        keyword_font = self.fonts.small
        keyword_color = _blend(tint, (255, 255, 255), 0.35)
        chip_render = (
            keyword_font.render(keywords, True, keyword_color)
            if keywords else None
        )
        right_col_w = max(
            chips_text.get_width(),
            chip_render.get_width() if chip_render else 0,
        ) + 36  # 22 right pad + 14 gap from tagline column
        # Tagline as the hero text in the panel — auto-wrap so longer
        # educational copy ("Sécheresse et fumées étouffent les villes…")
        # doesn't overflow the panel width.
        tagline = CATASTROPHE_TAGLINES.get(cat.name, "")
        tag_y = panel.top + 14
        tag_inner_w = panel.width - 22 - right_col_w
        if tagline:
            for line in self._wrap_text(
                tagline, self.fonts.medium, tag_inner_w, max_lines=2,
            ):
                tag = self.fonts.medium.render(line, True, self.palette.text)
                surface.blit(tag, (panel.left + 22, tag_y))
                tag_y += tag.get_height() + 1

        # Stats: three short bars below the tagline. Bar row pushed to
        # panel.top + 60 (was 56) so the second tagline line never bleeds
        # into the first stat row.
        stats = self._catastrophe_bar_stats(cat)
        bar_x = panel.left + 22
        bar_y = panel.top + 60
        bar_w = 142
        label_col_w = 90
        for i, (lbl, value) in enumerate(stats):
            row_y = bar_y + i * 16
            lbl_t = self.fonts.label.render(
                lbl, True, self.palette.text_label,
            )
            surface.blit(lbl_t, (bar_x, row_y))
            track = pygame.Rect(bar_x + label_col_w, row_y + 3, bar_w, 8)
            pygame.draw.rect(
                surface, self.palette.surface_overlay[:3], track,
                border_radius=4,
            )
            fill_w = int(track.width * max(0.0, min(1.0, value)))
            pygame.draw.rect(
                surface, tint,
                (track.x, track.y, fill_w, track.height),
                border_radius=4,
            )

        # Science reference — one anchor fact citing GIEC/OMM/OMS/USGS
        # so the picker doubles as a quick briefing screen. Wraps so the
        # longer references (USGS, OMM cyclone) don't overflow.
        reference = CATASTROPHE_REFERENCES.get(cat.name, "")
        if reference:
            ref_y = panel.bottom - 30
            for line in self._wrap_text(
                reference, self.fonts.small, panel.width - 44, max_lines=1,
            ):
                # Was text_dim (188, 198, 216 ≈ 9.4:1 on surface) — fine
                # in principle but visually flat against the tinted
                # detail panel. text_label (210, 222, 240 ≈ 12.3:1)
                # gives the science citation enough lift to register
                # as informational content, not background filler.
                ref_t = self.fonts.small.render(
                    line, True, self.palette.text_label,
                )
                surface.blit(ref_t, (panel.left + 22, ref_y))
                ref_y += ref_t.get_height() + 1

        # Keyword chips on the right — what the player will encounter.
        # Rendered above as part of the layout reservation; here we
        # just blit them right-anchored. Switched to ``small`` so the
        # tagline column is no longer overrun on Air/Terre/Feu.
        if keywords and chip_render is not None:
            surface.blit(
                chips_text,
                (panel.right - 22 - chips_text.get_width(), panel.top + 14),
            )
            surface.blit(
                chip_render,
                (panel.right - 22 - chip_render.get_width(),
                 panel.top + 14 + chips_text.get_height() + 8),
            )

    def _draw_picker_step_difficulty(
        self,
        surface: pygame.Surface,
        game: Game,
        mouse_pos: tuple[int, int],
    ) -> None:
        # Compact catastrophe chip at top, then the 3 visual hero cards, then
        # a focused detail panel below — mirrors the catastrophe step.
        w, h = self.screen_size
        cat = game.gaia.active
        cat_color = cat.arc_color
        banner_w = 220
        banner = pygame.Rect((w - banner_w) // 2, 120, banner_w, 36)
        pygame.draw.rect(
            surface, self.palette.surface_deep[:3], banner,
            border_radius=banner.height // 2,
        )
        pygame.draw.rect(
            surface, _blend(self.palette.surface_deep, cat_color, 0.55),
            banner, 1, border_radius=banner.height // 2,
        )
        badge_r = 12
        badge_cx = banner.left + 18 + badge_r
        pygame.draw.circle(
            surface, _blend((10, 12, 18), cat_color, 0.4),
            (badge_cx, banner.centery), badge_r,
        )
        pygame.draw.circle(
            surface, cat_color, (badge_cx, banner.centery), badge_r, 2,
        )
        self._draw_element_icon(
            surface, cat.name, (badge_cx, banner.centery), badge_r - 3, cat_color,
        )
        name = self.fonts.medium.render(cat.name.upper(), True, self.palette.text)
        surface.blit(
            name,
            (badge_cx + badge_r + 10,
             banner.centery - name.get_height() // 2),
        )
        # Difficulty cards positioned just under the catastrophe chip.
        cards = picker_pill_rects(self.config)
        active_diff = game.difficulty.label
        diff_tints = {
            "FACILE": (110, 210, 140),
            "NORMAL": (230, 180, 90),
            "BRUTAL": self.palette.severe,
        }
        diff_y = 180
        for label, card_rect in cards["difficulty"]:
            shifted = card_rect.copy()
            shifted.y = diff_y
            self._draw_difficulty_card(
                surface, shifted, label,
                diff_tints.get(label, self.palette.ui_accent),
                active=label == active_diff,
                hover=shifted.collidepoint(mouse_pos),
            )
        # Detail panel below the cards — bullets for the active difficulty.
        self._draw_difficulty_detail(surface, game, diff_tints)

    def _draw_difficulty_detail(
        self,
        surface: pygame.Surface,
        game: Game,
        tints: dict[str, tuple[int, int, int]],
    ) -> None:
        """Focused detail for the active difficulty — bullet points + impact."""
        w, h = self.screen_size
        label = game.difficulty.label
        tint = tints.get(label, self.palette.ui_accent)
        cards_bottom = 180 + PICKER_DIFF_CARD_H
        panel = pygame.Rect(40, cards_bottom + 18, w - 80, 92)
        self._fill_panel(surface, panel, self.palette.surface)
        pygame.draw.line(
            surface, tint,
            (panel.left, panel.top),
            (panel.left, panel.bottom),
            3,
        )
        # 3 bullets: two side-agnostic scenario descriptors + a side-aware
        # hint about who the difficulty favours, so the player understands
        # whether FACILE/BRUTAL is "easy" for them in particular.
        bullets = list(DIFFICULTY_BULLETS.get(label, ()))
        side = getattr(game, "player_side", "gaia")
        hint = _difficulty_player_hint(label, side)
        if bullets and len(bullets) >= 3:
            bullets[2] = hint
        elif hint:
            bullets.append(hint)
        y = panel.top + 16
        for bullet in bullets:
            if not bullet:
                continue
            # Side-hint bullets start with "⚠ " or "✓ ". Merge that glyph
            # into the bullet marker so the bullet itself carries its
            # severity — instead of "● ⚠ text" (two markers fighting)
            # we get "⚠ text" or "✓ text" with the glyph in the marker
            # slot. Glyph colour also distinguishes "good for you" from
            # "bad for you" at a glance.
            stripped = bullet
            marker_glyph: str | None = None
            marker_color = tint
            if bullet.startswith("⚠ "):
                marker_glyph = "⚠"
                marker_color = SOFT_WARNING  # amber — warning
                stripped = bullet[2:]
            elif bullet.startswith("✓ "):
                marker_glyph = "✓"
                # Same sage as the country tooltip's "Sain" pip, the
                # outro population row, and the side-info chip — was a
                # near-twin literal ``(115, 200, 130)`` 15 units off on
                # G channel. Routing through SOFT_SUCCESS keeps the
                # picker bullet's "good for you" tone in lockstep with
                # the rest of the soft-status family.
                marker_color = SOFT_SUCCESS
                stripped = bullet[2:]

            if marker_glyph is not None:
                # Procedural marker — Inter doesn't reliably ship the
                # ⚠ (U+26A0) and ✓ (U+2713) glyphs across all install
                # weights, so rendering them via the font dropped a
                # tofu box on the picker difficulty bullets at runtime.
                # Drawing the shapes ourselves makes the markers font-
                # independent and lets us match each one's severity
                # colour exactly (no font-renderer alpha-blending
                # mismatch on coloured glyphs either).
                marker_cx = panel.left + 26
                marker_cy = y + self.fonts.medium.get_height() // 2
                if marker_glyph == "⚠":
                    # Filled amber triangle — universal hazard sign.
                    r = 6
                    pygame.draw.polygon(
                        surface, marker_color,
                        [
                            (marker_cx, marker_cy - r),
                            (marker_cx + r, marker_cy + r - 1),
                            (marker_cx - r, marker_cy + r - 1),
                        ],
                    )
                else:  # "✓" — filled sage disc + white check stroke
                    pygame.draw.circle(
                        surface, marker_color, (marker_cx, marker_cy), 6,
                    )
                    check_pts = [
                        (marker_cx - 3, marker_cy),
                        (marker_cx - 1, marker_cy + 2),
                        (marker_cx + 3, marker_cy - 2),
                    ]
                    pygame.draw.lines(
                        surface, (255, 255, 255), False, check_pts, 2,
                    )
            else:
                pygame.draw.circle(
                    surface, tint,
                    (panel.left + 26, y + self.fonts.medium.get_height() // 2),
                    3,
                )
            line = self.fonts.medium.render(
                self._fit_text(stripped, self.fonts.medium, panel.width - 60),
                True, self.palette.text,
            )
            surface.blit(line, (panel.left + 40, y))
            y += line.get_height() + 4

    def _draw_picker_step_origin(
        self,
        surface: pygame.Surface,
        game: Game,
        mouse_pos: tuple[int, int],
    ) -> None:
        # Map is already drawn underneath at low dim. Add pending-country
        # marker if one is selected.
        cat_color = game.gaia.active.arc_color
        if game.pending_country:
            country = game.world.countries.get(game.pending_country)
            if country is not None:
                cx, cy = game.world.transform_point(
                    country.centroid, self.screen_size,
                )
                self._draw_pending_marker(
                    surface, int(cx), int(cy), cat_color,
                    name=country.name,
                )

    def _draw_picker_nav(
        self,
        surface: pygame.Surface,
        game: Game,
        mouse_pos: tuple[int, int],
    ) -> None:
        w, h = self.screen_size
        step = max(-1, min(2, game.picker_step))
        rects = picker_nav_button_rects(self.config)
        cat_color = game.gaia.active.arc_color
        # PRÉCÉDENT button (visible from step 0 onward — step -1 is the
        # first screen so back goes to title; we don't expose that here).
        if step > -1:
            self._draw_chunky_button(
                surface, rects["prev"],
                label="PRÉCÉDENT",
                primary=False,
                hover=rects["prev"].collidepoint(mouse_pos),
                font=self.fonts.large,
            )
        if step < 2:
            self._draw_chunky_button(
                surface, rects["next"],
                label="SUIVANT",
                primary=True,
                hover=rects["next"].collidepoint(mouse_pos),
                font=self.fonts.large,
            )
        else:
            # Final step — LANCER button. Label is constant so the
            # button shape never changes; the *colour* changes once a
            # country is picked (greyed → catastrophe-tinted) and the
            # chosen country's name surfaces near its map marker
            # instead of being crammed into the button.
            has_country = bool(game.pending_country)
            self._draw_chunky_button(
                surface, rects["next"],
                label="LANCER",
                primary=has_country,
                hover=has_country and rects["next"].collidepoint(mouse_pos),
                font=self.fonts.large,
                tint=cat_color if has_country else None,
            )

    def _draw_pending_marker(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        color: tuple[int, int, int],
        *,
        name: str | None = None,
    ) -> None:
        """Pulsing reticle on the pending patient-zero country.

        Reads as a target-lock: four short cardinal crosshair segments
        + a static inner ring + the existing pulsing outer rings + a
        solid core. The previous design was just two pulsing rings and
        a dot — felt like a passive radar ping, not "I have chosen
        this country as my first foyer".

        ``name`` paints a small caption pill next to the reticle so
        the player sees *which* country is locked without having to
        scan the LANCER button text. Auto-flips above/below the
        reticle when too close to the screen edge.
        """
        ticks = pygame.time.get_ticks()
        pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
        outer_r = int(18 + 6 * pulse)
        # Outer pulse rings (radar-style life).
        for ring_r, alpha in ((outer_r, 80), (outer_r + 8, 40)):
            ring = pygame.Surface((ring_r * 2 + 4, ring_r * 2 + 4), pygame.SRCALPHA)
            pygame.draw.circle(
                ring, (*color, alpha),
                (ring_r + 2, ring_r + 2), ring_r, 2,
            )
            surface.blit(ring, (cx - ring_r - 2, cy - ring_r - 2))
        # Static inner ring — gives the eye a fixed reference between
        # the pulses so the marker feels anchored.
        pygame.draw.circle(surface, color, (cx, cy), 11, 1)
        # Cardinal crosshair segments — short lines reaching from the
        # static ring to a few pixels short of the core. Reads as
        # "this is the locked target".
        crosshair_outer = 14
        crosshair_inner = 7
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            pygame.draw.line(
                surface, color,
                (cx + dx * crosshair_inner, cy + dy * crosshair_inner),
                (cx + dx * crosshair_outer, cy + dy * crosshair_outer),
                2,
            )
        # Solid core: catastrophe disc + white centre pip.
        pygame.draw.circle(surface, color, (cx, cy), 5)
        pygame.draw.circle(surface, (255, 255, 255), (cx, cy), 2)

        if name:
            self._draw_pending_marker_label(surface, cx, cy, name, color)

    def _draw_pending_marker_label(
        self,
        surface: pygame.Surface,
        cx: int,
        cy: int,
        name: str,
        color: tuple[int, int, int],
    ) -> None:
        """Small caption pill anchored to the pending-country reticle.

        Auto-flips above/below depending on which side has room, with
        a small horizontal nudge if the pill would cross a screen edge.
        Shadowed rounded-rect bg + catastrophe-tinted left stripe + the
        country name in white. Total height ≈ 26 px so it never crowds
        the reticle (outer pulse can reach r ≈ 32).
        """
        font = self.fonts.medium
        text_surf = font.render(name.upper(), True, (250, 252, 255))
        pad_x, pad_y = 12, 6
        stripe_w = 4
        pill_w = text_surf.get_width() + pad_x * 2 + stripe_w + 4
        pill_h = text_surf.get_height() + pad_y * 2
        gap = 36  # clears the outer pulse ring (max ≈ 32 px)

        screen_w, screen_h = self.screen_size
        # Prefer above; flip below if too close to the top edge.
        place_above = cy - gap - pill_h >= 6
        if place_above:
            pill_y = cy - gap - pill_h
        else:
            pill_y = cy + gap
        pill_x = cx - pill_w // 2
        # Keep pill on-screen horizontally.
        pill_x = max(6, min(screen_w - pill_w - 6, pill_x))

        pill_rect = pygame.Rect(pill_x, pill_y, pill_w, pill_h)
        # Drop shadow for legibility over busy map tiles.
        shadow = pygame.Surface(
            (pill_w + 8, pill_h + 8), pygame.SRCALPHA,
        )
        pygame.draw.rect(
            shadow, (0, 0, 0, 130),
            (4, 4, pill_w, pill_h), border_radius=10,
        )
        surface.blit(shadow, (pill_x - 4, pill_y - 4))
        # Pill body: dark surface with catastrophe-tinted border.
        body = pygame.Surface((pill_w, pill_h), pygame.SRCALPHA)
        pygame.draw.rect(
            body, (*_blend((12, 14, 22), color, 0.18), 245),
            (0, 0, pill_w, pill_h), border_radius=10,
        )
        pygame.draw.rect(
            body, (*_blend(color, (255, 255, 255), 0.20), 255),
            (0, 0, pill_w, pill_h), 1, border_radius=10,
        )
        # Catastrophe-tinted stripe on the left edge as a tiny banner-flag.
        pygame.draw.rect(
            body, color,
            (5, 5, stripe_w, pill_h - 10), border_radius=2,
        )
        surface.blit(body, (pill_x, pill_y))
        surface.blit(
            text_surf,
            (pill_x + stripe_w + 4 + pad_x,
             pill_y + (pill_h - text_surf.get_height()) // 2),
        )

    def _draw_catastrophe_card(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        name: str,
        tint: tuple[int, int, int],
        *,
        active: bool,
        hover: bool,
        catastrophe: "Catastrophe | None",
    ) -> None:
        """Hero-style card: BIG element icon + name only.

        All textual details (tagline / stats / keywords) live in the detail
        panel below the row so the cards themselves stay clean, scannable,
        and visual-first. The active card lifts and glows; hover gets a soft
        tint without committing.
        """
        # Soft drop shadow.
        shadow = rect.copy()
        shadow.y += 4
        self._draw_shadow(surface, rect, blur=14, alpha=160 if active else 100)

        # Pulsing outer glow ring on the active card — makes the
        # "you have selected this" affordance instantly visible across
        # the whole row instead of relying on the 2 px border alone,
        # which can blend into the catastrophe-tint background on the
        # darker elements (Eau, Terre).
        if active:
            ticks = pygame.time.get_ticks()
            pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
            glow_alpha = int(80 + 70 * pulse)
            glow_pad = 8
            glow = pygame.Surface(
                (rect.width + glow_pad * 2, rect.height + glow_pad * 2),
                pygame.SRCALPHA,
            )
            pygame.draw.rect(
                glow, (*tint, glow_alpha),
                (0, 0, rect.width + glow_pad * 2, rect.height + glow_pad * 2),
                3, border_radius=14 + glow_pad,
            )
            surface.blit(glow, (rect.left - glow_pad, rect.top - glow_pad))

        # Card body — active gets a brighter inner surface + a thicker
        # tint border (was 2 → 3) so the focused state pops without
        # needing to change the disc/wash layering inside.
        if active:
            fill = self.palette.surface_overlay[:3]
            border = tint
            border_w = 3
        else:
            fill = (
                self.palette.surface_elevated[:3]
                if hover else self.palette.surface_deep[:3]
            )
            border = _blend(
                self.palette.surface_deep, tint, 0.5 if hover else 0.2,
            )
            border_w = 1
        pygame.draw.rect(surface, fill, rect, border_radius=14)
        # Vertical gradient overlay — top +14 / bottom −14 luminance,
        # clipped to the rounded corners via a BLEND_RGBA_MULT mask
        # so the gradient respects the 14-px radius. Same depth idiom
        # shipped on the CÔTÉ side cards, milestone banners, outro
        # tiles, and ÉQUILIBRE tiles. Reads as "card is a material
        # surface" rather than "card is a coloured shape with a
        # spotlight on it" (which is what the radial wash alone
        # communicates).
        grad = pygame.Surface(rect.size, pygame.SRCALPHA)
        for gy in range(rect.height):
            tt = gy / max(1, rect.height - 1)
            shift = int(14 * (1.0 - 2 * tt))
            if shift > 0:
                pygame.draw.line(
                    grad, (255, 255, 255, min(255, shift * 3)),
                    (0, gy), (rect.width, gy),
                )
            elif shift < 0:
                pygame.draw.line(
                    grad, (0, 0, 0, min(255, -shift * 3)),
                    (0, gy), (rect.width, gy),
                )
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            mask, (255, 255, 255, 255),
            (0, 0, rect.width, rect.height), border_radius=14,
        )
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(grad, rect.topleft)
        pygame.draw.rect(surface, border, rect, border_w, border_radius=14)
        # Top-edge highlight + bottom-edge shadow strokes (1 px each,
        # inset 8 px to avoid the rounded corners). Asymmetric alphas
        # (highlight 55 / shadow 80) match the perceptual asymmetry —
        # the eye reads dark gradients more weakly than light ones at
        # the same numerical alpha, so the shadow needs to be ~50 %
        # higher α to balance visually with the highlight.
        hl_layer = pygame.Surface(
            (rect.width - 16, 1), pygame.SRCALPHA,
        )
        hl_layer.fill((255, 255, 255, 55))
        surface.blit(hl_layer, (rect.left + 8, rect.top + 1))
        sh_layer = pygame.Surface(
            (rect.width - 16, 1), pygame.SRCALPHA,
        )
        sh_layer.fill((0, 0, 0, 80))
        surface.blit(sh_layer, (rect.left + 8, rect.bottom - 2))

        # Catastrophe-tint radial wash inside the card so each one feels
        # distinct from a distance. Drawn AFTER the gradient + edge
        # strokes so the catastrophe identity reads *through* the
        # surface depth — wash = identity, gradient = material, both
        # belong, neither competes.
        wash = pygame.Surface(rect.size, pygame.SRCALPHA)
        wash_cx = rect.width // 2
        wash_cy = int(rect.height * 0.42)
        max_r = int(min(rect.width, rect.height) * 0.55)
        wash_alpha_base = 50 if active else 22
        for i in range(max_r, 0, -2):
            t = i / max_r
            a = int(wash_alpha_base * (1 - t) ** 1.6)
            if a < 1:
                continue
            pygame.draw.circle(wash, (*tint, a), (wash_cx, wash_cy), i)
        surface.blit(wash, rect.topleft)

        # BIG element icon — the hero of the card.
        icon_r = min(rect.width, rect.height) // 4
        icon_cx = rect.centerx
        icon_cy = rect.top + 24 + icon_r
        # Outer ring + inner disc give the element its identity badge.
        pygame.draw.circle(
            surface, _blend((10, 12, 18), tint, 0.45),
            (icon_cx, icon_cy), icon_r,
        )
        pygame.draw.circle(
            surface, tint, (icon_cx, icon_cy), icon_r, 3 if active else 2,
        )
        self._draw_element_icon(
            surface, name, (icon_cx, icon_cy), icon_r - 8, tint,
        )

        # Name — large, centered below the icon.
        name_color = self.palette.text if active else _blend(
            self.palette.text_label, tint, 0.25,
        )
        name_text = self.fonts.title.render(name.upper(), True, name_color)
        surface.blit(
            name_text,
            (rect.centerx - name_text.get_width() // 2,
             icon_cy + icon_r + 12),
        )

        # Active selector — small dot just under the name confirms the choice.
        if active:
            pygame.draw.circle(
                surface, tint,
                (rect.centerx, rect.bottom - 18),
                4,
            )

    def _catastrophe_bar_stats(
        self, catastrophe: "Catastrophe",
    ) -> list[tuple[str, float]]:
        """Three normalized stat values for the briefing card's micro-bars."""
        # References tuned so existing 5 catastrophes span ~0.2..1.0.
        speed = min(1.0, catastrophe.spread_neighbors / 6.0 + (1.0 if catastrophe.jump_chance > 0 else 0.0) * 0.15)
        ranged = min(1.0, catastrophe.spread_distance_half / 50.0)
        intensity = min(1.0, catastrophe.base_impact / 0.025)
        return [
            ("VITESSE", speed),
            ("PORTÉE", ranged),
            # Was "INTENS." — full word matches the radar chart below
            # and the dashboard column, removing the lone abbreviation.
            ("INTENSITÉ", intensity),
        ]

    def _catastrophe_radar_axes(
        self, catastrophe: "Catastrophe",
    ) -> list[tuple[str, float]]:
        """Four normalized axes for the active-card radar chart.

        Adds SAUTS (jump_chance) on top of the 3 micro-bar stats so the radar
        differentiates Air/Vie (high jumps) from Eau/Feu/Terre.
        """
        bars = self._catastrophe_bar_stats(catastrophe)
        jumps = min(1.0, catastrophe.jump_chance / 0.10)
        return [
            ("VITESSE", bars[0][1]),
            ("PORTÉE", bars[1][1]),
            ("INTENSITÉ", bars[2][1]),
            ("SAUTS", jumps),
        ]

    def _draw_radar_chart(
        self,
        surface: pygame.Surface,
        center: tuple[int, int],
        radius: int,
        axes: list[tuple[str, float]],
        tint: tuple[int, int, int],
    ) -> None:
        """Pygame radar chart: N-axis polygon with a value polygon overlaid.

        Backgrounds use 3 concentric rings at 33/66/100% so the value polygon
        reads against a calibrated grid. The polygon itself is filled with a
        translucent fill + sharp tint outline, matching the standard RPG-stat
        radar pattern from Code Monkey / Terresquall.
        """
        n = len(axes)
        if n < 3:
            return
        cx, cy = center
        # Pre-compute the angle for each axis (top-aligned, clockwise).
        angles = [-math.pi / 2 + (2 * math.pi * i / n) for i in range(n)]

        # Concentric rings for visual calibration.
        for ring in (0.33, 0.66, 1.0):
            ring_pts = [
                (
                    cx + math.cos(a) * radius * ring,
                    cy + math.sin(a) * radius * ring,
                )
                for a in angles
            ]
            pygame.draw.polygon(
                surface, _blend(self.palette.surface_deep, tint, 0.18),
                ring_pts, 1,
            )

        # Spokes from center to each axis tip.
        for a in angles:
            tip = (cx + math.cos(a) * radius, cy + math.sin(a) * radius)
            pygame.draw.line(
                surface, _blend(self.palette.surface_deep, tint, 0.30),
                (cx, cy), tip, 1,
            )

        # Value polygon (translucent fill + opaque outline).
        value_pts = [
            (
                cx + math.cos(a) * radius * max(0.0, min(1.0, v)),
                cy + math.sin(a) * radius * max(0.0, min(1.0, v)),
            )
            for a, (_, v) in zip(angles, axes)
        ]
        if len(value_pts) >= 3:
            fill_surf = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
            offset_pts = [
                (int(p[0] - cx + radius + 2), int(p[1] - cy + radius + 2))
                for p in value_pts
            ]
            pygame.draw.polygon(fill_surf, (*tint, 90), offset_pts)
            surface.blit(fill_surf, (cx - radius - 2, cy - radius - 2))
            pygame.draw.polygon(surface, tint, value_pts, 2)
            for pt in value_pts:
                pygame.draw.circle(surface, tint, (int(pt[0]), int(pt[1])), 3)

        # Axis labels.
        for a, (label, _) in zip(angles, axes):
            tx = cx + math.cos(a) * (radius + 14)
            ty = cy + math.sin(a) * (radius + 14)
            text = self.fonts.label.render(label, True, self.palette.text_label)
            surface.blit(
                text,
                (int(tx - text.get_width() / 2),
                 int(ty - text.get_height() / 2)),
            )

    def _draw_outro_tab(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        *,
        active: bool,
        accent: tuple[int, int, int],
        hover: bool,
    ) -> None:
        """Pill tab at the top of the outro recap with screen-surface depth.

        Same idiom as the info-panel tabs: active reads as *pressed-in
        lit pill* (gradient + top highlight + bottom shadow), inactive
        reads as *raised but dim* (top highlight only). Was flat
        coloured pills where the only thing distinguishing active from
        inactive was the fill colour.
        """
        radius = rect.height // 2
        if active:
            color = _blend(accent, (0, 0, 0), 0.35)
            pygame.draw.rect(surface, color, rect, border_radius=radius)
            # Vertical gradient (top +8, bottom −8) clipped to the pill.
            prev_clip = surface.get_clip()
            surface.set_clip(rect)
            grad = pygame.Surface(rect.size, pygame.SRCALPHA)
            for gy in range(rect.height):
                t = gy / max(1, rect.height - 1)
                shift = int(8 * (1.0 - 2 * t))
                if shift > 0:
                    pygame.draw.line(
                        grad, (255, 255, 255, min(255, shift * 4)),
                        (0, gy), (rect.width, gy),
                    )
                elif shift < 0:
                    pygame.draw.line(
                        grad, (0, 0, 0, min(255, -shift * 4)),
                        (0, gy), (rect.width, gy),
                    )
            surface.blit(grad, rect.topleft)
            surface.set_clip(prev_clip)
            # Top highlight + bottom shadow strokes, inset 4 px so they
            # don't crash the rounded pill ends.
            pygame.draw.line(
                surface,
                _blend(color, (255, 255, 255), 0.30),
                (rect.left + 4, rect.top + 1),
                (rect.right - 4, rect.top + 1),
                1,
            )
            pygame.draw.line(
                surface,
                _blend(color, (0, 0, 0), 0.45),
                (rect.left + 4, rect.bottom - 2),
                (rect.right - 4, rect.bottom - 2),
                1,
            )
            text_color = (255, 255, 255)
        else:
            bg = (
                self.palette.surface_overlay[:3]
                if hover else self.palette.surface[:3]
            )
            pygame.draw.rect(surface, bg, rect, border_radius=radius)
            # Inactive — top highlight only (raised pill feel).
            pygame.draw.line(
                surface,
                _blend(bg, (255, 255, 255), 0.20),
                (rect.left + 4, rect.top + 1),
                (rect.right - 4, rect.top + 1),
                1,
            )
            pygame.draw.rect(
                surface,
                _blend(self.palette.surface_deep, accent, 0.4),
                rect, 1, border_radius=radius,
            )
            text_color = self.palette.text_label
        text = self.fonts.label.render(label, True, text_color)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2,
             rect.centery - text.get_height() // 2),
        )

    def _draw_difficulty_card(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        tint: tuple[int, int, int],
        *,
        active: bool,
        hover: bool,
    ) -> None:
        """Hero-style difficulty card — pip count icon + label only.

        FACILE = 1 pip, NORMAL = 2 pips, BRUTAL = 3 pips. All bullets and
        descriptive copy live in the detail panel below the card row so the
        cards themselves stay clean and visual-first.
        """
        self._draw_shadow(surface, rect, blur=14, alpha=140 if active else 90)
        # Same focus-glow idiom as the catastrophe + side cards so the
        # selected difficulty reads instantly across the row.
        if active:
            ticks = pygame.time.get_ticks()
            pulse = 0.5 + 0.5 * math.sin(ticks * 0.005)
            glow_alpha = int(80 + 70 * pulse)
            glow_pad = 8
            glow = pygame.Surface(
                (rect.width + glow_pad * 2, rect.height + glow_pad * 2),
                pygame.SRCALPHA,
            )
            pygame.draw.rect(
                glow, (*tint, glow_alpha),
                (0, 0, rect.width + glow_pad * 2, rect.height + glow_pad * 2),
                3, border_radius=14 + glow_pad,
            )
            surface.blit(glow, (rect.left - glow_pad, rect.top - glow_pad))
        if active:
            fill = self.palette.surface_overlay[:3]
            border = tint
            border_w = 3
        else:
            fill = (
                self.palette.surface_elevated[:3]
                if hover else self.palette.surface_deep[:3]
            )
            border = _blend(
                self.palette.surface_deep, tint, 0.5 if hover else 0.2,
            )
            border_w = 1
        pygame.draw.rect(surface, fill, rect, border_radius=14)
        # Vertical gradient overlay — top +14 / bottom −14 luminance,
        # clipped to the rounded corners via a BLEND_RGBA_MULT mask.
        # Same depth idiom shipped on the CÔTÉ side cards and
        # CATASTROPHE picker cards in earlier picker steps, plus
        # milestone banners and outro tiles elsewhere. Together with
        # the radial wash below, the card carries both *material*
        # (gradient = surface depth) and *identity* (wash = tier
        # tint) without the two competing.
        grad = pygame.Surface(rect.size, pygame.SRCALPHA)
        for gy in range(rect.height):
            tt = gy / max(1, rect.height - 1)
            shift = int(14 * (1.0 - 2 * tt))
            if shift > 0:
                pygame.draw.line(
                    grad, (255, 255, 255, min(255, shift * 3)),
                    (0, gy), (rect.width, gy),
                )
            elif shift < 0:
                pygame.draw.line(
                    grad, (0, 0, 0, min(255, -shift * 3)),
                    (0, gy), (rect.width, gy),
                )
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            mask, (255, 255, 255, 255),
            (0, 0, rect.width, rect.height), border_radius=14,
        )
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        surface.blit(grad, rect.topleft)
        pygame.draw.rect(surface, border, rect, border_w, border_radius=14)
        # Top-edge highlight + bottom-edge shadow strokes (1 px each,
        # inset 8 px to avoid the rounded corners). Asymmetric alphas
        # (55 / 80) match the perceptual asymmetry — the eye reads
        # dark gradients more weakly than light ones at the same
        # numerical alpha, so the shadow needs ~50 % higher α to
        # balance visually with the highlight.
        hl_layer = pygame.Surface(
            (rect.width - 16, 1), pygame.SRCALPHA,
        )
        hl_layer.fill((255, 255, 255, 55))
        surface.blit(hl_layer, (rect.left + 8, rect.top + 1))
        sh_layer = pygame.Surface(
            (rect.width - 16, 1), pygame.SRCALPHA,
        )
        sh_layer.fill((0, 0, 0, 80))
        surface.blit(sh_layer, (rect.left + 8, rect.bottom - 2))

        # Soft radial wash in the tint so each tier feels distinct.
        # Drawn AFTER the gradient + edge strokes so the difficulty
        # tier identity reads *through* the surface depth.
        wash = pygame.Surface(rect.size, pygame.SRCALPHA)
        wcx, wcy = rect.width // 2, int(rect.height * 0.4)
        wash_alpha_base = 45 if active else 18
        max_r = int(min(rect.width, rect.height) * 0.55)
        for i in range(max_r, 0, -2):
            t = i / max_r
            a = int(wash_alpha_base * (1 - t) ** 1.6)
            if a < 1:
                continue
            pygame.draw.circle(wash, (*tint, a), (wcx, wcy), i)
        surface.blit(wash, rect.topleft)

        # Hero icon: 1/2/3 stacked pips inside a tinted shield-style disc.
        pip_count = {"FACILE": 1, "NORMAL": 2, "BRUTAL": 3}.get(label, 2)
        icon_r = min(rect.width, rect.height) // 4
        icon_cx = rect.centerx
        icon_cy = rect.top + 22 + icon_r
        pygame.draw.circle(
            surface, _blend((10, 12, 18), tint, 0.45),
            (icon_cx, icon_cy), icon_r,
        )
        pygame.draw.circle(
            surface, tint, (icon_cx, icon_cy), icon_r, 3 if active else 2,
        )
        # Pips arranged vertically inside the disc.
        pip_r = max(3, icon_r // 7)
        pip_spacing = pip_r * 3
        total_h = (pip_count - 1) * pip_spacing
        for i in range(pip_count):
            py = icon_cy - total_h // 2 + i * pip_spacing
            pygame.draw.circle(surface, tint, (icon_cx, py), pip_r)

        # Label below the icon.
        name_color = self.palette.text if active else _blend(
            self.palette.text_label, tint, 0.25,
        )
        label_text = self.fonts.title.render(label, True, name_color)
        surface.blit(
            label_text,
            (rect.centerx - label_text.get_width() // 2,
             icon_cy + icon_r + 14),
        )

        if active:
            pygame.draw.circle(
                surface, tint,
                (rect.centerx, rect.bottom - 16),
                4,
            )

    # -------------------------------------------------------- game over

    def _draw_game_over(self, surface: pygame.Surface, game: Game) -> None:
        w, h = self.screen_size

        # Vertical gradient backdrop tinted by *player* outcome — gradient
        # follows the player's side, not the raw is_victory flag.
        is_victory = game.outcome.value == "victory"
        side = getattr(game, "player_side", "gaia")
        is_player_win = (is_victory and side != "gaia") or (not is_victory and side == "gaia")
        if is_player_win:
            top = (24, 50, 38, 240)
            bottom = (10, 18, 14, 250)
        else:
            top = (52, 18, 22, 240)
            bottom = (16, 8, 10, 250)
        bg = self._gradient_surface(w, h, top, bottom)
        surface.blit(bg, (0, 0))

        outcome_tint = (90, 220, 140) if is_player_win else (220, 90, 90)

        # ---- Cinematic intro (first ~1.2s after entering OUTRO).
        elapsed_ms = pygame.time.get_ticks() - self._phase_transition_start_ms
        intro_duration_ms = 1200
        intro_t = min(1.0, max(0.0, elapsed_ms / intro_duration_ms)) if not game.reduce_motion else 1.0
        # Expanding shockwave ring from screen centre during intro.
        if intro_t < 1.0:
            ring_r = int(intro_t * max(w, h) * 0.6)
            ring_alpha = int(180 * (1.0 - intro_t))
            if ring_alpha > 4:
                ring_layer = pygame.Surface(
                    (ring_r * 2 + 6, ring_r * 2 + 6), pygame.SRCALPHA,
                )
                pygame.draw.circle(
                    ring_layer, (*outcome_tint, ring_alpha),
                    (ring_r + 3, ring_r + 3), ring_r, 3,
                )
                surface.blit(
                    ring_layer,
                    (w // 2 - ring_r - 3, h // 2 - ring_r - 3),
                )

        # Ambient particles: reuse the title-screen field but tinted by outcome.
        # Same trapezoidal brightness envelope as the title screen so
        # newborn particles don't pop in at full strength — kept at
        # 0.7× peak so the outro's heavier overlay panels stay the
        # focal point.
        self._update_title_particles(w, h)
        for p in self._title_particles:
            age = 1.0 - p["lifetime"] / max(1, p["max_lifetime"])
            if age < 0.15:
                env = age / 0.15
            elif age > 0.70:
                env = max(0.0, (1.0 - age) / 0.30)
            else:
                env = 1.0
            color = _blend((10, 12, 18), outcome_tint, env * 0.7)
            pygame.draw.circle(
                surface, color, (int(p["x"]), int(p["y"])), p["size"]
            )

        # Title with glow + bob, matching title-screen treatment. Title also
        # rides a brief intro envelope — drifts in from above + fades up
        # during the first 0.7 s of the outro so the moment has a feel of
        # arrival instead of snapping in.
        ticks = pygame.time.get_ticks()
        bob = math.sin(ticks / 700) * 6
        intro_title_t = min(1.0, max(0.0, elapsed_ms / 700)) if not game.reduce_motion else 1.0
        title_drift = int((1.0 - intro_title_t) * -40)  # starts above, lands at 0
        title_alpha = int(255 * (intro_title_t ** 0.6))
        title_text = "ÉQUILIBRE RÉTABLI" if is_victory else "BASCULE FRANCHIE"
        title_color = (240, 250, 245) if is_player_win else (250, 235, 235)
        glow_color = (60, 180, 110) if is_player_win else (200, 70, 70)
        # Subtitles reframed from win/lose verdicts to doc-anchored
        # reflections. The source pedagogy ("Comprendre, s'émerveiller,
        # agir") treats every outcome as a step in learning, so even
        # the catastrophe-win case ends on "reste à comprendre" instead
        # of "you tipped the planet". Anti-despair on losses, anti-
        # triumphalism on wins — matches the doc's "des raisons
        # d'espérer" voice without becoming preachy.
        if side == "humanite":
            subtitle_text = (
                "L'équilibre tient. Les bons gestes, à temps, font la différence."
                if is_victory
                else "L'épreuve nous reste. Elle nous montre où agir."
            )
        else:
            subtitle_text = (
                "L'humanité s'est adaptée. Le savoir-faire existait déjà."
                if is_victory
                else "La planète a parlé. Reste à comprendre — et à se préparer."
            )

        # Position title near the top so the stats card + buttons all fit
        # below it on the 960×640 canvas. During the intro envelope, the
        # title drifts down from -40 px so it appears to land.
        title_y = int(28 + bob + title_drift)
        glow = self.fonts.giant.render(title_text, True, glow_color)
        title = self.fonts.giant.render(title_text, True, title_color)
        # Wrap both glow + title in an SRCALPHA composite when alpha < 255 so
        # the drift-in fade actually shows.
        if title_alpha < 255:
            comp = pygame.Surface(
                (title.get_width() + 4, title.get_height() + 4),
                pygame.SRCALPHA,
            )
            for off in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                comp.blit(glow, (2 + off[0], 2 + off[1]))
            comp.blit(title, (2, 2))
            comp.set_alpha(title_alpha)
            surface.blit(
                comp, ((w - title.get_width()) // 2 - 2, title_y - 2),
            )
        else:
            glow_pos = ((w - glow.get_width()) // 2, title_y + 2)
            for off in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                surface.blit(glow, (glow_pos[0] + off[0], glow_pos[1] + off[1]))
            surface.blit(title, ((w - title.get_width()) // 2, title_y))
        # Subtitle inherits a delayed envelope so it cascades in after the
        # title — starts at 0.4 s, completes at 1.0 s.
        sub_t = (
            min(1.0, max(0.0, (elapsed_ms - 400) / 600))
            if not game.reduce_motion else 1.0
        )
        sub_drift = int((1.0 - sub_t) * -16)
        sub_alpha = int(255 * (sub_t ** 0.6))
        subtitle = self.fonts.medium.render(subtitle_text, True, (200, 210, 220))
        if sub_alpha < 255:
            subtitle.set_alpha(sub_alpha)
        surface.blit(
            subtitle,
            ((w - subtitle.get_width()) // 2,
             title_y + title.get_height() + 12 + sub_drift),
        )

        # Stats card — light dashboard panel sitting in the dark gradient.
        total_pop = sum(c.population for c in game.world.countries.values())
        total_dead = sum(c.dead for c in game.world.countries.values())
        critical = sum(1 for c in game.world.countries.values() if c.state >= 0.5)
        # Real purchases live in ``game.purchased_skills`` (skill_id → level).
        # The legacy ``evolution.nodes`` flag is never set anymore so the old
        # count always read 0/N. Total = skills available for the player's
        # side under the active catastrophe (matches the skill tree view).
        purchased = sum(1 for lvl in game.purchased_skills.values() if lvl > 0)
        side = getattr(game, "player_side", "gaia")
        active_cat = game.skill_catalog.for_catastrophe_side(
            game.gaia.active.name, side,
        )
        if active_cat is not None:
            total_nodes = sum(
                len(tier.skills)
                for axis in active_cat.axes
                for tier in axis.tiers
            )
        else:
            total_nodes = len(game.evolution.nodes)
        pop_lost = (total_dead / total_pop * 100) if total_pop else 0.0
        balance_pct = int(game.humans.global_progress * 100)

        # Use the shared helper so input handler hit-targets line up exactly.
        card_rect = outro_card_rect(self.config)
        card_w = card_rect.width
        card_h = card_rect.height
        self._draw_shadow(surface, card_rect, blur=22, alpha=170)
        self._fill_panel(surface, card_rect, self.palette.surface_elevated)
        pygame.draw.rect(
            surface, outcome_tint,
            (card_rect.left, card_rect.top, card_rect.width, 3),
        )

        # Tab bar — BILAN (stats) / IMPACTS (axes lessons) / PARCOURS (skills).
        active_tab = max(0, min(2, getattr(game, "outro_tab", 0)))
        tab_labels = ("BILAN", "IMPACTS", "PARCOURS")
        tab_rects = outro_tab_rects(self.config, card_rect)
        mouse_pos = pygame.mouse.get_pos()
        for i, label in enumerate(tab_labels):
            self._draw_outro_tab(
                surface, tab_rects[i], label,
                active=i == active_tab,
                accent=outcome_tint,
                hover=tab_rects[i].collidepoint(mouse_pos),
            )

        content_top = card_rect.top + 56
        content_left = card_rect.left + PAD + 4
        content_w = card_rect.width - PAD * 2 - 8
        if active_tab == 0:
            self._draw_outro_bilan(
                surface, card_rect, content_top, content_left, content_w,
                balance_pct=balance_pct,
                pop_lost=pop_lost,
                critical=critical,
                purchased=purchased,
                total_nodes=total_nodes,
                turn=game.turn,
                outcome_tint=outcome_tint,
                is_player_win=is_player_win,
            )
        elif active_tab == 1:
            # IMPACTS — visual axis breakdown. Replaces the previous text
            # list of "name + description" entries that overflowed for
            # long skill names. Now: one row per axis (Intensité / Portée
            # / Durée / Impact Écologique) with a tinted glyph, a
            # progression bar, and a chip showing the highest tier reached.
            self._draw_outro_impacts_visual(
                surface, card_rect, content_top, content_left, content_w,
                game=game, outcome_tint=outcome_tint,
            )
        else:
            # PARCOURS — visual tile grid. Each purchased skill becomes
            # a compact card with axis colour + glyph + truncated name +
            # NIV.X badge. Replaces the previous flat name+badge list
            # that overflowed on long skill names.
            self._draw_outro_parcours_visual(
                surface, card_rect, content_top, content_left, content_w,
                game=game, outcome_tint=outcome_tint,
            )

        # Chunky title-style buttons.
        rects = game_over_button_rects(self.config)
        mouse_pos = pygame.mouse.get_pos()
        self._draw_chunky_button(
            surface,
            rects["restart"],
            label="RECOMMENCER",
            primary=True,
            hover=rects["restart"].collidepoint(mouse_pos),
        )
        self._draw_chunky_button(
            surface,
            rects["menu"],
            label="MENU",
            primary=False,
            hover=rects["menu"].collidepoint(mouse_pos),
        )
        self._draw_chunky_button(
            surface,
            rects["quit"],
            label="QUITTER",
            primary=False,
            hover=rects["quit"].collidepoint(mouse_pos),
        )

    def _draw_outro_bilan(
        self,
        surface: pygame.Surface,
        card_rect: pygame.Rect,
        content_top: int,
        content_left: int,
        content_w: int,
        *,
        balance_pct: int,
        pop_lost: float,
        critical: int,
        purchased: int,
        total_nodes: int,
        turn: int,
        outcome_tint: tuple[int, int, int],
        is_player_win: bool,
    ) -> None:
        """Visual-first end-of-run dashboard — two hero donuts + a 3-tile
        stat strip. Replaces the previous 5-row label/value list.

        Top row: two circular gauges that tell the headline story at a
        glance — ÉQUILIBRE FINAL (signed by outcome) and POPULATION
        DÉCIMÉE (signed by severity). Bottom row: three tile cards with
        an iconic glyph + big number + caption for the secondary metrics
        (Pays critiques, Évolutions débloquées, Jours).
        """
        # ---- Top row: two donuts side-by-side.
        donut_r = 52
        donut_y = content_top + donut_r + 6
        donut_gap = 70
        donut1_cx = content_left + donut_r + 18
        donut2_cx = donut1_cx + donut_r * 2 + donut_gap

        # Donut 1 — Équilibre final. Colour follows progress.
        balance_t = max(0.0, min(1.0, balance_pct / 100.0))
        balance_color = _progress_color(balance_t)
        self._draw_outro_donut(
            surface, (donut1_cx, donut_y), donut_r,
            value_t=balance_t,
            # French typography: space before "%" — outro screen
            # carries the run's final numbers; sloppy "65%" reads
            # off on the climactic recap.
            value_text=f"{balance_pct} %",
            label="ÉQUILIBRE",
            sub="final",
            fill_color=balance_color,
        )
        # Donut 2 — Population décimée. Severity colour ramp inverted.
        pop_t = max(0.0, min(1.0, pop_lost / 100.0))
        if pop_lost >= 25:
            pop_color = self.palette.severe
        elif pop_lost >= 10:
            pop_color = SOFT_WARNING
        else:
            pop_color = SOFT_SUCCESS
        self._draw_outro_donut(
            surface, (donut2_cx, donut_y), donut_r,
            value_t=pop_t,
            value_text=f"{pop_lost:.1f} %",
            label="POPULATION",
            sub="décimée",
            fill_color=pop_color,
        )

        # ---- Bottom row: three stat tiles in a horizontal strip.
        strip_top = donut_y + donut_r + 38
        tile_h = card_rect.bottom - strip_top - 14
        tile_h = max(60, min(tile_h, 92))
        tile_gap = 12
        tile_w = (content_w - tile_gap * 2) // 3
        # Tile labels kept short so each fits inside the ~97 px text
        # column at fonts.label (12 pt bold caps). "PAYS CRITIQUES"
        # (111 px) and "JOURS ÉCOULÉS" (113 px) used to overflow into
        # neighbour tiles on a 560 px outro card; trimmed to
        # "EN CRISE" (67 px) and "JOURS" (35 px) — both still read
        # unambiguously against the value glyph + number above them.
        tiles = (
            ("globe",  str(critical),
             "EN CRISE",
             self.palette.severe if critical >= 50 else self.palette.text),
            ("dna",    f"{purchased}/{total_nodes}",
             "ÉVOLUTIONS",
             outcome_tint),
            ("clock",  str(turn),
             "JOURS",
             self.palette.text),
        )
        for i, (glyph, value, label, value_color) in enumerate(tiles):
            tile_x = content_left + i * (tile_w + tile_gap)
            tile_rect = pygame.Rect(tile_x, strip_top, tile_w, tile_h)
            self._draw_outro_tile(
                surface, tile_rect, glyph, value, label,
                value_color=value_color, accent=outcome_tint,
            )

    def _draw_outro_donut(
        self,
        surface: pygame.Surface,
        center: tuple[int, int],
        radius: int,
        *,
        value_t: float,
        value_text: str,
        label: str,
        sub: str,
        fill_color: tuple[int, int, int],
    ) -> None:
        """Circular progress gauge with a centred number + label below.

        Track is a faint full ring, fill is an arc whose length follows
        ``value_t`` (0..1). Numbers render in mono on the dark inner
        disc so they read against any backdrop.
        """
        cx, cy = center
        # Faint track ring.
        pygame.draw.circle(
            surface, self.palette.surface_overlay[:3],
            (cx, cy), radius, 5,
        )
        # Inner disc (slightly darker than the card) so the centre number
        # has its own little stage.
        pygame.draw.circle(
            surface, _blend(self.palette.surface_deep[:3], (0, 0, 0), 0.25),
            (cx, cy), radius - 8,
        )
        # Progress arc — drawn as a sequence of small dots so we don't need
        # pygame.draw.arc (which is line-quality at thick widths).
        if value_t > 0.01:
            steps = max(8, int(72 * value_t))
            for k in range(steps):
                t = k / 72.0
                if t > value_t:
                    break
                angle = -math.pi / 2 + t * math.pi * 2
                px = cx + int(math.cos(angle) * radius)
                py = cy + int(math.sin(angle) * radius)
                pygame.draw.circle(surface, fill_color, (px, py), 4)
            # Leading-edge cap at the exact arc tip — a brighter,
            # larger pip with a soft halo so the eye locks onto "this
            # is where the value lands" instead of trying to follow
            # the arc to its end. Skipped when value_t ≈ 1.0 (full
            # ring — no leading edge to highlight).
            if value_t < 0.99:
                tip_angle = -math.pi / 2 + value_t * math.pi * 2
                tx_px = cx + int(math.cos(tip_angle) * radius)
                ty_px = cy + int(math.sin(tip_angle) * radius)
                # Soft halo behind the cap.
                halo = pygame.Surface((24, 24), pygame.SRCALPHA)
                for hr in range(10, 0, -1):
                    a = int(110 * (1 - hr / 10) ** 1.6)
                    if a < 1:
                        continue
                    pygame.draw.circle(halo, (*fill_color, a), (12, 12), hr)
                surface.blit(halo, (tx_px - 12, ty_px - 12))
                # Bright cap pip on top.
                pygame.draw.circle(
                    surface,
                    _blend(fill_color, (255, 255, 255), 0.4),
                    (tx_px, ty_px), 5,
                )
                pygame.draw.circle(
                    surface, fill_color, (tx_px, ty_px), 6, 1,
                )
        # Value in centre (mono, white for contrast).
        value_surf = self.fonts.hero.render(
            value_text, True, (245, 248, 255),
        )
        if value_surf.get_width() > radius * 2 - 16:
            value_surf = self.fonts.large.render(
                value_text, True, (245, 248, 255),
            )
        surface.blit(
            value_surf,
            (cx - value_surf.get_width() // 2,
             cy - value_surf.get_height() // 2),
        )
        # Label below the donut.
        lab = self.fonts.label.render(label, True, self.palette.text_label)
        surface.blit(
            lab, (cx - lab.get_width() // 2, cy + radius + 6),
        )
        if sub:
            sub_surf = self.fonts.small.render(
                sub, True, self.palette.text_dim,
            )
            surface.blit(
                sub_surf,
                (cx - sub_surf.get_width() // 2,
                 cy + radius + 6 + lab.get_height() + 1),
            )

    def _draw_outro_tile(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        glyph: str,
        value: str,
        label: str,
        *,
        value_color: tuple[int, int, int],
        accent: tuple[int, int, int],
    ) -> None:
        """Single stat tile — glyph badge on the left, big value + caption
        stacked on the right. Translucent body, rounded corners, accent
        left-edge bar matching the rest of the card design."""
        # Body with screen-surface depth — flat fill + vertical
        # gradient (top +12 / bottom −12, masked to rounded corners
        # via BLEND_RGBA_MULT) + top-edge highlight + bottom-edge
        # shadow strokes + accent-tinted border (replaces the prior
        # neutral ``ui_border_soft``). Same depth idiom shipped on
        # the ÉQUILIBRE tiles, TENDANCE chips, info panel header,
        # milestone banners, and pause menu buttons.
        body = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            body, (*self.palette.surface_deep[:3], 220),
            (0, 0, rect.width, rect.height), border_radius=8,
        )
        # Vertical gradient drawn on a separate surface, then masked
        # to the rounded-rect shape so it respects the 8 px corners.
        grad = pygame.Surface(rect.size, pygame.SRCALPHA)
        for gy in range(rect.height):
            t = gy / max(1, rect.height - 1)
            shift = int(12 * (1.0 - 2 * t))
            if shift > 0:
                pygame.draw.line(
                    grad, (255, 255, 255, min(255, shift * 3)),
                    (0, gy), (rect.width, gy),
                )
            elif shift < 0:
                pygame.draw.line(
                    grad, (0, 0, 0, min(255, -shift * 3)),
                    (0, gy), (rect.width, gy),
                )
        mask = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            mask, (255, 255, 255, 255),
            (0, 0, rect.width, rect.height), border_radius=8,
        )
        grad.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        body.blit(grad, (0, 0))
        surface.blit(body, rect.topleft)
        # Accent left bar in the outcome tint.
        pygame.draw.rect(
            surface, accent,
            (rect.left, rect.top + 6, 3, rect.height - 12),
            border_radius=2,
        )
        # Top highlight + bottom shadow strokes (1 px each, inset 6 px
        # to avoid the rounded corners).
        hl_layer = pygame.Surface((rect.width - 12, 1), pygame.SRCALPHA)
        hl_layer.fill((255, 255, 255, 50))
        surface.blit(hl_layer, (rect.left + 6, rect.top + 1))
        sh_layer = pygame.Surface((rect.width - 12, 1), pygame.SRCALPHA)
        sh_layer.fill((0, 0, 0, 65))
        surface.blit(sh_layer, (rect.left + 6, rect.bottom - 2))
        # Accent-tinted border (40 % blend) instead of the neutral
        # ``ui_border_soft`` — tile chrome now carries the outcome
        # identity at its edges, not just at the accent stripe.
        pygame.draw.rect(
            surface,
            _blend(self.palette.surface_deep[:3], accent, 0.40),
            rect, 1, border_radius=8,
        )
        # Glyph badge.
        badge_r = min(14, rect.height // 3)
        badge_cx = rect.left + 16 + badge_r
        badge_cy = rect.top + rect.height // 2
        pygame.draw.circle(
            surface, _blend((10, 12, 18), accent, 0.45),
            (badge_cx, badge_cy), badge_r,
        )
        pygame.draw.circle(
            surface, accent, (badge_cx, badge_cy), badge_r, 2,
        )
        self._draw_outro_tile_glyph(
            surface, glyph, (badge_cx, badge_cy), badge_r - 5,
        )
        # Value + label.
        # Progressive font fallback (hero → large → medium) on the
        # value so wide ratios like ``"500/500"`` or ``"49/100"`` —
        # both ≥106 px at large — don't overflow the ~97 px text area
        # on a 560 px outro card. Same idiom for the label: fonts.label
        # at 111 px already overflows the ~107 px label area for
        # "PAYS CRITIQUES" and "JOURS ÉCOULÉS", so fall through to
        # fonts.small for those two without changing the others.
        text_x = badge_cx + badge_r + 10
        text_max_w = rect.right - text_x - 10
        # Progressive font fallback (hero → large → medium) on the
        # value so wide ratios like ``"500/500"`` or ``"49/100"`` —
        # both ≥106 px at large — don't overflow the ~97 px text area
        # on a 560 px outro card.
        value_text, value_font = self._fit_text_progressive(
            value, text_max_w,
            (self.fonts.hero, self.fonts.large, self.fonts.medium),
        )
        value_surf = value_font.render(value_text, True, value_color)
        # Label uses the tracked-out 12pt bold ``fonts.label`` — falling
        # through to ``fonts.small`` would actually widen these caps
        # strings (14pt regular > 12pt bold for uppercase), so the
        # safer fallback is to ellipsise at the same font.
        lab = self.fonts.label.render(
            self._fit_text(label, self.fonts.label, text_max_w),
            True, self.palette.text_label,
        )
        block_h = value_surf.get_height() + 2 + lab.get_height()
        block_top = rect.top + (rect.height - block_h) // 2
        surface.blit(value_surf, (text_x, block_top))
        surface.blit(
            lab, (text_x, block_top + value_surf.get_height() + 2),
        )

    def _draw_outro_tile_glyph(
        self,
        surface: pygame.Surface,
        kind: str,
        center: tuple[int, int],
        r: int,
    ) -> None:
        """Procedural icon for an outro stat tile."""
        cx, cy = center
        color = (245, 248, 255)
        if kind == "globe":
            pygame.draw.circle(surface, color, (cx, cy), r, 2)
            # Horizontal "equator" + meridian.
            pygame.draw.line(surface, color, (cx - r, cy), (cx + r, cy), 2)
            pygame.draw.line(surface, color, (cx, cy - r), (cx, cy + r), 1)
            # Subtle inner ellipse for tilt.
            ellipse_rect = pygame.Rect(
                cx - r, cy - r // 2, r * 2, r,
            )
            pygame.draw.ellipse(surface, color, ellipse_rect, 1)
        elif kind == "dna":
            # Twin DNA helix — reuse element-icon idiom.
            steps = 12
            for direction in (1, -1):
                pts: list[tuple[int, int]] = []
                for s in range(steps + 1):
                    t = s / steps
                    py = cy - r + int(t * (2 * r))
                    px = cx + int(direction * math.sin(t * math.pi * 2) * r * 0.7)
                    pts.append((px, py))
                pygame.draw.lines(surface, color, False, pts, 2)
        elif kind == "clock":
            # Proper clock face — circle bezel + four cardinal hour
            # markers (12 / 3 / 6 / 9) + hour and minute hands meeting
            # at a centre pip. Was a circle with one mark and a single
            # short bar that read as "an unfinished icon"; the player
            # could see it was supposed to be a clock but the hands
            # didn't articulate time. Now the two distinct-length
            # hands set at ~10:10 (the universal "everyone's happy"
            # clock pose used in product photos) communicate
            # *passage of time* clearly.
            pygame.draw.circle(surface, color, (cx, cy), r, 2)
            # Hour markers at the four cardinal positions.
            for mk_dx, mk_dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                mx = cx + int(mk_dx * (r - 4))
                my = cy + int(mk_dy * (r - 4))
                pygame.draw.circle(surface, color, (mx, my), 1)
            # Hour hand — shorter, pointing ~10 (upper-left).
            hour_end = (cx - r // 2 + 1, cy - r // 2 + 1)
            pygame.draw.line(surface, color, (cx, cy), hour_end, 2)
            # Minute hand — longer, pointing ~2 (upper-right).
            minute_end = (cx + r - 4, cy - r // 2 + 3)
            pygame.draw.line(surface, color, (cx, cy), minute_end, 2)
            # Centre pip — anchors the hands.
            pygame.draw.circle(surface, color, (cx, cy), 2)
        else:
            glyph = self.fonts.label.render(
                kind[:1].upper(), True, color,
            )
            surface.blit(
                glyph,
                (cx - glyph.get_width() // 2,
                 cy - glyph.get_height() // 2),
            )

    def _draw_axis_glyph(
        self,
        surface: pygame.Surface,
        axis_name: str,
        center: tuple[int, int],
        r: int,
    ) -> None:
        """Procedural icon for one of the four skill-tree axes.

        Used by the outro IMPACTS rows + PARCOURS tiles so each axis
        keeps its own visual identity (lightning / arcs / clock / leaf).
        """
        cx, cy = center
        color = (245, 248, 255)
        if axis_name == "Intensite":
            # Lightning bolt — sharp impact.
            pts = [
                (cx - r // 2, cy - r),
                (cx + r // 4, cy - r // 4),
                (cx - r // 4, cy + r // 8),
                (cx + r // 2, cy + r),
            ]
            pygame.draw.lines(surface, color, False, pts, 2)
        elif axis_name == "Portee":
            # Concentric arcs radiating outward — reach.
            big = pygame.Rect(cx - r, cy - r, r * 2, r * 2)
            small = pygame.Rect(cx - r // 2, cy - r // 2, r, r)
            pygame.draw.arc(surface, color, big, -2.6, -0.5, 2)
            pygame.draw.arc(surface, color, small, -2.6, -0.5, 2)
            pygame.draw.circle(surface, color, (cx, cy + 2), 2)
        elif axis_name == "Duree":
            # Clock face — endurance over time.
            pygame.draw.circle(surface, color, (cx, cy), r, 2)
            pygame.draw.line(surface, color, (cx, cy), (cx, cy - r + 2), 2)
            pygame.draw.line(surface, color, (cx, cy), (cx + r // 2, cy), 2)
        elif axis_name == "Impact Ecologique":
            # Leaf — life / ecology.
            leaf = pygame.Rect(cx - r, cy - int(r * 0.85), r * 2, int(r * 1.7))
            pygame.draw.ellipse(surface, color, leaf, 2)
            pygame.draw.line(
                surface, color,
                (cx - r // 2, cy + r // 2),
                (cx + r // 2, cy - r // 2),
                1,
            )
        else:
            glyph = self.fonts.label.render(
                axis_name[:1].upper(), True, color,
            )
            surface.blit(
                glyph,
                (cx - glyph.get_width() // 2,
                 cy - glyph.get_height() // 2),
            )

    def _axis_breakdown(
        self, game: Game,
    ) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
        """Count purchased skills + highest-tier reached per axis.

        Returns ``(purchased, totals, max_tier_index)`` keyed by axis
        name. ``max_tier_index`` is -1 when no skill on that axis has
        been purchased, else 0/1/2 for Fondations / Amplification /
        Transformation.
        """
        TIER_ORDER = ("Fondations", "Amplification", "Transformation")
        purchased = {a: 0 for a in SKILL_TREE_AXES}
        totals = {a: 0 for a in SKILL_TREE_AXES}
        max_tier = {a: -1 for a in SKILL_TREE_AXES}

        catalog = getattr(game, "skill_catalog", None)
        side = getattr(game, "player_side", "gaia")
        cat = (
            catalog.for_catastrophe_side(game.gaia.active.name, side)
            if catalog else None
        )
        if cat is not None:
            for axis in cat.axes:
                totals[axis.name] = sum(len(t.skills) for t in axis.tiers)

        for skill_id, level in game.purchased_skills.items():
            if level <= 0:
                continue
            parts = skill_id.split(":")
            if len(parts) < 4:
                continue
            axis_name = parts[1]
            tier_name = parts[2]
            if axis_name not in purchased:
                continue
            purchased[axis_name] += 1
            if tier_name in TIER_ORDER:
                idx = TIER_ORDER.index(tier_name)
                if idx > max_tier[axis_name]:
                    max_tier[axis_name] = idx
        # Default totals when catalog is missing so the bar still
        # renders something sensible.
        for a in SKILL_TREE_AXES:
            if totals[a] == 0:
                totals[a] = 9
        return purchased, totals, max_tier

    def _draw_outro_impacts_visual(
        self,
        surface: pygame.Surface,
        card_rect: pygame.Rect,
        content_top: int,
        content_left: int,
        content_w: int,
        *,
        game: Game,
        outcome_tint: tuple[int, int, int],
    ) -> None:
        """Visual 4-axis breakdown for the outro IMPACTS tab.

        Replaces the previous text-list of "skill name + description"
        entries that ran wide for long skill names. Now: one row per
        axis with a tinted glyph badge, a progression bar showing the
        fraction of skills purchased, and a chip with the deepest tier
        reached on that axis.
        """
        section = self.fonts.label.render(
            f"IMPACTS · {game.gaia.active.name.upper()}",
            True, outcome_tint,
        )
        surface.blit(section, (content_left, content_top))

        purchased, totals, max_tier = self._axis_breakdown(game)
        rows_top = content_top + section.get_height() + 10
        avail_h = card_rect.bottom - 14 - rows_top
        row_gap = 6
        # 4 axes; pick a row height that uses available vertical space.
        row_h = max(44, min(60, (avail_h - row_gap * 3) // 4))

        for i, axis_name in enumerate(SKILL_TREE_AXES):
            row_y = rows_top + i * (row_h + row_gap)
            if row_y + row_h > card_rect.bottom - 6:
                break
            rect = pygame.Rect(content_left, row_y, content_w, row_h)
            self._draw_outro_impact_row(
                surface, rect, axis_name,
                purchased=purchased.get(axis_name, 0),
                total=totals.get(axis_name, 9),
                max_tier=max_tier.get(axis_name, -1),
            )

    def _draw_outro_impact_row(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        axis_name: str,
        *,
        purchased: int,
        total: int,
        max_tier: int,
    ) -> None:
        """One axis row inside the IMPACTS panel — glyph + label + bar + chip."""
        axis_color = _axis_color(axis_name)
        # Body
        body = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            body, (*self.palette.surface_deep[:3], 210),
            (0, 0, rect.width, rect.height), border_radius=8,
        )
        surface.blit(body, rect.topleft)
        # Gradient + top-edge highlight + bottom-edge shadow — same
        # depth idiom shipped on every other tactile chrome surface,
        # extended here to the outro IMPACTS rows (one per axis,
        # shown at end-of-run on the BILAN screen). Previously the
        # rows sat as flat translucent rects, which read as dim
        # patches next to the textured outro card; now they read
        # as sub-cards inside the parent card.
        self._apply_button_depth(
            surface, rect, self.palette.surface_deep[:3], radius=8,
        )
        pygame.draw.rect(
            surface, self.palette.ui_border_soft,
            rect, 1, border_radius=8,
        )
        pygame.draw.rect(
            surface, axis_color,
            (rect.left, rect.top + 6, 3, rect.height - 12),
            border_radius=2,
        )

        # Glyph badge on the left
        badge_r = min(13, rect.height // 3)
        badge_cx = rect.left + 14 + badge_r
        badge_cy = rect.centery
        pygame.draw.circle(
            surface, _blend((10, 12, 18), axis_color, 0.40),
            (badge_cx, badge_cy), badge_r,
        )
        pygame.draw.circle(
            surface, axis_color, (badge_cx, badge_cy), badge_r, 2,
        )
        self._draw_axis_glyph(
            surface, axis_name, (badge_cx, badge_cy), badge_r - 4,
        )

        # Axis label
        label_x = badge_cx + badge_r + 12
        label_t = self.fonts.medium.render(
            SKILL_TREE_AXIS_LABELS.get(axis_name, axis_name.upper()),
            True, self.palette.text,
        )
        surface.blit(label_t, (label_x, rect.top + 6))

        # Progress bar + count caption
        pct = (purchased / total) if total else 0.0
        chip_w = 64
        bar_x = label_x
        bar_y = rect.top + label_t.get_height() + 9
        bar_w = max(60, rect.right - bar_x - chip_w - 60)
        bar_h = 6
        pygame.draw.rect(
            surface, self.palette.surface_overlay[:3],
            (bar_x, bar_y, bar_w, bar_h), border_radius=3,
        )
        pygame.draw.rect(
            surface, axis_color,
            (bar_x, bar_y, int(bar_w * max(0.0, min(1.0, pct))), bar_h),
            border_radius=3,
        )
        count_t = self.fonts.small.render(
            f"{purchased}/{total}", True, self.palette.text_dim,
        )
        surface.blit(count_t, (bar_x + bar_w + 8, bar_y - 4))

        # Tier chip on the right
        chip_h = 22
        chip_rect = pygame.Rect(
            rect.right - chip_w - 10,
            rect.centery - chip_h // 2,
            chip_w, chip_h,
        )
        if max_tier >= 0:
            chip_label = SKILL_TIER_LABELS_SHORT[max_tier]
            chip_color = axis_color
        else:
            chip_label = "—"
            chip_color = self.palette.text_dim
        pygame.draw.rect(
            surface, _blend((10, 12, 18), chip_color, 0.25),
            chip_rect, border_radius=chip_h // 2,
        )
        pygame.draw.rect(
            surface, chip_color, chip_rect, 1,
            border_radius=chip_h // 2,
        )
        chip_t = self.fonts.label.render(chip_label, True, chip_color)
        surface.blit(
            chip_t,
            (chip_rect.centerx - chip_t.get_width() // 2,
             chip_rect.centery - chip_t.get_height() // 2),
        )

    def _draw_outro_parcours_visual(
        self,
        surface: pygame.Surface,
        card_rect: pygame.Rect,
        content_top: int,
        content_left: int,
        content_w: int,
        *,
        game: Game,
        outcome_tint: tuple[int, int, int],
    ) -> None:
        """Visual 3×2 tile grid for the outro PARCOURS tab.

        Each purchased skill becomes a tile with its axis-tinted glyph,
        a short skill name (wrapped to 2 lines), and a NIV.X badge.
        Replaces the previous text list that overflowed for long names.
        """
        # Use the canonical player-facing side labels — internal Python
        # tokens "gaia"/"humanite" would render as "GAIA"/"HUMANITE":
        # GAIA was explicitly rejected as "mythological" in favour of
        # "PLANÈTE" (see picker side-label comment), and naive
        # ``.upper()`` on "humanite" drops the acute accent the rest of
        # the UI carries. Mapping ensures the outro header matches the
        # picker cards, side glyphs, and side-aware taglines.
        side_label = (
            "PLANÈTE" if game.player_side == "gaia" else "HUMANITÉ"
        )
        section = self.fonts.label.render(
            f"PARCOURS · {side_label}",
            True, outcome_tint,
        )
        surface.blit(section, (content_left, content_top))

        purchased = [
            (sid, lvl) for sid, lvl in game.purchased_skills.items()
            if lvl > 0
        ]
        purchased.sort(key=lambda kv: -kv[1])
        grid_top = content_top + section.get_height() + 10

        if not purchased:
            t = self.fonts.medium.render(
                "Aucune évolution achetée durant le scénario.",
                True, self.palette.text_label,
            )
            surface.blit(t, (content_left, grid_top + 16))
            return

        cols = 3
        rows = 2
        gap = 8
        tile_w = (content_w - gap * (cols - 1)) // cols
        avail_h = card_rect.bottom - 22 - grid_top
        # Reserve a small footer line at the bottom for the overflow count.
        footer_h = self.fonts.small.get_height() + 4
        avail_h -= footer_h
        tile_h = max(56, min(96, (avail_h - gap * (rows - 1)) // rows))

        visible = purchased[: cols * rows]
        for idx, (sid, lvl) in enumerate(visible):
            col = idx % cols
            row = idx // cols
            tile_x = content_left + col * (tile_w + gap)
            tile_y = grid_top + row * (tile_h + gap)
            tile_rect = pygame.Rect(tile_x, tile_y, tile_w, tile_h)
            skill = (
                game.skill_catalog.find_skill(sid)
                if game.skill_catalog else None
            )
            skill_name = skill.name if skill else sid.split(":")[-1]
            parts = sid.split(":")
            axis_name = parts[1] if len(parts) >= 2 else "Intensite"
            self._draw_outro_skill_tile(
                surface, tile_rect, skill_name, axis_name, lvl,
            )

        # Overflow footer when the player bought more than 6 skills.
        extra = len(purchased) - len(visible)
        if extra > 0:
            plural = "s" if extra > 1 else ""
            footer = self.fonts.small.render(
                f"+ {extra} évolution{plural} non affichée{plural}",
                True, self.palette.text_dim,
            )
            surface.blit(
                footer,
                (card_rect.right - PAD - 4 - footer.get_width(),
                 card_rect.bottom - 8 - footer.get_height()),
            )

    def _draw_outro_skill_tile(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        skill_name: str,
        axis_name: str,
        level: int,
    ) -> None:
        """Single skill tile — axis glyph + truncated name + NIV.X badge."""
        axis_color = _axis_color(axis_name)
        body = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(
            body, (*self.palette.surface_deep[:3], 220),
            (0, 0, rect.width, rect.height), border_radius=8,
        )
        surface.blit(body, rect.topleft)
        # Gradient + edge-stroke depth — same idiom shipped on the
        # IMPACTS rows on the sibling tab. PARCOURS tiles were flat
        # translucent rects against the textured outro card body;
        # now they read as proper sub-cards with depth in lockstep
        # with the chrome family elsewhere (settings rows, sidebar
        # two-col, impact-card cells, etc.).
        self._apply_button_depth(
            surface, rect, self.palette.surface_deep[:3], radius=8,
        )
        pygame.draw.rect(
            surface, self.palette.ui_border_soft,
            rect, 1, border_radius=8,
        )
        pygame.draw.rect(
            surface, axis_color,
            (rect.left, rect.top + 6, 3, rect.height - 12),
            border_radius=2,
        )

        # Glyph badge top-left.
        badge_r = 11
        badge_cx = rect.left + 14 + badge_r
        badge_cy = rect.top + 8 + badge_r
        pygame.draw.circle(
            surface, _blend((10, 12, 18), axis_color, 0.45),
            (badge_cx, badge_cy), badge_r,
        )
        pygame.draw.circle(
            surface, axis_color, (badge_cx, badge_cy), badge_r, 1,
        )
        self._draw_axis_glyph(
            surface, axis_name, (badge_cx, badge_cy), badge_r - 3,
        )

        # NIV.X chip top-right.
        niv_t = self.fonts.label.render(
            f"NIV.{level}", True, axis_color,
        )
        surface.blit(
            niv_t,
            (rect.right - 10 - niv_t.get_width(), rect.top + 10),
        )

        # Skill name — wrap up to 2 lines below the badge row.
        text_max_w = rect.width - 20
        name_y = badge_cy + badge_r + 6
        max_lines = 2 if rect.height >= 70 else 1
        for line in self._wrap_text(
            skill_name, self.fonts.small, text_max_w, max_lines=max_lines,
        ):
            t = self.fonts.small.render(line, True, self.palette.text)
            surface.blit(t, (rect.left + 10, name_y))
            name_y += t.get_height() + 1
            if name_y > rect.bottom - 6:
                break

    def _impact_report_lines(self, game: Game) -> list[tuple[str, str]]:
        """Build the outro's "what you learned" report.

        If the player purchased skills, list each purchased skill's name + the
        first impact description of the highest level they reached. Otherwise
        fall back to a default per-axis preview at the deepest catalog tier so
        the screen is never blank.
        """
        catalog = game.skill_catalog
        if not catalog or not catalog.catastrophes:
            return []
        side = getattr(game, "player_side", "gaia")
        cat = catalog.for_catastrophe_side(game.gaia.active.name, side)
        if cat is None:
            return []

        if game.purchased_skills:
            lines: list[tuple[str, str]] = []
            for skill_id, level in sorted(
                game.purchased_skills.items(),
                key=lambda kv: -kv[1],  # highest-level skills first
            ):
                skill = catalog.find_skill(skill_id)
                if skill is None or not skill.levels:
                    continue
                level_idx = max(0, min(level - 1, len(skill.levels) - 1))
                impact = skill.levels[level_idx].impact_descriptions
                if not impact:
                    continue
                _indicator, description = next(iter(impact.items()))
                lines.append((f"{skill.name} (niv. {level})", description))
                if len(lines) >= 8:
                    break
            return lines

        # Fallback when no purchases were made — preview the deepest-tier
        # description per axis so the educational angle still reads.
        axis_map = (
            ("Intensité",        "Intensite",          "Resilience Technologique"),
            ("Portée",           "Portee",             "Stabilite Societale"),
            ("Impact écologique", "Impact Ecologique", "Regeneration Ecologique"),
            ("Durée",            "Duree",              "Adaptation Evolutive"),
        )
        lines = []
        for display_axis, json_axis, indicator in axis_map:
            axis = cat.axis(json_axis)
            if axis is None or not axis.tiers:
                continue
            tier = axis.tiers[-1]
            if not tier.skills:
                continue
            skill = tier.skills[0]
            if not skill.levels:
                continue
            description = skill.levels[-1].impact_descriptions.get(indicator)
            if description:
                lines.append((display_axis, description))
        return lines

    def _draw_action_button(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        label: str,
        primary: bool,
        hover: bool,
    ) -> None:
        """Flat (non-primary) action button — used for the disabled / locked
        / unaffordable states of the AMÉLIORER slot (MAÎTRISÉ, VERROUILLÉ,
        manque ÉN).

        Was a flat fill + 1-px border + centred text. Read as a regular
        button rather than a disabled state. Now adds:

          * **Inset shadow** along the top edge — pseudo-3D recess that
            cues the eye "this button is pressed in / unavailable",
            distinct from the raised ``_draw_chunky_button`` used for
            the active AMÉLIORER state.
          * **Diagonal hatch** for the disabled states (non-primary +
            non-hover), painted at very low alpha so the button reads
            as "locked" without being noisy.
          * The original fill + border + text remain on top so the
            existing colour vocabulary is preserved.

        Primary (still hover-able) skips the hatch — only the disabled
        states get the locked-look treatment.
        """
        if primary:
            fill = (60, 26, 28) if hover else (40, 22, 24)
            border = self.palette.ui_accent
            text_color = self.palette.text
        else:
            fill = (28, 36, 50) if hover else (20, 26, 38)
            border = self.palette.ui_border
            text_color = self.palette.text_dim
        pygame.draw.rect(surface, fill, rect, border_radius=4)

        # Inset top-edge shadow — a 3-row alpha-decaying dark line just
        # inside the rect's top border. Reads as a recessed slot rather
        # than a raised button.
        inset = pygame.Surface(
            (rect.width - 2, 4), pygame.SRCALPHA,
        )
        for row in range(4):
            a = int(70 * (1 - row / 4))
            if a < 1:
                continue
            pygame.draw.line(
                inset, (0, 0, 0, a),
                (0, row), (rect.width - 3, row),
            )
        surface.blit(inset, (rect.left + 1, rect.top + 1))

        # Disabled hatch — diagonal cross-lines at very low alpha. Only
        # painted on the non-primary states where this button is acting
        # as a "you can't click this" label.
        if not primary:
            hatch = pygame.Surface(
                (rect.width - 4, rect.height - 4), pygame.SRCALPHA,
            )
            step = 8
            hatch_color = (255, 255, 255, 8)
            # Two interleaved diagonal sets give a soft cross-hatch.
            for offset in range(-rect.height, rect.width + rect.height, step):
                pygame.draw.line(
                    hatch, hatch_color,
                    (offset, 0), (offset + rect.height, rect.height - 4),
                )
            surface.blit(hatch, (rect.left + 2, rect.top + 2))

        pygame.draw.rect(surface, border, rect, 1, border_radius=4)
        text = self.fonts.medium.render(label, True, text_color)
        surface.blit(
            text,
            (rect.centerx - text.get_width() // 2, rect.centery - text.get_height() // 2),
        )

    # ----------------------------------------------------------- helpers

    def _acquire_map_overlay(self, size: tuple[int, int]) -> pygame.Surface:
        """Return a cleared map-sized SRCALPHA surface, reusing the cached one.

        Three per-frame consumers (ring pulse, off-screen arrows, spread
        arcs) used to allocate their own map-sized ``Surface((w, h),
        SRCALPHA)`` and discard it after one blit. On mobile pygame
        each such allocation costs a malloc + a per-pixel-alpha clear;
        sharing the buffer drops that to one allocation for the entire
        run (re-allocated only when the map size changes — sidebar
        toggle or window resize).
        """
        overlay = self._map_overlay
        if overlay is None or overlay.get_size() != size:
            overlay = pygame.Surface(size, pygame.SRCALPHA)
            self._map_overlay = overlay
        else:
            overlay.fill((0, 0, 0, 0))
        return overlay

    def cached_render(
        self,
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
    ) -> pygame.Surface:
        """Memoized ``font.render`` for static labels.

        Use only for text whose ``(font, text, color)`` tuple is stable
        across many frames — tab labels, section headers, axis titles,
        floating-text content. Dynamic text (timers, hover values) keeps
        calling ``font.render`` directly; caching it would balloon the
        dict.
        """
        key = (id(font), text, color)
        cached = self._text_cache.get(key)
        if cached is not None:
            return cached
        # Bound the cache. 1024 distinct surfaces is well above what any
        # single screen renders (~50-100 unique static strings); if we
        # exceed it, a caller is feeding dynamic text in and we clear
        # rather than grow without bound.
        if len(self._text_cache) >= 1024:
            self._text_cache.clear()
        surf = font.render(text, True, color)
        self._text_cache[key] = surf
        return surf

    def _fill_panel(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        color: tuple[int, int, int, int],
    ) -> None:
        """Render a panel background with a subtle vertical gradient.

        Top edge starts ~10% lighter than ``color``, bottom ends ~10% darker.
        The gradient gives panels card-like elevation without a hard border.
        Surfaces are cached by (size, top, bottom) so a given panel only pays
        the per-pixel cost once.
        """
        top = _shade(color, 1.10)
        bottom = _shade(color, 0.85)
        overlay = self._gradient_surface(rect.width, rect.height, top, bottom)
        surface.blit(overlay, rect.topleft)

    def _fade_card_highlight(
        self,
        target: pygame.Surface,
        width: int,
        height: int,
        radius: int,
        peak_alpha: int = 14,
        peak_lowlight_alpha: int = 0,
    ) -> None:
        """Soft top-edge highlight + optional bottom-edge shadow.

        Replaces the half-panel rect overlay (255,255,255,A on (0..h/2))
        which produced a visible midline on taller panels — the
        "two-tone background" the player saw on the PARAMÈTRES card. Paint
        thin alpha lines from row 0 down to roughly half-height, easing the
        alpha so the highlight blends into the body instead of cutting.

        When ``peak_lowlight_alpha > 0``, draws a complementary bottom-
        edge shadow with mirrored quadratic falloff and matching
        rounded-corner insets — same idiom shipped on the info-panel
        header, TENDANCE chart container, pause menu buttons, and
        milestone banner bodies. Cards get both a lit top edge and an
        anchored bottom shadow with a single helper call.
        """
        fade_h = max(8, int(height * 0.55))
        for y in range(fade_h):
            t = y / fade_h
            # Quadratic ease-out — alpha drops fast near the midline so
            # most of the gradient lives near the top edge.
            alpha = int(peak_alpha * (1.0 - t) ** 2)
            if alpha <= 0:
                continue
            # First and last few rows are inset so the rounded corners
            # don't pick up the highlight as a square block.
            inset = 0 if y >= radius else max(0, radius - y)
            pygame.draw.line(
                target, (255, 255, 255, alpha),
                (inset, y), (width - 1 - inset, y),
            )
        if peak_lowlight_alpha > 0:
            shadow_h = max(8, int(height * 0.40))
            for offset in range(shadow_h):
                y = height - 1 - offset
                if y < 0:
                    break
                t = offset / shadow_h
                alpha = int(peak_lowlight_alpha * (1.0 - t) ** 2)
                if alpha <= 0:
                    continue
                # Mirror the corner-inset logic to the bottom corners.
                inset = (
                    0 if offset >= radius
                    else max(0, radius - offset)
                )
                pygame.draw.line(
                    target, (0, 0, 0, alpha),
                    (inset, y), (width - 1 - inset, y),
                )

    def _drop_shadow(
        self,
        width: int,
        height: int,
        blur: int = 18,
        alpha: int = 170,
    ) -> tuple[pygame.Surface | None, int]:
        """Return a Pillow-blurred drop shadow + the inset (pad) used.

        Returns ``(None, 0)`` when Pillow isn't installed — drawing degrades
        gracefully to no shadow rather than failing.
        """
        if not _PIL_AVAILABLE:
            return None, 0
        key = (width, height, blur, alpha)
        cached = self._shadow_cache.get(key)
        if cached is not None:
            return cached, blur * 2
        pad = blur * 2
        img = Image.new("RGBA", (width + pad * 2, height + pad * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [pad, pad, pad + width, pad + height], fill=(0, 0, 0, alpha)
        )
        img = img.filter(ImageFilter.GaussianBlur(blur))
        surface = pygame.image.frombuffer(img.tobytes(), img.size, "RGBA").convert_alpha()
        self._shadow_cache[key] = surface
        return surface, pad

    def _draw_shadow(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        blur: int = 18,
        alpha: int = 170,
        offset_y: int = 6,
    ) -> None:
        """Blit a soft drop shadow under ``rect``. No-op when Pillow is missing."""
        shadow, pad = self._drop_shadow(rect.width, rect.height, blur, alpha)
        if shadow is None:
            return
        surface.blit(shadow, (rect.left - pad, rect.top - pad + offset_y))

    def _draw_edge_shadow(
        self,
        surface: pygame.Surface,
        y: int,
        height: int = 8,
        downward: bool = True,
    ) -> None:
        """Soft horizontal shadow band below (or above) a fixed-y edge.

        Used by the top bar and news ticker to read as floating panels without
        committing to a full Pillow-blurred drop shadow per redraw (which is
        wasteful since these surfaces span the entire screen width).
        """
        w, _ = self.screen_size
        band = pygame.Surface((w, height), pygame.SRCALPHA)
        for i in range(height):
            t = i / max(1, height - 1)
            alpha = int(80 * (1.0 - t)) if downward else int(80 * t)
            pygame.draw.line(band, (0, 0, 0, alpha), (0, i), (w, i))
        surface.blit(band, (0, y))

    def _gradient_surface(
        self,
        width: int,
        height: int,
        top: tuple[int, int, int, int],
        bottom: tuple[int, int, int, int],
    ) -> pygame.Surface:
        key = (width, height, top, bottom)
        cached = self._gradient_cache.get(key)
        if cached is not None:
            return cached
        overlay = pygame.Surface((width, height), pygame.SRCALPHA)
        for y in range(height):
            t = y / max(1, height - 1)
            r = int(top[0] + (bottom[0] - top[0]) * t)
            g = int(top[1] + (bottom[1] - top[1]) * t)
            b = int(top[2] + (bottom[2] - top[2]) * t)
            a = int(top[3] + (bottom[3] - top[3]) * t)
            pygame.draw.line(overlay, (r, g, b, a), (0, y), (width, y))
        self._gradient_cache[key] = overlay
        return overlay


def close_button_rect(config: Config) -> pygame.Rect:
    """Rect used by the input handler to detect close-button clicks.

    Sits on the info panel's catastrophe-color header strip as a round red ×.
    Touch-mode grows 28×28 → 48×48; the rect keeps its right-edge anchor
    so the header layout still reads "× at the right of the header strip"
    on both touch and desktop.
    """
    panel_x = 16
    panel_y = TOP_BAR_H + 16
    size = MIN_TOUCH_TARGET if config.display.touch_mode else 28
    header_h = 60
    return pygame.Rect(
        panel_x + INFO_PANEL_W - size - 14,
        panel_y + (header_h - size) // 2,
        size, size,
    )


OUTRO_CARD_W = 560
OUTRO_CARD_H = 360
OUTRO_TITLE_Y = 28
# Actual rendered height of the 62 pt giant title is closer to 72 px once
# ascenders/descenders are accounted for; the +10 buffer keeps the card's
# accent stripe clear of the subtitle baseline.
OUTRO_TITLE_GIANT_H = 72
OUTRO_SUBTITLE_H = 26


def outro_card_rect(config: Config) -> pygame.Rect:
    """Stable rect for the outro recap card — keeps the input handler and
    renderer aligned regardless of font metrics on the running platform."""
    w = config.display.width
    h = config.display.height
    card_top = OUTRO_TITLE_Y + OUTRO_TITLE_GIANT_H + OUTRO_SUBTITLE_H + 24
    button_top = h - 30 - GAME_OVER_BTN_H
    max_h = button_top - card_top - 12
    card_h = min(OUTRO_CARD_H, max_h)
    return pygame.Rect((w - OUTRO_CARD_W) // 2, card_top, OUTRO_CARD_W, card_h)


def outro_tab_rects(config: Config, card_rect: pygame.Rect) -> list[pygame.Rect]:
    """Three pill tabs across the top of the outro recap card."""
    tab_w = (card_rect.width - 60) // 3
    tab_h = 28
    tab_y = card_rect.top + 14
    gap = 6
    return [
        pygame.Rect(card_rect.left + 16 + i * (tab_w + gap), tab_y, tab_w, tab_h)
        for i in range(3)
    ]


def skill_tree_close_button_rect(config: Config) -> pygame.Rect:
    """× close button in the top-right corner of the evolution panel.

    Touch-mode grows 28×28 → 48×48 so finger taps land on it. The
    visual × glyph in the renderer stays small — only the hit-test
    rect expands.
    """
    panel = evolution_panel_rect(config)
    size = MIN_TOUCH_TARGET if config.display.touch_mode else 28
    return pygame.Rect(panel.right - size - 14, panel.top + 14, size, size)


def evolution_panel_rect(config: Config) -> pygame.Rect:
    """Now houses the catalog-driven skill tree (was humanity evolution tree)."""
    w, h = config.display.width, config.display.height
    pw = min(1100, w - 60)
    ph = min(720, h - 50)
    return pygame.Rect((w - pw) // 2, (h - ph) // 2, pw, ph)


SKILL_TREE_AXES = ("Intensite", "Portee", "Duree", "Impact Ecologique")
SKILL_TREE_AXIS_LABELS = {
    "Intensite": "INTENSITÉ",
    "Portee": "PORTÉE",
    "Duree": "DURÉE",
    "Impact Ecologique": "IMPACT ÉCOLOGIQUE",
}
SKILL_TIER_LABELS = ("FONDATIONS", "AMPLIFICATION", "TRANSFORMATION")
SKILL_TIER_LABELS_SHORT = ("FOND.", "AMPL.", "TRANS.")

# Per-axis identity colours — used by the outro IMPACTS rows + PARCOURS
# tiles so each axis carries a consistent visual signature across
# screens. Warm coral for intensity (striking impact), cool blue for
# reach (distance), amber for duration (time), sage for ecology (life).
AXIS_COLORS: dict[str, tuple[int, int, int]] = {
    "Intensite":        (235, 110, 95),
    "Portee":           (110, 160, 230),
    "Duree":            (220, 180, 90),
    "Impact Ecologique": (110, 200, 130),
}


def _axis_color(axis_name: str) -> tuple[int, int, int]:
    return AXIS_COLORS.get(axis_name, (140, 150, 170))


def skill_tree_axis_tab_rects(config: Config) -> dict[str, pygame.Rect]:
    """4 axis tab rects, evenly distributed under the panel header.

    Touch mode bumps tab height 36 → 44 px to give fingers a fairer
    target. The grid below sits at a hardcoded ``panel.top + 144``
    so the bump just shrinks the gap from 22 → 14 px — still
    adequate breathing room and no card/grid layout change. Desktop
    keeps 36 to preserve the existing visual rhythm.
    """
    panel = evolution_panel_rect(config)
    tab_top = panel.top + 86
    tab_h = 44 if config.display.touch_mode else 36
    pad = 24
    available = panel.width - pad * 2
    tab_w = (available - 12 * 3) // 4
    rects: dict[str, pygame.Rect] = {}
    for i, axis in enumerate(SKILL_TREE_AXES):
        x = panel.left + pad + i * (tab_w + 12)
        rects[axis] = pygame.Rect(x, tab_top, tab_w, tab_h)
    return rects


SKILL_TREE_DETAIL_H = 168  # detail panel — tightened from 200 to give the grid more room
# Width of the right-edge AMÉLIORER / VERROUILLÉ / cost button. Used by
# both the button rect and the detail-tab row's right-edge reservation
# so widening here automatically narrows the tab row in lockstep —
# previously the value lived as a magic 240 in two coupled places.
# Bumped 240 → 264 because the affordable CTA label
# "AMÉLIORER · +{cost} ÉN" at fonts.large measured 215-221 px across
# the actual in-game cost range (effective JSON cost × 2.50 multiplier
# = 12-88), so the prior 240 width (interior 216) ellipsised the
# label on every cost ≥ 25. 264 keeps the same fonts.large weight
# without ellipsis on the longest realistic label.
SKILL_TREE_ACTION_BTN_W = 264


def skill_tree_card_rects(config: Config) -> list[pygame.Rect]:
    """3×3 grid (tiers × skills) of skill-card rects in the active panel area.

    Layout reservation:
      header  — top 78px
      tabs    — 86..122 (36 high)
      column header bands — 144..176 (32 high, includes banner padding)
      cards   — fills remaining vertical space above the detail panel
      gap     — 10 px breathing room between last card row and detail panel
      detail panel — bottom SKILL_TREE_DETAIL_H px
    """
    panel = evolution_panel_rect(config)
    grid_left = panel.left + 24
    # Pulled up 10 px (154 → 144) so the grid + a 10 px gap below sit
    # cleanly above the detail panel instead of the last card row
    # touching the detail panel header.
    grid_top = panel.top + 144
    grid_w = panel.width - 48
    col_header_h = 32
    # Reserve 26 px below the grid: 16 native bottom padding + 10 px
    # explicit gap between the last card row and the detail panel.
    grid_h = panel.height - (grid_top - panel.top) - SKILL_TREE_DETAIL_H - 26
    cols = 3
    rows = 3
    col_gap = 18
    row_gap = 14
    card_w = (grid_w - col_gap * (cols - 1)) // cols
    card_h = (grid_h - col_header_h - row_gap * (rows - 1)) // rows
    rects: list[pygame.Rect] = []
    for r in range(rows):
        for c in range(cols):
            x = grid_left + c * (card_w + col_gap)
            y = grid_top + col_header_h + r * (card_h + row_gap)
            rects.append(pygame.Rect(x, y, card_w, card_h))
    return rects


def skill_tree_detail_panel_rect(config: Config) -> pygame.Rect:
    """The persistent detail/CTA panel below the skill grid."""
    panel = evolution_panel_rect(config)
    return pygame.Rect(
        panel.left + 24,
        panel.bottom - SKILL_TREE_DETAIL_H - 16,
        panel.width - 48,
        SKILL_TREE_DETAIL_H,
    )


def skill_detail_tab_rects(config: Config) -> list[pygame.Rect]:
    """Three pill tabs across the top of the skill detail content area.

    Touch mode bumps tab height 24 → 36 px (still pill-shaped, not
    a full 48-px square — the detail panel is only 168 px tall so
    a full 48 would eat too much content area). The renderer reads
    ``content_top = first_tab.bottom + 8`` (see
    ``_draw_skill_detail_panel``) so the scrollable content area
    auto-shrinks by 12 px on touch — acceptable since swipe-scroll
    is now wired and the content is paginated by tab anyway.
    Desktop keeps 24 to preserve the existing visual density.
    """
    panel = skill_tree_detail_panel_rect(config)
    # Sits just under the title/pip strip, left of the AMÉLIORER button.
    button_w = SKILL_TREE_ACTION_BTN_W
    text_x = panel.left + 18
    text_right = panel.left + panel.width - button_w - 36
    inner_w = text_right - text_x
    # Title was ``fonts.title`` (~30 px) — shrunk to ``fonts.large``
    # (~22 px), and the gap after the pips trimmed 4 → 2, pulling the
    # tab row up by ~10 px so the content band below has room to
    # breathe before the panel bottom.
    pad_top = 14 + 22 + 6 + 9
    tab_y = panel.top + pad_top + 2
    tab_h = 36 if config.display.touch_mode else 24
    gap = 4
    tab_w = (inner_w - gap * 2) // 3
    return [
        pygame.Rect(text_x + i * (tab_w + gap), tab_y, tab_w, tab_h)
        for i in range(3)
    ]


def skill_tree_action_button_rect(config: Config) -> pygame.Rect:
    """AMÉLIORER button on the right of the detail panel."""
    panel = skill_tree_detail_panel_rect(config)
    btn_w = SKILL_TREE_ACTION_BTN_W
    btn_h = 56
    return pygame.Rect(
        panel.right - btn_w - 18,
        panel.centery - btn_h // 2,
        btn_w, btn_h,
    )


def skill_tree_active_axis(game: "Game") -> str:
    """Return the currently displayed axis, falling back to a sensible default."""
    if game.skill_tree_axis in SKILL_TREE_AXES:
        return game.skill_tree_axis
    return SKILL_TREE_AXES[0]


def skill_tree_skills_for_axis(game: "Game", axis: str) -> list[tuple[str, "Skill"]]:
    """Flatten the active axis to a list of (tier_label, skill) in row order.

    Row r, column c → tier r, skill c. Side-aware: GAIA uses the catastrophe
    ladder from skills.json, HUMANITÉ uses the parallel defensive ladder.
    """
    side = getattr(game, "player_side", "gaia")
    catalog = game.skill_catalog.for_catastrophe_side(
        game.gaia.active.name, side,
    )
    if catalog is None:
        return []
    target = catalog.axis(axis)
    if target is None:
        return []
    flat: list[tuple[str, "Skill"]] = []
    for tier in target.tiers[:3]:
        for skill in tier.skills[:3]:
            flat.append((tier.name, skill))
    return flat


def evolution_node_rects(config: Config) -> dict[str, pygame.Rect]:
    """Stable mapping from node id to screen rect, derived from layout constants."""
    panel = evolution_panel_rect(config)
    rows_top = panel.top + 78
    rects: dict[str, pygame.Rect] = {}
    nodes_x = panel.left + EVO_ROW_LABEL_W
    for row_idx, branch in enumerate(BRANCHES):
        y = rows_top + row_idx * (EVO_NODE_H + EVO_ROW_GAP)
        for tier in range(4):
            x = nodes_x + tier * (EVO_NODE_W + EVO_NODE_GAP_X)
            rects[f"{branch}_{tier}"] = pygame.Rect(x, y, EVO_NODE_W, EVO_NODE_H)
    return rects


PICKER_CATASTROPHES = ("Eau", "Feu", "Terre", "Air", "Vie")
PICKER_DIFFICULTIES = ("FACILE", "NORMAL", "BRUTAL")

# Per-catastrophe tagline shown above the briefing panel's stat bars.
# Two-clause "active narration — countermeasure" format. The narration
# clause uses subject-verb-object descriptions of the catastrophe in
# motion (no ``qui souffle / qui submerge / qui consume`` metaphor
# patterns that the earlier "Source de toute vie, force qui submerge"
# tagline leaned on); the action clause keeps the source pedagogy
# doc's "À RETENIR" verb set. Sits between a metaphor-heavy version
# (too literary for a picker the player spends ~10 s on) and a flat
# noun-list version (too utilitarian, indistinguishable from the
# CATASTROPHE_LEARN keyword chip already shown right next to it).
CATASTROPHE_TAGLINES: dict[str, str] = {
    "Eau":   "L'eau monte, les côtes reculent — anticiper, protéger.",
    "Feu":   "Le feu progresse, l'air s'empoisonne — détecter tôt, reboiser.",
    "Terre": "Le sol tremble, les pentes cèdent — bâtir parasismique.",
    "Air":   "Les vents s'intensifient, les côtes érodent — prévoir, abriter.",
    "Vie":   "Les pathogènes circulent, les systèmes saturent — soigner, isoler.",
}

# Three-term keyword strip shown on each catastrophe briefing card —
# "ce que vous découvrirez" framing for the picker. Was uneven: three
# entries had three terms, but Terre and Air only had two — visually
# breaking the rhythm of the picker card row. Normalised to three
# terms each, with the added items drawn from concepts the source
# pedagogy doc (faits_planete.txt) names as central:
#   * Terre adds TSUNAMI — the doc's "Du côté de la catastrophe"
#     section opens on sea-floor earthquakes and tsunami chains.
#   * Air adds SUBMERSIONS — the doc's headline insight that the
#     majority of cyclone damage comes from water (storm surge +
#     torrential rain), not wind.
# Both additions also pair with their existing LOADING_FACTS entries
# (the "danser avec la secousse" / "majorité des dégâts vient de
# l'eau" facts), so the strip flows into the loading-bridge content.
CATASTROPHE_LEARN: dict[str, str] = {
    "Eau":   "CRUES · ÉROSION · MARÉES",
    "Feu":   "COMBUSTION · FUMÉE · ALBÉDO",
    "Terre": "MAGNITUDE · LIQUÉFACTION · TSUNAMI",
    "Air":   "CYCLONES · COURANTS-JETS · SUBMERSIONS",
    # "R0" replaced with "CONTAGION" — the epidemiology variable name
    # is precise but doesn't decode without a science background, while
    # the other four catastrophes' chips lead with words a general
    # audience already owns ("CRUES", "COMBUSTION", "MAGNITUDE",
    # "CYCLONES"). "CONTAGION" is the player-facing concept R0 is a
    # mathematical handle for.
    "Vie":   "CONTAGION · MUTATIONS · IMMUNITÉ",
}

# A one-line scientific reference shown under the stat bars in the
# catastrophe briefing panel — picks up an anchor fact every time the
# player selects a card. Each line carries a citing authority prefix
# (GIEC / OMM / OMS / USGS) — the acronym signals "this is sourced
# science, not flavour text" to the player, which matters for an
# educational picker. Only the Vie line's internal vocabulary has
# been reworked: the previous "avec R0 = 3" required familiarity with
# the epidemiology basic-reproduction-number variable, so the same
# threshold is now stated in plain language ("si chaque malade en
# contamine 3 autres") that any reader can parse on first pass.
CATASTROPHE_REFERENCES: dict[str, str] = {
    "Eau":   "GIEC : +1 m d'élévation expose 230 M de personnes en zone côtière.",
    "Feu":   "OMM : 2023 a brûlé près de 8 M d'hectares de forêt boréale.",
    "Terre": "USGS : une magnitude 9 libère ~32× l'énergie d'une magnitude 8.",
    "Air":   "OMM : un cyclone de catégorie 5 libère ~10 000 fois plus d'énergie qu'une bombe A.",
    "Vie":   "OMS : si chaque malade en contamine 3 autres, ~60 % d'une population non immunisée est touchée.",
}

# Side-agnostic descriptions of what each difficulty tuning does to the
# simulation. The runtime appends a player-difficulty hint via
# `_difficulty_player_hint` so labels remain consistent but the consequence
# for the player is explicit.
DIFFICULTY_BULLETS: dict[str, tuple[str, str, str]] = {
    # Vocabulary aligned with ``_difficulty_player_hint`` below:
    # ``atténuée`` / ``amplifiée`` for the catastrophe-strength
    # modulation. The bullets previously read "Catastrophe modérée /
    # extrême" while the hint right beside them on the same card said
    # "Catastrophe atténuée / amplifiée" — two vocabularies for the
    # same concept on the same card. The hint's comment already
    # documents why "atténuée / amplifiée" is the right reading
    # (a *choice that shapes* the upcoming sim, not an outcome);
    # the bullets just hadn't been brought in line.
    "FACILE": (
        "Catastrophe atténuée, ressources généreuses.",
        "Sociétés préparées, alertes rapides.",
        "",  # side hint slot, filled at draw time
    ),
    "NORMAL": (
        "Catastrophe équilibrée, ressources comptées.",
        "Réponses partielles, défis quotidiens.",
        "",
    ),
    "BRUTAL": (
        "Catastrophe amplifiée, ressources rares.",
        "Sociétés fragilisées, coopération difficile.",
        "",
    ),
}


def _difficulty_player_hint(label: str, side: str) -> str:
    """Hint that flips per-side so the player knows whether the difficulty
    favours them. FACILE = weak catastrophe → easy for HUMANITÉ, hard for GAIA.

    Word choice: previously "Catastrophe contenue" read as "the
    catastrophe is over" — semantically wrong for a difficulty that
    *modulates* the catastrophe's strength before the run starts.
    Switched to "Catastrophe atténuée" ("mitigated") for FACILE and
    "Catastrophe amplifiée" for BRUTAL — these read as choices that
    shape the upcoming simulation, not descriptions of an outcome.
    """
    if side == "gaia":
        return {
            "FACILE": "⚠ Catastrophe atténuée : votre tâche sera difficile.",
            "NORMAL": "Difficulté standard pour les deux camps.",
            "BRUTAL": "✓ Catastrophe amplifiée : avantage pour la Planète.",
        }.get(label, "")
    return {
        "FACILE": "✓ Catastrophe atténuée : avantage pour l'humanité.",
        "NORMAL": "Difficulté standard pour les deux camps.",
        "BRUTAL": "⚠ Catastrophe amplifiée : votre tâche sera difficile.",
    }.get(label, "")


# Briefing-room layout constants for the new picker. Tuned so the cards
# occupy the upper third only — the lower 2/3 stays clear for country clicks.
PICKER_CARD_W = 160
PICKER_CARD_H = 200
PICKER_CARD_GAP = 12
PICKER_CARDS_TOP = 150  # under the stepper + title + tagline
PICKER_DIFF_CARD_W = 210
PICKER_DIFF_CARD_H = 200
PICKER_DIFF_GAP = 14
PICKER_DIFF_TOP_OFFSET = 8  # gap between catastrophe row and difficulty row
PICKER_LAUNCH_BTN_W = 460
PICKER_LAUNCH_BTN_H = 54


def picker_side_card_rects(config: Config) -> list[pygame.Rect]:
    """Two large side-selection cards centred on the side-picker step."""
    w, h = config.display.width, config.display.height
    card_w = 290
    card_h = 320  # taller — was 280; the wrapped sub text bled past the card
    gap = 24
    total = card_w * 2 + gap
    left = (w - total) // 2
    top = (h - card_h) // 2 - 20
    return [
        pygame.Rect(left, top, card_w, card_h),
        pygame.Rect(left + card_w + gap, top, card_w, card_h),
    ]


def picker_nav_button_rects(config: Config) -> dict[str, pygame.Rect]:
    """PRÉCÉDENT / SUIVANT (or LANCER) buttons at the bottom of the picker."""
    w, h = config.display.width, config.display.height
    btn_h = 48
    next_w = 320
    prev_w = 160
    y = h - btn_h - 40
    cx = w // 2
    return {
        "prev": pygame.Rect(cx - next_w // 2 - prev_w - 16, y, prev_w, btn_h),
        "next": pygame.Rect(cx - next_w // 2, y, next_w, btn_h),
    }


def picker_pill_rects(config: Config) -> dict[str, list[tuple[str, pygame.Rect]]]:
    """Briefing-card rects: ``{kind: [(value, rect), ...]}``.

    Compatibility-named (the old "pill" model is gone — these are now full
    briefing cards). ``kind`` is "catastrophe" (5 cards) or "difficulty" (3).
    """
    w, _ = config.display.width, config.display.height

    # Row 1: 5 catastrophe cards horizontally centered.
    total_cat_w = 5 * PICKER_CARD_W + 4 * PICKER_CARD_GAP
    cat_left = (w - total_cat_w) // 2
    catastrophe_cards: list[tuple[str, pygame.Rect]] = []
    for i, name in enumerate(PICKER_CATASTROPHES):
        x = cat_left + i * (PICKER_CARD_W + PICKER_CARD_GAP)
        catastrophe_cards.append((
            name,
            pygame.Rect(x, PICKER_CARDS_TOP, PICKER_CARD_W, PICKER_CARD_H),
        ))

    # Row 2: 3 difficulty cards centered.
    diff_y = PICKER_CARDS_TOP + PICKER_CARD_H + PICKER_DIFF_TOP_OFFSET
    total_diff_w = 3 * PICKER_DIFF_CARD_W + 2 * PICKER_DIFF_GAP
    diff_left = (w - total_diff_w) // 2
    difficulty_cards: list[tuple[str, pygame.Rect]] = []
    for i, label in enumerate(PICKER_DIFFICULTIES):
        x = diff_left + i * (PICKER_DIFF_CARD_W + PICKER_DIFF_GAP)
        difficulty_cards.append((
            label,
            pygame.Rect(x, diff_y, PICKER_DIFF_CARD_W, PICKER_DIFF_CARD_H),
        ))

    return {
        "catastrophe": catastrophe_cards,
        "difficulty": difficulty_cards,
    }


def picker_launch_button_rect(config: Config) -> pygame.Rect:
    """LANCER LA SIMULATION button — visible after a country is selected."""
    w, h = config.display.width, config.display.height
    return pygame.Rect(
        (w - PICKER_LAUNCH_BTN_W) // 2,
        h - NEWS_BAR_H - PICKER_LAUNCH_BTN_H - 18,
        PICKER_LAUNCH_BTN_W,
        PICKER_LAUNCH_BTN_H,
    )




def title_button_rects(config: Config) -> dict[str, pygame.Rect]:
    """Buttons on the title screen."""
    w, h = config.display.width, config.display.height
    cx = (w - TITLE_BTN_W) // 2
    play_y = h // 2 + 30
    return {
        "play": pygame.Rect(cx, play_y, TITLE_BTN_W, TITLE_BTN_H),
        "quit": pygame.Rect(
            cx, play_y + TITLE_BTN_H + TITLE_BTN_GAP, TITLE_BTN_W, TITLE_BTN_H
        ),
    }


def title_last_run_card_rect(config: Config) -> pygame.Rect:
    """Card above the JOUER button summarising the most-recent run, if any."""
    w, h = config.display.width, config.display.height
    card_w = 460
    card_h = 76
    return pygame.Rect((w - card_w) // 2, h // 2 - 60, card_w, card_h)


def game_over_button_rects(config: Config) -> dict[str, pygame.Rect]:
    """Buttons shown on the game-over overlay: restart / menu / quit.

    Anchored to the bottom edge so the variable-height stats card (which grows
    to fit the impact report) doesn't overlap the buttons.
    """
    w, h = config.display.width, config.display.height
    total_w = GAME_OVER_BTN_W * 3 + GAME_OVER_BTN_GAP * 2
    y = h - 30 - GAME_OVER_BTN_H
    left_x = (w - total_w) // 2
    step = GAME_OVER_BTN_W + GAME_OVER_BTN_GAP
    return {
        "restart": pygame.Rect(left_x, y, GAME_OVER_BTN_W, GAME_OVER_BTN_H),
        "menu": pygame.Rect(left_x + step, y, GAME_OVER_BTN_W, GAME_OVER_BTN_H),
        "quit": pygame.Rect(left_x + 2 * step, y, GAME_OVER_BTN_W, GAME_OVER_BTN_H),
    }


# Milestone banner dimensions — generous box so a 2-line wrapped title
# fits without ellipsising. Updated from the previous 360×56 layout
# (where long titles got truncated mid-word).
MILESTONE_BANNER_W = 440
MILESTONE_BANNER_H = 80
MILESTONE_BANNER_GAP = 8
MILESTONE_CLOSE_SIZE = 22


def milestone_banner_rects(config: Config, count: int) -> list[pygame.Rect]:
    """Stacked central-top milestone banner rects (newest at the top).

    Anchored to the visible map centre rather than the canvas centre so
    the banners stay aligned with the world view whether the sidebar is
    collapsed or expanded.
    """
    if count <= 0:
        return []
    w = config.display.width
    # When the sidebar is rendered, account for it when picking the
    # visual centre; otherwise centre on the canvas. The renderer
    # tracks the current sidebar state on ``self._last_sidebar_collapsed``
    # but we don't have a renderer reference here — assume collapsed,
    # which is the default. (Input handler hit-tests use the same rect,
    # so the worst case is "banners are a few pixels left of perfect
    # centre when the sidebar is open" — still clickable.)
    map_right = w  # collapsed default
    anchor_x = (map_right - MILESTONE_BANNER_W) // 2
    anchor_y = TOP_BAR_H + 12
    return [
        pygame.Rect(
            anchor_x,
            anchor_y + i * (MILESTONE_BANNER_H + MILESTONE_BANNER_GAP),
            MILESTONE_BANNER_W,
            MILESTONE_BANNER_H,
        )
        for i in range(count)
    ]


def milestone_banner_close_rect(
    banner_rect: pygame.Rect, *, touch_mode: bool = False,
) -> pygame.Rect:
    """× close-button rect inside a milestone banner (top-right corner).

    Touch-mode grows the hit rect 22×22 → 48×48 so finger taps land on
    it. The visual × glyph (drawn separately in
    ``_draw_milestone_close_glyph``) keeps its 22 px size — only the
    tappable rect expands. Caller passes ``touch_mode`` because this
    helper is invoked from both the renderer (has Config) and the
    input handler (also has Config) — exposing it as a kwarg keeps
    the helper signature stable across both call sites.
    """
    size = MIN_TOUCH_TARGET if touch_mode else MILESTONE_CLOSE_SIZE
    return pygame.Rect(
        banner_rect.right - size - 8,
        banner_rect.top + 8,
        size,
        size,
    )


def info_panel_tab_rects(config: Config) -> list[pygame.Rect]:
    """Three pill tabs across the top of the info panel body (BILAN / ÉQUILIBRE / TENDANCE)."""
    panel_x = 16
    panel_y = TOP_BAR_H + 16
    header_h = 60
    tab_y = panel_y + header_h + 10
    tab_h = 32
    pad = 16
    inner_w = INFO_PANEL_W - pad * 2
    gap = 4
    tab_w = (inner_w - gap * 2) // 3
    return [
        pygame.Rect(panel_x + pad + i * (tab_w + gap), tab_y, tab_w, tab_h)
        for i in range(3)
    ]


def sidebar_toggle_rect(config: Config, collapsed: bool) -> pygame.Rect:
    """Chevron pill that hides / shows the right dashboard panel."""
    w, h = config.display.width, config.display.height
    btn_w, btn_h = 22, 56
    if collapsed:
        x = w - btn_w - 4
    else:
        x = w - RIGHT_PANEL_W - btn_w - 2
    y = TOP_BAR_H + (h - TOP_BAR_H - NEWS_BAR_H - btn_h) // 2
    return pygame.Rect(x, y, btn_w, btn_h)


def recenter_map_button_rect(config: Config) -> pygame.Rect:
    """Discrete "fit to screen" button at the bottom-left of the map.

    Resets ``world.scale`` and ``world.offset_x/y`` to defaults so the
    player can recover from a deep zoom or panned-off-edge view in
    one tap instead of pinch-zooming back to fit. Lives just inside
    the map's bottom-left corner so it sits in dead space the eye
    rarely tracks during gameplay — visible enough to find when
    needed, ignorable otherwise.

    Touch-mode bumps the size 28 → 44 to clear the Material Design
    minimum tap target. Both sizes square so the icon (centred
    cross-hairs) renders symmetrically.
    """
    h = config.display.height
    size = MIN_TOUCH_TARGET if config.display.touch_mode else 28
    # Bottom-left of map area: 10px in from left, 10px above news ticker.
    return pygame.Rect(10, h - NEWS_BAR_H - 10 - size, size, size)


def minimap_rect(config: Config) -> pygame.Rect:
    """Mini-globe at the top of the right panel — click to jump-pan the map."""
    panel_left = config.display.width - RIGHT_PANEL_W
    # Shorter at 96 (was 124) — the main map is now large and readable, so the
    # mini-globe just needs to give context, not be a hero element.
    return pygame.Rect(panel_left + 12, TOP_BAR_H + 12, RIGHT_PANEL_W - 24, 96)


def minimap_to_world(config: Config, point: tuple[int, int]) -> tuple[float, float]:
    """Convert a minimap-pixel point to (lon, lat) world coords."""
    mm = minimap_rect(config)
    x, y = point
    lon = -180.0 + (x - mm.left) * 360.0 / max(1, mm.width)
    lat = 90.0 - (y - mm.top) * 180.0 / max(1, mm.height)
    return lon, lat


def speed_button_rects(config: Config) -> dict[int, pygame.Rect]:
    """Top-bar speed buttons keyed by speed value (0=pause, 1/2/3=play)."""
    speeds = (0, 1, 2, 3)
    total_w = len(speeds) * SPEED_BUTTON_W + (len(speeds) - 1) * SPEED_BUTTON_GAP
    start_x = (config.display.width - total_w) // 2 - 200
    y = (TOP_BAR_H - SPEED_BUTTON_H) // 2 + 2
    return {
        speed: pygame.Rect(
            start_x + i * (SPEED_BUTTON_W + SPEED_BUTTON_GAP),
            y,
            SPEED_BUTTON_W,
            SPEED_BUTTON_H,
        )
        for i, speed in enumerate(speeds)
    }


EVOLUTION_DNA_BTN_W = 158


def evolution_dna_badge_rect(config: Config) -> pygame.Rect:
    """Top-bar DNA / skill-tree button — clicking it opens the evolution overlay.

    Combines the catastrophe DNA icon + ÉNERGIE caption + point count into a
    single visible pill at the top-right so the route to the skill tree is
    discoverable instead of an invisible hit-rect.
    """
    w = config.display.width
    return pygame.Rect(
        w - PAD - EVOLUTION_DNA_BTN_W, 10,
        EVOLUTION_DNA_BTN_W, TOP_BAR_H - 20,
    )


def audio_toggle_rect(config: Config) -> pygame.Rect:
    """Top-bar audio toggle, just left of the DNA badge.

    Touch-mode bumps the height from 32 → 48 (Material Design min)
    so a finger tap reliably lands on it. Centred vertically in the
    top bar so the visual position is unchanged for the eye.
    """
    dna = evolution_dna_badge_rect(config)
    w = 56
    h = MIN_TOUCH_TARGET if config.display.touch_mode else TOP_BAR_H - 28
    return pygame.Rect(dna.left - 8 - w, (TOP_BAR_H - h) // 2, w, h)


SETTINGS_PANEL_W = 640
# Trimmed from 460 → 360 — the accessibility tab tops out at 3 rows and
# the audio tab has just 1, so 460 left ~130 px of dead space below the
# content. 360 keeps a comfortable hint-row gap on the 3-row case.
SETTINGS_PANEL_H = 360


def settings_panel_rect(config: Config) -> pygame.Rect:
    w, h = config.display.width, config.display.height
    return pygame.Rect(
        (w - SETTINGS_PANEL_W) // 2,
        (h - SETTINGS_PANEL_H) // 2,
        SETTINGS_PANEL_W, SETTINGS_PANEL_H,
    )


def settings_tab_rects(config: Config) -> dict[str, pygame.Rect]:
    """Pill tabs for the settings modal.

    Tabs sit below the RÉGLAGES tag + PARAMÈTRES title block. Was at +64
    which collided with the redesigned header — now at +78 with extra
    breathing room.
    """
    panel = settings_panel_rect(config)
    tab_w = (panel.width - 60) // 2
    tab_y = panel.top + 78
    tab_h = 36
    return {
        "audio": pygame.Rect(panel.left + 20, tab_y, tab_w, tab_h),
        "accessibility": pygame.Rect(panel.left + 40 + tab_w, tab_y, tab_w, tab_h),
    }


def settings_toggle_rects(config: Config) -> dict[str, pygame.Rect]:
    """Toggle rects for settings rows. Keyed by toggle id.

    Each tab indexes its own toggles from row 0 — so ``mute`` (the only
    audio tab toggle) sits at row 0, and the three accessibility toggles
    also start at row 0. Previously the enumeration was global which made
    the accessibility tab's labels sit at row 0/1/2 while their toggles
    floated at row 1/2/3 — a visible one-row vertical misalignment.

    Touch-mode bumps each pill from 80×32 to 80×48 so finger taps land
    cleanly on the on/off body of the toggle.
    """
    panel = settings_panel_rect(config)
    rows_top = panel.top + 130
    row_h = 56
    toggle_w = 80
    toggle_h = MIN_TOUCH_TARGET if config.display.touch_mode else 32

    def _rect_at(row: int) -> pygame.Rect:
        return pygame.Rect(
            panel.right - 30 - toggle_w,
            rows_top + row * row_h + (row_h - toggle_h) // 2,
            toggle_w, toggle_h,
        )

    return {
        "mute":          _rect_at(0),
        "reduce_motion": _rect_at(0),
        "disable_flash": _rect_at(1),
        "high_contrast": _rect_at(2),
    }


def settings_close_rect(config: Config) -> pygame.Rect:
    """Close × in the top-right of the settings modal.

    Touch-mode grows 28×28 → 48×48 (Material Design min) while
    keeping the top-right alignment so the visual identity is
    unchanged.
    """
    panel = settings_panel_rect(config)
    size = MIN_TOUCH_TARGET if config.display.touch_mode else 28
    return pygame.Rect(panel.right - 28 - size, panel.top + 14, size, size)


PAUSE_MENU_W = 360
PAUSE_MENU_BTN_H = 52
PAUSE_MENU_BTN_GAP = 10


def pause_menu_button_rects(config: Config) -> dict[str, pygame.Rect]:
    """Stack of buttons for the pause menu.

    Three visual groups, each separated by an extra gap so the destructive
    actions never sit next to the safe ones (mis-click protection):

        REPRENDRE                       (primary action)
        ────
        RECOMMENCER · PARAMÈTRES · AIDE (safe utility actions)
        ────
        ABANDONNER · QUITTER LE JEU     (destructive — separated)
    """
    w, h = config.display.width, config.display.height
    keys = (
        "resume", "restart", "settings", "help", "abandon", "quit",
    )
    # Each key's extra top-gap (in addition to PAUSE_MENU_BTN_GAP). 'restart'
    # and 'abandon' open new groups so they get a slightly bigger top margin.
    group_lead = {"restart": 10, "abandon": 14}
    total_h = (
        len(keys) * PAUSE_MENU_BTN_H
        + (len(keys) - 1) * PAUSE_MENU_BTN_GAP
        + sum(group_lead.values())
    )
    top = (h - total_h) // 2
    left = (w - PAUSE_MENU_W) // 2
    rects: dict[str, pygame.Rect] = {}
    y = top
    for i, key in enumerate(keys):
        if i > 0:
            y += PAUSE_MENU_BTN_GAP + group_lead.get(key, 0)
        rects[key] = pygame.Rect(left, y, PAUSE_MENU_W, PAUSE_MENU_BTN_H)
        y += PAUSE_MENU_BTN_H
    return rects


def pause_confirm_button_rects(config: Config) -> dict[str, pygame.Rect]:
    """Confirm/cancel buttons that appear over the pause menu for destructive actions."""
    w, h = config.display.width, config.display.height
    btn_w = 160
    btn_h = 48
    gap = 16
    total = btn_w * 2 + gap
    left = (w - total) // 2
    y = h // 2 + 30
    return {
        "confirm": pygame.Rect(left, y, btn_w, btn_h),
        "cancel": pygame.Rect(left + btn_w + gap, y, btn_w, btn_h),
    }


def help_button_rect(config: Config) -> pygame.Rect:
    """Top-bar ? help toggle, between the audio toggle and the speed buttons.

    Touch-mode widens 30 → 48 to meet the tap minimum on both axes.
    """
    audio = audio_toggle_rect(config)
    w = MIN_TOUCH_TARGET if config.display.touch_mode else 30
    return pygame.Rect(audio.left - (w + 8), audio.top, w, audio.height)


def tutorial_button_rect(config: Config) -> pygame.Rect:
    """Discrete "Tutoriel" chip at the top-left of the map area.

    Lives just inside the map rect so it reads as an in-world affordance
    (next to the simulation it explains), not a top-bar control alongside
    Help / Audio. Sized small enough to be ignorable (118 × 26 px) but
    visible — a play-triangle glyph + the word "TUTORIEL" — so a new
    player notices and a returning player doesn't.

    Touch-mode bumps the height 26 → 48 so the chip is reliably
    tappable. Width stays at 118 (long axis already comfortable).
    """
    h = MIN_TOUCH_TARGET if config.display.touch_mode else 26
    return pygame.Rect(12, TOP_BAR_H + 10, 118, h)


def tutorial_overlay_button_rects(config: Config) -> dict[str, pygame.Rect]:
    """Bottom-of-modal nav buttons for the tutorial overlay.

    Returned keys: ``skip`` (left, secondary) and ``next`` (right,
    primary). ``next`` label switches to ``COMMENCER`` on the last
    slide — the medium font renders that label at ~111 px which
    overflowed the previous 120 px button (which had only ~104 px of
    interior after the rounded-corner padding). Widened ``next`` to
    144 px (≈ 128 px interior); ``skip`` stays at 120 since ``PASSER``
    is only ~64 px wide. Right margin (24 px from modal edge) is
    preserved so the visual alignment with the modal close × matches.
    """
    w, h = config.display.width, config.display.height
    modal_w, modal_h = 560, 340
    modal_left = (w - modal_w) // 2
    modal_top = (h - modal_h) // 2
    btn_h = 36
    btn_y = modal_top + modal_h - btn_h - 20
    next_w = 144
    return {
        "skip": pygame.Rect(modal_left + 24, btn_y, 120, btn_h),
        "next": pygame.Rect(
            modal_left + modal_w - 24 - next_w, btn_y, next_w, btn_h,
        ),
    }


def _progress_color(progress: float) -> tuple[int, int, int]:
    """Severity colour for a "progress" indicator (higher = better).

    Unified with the LIGHT_DANGER / LIGHT_WARNING / LIGHT_SUCCESS
    constants so the HUD's ÉQUILIBRE counter, the BILAN tab fill, the
    country balance value, and the outro balance card all speak the
    same colour vocabulary as the sparkline chips / TENDANCE tab
    (which route through ``_indicator_color`` using the LIGHT_* set).
    Was a parallel set of slightly darker / less-saturated literal
    tuples — (210, 60, 50) vs LIGHT_DANGER's (242, 110, 100), etc. —
    that left two sibling cells in the same panel disagreeing about
    which "red" meant *critical*. Threshold bands are kept at the
    inverted 0.33 / 0.66 the caller semantics expect (higher progress
    is better here, whereas ``_indicator_color`` reads the same way
    via the ``1 - state`` convention its callers use).
    """
    if progress < 0.33:
        return LIGHT_DANGER
    if progress < 0.66:
        return LIGHT_WARNING
    return LIGHT_SUCCESS


def _shade(color: tuple, factor: float) -> tuple:
    """Multiply RGB channels by ``factor``; preserve alpha if present."""
    if len(color) == 4:
        r, g, b, a = color
        return (
            max(0, min(255, int(r * factor))),
            max(0, min(255, int(g * factor))),
            max(0, min(255, int(b * factor))),
            a,
        )
    r, g, b = color
    return (
        max(0, min(255, int(r * factor))),
        max(0, min(255, int(g * factor))),
        max(0, min(255, int(b * factor))),
    )


def _difficulty_color(difficulty: Difficulty, palette: Palette) -> tuple[int, int, int]:
    # CASUAL was hardcoded ``(90, 200, 130)`` — literally LIGHT_SUCCESS,
    # so the colour was already centralised, just written by hand here.
    # Reference the constant directly so any future tonal shift on the
    # success colour propagates to the difficulty chip in lockstep with
    # the rest of the dashboard.
    if difficulty is Difficulty.CASUAL:
        return LIGHT_SUCCESS
    if difficulty is Difficulty.BRUTAL:
        return palette.severe
    return palette.text


def _country_color(country: Country, palette: Palette) -> tuple[int, int, int]:
    """Severity gradient: healthy → affected → severe → dead.

    Stays with **linear RGB** blending between palette stops despite
    its muddy mid-tones, because the alternatives are semantically
    worse:

      * HSV short-way: when the endpoint hues span > 180° of the
        wheel (healthy blue ↔ affected orange = 184°), the "short
        way" detours through purple/magenta — producing artificial
        vibrant colour stops mid-transition that don't match the
        "country is slipping" semantic.
      * HSV long-way: same problem in the opposite direction
        (detours through green).

    The RGB midpoint's wash through neutral tones is actually the
    right visual idiom for "country is between two states" — the
    eye reads the desaturated mid-tone as *transition*, not as a
    distinct state. The vibrancy concern is addressed downstream
    in ``_draw_world`` by lifting chroma after the blend (see the
    saturation-lift block — ``× 1.30`` factor).
    """
    s = country.state
    if s < 0.33:
        return _blend(palette.healthy, palette.affected, s / 0.33)
    if s < 0.66:
        return _blend(palette.affected, palette.severe, (s - 0.33) / 0.33)
    return _blend(palette.severe, palette.dead, (s - 0.66) / 0.34)


def _blend(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    ratio: float,
) -> tuple[int, int, int]:
    ratio = max(0.0, min(1.0, ratio))
    return (
        int(start[0] + (end[0] - start[0]) * ratio),
        int(start[1] + (end[1] - start[1]) * ratio),
        int(start[2] + (end[2] - start[2]) * ratio),
    )


def _blend_hsv(
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    ratio: float,
) -> tuple[int, int, int]:
    """Perceptually-richer interpolation through HSV space.

    Three-channel walk:
      * Hue: takes the *short way* around the colour wheel (so e.g.
        blending red H≈0 with magenta H≈0.83 goes the short way via
        wrap-around, not the long way through green-blue).
      * Saturation: linear between endpoint saturations.
      * Value: linear between endpoint values.

    The end result is that mid-blends stay *saturated* — a 50 %
    blend between two pure but different-hue colours produces a
    third saturated colour, not a desaturated mud average. The
    difference matters most visibly when the endpoint hues are far
    apart (≥ 60° on the wheel), which is exactly the case for the
    country state ramp (blue-grey → amber → coral → wine spans
    most of the visible wheel).

    Uses ``colorsys`` which is implemented in CPython itself —
    micro-cost (~5 µs per call). For ~239 countries per frame this
    is negligible relative to the polygon fills.
    """
    import colorsys
    ratio = max(0.0, min(1.0, ratio))
    h1, s1, v1 = colorsys.rgb_to_hsv(
        start[0] / 255.0, start[1] / 255.0, start[2] / 255.0,
    )
    h2, s2, v2 = colorsys.rgb_to_hsv(
        end[0] / 255.0, end[1] / 255.0, end[2] / 255.0,
    )
    # Take the short way around the hue wheel.
    dh = h2 - h1
    if dh > 0.5:
        dh -= 1.0
    elif dh < -0.5:
        dh += 1.0
    h = (h1 + dh * ratio) % 1.0
    s = s1 + (s2 - s1) * ratio
    v = v1 + (v2 - v1) * ratio
    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))


def _wrap(text: str, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + (1 if current else 0) <= max_chars:
            current = f"{current} {word}".strip()
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines or [text]


def _fmt_big(n: int) -> str:
    """Compact number format: 1234 → 1,234; 1_500_000 → 1.5M."""
    if n >= 1_000_000_000:
        return f"{n / 1_000_000_000:.2f}Md"
    if n >= 1_000_000:
        return f"{n / 1_000_000:.2f}M"
    if n >= 10_000:
        return f"{n / 1_000:.1f}k"
    return f"{n:,}".replace(",", " ")
