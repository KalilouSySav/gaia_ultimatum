"""Translate pygame events into game-state mutations."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from gaia_ultimatum.config import Config
from gaia_ultimatum.models import Game, GameEvent, Phase
from gaia_ultimatum.models.catastrophe import CatastrophePoint
from gaia_ultimatum.view.renderer import (
    NEWS_BAR_H,
    RIGHT_PANEL_W,
    TOP_BAR_H,
    audio_toggle_rect,
    close_button_rect,
    evolution_dna_badge_rect,
    evolution_panel_rect,
    game_over_button_rects,
    help_button_rect,
    minimap_rect,
    minimap_to_world,
    pause_confirm_button_rects,
    pause_menu_button_rects,
    picker_launch_button_rect,
    picker_pill_rects,
    settings_close_rect,
    settings_panel_rect,
    settings_tab_rects,
    settings_toggle_rects,
    skill_tree_action_button_rect,
    title_last_run_card_rect,
    skill_tree_active_axis,
    skill_tree_axis_tab_rects,
    skill_tree_card_rects,
    skill_tree_skills_for_axis,
    speed_button_rects,
    title_button_rects,
    tutorial_button_rect,
    tutorial_overlay_button_rects,
)


@dataclass
class _DragState:
    start: tuple[int, int]
    initial_offset: tuple[float, float]


PAN_SPEED_PX = 8

# Pinch-zoom sensitivity. SDL's MULTIGESTURE.dDist reports the *change*
# in distance between two fingers as a fraction of the canvas diagonal
# per event (typical magnitudes 0.001–0.02 per gesture frame). Mapping
# to ``world.scale`` directly would feel either glacial (raw) or
# uncontrollable (×100). 25 lands the sensitivity where a comfortable
# 4 cm finger spread roughly doubles the zoom — close to how the
# mouse-wheel ``zoom_step`` (1.10×) feels per detent on desktop.
PINCH_ZOOM_SENSITIVITY = 25.0


class InputHandler:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._drag: _DragState | None = None
        self._hover_cache_pos: tuple[int, int] | None = None
        # Touch-swipe scroll state for the skill detail panel. Mobile
        # users can't reach a 6-px-wide scrollbar with a finger and the
        # mouse wheel doesn't exist on touch; instead, dragging a
        # finger vertically inside the panel's content area scrolls
        # like every other mobile list. Recorded on MOUSEBUTTONDOWN
        # inside the panel (but not on the scrollbar or tabs), applied
        # on MOUSEMOTION once total Δy exceeds the activation
        # threshold so a quick tap doesn't accidentally scroll.
        self._panel_swipe_start_y: int | None = None
        self._panel_swipe_start_scroll: int = 0
        self._panel_swipe_active: bool = False

    def update_camera(self, game: Game) -> None:
        """Per-frame: smooth-pan the map while arrow keys are held + refresh hover."""
        if game.phase is Phase.TITLE:
            game.hovered_country = None
            self._hover_cache_pos = None
            return
        if not (game.evolution_open or game.game_over):
            keys = pygame.key.get_pressed()
            panned = False
            if keys[pygame.K_LEFT]:
                game.world.offset_x += PAN_SPEED_PX
                panned = True
            if keys[pygame.K_RIGHT]:
                game.world.offset_x -= PAN_SPEED_PX
                panned = True
            if keys[pygame.K_UP]:
                game.world.offset_y += PAN_SPEED_PX
                panned = True
            if keys[pygame.K_DOWN]:
                game.world.offset_y -= PAN_SPEED_PX
                panned = True
            if panned:
                self._hover_cache_pos = None
        self._update_hover(game)

    def _update_hover(self, game: Game) -> None:
        """Cache hovered country on Game for the renderer; cheap when idle."""
        if (
            game.phase is Phase.TITLE
            or game.evolution_open
            or game.game_over
            or self._drag is not None
        ):
            game.hovered_country = None
            self._hover_cache_pos = None
            return
        pos = pygame.mouse.get_pos()
        if not self._inside_map(pos, game):
            game.hovered_country = None
            self._hover_cache_pos = pos
            return
        # Skip the polygon scan when the cursor hasn't moved since last frame.
        if pos == self._hover_cache_pos:
            return
        self._hover_cache_pos = pos
        map_point = game.world.inverse_transform(
            pos, (self.config.display.width, self.config.display.height)
        )
        game.hovered_country = game.world.country_at(map_point)

    def handle(self, event: pygame.event.Event, game: Game) -> bool:
        """Return False to signal the main loop to exit."""
        if event.type == pygame.QUIT:
            return False
        # MP4 cinematic is the topmost modal: every click / ESC / SPACE skips
        # straight to the destination screen so the player never feels stuck
        # in a video they've already seen. The cinematic name is marked
        # "played" so it won't reappear after a restart.
        if game.cinematic_playing is not None:
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self._skip_cinematic(game)
                return True
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN,
                pygame.K_AC_BACK,
            ):
                # K_AC_BACK is the Android system back button/gesture
                # (SDL maps the hardware/navigation back action to this
                # key on Android; it never fires on desktop). Treating
                # it as a cinematic-skip lets phone users dismiss a
                # video the same way Escape does on desktop.
                self._skip_cinematic(game)
                return True
            # Swallow other input while the cinematic is up so background
            # state isn't mutated by stale clicks/keys.
            return True
        if event.type == pygame.MOUSEBUTTONDOWN:
            self._on_mouse_down(event, game)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._drag = None
            # End any in-flight scrollbar drag too — both interactions
            # use the same left button, so a single ``MOUSEBUTTONUP``
            # clears both states.
            game.skill_detail_scroll_drag_y = None
            self._panel_swipe_start_y = None
            self._panel_swipe_active = False
        elif event.type == pygame.MOUSEMOTION:
            # Touch-swipe on the skill detail panel: track Δy from the
            # initial press; once it exceeds 8 px we commit to scroll
            # mode and update game.skill_detail_scroll. The threshold
            # keeps a slightly-shaky finger tap from accidentally
            # scrolling. Scrollbar drag and map pan handlers stay
            # mutually exclusive with this one (set on MOUSEBUTTONDOWN).
            if self._panel_swipe_start_y is not None:
                dy = event.pos[1] - self._panel_swipe_start_y
                if not self._panel_swipe_active and abs(dy) >= 8:
                    self._panel_swipe_active = True
                if self._panel_swipe_active:
                    self._apply_swipe_scroll(dy, game)
            elif game.skill_detail_scroll_drag_y is not None:
                # Scrollbar drag takes priority over map pan because the
                # player explicitly initiated it on the scrollbar rect.
                self._on_scrollbar_drag(event, game)
            elif self._drag is not None:
                self._on_drag(event, game)
        elif event.type == pygame.KEYDOWN:
            self._on_key_down(event, game)
        elif event.type == pygame.MULTIGESTURE:
            # Pinch-zoom — the only touch gesture that doesn't already
            # work via SDL's mouse-event synthesis from single touches.
            # Single-finger taps/drags auto-synth as left-click/drag
            # (existing MOUSE handlers cover them), long-press synths
            # as right-click, but the mouse-wheel zoom path
            # (``_on_mouse_down`` buttons 4/5) has no touch equivalent
            # — so pinch is the missing axis. Only handle when the
            # player is in a phase where zoom makes sense (playing on
            # the map, not in modal overlays or the title screen) so
            # an accidental two-finger touch on the picker doesn't
            # silently rescale state the player can't see.
            if self._zoom_allowed(game):
                self._on_pinch(event, game)
        return True

    @staticmethod
    def _zoom_allowed(game: Game) -> bool:
        """Same gates as wheel-zoom (``_on_mouse_down`` buttons 4/5).

        Wheel-zoom was implicitly gated by the player needing the
        cursor over the world map — pinch has no cursor, so gate
        explicitly on the same set of "world map is the topmost
        interactive surface" conditions. Modal overlays, picker, and
        title eat the gesture so the player doesn't accidentally zoom
        invisible world state.
        """
        return (
            game.phase is Phase.PLAYING
            and not game.evolution_open
            and not game.settings_open
            and not game.pause_menu_open
            and not game.game_over
            and game.cinematic_playing is None
        )

    def _on_pinch(self, event: pygame.event.Event, game: Game) -> None:
        """Map a MULTIGESTURE pinch delta to ``world.scale``.

        SDL's MULTIGESTURE reports the centroid (x, y) of the two
        fingers as normalised canvas coords (0–1) plus a per-frame
        change in inter-finger distance. **Attribute name varies by
        pygame fork**:
          * upstream pygame (the p4a Android recipe): ``event.pinched``
          * pygame_ce / pygame_sdl2 (desktop and web builds):
            ``event.dDist`` (raw SDL2 camelCase passthrough)
        We accept either via ``getattr`` so the same code path runs on
        Android, desktop, and pygbag without a platform branch. Falls
        back to ``0.0`` (no-op zoom) if neither attribute exists, so a
        future pygame rename doesn't crash the input loop.
        We scale by ``PINCH_ZOOM_SENSITIVITY`` and apply as a
        multiplicative bump on ``world.scale`` — same clamping bounds
        as the mouse-wheel path (``min_zoom`` / ``max_zoom``) so touch
        and desktop reach the same extremes.
        """
        d_dist = getattr(event, "pinched", None)
        if d_dist is None:
            d_dist = getattr(event, "dDist", 0.0)
        factor = 1.0 + d_dist * PINCH_ZOOM_SENSITIVITY
        gameplay = self.config.gameplay
        game.world.scale = max(
            gameplay.min_zoom,
            min(gameplay.max_zoom, game.world.scale * factor),
        )
        self._hover_cache_pos = None

    @staticmethod
    def _skip_cinematic(game: Game) -> None:
        if game.cinematic_playing is not None:
            game.cinematic_played.add(game.cinematic_playing)
            game.cinematic_playing = None
            game.push_event(GameEvent.BUTTON_CLICK)

    def _on_mouse_down(self, event: pygame.event.Event, game: Game) -> None:
        if event.button == 1:
            self._on_left_click(event, game)
        elif event.button == 3:
            self._on_right_click(event, game)
        elif event.button == 4:
            # Wheel up: scroll the skill detail panel when the player
            # is reading a long description with the evolution overlay
            # open. Otherwise the wheel zooms the map as before.
            if self._scroll_skill_detail(event.pos, game, delta=-24):
                return
            game.world.scale = min(
                game.world.scale * self.config.gameplay.zoom_step,
                self.config.gameplay.max_zoom,
            )
            self._hover_cache_pos = None
        elif event.button == 5:
            # Wheel down: same routing — scroll the detail panel when
            # cursor is over it, otherwise zoom out.
            if self._scroll_skill_detail(event.pos, game, delta=+24):
                return
            game.world.scale = max(
                game.world.scale / self.config.gameplay.zoom_step,
                self.config.gameplay.min_zoom,
            )
            self._hover_cache_pos = None

    def _scroll_skill_detail(
        self,
        mouse_pos: tuple[int, int],
        game: Game,
        delta: int,
    ) -> bool:
        """Route a wheel event to the skill detail panel scroll.

        Returns True iff the event was consumed by the scroll (so the
        caller should skip its zoom fallback). Three gates:
        * evolution overlay must be open,
        * a skill must be selected (no scroll when the placeholder is
          shown — there's no description to scroll),
        * cursor must be over the skill detail panel rect.
        Scroll is clamped to ``[0, content_h - visible_h]`` using the
        bounds the renderer wrote on the previous frame.
        """
        if not getattr(game, "evolution_open", False):
            return False
        if not getattr(game, "selected_skill_id", None):
            return False
        from gaia_ultimatum.view.renderer import skill_tree_detail_panel_rect
        panel = skill_tree_detail_panel_rect(self.config)
        if not panel.collidepoint(mouse_pos):
            return False
        content_h = max(0, int(getattr(game, "skill_detail_content_h", 0)))
        visible_h = max(0, int(getattr(game, "skill_detail_visible_h", 0)))
        max_scroll = max(0, content_h - visible_h)
        if max_scroll == 0:
            # Content fits — wheel still consumed so the map doesn't
            # zoom while the player is reading a short description.
            return True
        current = int(getattr(game, "skill_detail_scroll", 0))
        game.skill_detail_scroll = max(0, min(max_scroll, current + delta))
        return True

    def _apply_scrollbar_click(
        self,
        mouse_y: int,
        track_top: int,
        track_h: int,
        game: Game,
    ) -> None:
        """Map a click position on the scrollbar to a scroll offset.

        Slider-style: the click y *is* the new thumb position. The
        thumb's centre lands at the click y (clamped so the thumb
        stays within the track). This makes click-anywhere-on-the-bar
        feel responsive — the content jumps to the requested position
        immediately instead of paging-by-one-thumb-height the way
        traditional desktop scrollbars do.
        """
        content_h = max(0, int(getattr(game, "skill_detail_content_h", 0)))
        visible_h = max(0, int(getattr(game, "skill_detail_visible_h", 0)))
        max_scroll = max(0, content_h - visible_h)
        if max_scroll == 0 or track_h <= 0:
            return
        # Normalised position 0..1 inside the track.
        progress = (mouse_y - track_top) / track_h
        progress = max(0.0, min(1.0, progress))
        game.skill_detail_scroll = int(progress * max_scroll)

    def _on_scrollbar_drag(
        self,
        event: pygame.event.Event,
        game: Game,
    ) -> None:
        """Update scroll based on current mouse y during a scrollbar drag.

        Reads the scrollbar rect from the renderer-written game state
        and routes the current mouse y through ``_apply_scrollbar_click``
        — same slider-style mapping as the initial click, so dragging
        feels continuous with the click that started it. If the
        scrollbar disappears mid-drag (skill switched, content shrank),
        the drag silently no-ops rather than crashing.
        """
        bar = getattr(game, "skill_detail_scrollbar", None)
        if bar is None:
            return
        bx, by, bw, bh = bar
        self._apply_scrollbar_click(event.pos[1], by, bh, game)

    def _on_left_click(self, event: pygame.event.Event, game: Game) -> None:
        mouse_pos = event.pos

        # Settings overlay — eats clicks (highest priority modal).
        if game.settings_open:
            self._on_settings_click(mouse_pos, game)
            return

        # Pause menu — when open it eats clicks so nothing leaks to the map.
        if game.pause_menu_open:
            self._on_pause_menu_click(mouse_pos, game)
            return

        # Impact card dismisses on any click but doesn't *eat* the click —
        # falls through to normal handling so a click on AMÉLIORER does
        # dismiss-and-commit in one motion (fast leveling stays fluid).
        if game.impact_card is not None:
            game.impact_card = None

        if game.phase is Phase.TITLE:
            rects = title_button_rects(self.config)
            # Last-run card has been removed from the title screen — recap
            # lives on the outro now, keeping the title a clean menu.
            if rects["play"].collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.phase = Phase.PICKER
            elif rects["quit"].collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return

        if game.game_over:
            rects = game_over_button_rects(self.config)
            if rects["restart"].collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.request_restart()
                return
            if rects["menu"].collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.request_menu()
                return
            if rects["quit"].collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                pygame.event.post(pygame.event.Event(pygame.QUIT))
                return
            # Outro recap tabs (BILAN / IMPACTS / PARCOURS).
            from gaia_ultimatum.view.renderer import outro_card_rect, outro_tab_rects
            card_rect = outro_card_rect(self.config)
            for i, tab_rect in enumerate(outro_tab_rects(self.config, card_rect)):
                if tab_rect.collidepoint(mouse_pos):
                    game.push_event(GameEvent.BUTTON_CLICK)
                    game.outro_tab = i
                    return
            return

        # Tutorial overlay owns input — modal click semantics: SUIVANT /
        # PASSER nav buttons + close × (the renderer puts the × in a
        # 28×28 circle at the modal's top-right). Clicks anywhere else
        # are inert: outside clicks don't dismiss the modal because
        # the tutorial is a guided 4-slide sequence with explicit
        # navigation, and the player should commit to PASSER (skip)
        # rather than accidentally bail mid-slide. The help modal next
        # door takes the opposite stance (any outside click dismisses)
        # because it's a quick-reference dump, not a sequence. Both
        # modals freeze the simulation via the ``tick_animations``
        # gate, so leaving either open is now genuinely paused — was
        # historically ungated; the rationale here predates that fix.
        if game.tutorial_open:
            nav = tutorial_overlay_button_rects(self.config)
            if nav["next"].collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.advance_tutorial()
                return
            if nav["skip"].collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.close_tutorial()
                return
            # Top-right × close button — same geometry as the renderer
            # uses. Modal rect is 560×340 centred; × is a 28×28 square
            # at (modal.right − 40, modal.top + 16). Touch-mode grows
            # the hit area to 48×48 (the visual × stays at 28; the
            # extra padding is invisible but tappable).
            w_, h_ = self.config.display.width, self.config.display.height
            mw, mh = 560, 340
            mleft = (w_ - mw) // 2
            mtop = (h_ - mh) // 2
            from gaia_ultimatum.config import MIN_TOUCH_TARGET
            close_size = (
                MIN_TOUCH_TARGET if self.config.display.touch_mode else 28
            )
            close_rect = pygame.Rect(
                mleft + mw - 12 - close_size, mtop + 16,
                close_size, close_size,
            )
            if close_rect.collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.close_tutorial()
                return
            return

        if game.help_open:
            # Any click outside the modal closes it; clicks inside are inert.
            game.push_event(GameEvent.BUTTON_CLICK)
            game.toggle_help()
            return

        if game.evolution_open:
            self._on_evolution_click(mouse_pos, game)
            return

        if audio_toggle_rect(self.config).collidepoint(mouse_pos):
            game.push_event(GameEvent.BUTTON_CLICK)
            game.toggle_mute()
            return

        if help_button_rect(self.config).collidepoint(mouse_pos):
            game.push_event(GameEvent.BUTTON_CLICK)
            game.toggle_help()
            return

        # Discrete TUTORIEL chip at the top-left of the map. Opens
        # the "how to play" overlay. Gated on PLAYING phase + no
        # other modal active so the chip's rect can't intercept
        # clicks meant for those modals.
        # Tutorial chip click. Gate must mirror the renderer's visibility
        # gating in ``_draw_tutorial_button`` — clicks on a *hidden*
        # chip would otherwise eat clicks meant for whatever's below
        # (a country click, an orb collection, etc.). Two extra
        # conditions over the modal gates:
        #   * focus gate: hidden while country info panel is open OR
        #     the sidebar is expanded (the chip is not drawn there)
        #   * veteran gate: hidden once ``game.turn`` crosses the
        #     ``TUTORIAL_VETERAN_TURN`` threshold (20 days)
        TUTORIAL_VETERAN_TURN = 20
        from gaia_ultimatum.models.game import Phase as _Phase
        if (
            game.phase is _Phase.PLAYING
            and not game.evolution_open
            and not game.help_open
            and not game.pause_menu_open
            and not game.settings_open
            and not game.cinematic_playing
            and not game.info_panel_visible
            and game.sidebar_collapsed
            and game.turn < TUTORIAL_VETERAN_TURN
            and tutorial_button_rect(self.config).collidepoint(mouse_pos)
        ):
            game.push_event(GameEvent.BUTTON_CLICK)
            game.open_tutorial()
            return

        if not game.awaiting_start:
            for speed, rect in speed_button_rects(self.config).items():
                if rect.collidepoint(mouse_pos):
                    game.push_event(GameEvent.BUTTON_CLICK)
                    game.set_speed(speed)
                    return

            if game.info_panel_visible and close_button_rect(self.config).collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.close_info_panel()
                return

            # Info-panel tab pills (BILAN / ÉQUILIBRE / TENDANCE).
            if game.info_panel_visible:
                from gaia_ultimatum.view.renderer import info_panel_tab_rects
                for i, tab_rect in enumerate(info_panel_tab_rects(self.config)):
                    if tab_rect.collidepoint(mouse_pos):
                        game.push_event(GameEvent.BUTTON_CLICK)
                        game.info_panel_tab = i
                        return

            if evolution_dna_badge_rect(self.config).collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.toggle_evolution_panel()
                return

            # Sidebar collapse / expand chevron — visible at all times during
            # PLAYING, regardless of current panel state.
            from gaia_ultimatum.view.renderer import sidebar_toggle_rect
            if sidebar_toggle_rect(
                self.config, game.sidebar_collapsed,
            ).collidepoint(mouse_pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.sidebar_collapsed = not game.sidebar_collapsed
                return

            for country_id, row_rect in game.leaderboard_rects:
                if row_rect.collidepoint(mouse_pos):
                    game.push_event(GameEvent.BUTTON_CLICK)
                    self._focus_country(game, country_id)
                    return

            # Minimap click — recentre the world on the clicked lon/lat.
            # ONLY when the right panel is actually drawn (sidebar
            # expanded). When the sidebar is collapsed (default), the
            # minimap is invisible but its rect (x=676-948, y=72-168
            # at default size) overlaps the centred milestone banner's
            # × close button at (~670-692, 80-102). The handler used
            # to consume those clicks silently — players who tried to
            # dismiss the top notification got the world re-centred on
            # an invisible mini-globe instead. Gating on sidebar state
            # fixes the bug and matches what the player can actually see.
            if not game.sidebar_collapsed:
                mm = minimap_rect(self.config)
                if mm.collidepoint(mouse_pos):
                    game.push_event(GameEvent.BUTTON_CLICK)
                    lon, lat = minimap_to_world(self.config, mouse_pos)
                    self._focus_world_point(game, lon, lat)
                    return

            # Side event cards have been retired — no top-right click target
            # to handle. Same information now lives in the news ticker and
            # the central milestone banner.

            # Milestone banner × close buttons — let the player dismiss
            # notifications immediately instead of waiting for the
            # auto-fade. Mirrors the renderer's slide animation so the
            # × stays clickable during fade-in / fade-out (when the
            # visible banner is shifted up to 20 px from its static
            # base rect — without this offset, the very first click on
            # a brand-new notification missed because the visible × was
            # already 20 px above the static hit zone).
            if game.milestone_banners:
                from gaia_ultimatum.view.renderer import (
                    milestone_banner_close_rect, milestone_banner_rects,
                )
                banner_rects = milestone_banner_rects(
                    self.config, len(game.milestone_banners),
                )
                banners = list(game.milestone_banners)
                for idx, br in enumerate(banner_rects):
                    if idx >= len(banners):
                        break
                    banner = banners[idx]
                    # Re-derive the renderer's envelope + slide so the
                    # hit-test follows the visible × position frame by
                    # frame. Three-phase envelope: 8 % fade-in, 74 %
                    # hold, 18 % fade-out.
                    progress = banner.age / banner.lifetime
                    if progress < 0.08:
                        envelope = progress / 0.08
                    elif progress < 0.82:
                        envelope = 1.0
                    else:
                        envelope = max(0.0, 1.0 - (progress - 0.82) / 0.18)
                    slide = int(20 * (1.0 - envelope))
                    visible_close = milestone_banner_close_rect(
                        br, touch_mode=self.config.display.touch_mode,
                    ).move(0, -slide)
                    if visible_close.collidepoint(mouse_pos):
                        if game.dismiss_milestone_banner(idx):
                            game.push_event(GameEvent.BUTTON_CLICK)
                            return
                    # Banner body click — when a banner carries a
                    # ``country_id`` (set by ``push_event_card`` for
                    # country-scoped events like "Bangladesh en zone
                    # critique"), clicking the body focuses that
                    # country in the info panel. Same affordance as
                    # the leaderboard rows; the × close still wins on
                    # overlapping clicks because it's checked first.
                    # The ``country_id`` flag was previously dropped on
                    # the floor by the corner-card → central-banner
                    # migration; now it threads to actual interactivity.
                    visible_body = br.move(0, -slide)
                    if (
                        banner.country_id is not None
                        and banner.country_id in game.world.countries
                        and visible_body.collidepoint(mouse_pos)
                    ):
                        game.select_country(banner.country_id)
                        game.dismiss_milestone_banner(idx)
                        game.push_event(GameEvent.BUTTON_CLICK)
                        return

        if game.awaiting_start:
            # Wizard nav buttons (PRÉCÉDENT / SUIVANT / LANCER) are checked
            # first regardless of step.
            from gaia_ultimatum.view.renderer import (
                picker_nav_button_rects, picker_side_card_rects,
            )
            nav = picker_nav_button_rects(self.config)
            if nav["prev"].collidepoint(mouse_pos) and game.picker_step > -1:
                game.push_event(GameEvent.BUTTON_CLICK)
                # If the loading bridge was already counting down (player
                # clicked LANCER and now wants to back out within the
                # 0.5 s wait window), cancel it. Otherwise the bridge
                # would continue ticking in the background and fire
                # start_with_country while the player is browsing
                # picker step 1, dropping them into PLAYING from the
                # wrong picker step.
                game.loading_bridge = None
                game.picker_step -= 1
                return
            if nav["next"].collidepoint(mouse_pos):
                if game.picker_step < 2:
                    game.push_event(GameEvent.BUTTON_CLICK)
                    game.picker_step += 1
                    return
                if game.pending_country:
                    game.push_event(GameEvent.BUTTON_CLICK)
                    game.request_loading_bridge(game.pending_country)
                    game.pending_country = None
                    return
                # Step 2 with no country picked — ignore click on disabled button.
                return

            # Side cards — only active on step -1.
            if game.picker_step == -1:
                side_rects = picker_side_card_rects(self.config)
                for key, rect in zip(("gaia", "humanite"), side_rects):
                    if rect.collidepoint(mouse_pos):
                        game.push_event(GameEvent.BUTTON_CLICK)
                        game.player_side = key
                        return

            cards = picker_pill_rects(self.config)
            # Catastrophe cards — only active on step 0.
            if game.picker_step == 0:
                for name, card_rect in cards["catastrophe"]:
                    if card_rect.collidepoint(mouse_pos):
                        game.push_event(GameEvent.BUTTON_CLICK)
                        for idx, c in enumerate(game.gaia.catastrophes):
                            if c.name == name:
                                game.gaia.active_index = idx
                                break
                        return
            # Difficulty cards — only active on step 1, with the shifted Y
            # used by `_draw_picker_step_difficulty`.
            if game.picker_step == 1:
                from gaia_ultimatum.view.renderer import PICKER_DIFF_CARD_H
                diff_y = 180  # matches renderer's _draw_picker_step_difficulty
                for label, card_rect in cards["difficulty"]:
                    shifted = card_rect.copy()
                    shifted.y = diff_y
                    if shifted.collidepoint(mouse_pos):
                        game.push_event(GameEvent.BUTTON_CLICK)
                        from gaia_ultimatum.models.game import Difficulty as _Diff
                        for diff in _Diff:
                            if diff.label == label:
                                game.difficulty = diff
                                break
                        return

        if not self._inside_map(mouse_pos, game):
            return

        if game.awaiting_start:
            # Country click only matters on step 2 (origin selection).
            if game.picker_step != 2:
                return
            # Bridge already counting down — player has committed via
            # LANCER (or second-click on a country). Ignore further
            # country picks so they don't orphan `pending_country` on
            # a different country while the bridge fires on the
            # originally-chosen one. PREV is still available (and
            # cancels the bridge per the dedicated handler).
            if game.loading_bridge is not None:
                return
            map_point = game.world.inverse_transform(
                mouse_pos, (self.config.display.width, self.config.display.height)
            )
            # Use the lenient (centroid-fallback) hit-test so tiny
            # islands at the far right of the equirectangular map (Fiji,
            # Kiribati, Tuvalu, Marshall Is., etc.) are actually
            # reachable. Strict polygon-only hit-test was the root
            # cause of the recurring "right-side islands unclickable"
            # complaint, not the screen-bound clamp alone.
            country_id = game.world.country_at_lenient(map_point)
            if country_id is not None:
                if game.pending_country == country_id:
                    game.request_loading_bridge(country_id)
                    game.pending_country = None
                else:
                    game.pending_country = country_id
                    game.push_event(GameEvent.BUTTON_CLICK)
            else:
                self._drag = _DragState(
                    start=mouse_pos,
                    initial_offset=(game.world.offset_x, game.world.offset_y),
                )
            return

        clicked_point = self._point_at(mouse_pos, game)
        if clicked_point is not None:
            game.collect_point(clicked_point)
            return

        map_point = game.world.inverse_transform(
            mouse_pos, (self.config.display.width, self.config.display.height)
        )
        # Same lenient hit-test for in-game country selection — clicking
        # near a tiny island opens its info panel even when the polygon
        # itself is only a few pixels wide.
        country_id = game.world.country_at_lenient(map_point)
        if country_id is not None:
            game.select_country(country_id)
        else:
            self._drag = _DragState(
                start=mouse_pos,
                initial_offset=(game.world.offset_x, game.world.offset_y),
            )

    def _map_right_bound(self, game: Game) -> int:
        """Right edge of the clickable map area.

        The right panel is only drawn during PLAYING with the sidebar
        expanded. Everywhere else (PICKER, OUTRO, PLAYING-with-collapsed-
        sidebar) the map fills the full canvas width, so click hit-tests
        must extend all the way to the right edge. The previous
        implementation only checked ``sidebar_collapsed`` and so
        rejected right-side clicks during PICKER step 2 if the sidebar
        flag happened to be False — phase-aware here closes that gap.
        """
        if game.phase is not Phase.PLAYING:
            return self.config.display.width
        if getattr(game, "sidebar_collapsed", False):
            return self.config.display.width
        return self.config.display.width - RIGHT_PANEL_W

    def _focus_world_point(self, game: Game, lon: float, lat: float) -> None:
        """Recentre the camera on a (lon, lat) world point."""
        screen = (self.config.display.width, self.config.display.height)
        cur_x, cur_y = game.world.transform_point((lon, lat), screen)
        center_x = self._map_right_bound(game) / 2
        center_y = TOP_BAR_H + (self.config.display.height - TOP_BAR_H - NEWS_BAR_H) / 2
        game.world.offset_x += center_x - cur_x
        game.world.offset_y += center_y - cur_y
        self._hover_cache_pos = None

    def _focus_country(self, game: Game, country_id: str) -> None:
        """Select a country and recenter the camera on its centroid."""
        country = game.world.countries.get(country_id)
        if country is None:
            return
        screen = (self.config.display.width, self.config.display.height)
        cur_x, cur_y = game.world.transform_point(country.centroid, screen)
        # Center inside the *currently visible* map area: full width when
        # the sidebar is collapsed, width − RIGHT_PANEL_W otherwise.
        center_x = self._map_right_bound(game) / 2
        center_y = TOP_BAR_H + (self.config.display.height - TOP_BAR_H - NEWS_BAR_H) / 2
        game.world.offset_x += center_x - cur_x
        game.world.offset_y += center_y - cur_y
        game.select_country(country_id)
        # Hover cache may now point at a stale position; invalidate.
        self._hover_cache_pos = None

    def _inside_map(self, pos: tuple[int, int], game: Game | None = None) -> bool:
        """Is the screen-space ``pos`` inside the clickable map area?

        Sidebar-aware: when ``game.sidebar_collapsed`` is True (the
        default), the right boundary is the canvas edge instead of
        ``width − RIGHT_PANEL_W``. ``game`` is optional for legacy
        callers that don't have it; without it we keep the conservative
        old behaviour.
        """
        x, y = pos
        if game is not None:
            right = self._map_right_bound(game)
        else:
            right = self.config.display.width - RIGHT_PANEL_W
        return (
            0 <= x < right
            and TOP_BAR_H <= y < self.config.display.height - NEWS_BAR_H
        )

    def _on_right_click(self, event: pygame.event.Event, game: Game) -> None:
        """Right-click: in the skill tree, refund a level on the targeted card."""
        if not game.evolution_open:
            return
        pos = event.pos
        if not evolution_panel_rect(self.config).collidepoint(pos):
            return
        active_axis = skill_tree_active_axis(game)
        skills = skill_tree_skills_for_axis(game, active_axis)
        cards = skill_tree_card_rects(self.config)
        for idx, (_tier, skill) in enumerate(skills):
            if idx >= len(cards):
                break
            if cards[idx].collidepoint(pos):
                if game.refund_skill(skill.id):
                    # If we refunded the last level, the player would expect the
                    # selection to remain so they can re-buy quickly.
                    pass
                return

    def _on_settings_click(self, pos: tuple[int, int], game: Game) -> None:
        """Settings overlay click routing."""
        # Click outside the panel closes the overlay.
        panel = settings_panel_rect(self.config)
        if not panel.collidepoint(pos):
            game.push_event(GameEvent.BUTTON_CLICK)
            game.close_settings()
            return
        # Close button.
        if settings_close_rect(self.config).collidepoint(pos):
            game.push_event(GameEvent.BUTTON_CLICK)
            game.close_settings()
            return
        # Tab switch.
        for tab_id, tab_rect in settings_tab_rects(self.config).items():
            if tab_rect.collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.settings_tab = tab_id
                return
        # Toggles — react only to the row visible for the active tab.
        toggles = settings_toggle_rects(self.config)
        if game.settings_tab == "audio":
            if toggles["mute"].collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.toggle_mute()
                return
        else:
            if toggles["reduce_motion"].collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.reduce_motion = not game.reduce_motion
                return
            if toggles["disable_flash"].collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.disable_flash = not game.disable_flash
                return
            if toggles["high_contrast"].collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.high_contrast = not game.high_contrast
                return

    def _on_pause_menu_click(self, pos: tuple[int, int], game: Game) -> None:
        """Pause-menu click routing, including the destructive-action confirm step."""
        # If a confirmation is in flight, only the confirm/cancel buttons respond.
        if game.pause_confirm:
            confirm_rects = pause_confirm_button_rects(self.config)
            if confirm_rects["confirm"].collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                action = game.pause_confirm
                game.pause_confirm = None
                if action == "abandon":
                    game.abandon_run()
                elif action == "restart":
                    # Same flow as game-over RECOMMENCER: rebuild into a
                    # fresh picker via the main-loop restart hook.
                    game.close_pause_menu()
                    game.request_restart()
                elif action == "quit":
                    pygame.event.post(pygame.event.Event(pygame.QUIT))
                return
            if confirm_rects["cancel"].collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.pause_confirm = None
            return

        rects = pause_menu_button_rects(self.config)
        for key, rect in rects.items():
            if rect.collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                if key == "resume":
                    game.close_pause_menu()
                    if game.last_speed > 0:
                        game.set_speed(game.last_speed)
                elif key == "restart":
                    # Goes through the same confirm gate as ABANDON — restart
                    # also drops in-flight progress, so the player gets a
                    # chance to back out instead of an instant reset.
                    game.pause_confirm = "restart"
                elif key == "settings":
                    game.close_pause_menu()
                    game.open_settings()
                elif key == "help":
                    game.close_pause_menu()
                    game.toggle_help()
                elif key == "abandon":
                    game.pause_confirm = "abandon"
                elif key == "quit":
                    game.pause_confirm = "quit"
                return

    def _on_evolution_click(self, pos: tuple[int, int], game: Game) -> None:
        # Click outside the panel closes the overlay.
        if not evolution_panel_rect(self.config).collidepoint(pos):
            game.push_event(GameEvent.BUTTON_CLICK)
            game.toggle_evolution_panel()
            return
        # × close button at the top-right.
        from gaia_ultimatum.view.renderer import skill_tree_close_button_rect
        if skill_tree_close_button_rect(self.config).collidepoint(pos):
            game.push_event(GameEvent.BUTTON_CLICK)
            game.toggle_evolution_panel()
            return
        # AMÉLIORER button — commits the currently-selected skill.
        if (
            game.selected_skill_id
            and skill_tree_action_button_rect(self.config).collidepoint(pos)
        ):
            ok = game.purchase_skill(game.selected_skill_id)
            if not ok:
                game.push_event(GameEvent.BUTTON_CLICK)
            # Stay selected so player can keep leveling the same skill quickly.
            return

        # Skill detail scrollbar — click anywhere on the bar jumps the
        # thumb to the click y (slider-style); the same click starts a
        # drag tracked by MOUSEMOTION handler so the player can scrub
        # without lifting the mouse button. Bar rect is written by the
        # renderer on the previous frame, including a 4-px hit-pad on
        # each side so pixel-precise aim isn't required.
        bar_rect_tuple = getattr(game, "skill_detail_scrollbar", None)
        if bar_rect_tuple is not None:
            bx, by, bw, bh = bar_rect_tuple
            if bx <= pos[0] < bx + bw and by <= pos[1] < by + bh:
                self._apply_scrollbar_click(pos[1], by, bh, game)
                game.skill_detail_scroll_drag_y = pos[1]
                return

        # Skill detail tab pills (APERÇU / IMPACTS / NIVEAUX). Only meaningful
        # when a skill is selected — otherwise the detail panel shows the
        # element-icon placeholder.
        if game.selected_skill_id:
            from gaia_ultimatum.view.renderer import skill_detail_tab_rects
            for i, tab_rect in enumerate(skill_detail_tab_rects(self.config)):
                if tab_rect.collidepoint(pos):
                    game.push_event(GameEvent.BUTTON_CLICK)
                    # Reset scroll on tab change — the previous tab's
                    # offset would be meaningless for the new tab's
                    # content height.
                    if game.skill_detail_tab != i:
                        game.skill_detail_scroll = 0
                    game.skill_detail_tab = i
                    return
        # Axis tabs.
        for axis_name, tab_rect in skill_tree_axis_tab_rects(self.config).items():
            if tab_rect.collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                game.skill_tree_axis = axis_name
                # Selection clears when switching axis (different content).
                game.selected_skill_id = None
                return
        # Skill cards — single click SELECTS, does not commit (HSR/Genshin pattern).
        active_axis = skill_tree_active_axis(game)
        skills = skill_tree_skills_for_axis(game, active_axis)
        cards = skill_tree_card_rects(self.config)
        for idx, (_tier, skill) in enumerate(skills):
            if idx >= len(cards):
                break
            if cards[idx].collidepoint(pos):
                game.push_event(GameEvent.BUTTON_CLICK)
                # Reset scroll when selecting a different skill — the
                # current offset was sized for the previous skill's
                # description, which the new selection won't share.
                if game.selected_skill_id != skill.id:
                    game.skill_detail_scroll = 0
                game.selected_skill_id = skill.id
                return

        # Fall-through: the click didn't hit any actionable element.
        # If it landed inside the skill detail panel, treat it as the
        # *start* of a finger-swipe-to-scroll gesture (mobile users
        # can't reach the 6-px scrollbar with a finger and there's no
        # wheel on touch). MOUSEMOTION will commit it once Δy ≥ 8 px;
        # MOUSEBUTTONUP clears the state. Gated on a selected skill +
        # scrollable content so a tap on the empty placeholder area
        # doesn't pretend to scroll something that has no scroll
        # range, and so the click handler isn't fooled into thinking
        # every dead-space tap means "scroll".
        if getattr(game, "selected_skill_id", None):
            from gaia_ultimatum.view.renderer import skill_tree_detail_panel_rect
            panel = skill_tree_detail_panel_rect(self.config)
            if panel.collidepoint(pos):
                content_h = max(0, int(getattr(game, "skill_detail_content_h", 0)))
                visible_h = max(0, int(getattr(game, "skill_detail_visible_h", 0)))
                if content_h > visible_h:
                    self._panel_swipe_start_y = pos[1]
                    self._panel_swipe_start_scroll = int(
                        getattr(game, "skill_detail_scroll", 0)
                    )

    def _apply_swipe_scroll(self, dy: int, game: Game) -> None:
        """Apply a finger-swipe Δy to the skill detail scroll offset.

        Follows the standard mobile content-follows-finger convention:
        finger drag *down* (dy positive) shows what was *above* (scroll
        offset decreases), and finger drag *up* shows what was below.
        Clamps to the renderer-reported scroll range; silently no-ops
        if the content shrank below the visible area between the
        gesture's start and now (rare — skill switch mid-drag).
        """
        content_h = max(0, int(getattr(game, "skill_detail_content_h", 0)))
        visible_h = max(0, int(getattr(game, "skill_detail_visible_h", 0)))
        max_scroll = max(0, content_h - visible_h)
        if max_scroll == 0:
            return
        target = self._panel_swipe_start_scroll - dy
        game.skill_detail_scroll = max(0, min(max_scroll, target))

    def _point_at(self, mouse_pos: tuple[int, int], game: Game) -> CatastrophePoint | None:
        """Hit-test catastrophe orbs against the mouse position.

        Hit radius generously exceeds the drawn orb so the player isn't
        punished for landing a click a few pixels off — orbs are
        time-limited, so missing one because the click was 2 px off felt
        bad. ``max(point.size * 2.2, 16)`` gives a 16-20 px reachable
        target for orbs that visually render 5-8 px wide.
        """
        screen = (self.config.display.width, self.config.display.height)
        for point in game.gaia.active.active_points:
            px, py = game.world.transform_point(point.position, screen)
            hit_r = max(point.size * 2.2, 16.0)
            if math.hypot(mouse_pos[0] - px, mouse_pos[1] - py) < hit_r:
                return point
        return None

    def _on_drag(self, event: pygame.event.Event, game: Game) -> None:
        assert self._drag is not None
        dx = event.pos[0] - self._drag.start[0]
        dy = event.pos[1] - self._drag.start[1]
        game.world.offset_x = self._drag.initial_offset[0] + dx
        game.world.offset_y = self._drag.initial_offset[1] + dy

    def _on_key_down(self, event: pygame.event.Event, game: Game) -> None:
        # K_AC_BACK is the Android hardware/gesture back action; SDL2
        # surfaces it as a distinct key (NOT K_ESCAPE). On desktop it
        # never fires, so adding it alongside K_ESCAPE everywhere is
        # safe and gives phone users the same "back/cancel/dismiss"
        # affordance the keyboard offers.
        back_keys = (pygame.K_ESCAPE, pygame.K_AC_BACK)
        if game.phase is Phase.TITLE:
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                game.phase = Phase.PICKER
            elif event.key in back_keys:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return
        if game.game_over:
            if event.key == pygame.K_r:
                game.request_restart()
            elif event.key == pygame.K_m:
                game.request_menu()
            elif event.key in back_keys:
                pygame.event.post(pygame.event.Event(pygame.QUIT))
            return
        if event.key == pygame.K_SPACE:
            if not game.evolution_open and not game.awaiting_start:
                game.toggle_pause()
        elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3):
            if not game.evolution_open and not game.awaiting_start:
                game.set_speed(int(event.unicode) if event.unicode.isdigit() else 1)
        elif event.key == pygame.K_c:
            # Was ungated, which meant pressing C mid-game switched the
            # active catastrophe — `gaia.active_index` changed, orbs
            # from the prior catastrophe became orphaned in their own
            # `active_points` deque, spread state diverged, and
            # purchased skills referenced a different catastrophe than
            # the one now ticking. Gate to PICKER so the keyboard
            # shortcut helps catastrophe selection on step 0 only.
            if game.awaiting_start:
                game.cycle_catastrophe()
        elif event.key == pygame.K_d:
            if game.awaiting_start:
                game.cycle_difficulty()
        elif event.key == pygame.K_m:
            game.toggle_mute()
        elif event.key == pygame.K_h:
            game.toggle_help()
        elif event.key == pygame.K_TAB:
            # Hide / show the right dashboard panel.
            if not game.evolution_open and not game.awaiting_start:
                game.sidebar_collapsed = not game.sidebar_collapsed
        elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            if not game.evolution_open:
                gameplay = self.config.gameplay
                game.world.scale = min(
                    game.world.scale * gameplay.zoom_step, gameplay.max_zoom
                )
                self._hover_cache_pos = None
        elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            if not game.evolution_open:
                gameplay = self.config.gameplay
                game.world.scale = max(
                    game.world.scale / gameplay.zoom_step, gameplay.min_zoom
                )
                self._hover_cache_pos = None
        elif event.key == pygame.K_e:
            if not game.awaiting_start:
                game.toggle_evolution_panel()
        elif event.key == pygame.K_p:
            if game.phase is Phase.PLAYING and not game.pause_menu_open:
                game.open_pause_menu()
        elif event.key in back_keys:
            # Strict ESC / Android-back priority: dismiss whatever's
            # deepest first; in PLAYING phase with nothing else open,
            # ESC opens the pause menu (also acts as the mobile
            # "resume" path — back during play → menu → tap Resume).
            if game.settings_open:
                game.close_settings()
            elif game.pause_confirm:
                game.pause_confirm = None
            elif game.pause_menu_open:
                game.close_pause_menu()
                if game.last_speed > 0:
                    game.set_speed(game.last_speed)
            elif game.tutorial_open:
                game.close_tutorial()
            elif game.help_open:
                game.help_open = False
            elif game.evolution_open:
                game.evolution_open = False
            elif game.awaiting_start and game.pending_country is not None:
                game.pending_country = None
            elif game.phase is Phase.PLAYING and game.info_panel_visible:
                game.close_info_panel()
            elif game.phase is Phase.PLAYING:
                game.open_pause_menu()
            else:
                game.close_info_panel()
