"""Application entry point: wires up model, view, controller and runs the loop.

The loop is ``async`` so that the same code path runs both on the desktop
(through ``asyncio.run``) and in the browser via `pygbag <https://pygame-web.github.io>`_.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import logging
import sys
from pathlib import Path

import pygame

from gaia_ultimatum import __version__
from gaia_ultimatum.assets import CINEMATICS_DIR, ZONES_GEOJSON
from gaia_ultimatum.audio import AudioManager
from gaia_ultimatum.cinematics_player import CinematicLibrary
from gaia_ultimatum.config import Config, load_config
from gaia_ultimatum.controller import InputHandler
from gaia_ultimatum.logging_setup import configure_logging
from gaia_ultimatum.models import Game, GameEvent, GameOutcome, Phase
from gaia_ultimatum.models.game import MilestoneBanner
from gaia_ultimatum.persistence import (
    Prefs,
    RunRecord,
    append_run,
    load_history,
    load_prefs,
    now_iso,
    save_prefs,
)
from gaia_ultimatum.models.world import GeoJsonLoadError
from gaia_ultimatum.view import Renderer
from gaia_ultimatum.view.fonts import Fonts

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gaia-ultimatum", description="Terre Vivante")
    parser.add_argument("--version", action="version", version=f"Terre Vivante {__version__}")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible runs")
    parser.add_argument("--map", type=Path, default=ZONES_GEOJSON, help="Path to the map GeoJSON")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging")
    parser.add_argument("--no-audio", action="store_true", help="Disable audio playback")
    # ``BooleanOptionalAction`` (3.9+) gives us ``--fullscreen`` /
    # ``--no-fullscreen`` from a single declaration. Default is ``None``
    # so ``run_async`` can distinguish "user said nothing" (fall back to
    # config-file + env + touch-mode-default chain) from "user explicitly
    # picked one" (override the chain). Steam Deck users + Android
    # users want fullscreen by default — touch_mode auto-flips
    # ``config.display.fullscreen`` upstream in ``load_config``; this
    # flag exists for the rare "Android dev wants a windowed run" or
    # "Steam Deck user wants windowed Big Picture" cases.
    parser.add_argument(
        "--fullscreen",
        action=argparse.BooleanOptionalAction,
        default=None,
        help=(
            "Launch in fullscreen (use --no-fullscreen for windowed). "
            "Auto-enabled on touch/Android targets; overrides "
            "GAIA_FULLSCREEN env and config.json when set."
        ),
    )
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    """Synchronous desktop entry point."""
    return asyncio.run(run_async(argv))


async def run_async(argv: list[str] | None = None) -> int:
    """Async entry point used by both desktop (``asyncio.run``) and pygbag."""
    args = parse_args(argv)
    config = load_config()
    if args.debug:
        config = dataclasses.replace(config, debug=True)
    # CLI ``--fullscreen`` / ``--no-fullscreen`` wins over the config
    # file + env + touch-mode auto-default chain. ``None`` means the
    # flag wasn't given; preserve whatever ``load_config`` resolved.
    if args.fullscreen is not None:
        config = dataclasses.replace(
            config,
            display=dataclasses.replace(
                config.display, fullscreen=args.fullscreen,
            ),
        )
    configure_logging(debug=args.debug or config.debug)

    # ``mixer.pre_init`` must be called before ``pygame.init`` to take
    # effect — once pygame.init runs the mixer it's already bound to
    # whatever default the SDL backend picked (on some builds buffer=512,
    # ~12 ms, which underruns during long frames and produces audible
    # clicks during catastrophe cascades / milestone banners).
    # 44.1 kHz / 16-bit / stereo matches the playlist WAV format the
    # cutter produces (so SDL doesn't have to resample on every chunk),
    # and buffer=1024 (~23 ms) gives the audio thread roughly 2× the
    # headroom against 60 Hz game-loop jitter without adding perceptible
    # latency. Wrapped in try/except so a backend that rejects the
    # explicit format falls back to whatever it can do — better than
    # crashing on systems without enough audio hardware to honour the
    # request.
    if not args.no_audio:
        try:
            pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=1024)
        except pygame.error as exc:
            logger.warning("mixer.pre_init failed (%s); falling back to SDL defaults", exc)
    # Text crispness on devices where SCALED's upscale would otherwise
    # bilinear-blur every glyph. SDL's render-scale-quality hint:
    #   "0" = nearest neighbour (pixel-perfect, sharp text, slight
    #         pixelation on diagonals)
    #   "1" = linear / bilinear (default; smooths everything but
    #         makes 12-14 pt UI text mushy on phones where the
    #         logical canvas upscales 1.5–2.5× to the device pixels)
    #   "2" = anisotropic (Direct3D only; ignored on Android/iOS)
    # On a 960×640 logical canvas upscaled to a 2272×1080 phone screen
    # (~2.37× factor), "1" was producing the blurry picker text the
    # player reported. "0" keeps each glyph's pixel grid intact.
    # Set via env var because SDL reads scale-quality at renderer
    # creation time (inside ``pygame.display.set_mode``), so it has
    # to be in place before pygame.init runs.
    import os as _os
    _os.environ.setdefault("SDL_HINT_RENDER_SCALE_QUALITY", "0")
    pygame.init()
    try:
        return await _run_game(config, args)
    finally:
        pygame.quit()


async def _run_game(config: Config, args: argparse.Namespace) -> int:
    # SCALED keeps a logical (config.display.width × config.display.height)
    # surface (the rendering target) and transparently scales it to any
    # window size while remapping mouse coordinates back to logical
    # space — so the player can stretch the window without breaking
    # layout or click targets.
    #
    # Android: we **need** FULLSCREEN on Android, contrary to the old
    # comment here. SDL2's Android backend treats the size passed to
    # ``set_mode`` as the literal pixel size of the GL surface; without
    # FULLSCREEN, a 960×640 set_mode produces a 960×640 surface that
    # the Android compositor centers inside the device's full viewport
    # (e.g. 2272×954) — the entire UI shows up as a tiny letterboxed
    # rectangle. FULLSCREEN tells SDL "this window owns the whole
    # screen"; SCALED then handles the design-size → screen-size
    # upscale internally. The historical comment claimed SDL2 rejected
    # SCALED | FULLSCREEN on Android, but that was a much older SDL
    # (≤2.0.16); SDL 2.30.11 (what p4a's recipe ships now) accepts the
    # combo cleanly. The fallback chain below still catches any
    # rejection so a flag mismatch can't crash boot.
    flags = pygame.SCALED
    # p4a doesn't always report ``sys.platform == "android"`` — some
    # bootstraps report the underlying Linux signature. The
    # ``ANDROID_ARGUMENT`` env var + ``getandroidapilevel`` are set
    # universally though, so combine all three.
    import os as _os
    is_android = (
        sys.platform == "android"
        or "ANDROID_ARGUMENT" in _os.environ
        or hasattr(sys, "getandroidapilevel")
    )
    if config.display.fullscreen or is_android:
        flags |= pygame.FULLSCREEN
    if getattr(config.display, "resizable", False) and not config.display.fullscreen:
        flags |= pygame.RESIZABLE
    size = (config.display.width, config.display.height)
    # On Android, the design canvas (960×640, 1.5:1) doesn't match the
    # device screen (typically 2:1+ in landscape) — SCALED preserves
    # aspect ratio and letterboxes with side bars. Grow the logical
    # canvas width to match the device aspect so SCALED fills the
    # screen cleanly. Height stays fixed (vertical layout already fits
    # 640 logical px). The ~48% extra pixel-work cost vs the 960×640
    # baseline is compensated by the 30 fps cap below on touch mode +
    # the nearest-neighbour SDL scale hint set above (cheaper than
    # bilinear, also keeps text sharp).
    if is_android:
        try:
            desktops = pygame.display.get_desktop_sizes()
        except (pygame.error, AttributeError):
            desktops = []
        if desktops:
            dev_w, dev_h = desktops[0]
            if dev_w > 0 and dev_h > 0:
                device_aspect = dev_w / dev_h
                design_h = config.display.height
                design_w = max(
                    config.display.width,
                    round(design_h * device_aspect),
                )
                size = (design_w, design_h)
                logger.info(
                    "Android device %d×%d (aspect %.2f) → design canvas %d×%d",
                    dev_w, dev_h, device_aspect, design_w, design_h,
                )
    try:
        screen = pygame.display.set_mode(size, flags)
    except pygame.error as exc:
        logger.warning(
            "set_mode(%s, flags=%d) failed (%s); retrying with no flags",
            size, flags, exc,
        )
        try:
            screen = pygame.display.set_mode(size)
        except pygame.error as exc2:
            logger.warning(
                "set_mode(%s) failed (%s); retrying with (0, 0) — "
                "let SDL pick the native resolution",
                size, exc2,
            )
            screen = pygame.display.set_mode((0, 0))
    # Reconcile ``config.display.width`` / ``height`` with the actual
    # surface SCALED gave us. The renderer + ~21 module-level layout
    # helpers in ``view/renderer.py`` read these values directly; if
    # they stay at 960 while the surface is 1422 wide (Android
    # wider-canvas path), every right-anchored element
    # (``w - RIGHT_PANEL_W``) and every centered element
    # (``(w - card_w) // 2``) would land in the wrong place. Updating
    # the dataclass here makes the renderer's existing canvas-
    # relative math redistribute UI naturally to fill the actual
    # canvas. Also covers the rare ``set_mode((0, 0))`` fallback
    # branch where SDL picked an unexpected size.
    actual_w, actual_h = screen.get_size()
    if (actual_w, actual_h) != (config.display.width, config.display.height):
        logger.info(
            "Reconciling config.display %d×%d → actual surface %d×%d",
            config.display.width, config.display.height, actual_w, actual_h,
        )
        config = dataclasses.replace(
            config,
            display=dataclasses.replace(
                config.display, width=actual_w, height=actual_h,
            ),
        )
    # No FPS cap on touch devices. Previously capped at 30 fps to
    # offset the wider-canvas pixel cost — but every animation in
    # ``models.game.tick_animations`` counts in FRAMES not ms
    # (``edge.age += 1``, ``self._tick_accumulator += 1``, etc.), so
    # halving fps halved all animation speed AND halved the
    # simulation turn rate, making the world map "feel off". The
    # right fix is renderer-side: a polygon transform cache in
    # ``view/renderer.py`` cuts the ~885k ``transform_point`` calls
    # per frame to 0 when the player isn't panning/zooming. That
    # buys back the perf budget the wider canvas costs without
    # touching the animation timeline.
    runtime_fps = config.display.fps
    pygame.display.set_caption(config.display.title)
    # App icon — drawn in the OS title bar and taskbar / dock. Falls
    # back gracefully when the asset is missing (e.g. a stripped
    # install): just leaves pygame's default icon in place rather than
    # crashing on a missing file. ``tools/generate_app_icon.py``
    # regenerates the PNG + ICO bundle.
    from gaia_ultimatum.assets import IMAGES_DIR
    icon_path = IMAGES_DIR / "app_icon.png"
    if icon_path.is_file():
        try:
            icon_surf = pygame.image.load(str(icon_path)).convert_alpha()
            pygame.display.set_icon(icon_surf)
        except (pygame.error, OSError) as exc:
            logger.warning("Could not set app icon (%s); using default", exc)
    clock = pygame.time.Clock()
    fonts = Fonts.create()

    audio: AudioManager | None = None
    if not args.no_audio:
        audio = AudioManager(config.audio)
        # ``click`` rides a 50 ms cooldown — a 55 ms sample stacking on
        # rapid UI ticks (e.g. BUTTON_CLICK + EVOLUTION_PURCHASED in
        # the same drain) used to burn two mixer channels on what the
        # listener perceives as one click; the cooldown drops the
        # duplicate without affecting any human-paced interaction
        # (300+ ms between clicks). ``effect`` stays uncapped — each
        # dramatic chime (milestone / victory / defeat) is a
        # semantically distinct event the player should hear.
        audio.load_sound("click", "button-click.mp3", cooldown_ms=50)
        audio.load_sound("effect", "effect1.wav")
        # Discover any playlists under sounds/playlists/<category>/. Players
        # can drop new tracks into title / picker / playing / outro folders
        # to grow the in-game soundtrack without touching code.
        playlist_summary = audio.discover_playlists()
        # Always keep a "default" fallback (the legacy single track) so
        # everything keeps working even with zero playlist files installed.
        audio.register_playlist("default", ["background.mp3"])
        # Soft fade-in on the very first track of the session. With
        # ``crossfade_ms=0`` the title music snapped on at full target
        # volume the instant the window opened — fine technically,
        # harsh in practice. A short ramp lets the cold-start moment
        # land more like the in-game phase transitions (which already
        # use a 1500 ms cross-fade in ``app.py:427``).
        STARTUP_FADE_MS = 1500
        # play_playlist returns False when the playlist is missing /
        # empty / the mixer is unavailable. Surface that on boot so
        # "the game starts silent" has a diagnostic trail: without
        # this the only signal was the absence of sound, with no
        # log line pointing at music vs SFX vs mixer-init as the
        # source. Both branches funnel into the same warning.
        if not playlist_summary:
            started = audio.play_playlist(
                "default", crossfade_ms=STARTUP_FADE_MS,
            )
        else:
            logger.info("Music playlists: %s", playlist_summary)
            # Start on the title playlist if it exists, else default.
            started = audio.play_playlist(
                "title" if "title" in playlist_summary else "default",
                crossfade_ms=STARTUP_FADE_MS,
            )
        if not started:
            # Also report ``audio.available`` so the warning
            # distinguishes "mixer never came up" from "mixer is fine
            # but no playable tracks". ``register_playlist`` doesn't
            # gate on availability — so when the mixer fails to init
            # but ``background.mp3`` exists on disk, the playlist
            # gets registered, ``has_playlist`` returns True, and
            # the old warning misleadingly said "fallback
            # registered=True" while the actual reason for silence
            # was the unavailable mixer.
            logger.warning(
                "No music could be started on boot — mixer available=%s, "
                "discovered playlists=%s, legacy fallback registered=%s.",
                audio.available,
                list(playlist_summary.keys()) if playlist_summary else [],
                audio.has_playlist("default"),
            )

    prefs = load_prefs()
    try:
        game = Game.create(
            config=config,
            geojson_path=args.map,
            seed=args.seed,
            phase=Phase.TITLE,
        )
    except GeoJsonLoadError as exc:
        logger.error("%s", exc)
        return 1
    # Apply prefs to the freshly-built Game.
    _apply_prefs_to_game(game, prefs)

    renderer = Renderer(config, fonts)
    input_handler = InputHandler(config)

    # MP4 cinematics live in cinematics/. ``from_paths_lazy`` registers
    # every clip's *path* without opening it — boot is instant. A
    # background daemon thread then walks the registry, pre-opening
    # each clip so first-play latency is also zero. If the player
    # triggers a cinematic before the preloader reaches it, the lazy
    # ``get()`` opens it on the main thread (~30–100 ms behind the
    # fade-in the renderer already uses, invisible). Previously
    # ``from_paths`` opened all 16 MP4s sequentially via
    # ``cv2.VideoCapture.open`` — a 3–5 s hitch on Android storage
    # and noticeable on Steam Deck disk too.
    #
    # When OpenCV is unavailable (pygbag/browser, minimal envs) the
    # library yields ``None`` from every ``get`` and the renderer
    # falls back to its procedural intro/outro envelope.
    cinematics = CinematicLibrary.from_paths_lazy({
        "intro":   CINEMATICS_DIR / "intro.mp4",
        "midgame": CINEMATICS_DIR / "midgame.mp4",
        # Outcome-specific clips — picked over the neutral outro when the
        # outcome is decisive. Both fall back to outro.mp4 if missing.
        "victory": CINEMATICS_DIR / "victory.mp4",
        "defeat":  CINEMATICS_DIR / "defeat.mp4",
        "outro":   CINEMATICS_DIR / "outro.mp4",
        # Element midgame cards — fire on the ``first_critical`` milestone.
        # 5 elements × {gaia, humanite} sides = 10 clips. The runtime
        # picker uses the active catastrophe + ``game.player_side`` to
        # resolve the key. Run-specific variation (which country tipped,
        # the day count, current mortality) is added at runtime by the
        # scenario-info overlay drawn over the frame in
        # ``Renderer._draw_cinematic`` — not by pre-rendered MP4 variants.
        **{
            f"element_{element}_{side}":
                CINEMATICS_DIR / f"element_{element}_{side}.mp4"
            for element in ("eau", "feu", "terre", "air", "vie")
            for side in ("gaia", "humanite")
        },
        # Slope-confirmed card — fires on the ``quarter_dead``
        # milestone (25 % of humanity dead). Was previously triggered
        # on ``collapse_imminent`` (60 % dead) which sat just 5 points
        # before the defeat threshold, so this card and the defeat
        # card landed 1-3 turns apart with the same red palette — two
        # clips for one moment. Re-anchored at 25 % to give ~30 game-
        # days of breathing room before defeat, sequencing the three
        # late-game cards as midgame (world tipping) → point_de_non_
        # retour (slope confirmed) → defeat (close).
        "point_de_non_retour": CINEMATICS_DIR / "point_de_non_retour.mp4",
    })
    # Kick off the background preloader. The first cinematic the player
    # reaches (the intro on PLAY) typically lands at +2-4 s of game time,
    # which is plenty for the daemon thread to have opened it. If the
    # player skips the title and clicks PLAY in < 1 s, the lazy
    # ``cinematics.get("intro")`` path will catch the race and open
    # synchronously on the main thread — still cheaper than the old
    # eager-open-everything boot.
    cinematics.preload_in_background()
    renderer.attach_cinematics(cinematics)

    running = True
    last_outcome_recorded: str | None = None
    last_phase: Phase | None = None
    while running:
        for event in pygame.event.get():
            # Audio consumes its own end-of-track events so the playlist
            # auto-advances; do not forward those to the input handler.
            if audio is not None and audio.handle_event(event):
                continue
            if not input_handler.handle(event, game):
                running = False
                break
        if not running:
            break
        if game.restart_to is not None:
            target = game.restart_to
            prev_muted = game.audio_muted
            prev_played = set(game.cinematic_played)
            # If the player restarts mid-cinematic (R / RECOMMENCER while
            # a clip is still in flight), the clip name hasn't yet been
            # added to ``cinematic_played`` — that only happens on skip
            # or auto-finish, which the restart bypasses. Without this
            # carry-forward, the very same intro / midgame / outcome
            # cinematic would replay on the next matching phase
            # transition in the new run, even though the player just
            # acted to leave it. Treat "playing at the moment of
            # restart" as equivalent to "seen" so the player isn't
            # forced through a rewatch loop.
            if game.cinematic_playing is not None:
                prev_played.add(game.cinematic_playing)
            game = Game.create(
                config=config, geojson_path=args.map, seed=None, phase=target
            )
            game.audio_muted = prev_muted
            # Carry forward which cinematics have already been seen — restarts
            # shouldn't force the player to rewatch the intro every time.
            game.cinematic_played = prev_played
            _apply_prefs_to_game(game, prefs)
            last_outcome_recorded = None
            last_phase = None  # re-evaluate transition triggers post-restart
        # Phase-change cinematic triggers. Each clip plays at most once per
        # session — once dismissed (skipped or finished), it's added to
        # cinematic_played and won't re-fire on restart.
        #
        # ``reduce_motion`` gating: MP4 cinematics are the most motion-
        # intense surface in the app (camera moves, cuts, atmospheric
        # FX), but they shipped without a reduce-motion accommodation
        # while every procedural envelope already gates on the flag.
        # For players who set the preference, the trigger now marks the
        # clip as "played" without queueing playback — the destination
        # screen's procedural envelope (title planet rise, picker
        # aurora, outro bob/drift) carries the transition. Those
        # envelopes already respect ``reduce_motion``, so the player
        # gets a calm version of the moment instead of a forced video.
        if last_phase != game.phase:
            if (
                last_phase == Phase.TITLE
                and game.phase == Phase.PICKER
                and game.cinematic_playing is None
                and "intro" not in game.cinematic_played
                and cinematics.get("intro") is not None
            ):
                if game.reduce_motion:
                    game.cinematic_played.add("intro")
                else:
                    game.cinematic_playing = "intro"
                    game.cinematic_started_ms = pygame.time.get_ticks()
            elif (
                game.phase == Phase.OUTRO
                and last_phase != Phase.OUTRO
                and game.cinematic_playing is None
            ):
                # Pick the most specific outcome cinematic available, with
                # outro.mp4 as the neutral fallback. Each variant only plays
                # once per session so re-runs don't replay the same reveal.
                outcome_name = (
                    "victory" if game.outcome.value == "victory"
                    else "defeat" if game.outcome.value == "defeat"
                    else "outro"
                )
                pick = next(
                    (
                        n for n in (outcome_name, "outro")
                        if cinematics.get(n) is not None
                        and n not in game.cinematic_played
                    ),
                    None,
                )
                if pick is not None:
                    if game.reduce_motion:
                        game.cinematic_played.add(pick)
                    else:
                        game.cinematic_playing = pick
                        game.cinematic_started_ms = pygame.time.get_ticks()
            last_phase = game.phase
        # Element midgame card — fires when the active catastrophe
        # FIRST manifests itself in the world: the ``first_critical``
        # milestone (first country tipping into critical state ≥ 0.5).
        # Element comes from the active catastrophe; side from
        # ``game.player_side`` (Gaia voice asserts the threat, Humanité
        # voice frames the response). Run-specific variation (which
        # country tipped, the day count) is layered on by the renderer
        # as a scenario-info overlay, so the same MP4 lands differently
        # each run without needing pre-rendered variants.
        if (
            game.phase == Phase.PLAYING
            and game.cinematic_playing is None
            and "first_critical" in game.unlocked_milestones
        ):
            element = game.gaia.active.name.lower()
            side = "humanite" if game.player_side == "humanite" else "gaia"
            clip_key = f"element_{element}_{side}"
            if (
                clip_key not in game.cinematic_played
                and cinematics.get(clip_key) is not None
            ):
                game.cinematic_played.add(clip_key)
                if not game.reduce_motion:
                    game.cinematic_playing = clip_key
                    game.cinematic_started_ms = pygame.time.get_ticks()
        # Mid-late slope trigger — fires once when the ``quarter_dead``
        # milestone unlocks (25 % of humanity dead).
        #
        # Trigger moved here from ``collapse_imminent`` (60 % dead).
        # The previous placement sat 5 mortality-points before the
        # defeat threshold (65 %), so this cinematic and the defeat
        # cinematic fired 1-3 turns apart — same red palette, same
        # gravity, two clips for one moment. ``quarter_dead`` puts
        # ~30 game-days of distance before defeat so each card lands
        # as its own beat: midgame (world tipping) → point-de-non-
        # retour (slope confirmed at 25 % loss) → defeat (close).
        if (
            game.phase == Phase.PLAYING
            and game.cinematic_playing is None
            and "point_de_non_retour" not in game.cinematic_played
            and "quarter_dead" in game.unlocked_milestones
            and cinematics.get("point_de_non_retour") is not None
        ):
            if game.reduce_motion:
                game.cinematic_played.add("point_de_non_retour")
            else:
                game.cinematic_playing = "point_de_non_retour"
                game.cinematic_started_ms = pygame.time.get_ticks()
        # In-game midgame trigger — fires once per session when EITHER
        # condition is met:
        #   (a) ≥ 50 % of the *world population* lives in critical-state
        #       regions — the passive world-state arc, OR
        #   (b) the player has purchased their first Transformation-tier
        #       skill on any axis — the player-agency arc.
        # (a) was a raw country count (``critical >= len(countries) // 2``)
        # which under-counted tension the same way the old defeat /
        # music-intensity counters did: India going critical bumped
        # the count by 1, the same weight as Tuvalu, so the cinematic
        # could fire on a cascade of small islands while the real
        # population stayed mostly safe — and conversely, when a
        # populous region tipped alone, the moment never landed.
        # Switched to the same population-weighted critical share
        # ``_check_outcome`` / ``_music_intensity`` already use so the
        # cinematic agrees with the subtitle "la moitié du monde a
        # vacillé" and with what the player perceives as "the world".
        #
        # The OR is what fixes the "I never see the midgame cinematic"
        # report. (a) alone never fired for players who lived in the
        # skill tree because the tree freezes ``next_turn`` (see
        # ``tick_animations``), so world state stayed below 50 % even
        # as the player burned through tier after tier. (b) gives the
        # cinematic a path that's driven by what the player just *did*,
        # so the moment lands with causal weight instead of arriving
        # as a passive arrival.
        #
        # Trigger detection is decoupled from playback path so that
        # players without OpenCV / a midgame.mp4 still receive the
        # narrative beat through a procedural fallback (a milestone
        # banner). Intro / outro have phase-change procedural envelopes
        # baked into their destination screens; midgame doesn't — it's
        # an in-phase event — so without this fallback the moment
        # silently vanished for that install profile.
        if (
            game.phase == Phase.PLAYING
            and game.cinematic_playing is None
            and "midgame" not in game.cinematic_played
        ):
            countries = list(game.world.countries.values())
            total_pop = sum(c.population for c in countries)
            crit_pop = sum(
                c.population for c in countries if c.state >= 0.5
            )
            # World trigger fires at 50 % critical share — half-way to
            # the 75 % defeat trigger that ``_check_outcome`` uses,
            # so the cinematic lands as a *midpoint* warning rather
            # than the defeat itself.
            world_trigger = total_pop > 0 and (crit_pop / total_pop) >= 0.50
            player_trigger = game._milestone_transformation_reached
            if world_trigger or player_trigger:
                # ``reduce_motion`` forces the procedural banner path
                # even when the MP4 is available. Midgame has no
                # destination-screen envelope to fall back on (unlike
                # intro / outro which can rely on title planet rise /
                # outro intro envelope), so the banner is the only way
                # to deliver the moment without violating the player's
                # motion preference.
                use_mp4 = (
                    cinematics.get("midgame") is not None
                    and not game.reduce_motion
                )
                if use_mp4:
                    # MP4 path — the cinematic is the moment.
                    game.cinematic_playing = "midgame"
                    game.cinematic_started_ms = pygame.time.get_ticks()
                else:
                    # Procedural fallback. The milestone banner is the
                    # only on-screen central notification (corner cards
                    # are retired), 3 s lifetime, with severity / tag
                    # styling already wired up in the renderer. Two
                    # variants so the moment matches what caused it:
                    #
                    #   player_trigger → "trophy" (TROPHÉE tag, ui_accent,
                    #     star icon) — the player just deployed their
                    #     apex skill; framed as an achievement.
                    #   world_trigger → "critical" (CRITIQUE tag, severe
                    #     red, skull icon) — the world has tipped; framed
                    #     as gravity, matching what the MP4 itself depicts.
                    #
                    # ``cinematic_played.add("midgame")`` is dedup-equivalent
                    # to the MP4 path: subsequent frames won't refire
                    # the banner just because the condition still holds.
                    if player_trigger:
                        title = "Compétence apex déployée — palier atteint."
                        severity = "trophy"
                    else:
                        title = "Moment de bascule — la moitié du monde a vacillé."
                        severity = "critical"
                    game.milestone_banners.append(
                        MilestoneBanner(title=title, severity=severity),
                    )
                    game.cinematic_played.add("midgame")
        if audio is not None:
            audio.set_muted(game.audio_muted)
            audio.set_music_intensity(_music_intensity(game))
            # Phase-driven music: when a discovered playlist matches the
            # current phase name, switch into it with a soft crossfade.
            # Falls back to whatever's already playing when no per-phase
            # playlist is installed.
            desired = _music_category_for(game.phase)
            if (
                audio.has_playlist(desired)
                and audio.current_playlist != desired
            ):
                audio.play_playlist(desired, crossfade_ms=1500)
        # Persist any pref changes the moment they happen — small JSON write.
        prefs_dirty = False
        if prefs.audio_muted != game.audio_muted:
            prefs.audio_muted = game.audio_muted
            prefs_dirty = True
        if prefs.reduce_motion != game.reduce_motion:
            prefs.reduce_motion = game.reduce_motion
            prefs_dirty = True
        if prefs.disable_flash != game.disable_flash:
            prefs.disable_flash = game.disable_flash
            prefs_dirty = True
        if prefs.high_contrast != game.high_contrast:
            prefs.high_contrast = game.high_contrast
            prefs_dirty = True
        # Track last-used picker selections while in PICKER phase.
        if game.phase is Phase.PICKER:
            if prefs.last_catastrophe != game.gaia.active.name:
                prefs.last_catastrophe = game.gaia.active.name
                prefs_dirty = True
            if prefs.last_difficulty != game.difficulty.label:
                prefs.last_difficulty = game.difficulty.label
                prefs_dirty = True
        if prefs_dirty:
            save_prefs(prefs)
        # Record run history exactly once on the transition into OUTRO.
        if (
            game.phase is Phase.OUTRO
            and last_outcome_recorded != id(game)
        ):
            try:
                origin = next(
                    (
                        cid for cid, c in game.world.countries.items()
                        if c.state >= 0.18 and c.population > 0
                    ),
                    "?",
                )
                append_run(RunRecord(
                    catastrophe=game.gaia.active.name,
                    difficulty=game.difficulty.label,
                    country=game.world.countries.get(origin).name if origin in game.world.countries else "?",
                    outcome=game.outcome.value,
                    turns=game.turn,
                    timestamp=now_iso(),
                ))
            except Exception as exc:  # noqa: BLE001 — never crash on bad save
                logger.warning("Could not append run history: %s", exc)
            last_outcome_recorded = id(game)
        input_handler.update_camera(game)
        _drain_audio_events(game, audio)
        game.tick_animations()
        renderer.draw(screen, game)
        pygame.display.flip()
        await asyncio.sleep(0)
        clock.tick(runtime_fps)

    if game.outcome is GameOutcome.VICTORY:
        logger.info("Final outcome: VICTORY")
    elif game.outcome is GameOutcome.DEFEAT:
        logger.info("Final outcome: DEFEAT")

    if audio is not None:
        audio.stop_music()
    cinematics.close_all()
    return 0


def _apply_prefs_to_game(game: Game, prefs: Prefs) -> None:
    """Hydrate a freshly-built Game with persisted preferences."""
    game.audio_muted = prefs.audio_muted
    game.reduce_motion = prefs.reduce_motion
    game.disable_flash = prefs.disable_flash
    game.high_contrast = prefs.high_contrast
    # Surface the most recent run on the title screen (read on each create so
    # restarting after a finished run shows the new "last run" card).
    history = load_history()
    if history:
        latest = history[-1]
        game.last_run_summary = latest.to_dict()
    # Restore last picker selections so returning users see their last choice
    # pre-selected on the picker screen.
    if prefs.last_catastrophe:
        for idx, cat in enumerate(game.gaia.catastrophes):
            if cat.name == prefs.last_catastrophe:
                game.gaia.active_index = idx
                break
    if prefs.last_difficulty:
        from gaia_ultimatum.models.game import Difficulty as _Diff
        for diff in _Diff:
            if diff.label == prefs.last_difficulty:
                game.difficulty = diff
                break


def _music_category_for(phase: Phase) -> str:
    """Map a Phase to the playlist category name used by AudioManager.

    Categories match the folder names under ``sounds/playlists/<name>/``
    so the player can drop tracks like ``sounds/playlists/playing/01.mp3``
    and have them rotate during gameplay automatically. Missing folders
    silently leave the previous playlist running.
    """
    return {
        Phase.TITLE:   "title",
        Phase.PICKER:  "picker",
        Phase.PLAYING: "playing",
        Phase.OUTRO:   "outro",
    }.get(phase, "default")


def _music_intensity(game: Game) -> float:
    """Map current simulation tension to a [0..1] music modulation curve.

    During PLAYING the curve takes the **max** of three signals so any
    one of them surging carries the music:

      * **Population-weighted critical share** — fraction of *people*
        (not countries) living in regions whose state >= 0.5. Was a raw
        country count (``sum(1 for c if c.state >= 0.5) / len(countries)``)
        which under-counted tension when populous regions tipped:
        India going critical bumped the score by 1/N, the same weight
        as Tuvalu. The new pop-weighted form matches the secondary-
        defeat metric the simulator uses to call collapse, so the
        music and the game agree on what "critical" means.

      * **Mortality share** — fraction of population dead, weighted
        1.2× so a low-mortality cascade still reads as tense.

      * **Catastrophe intensity (normalised)** — direct read of
        ``gaia.active.intensity`` mapped from [1.0, 3.0] → [0.0, 1.0].
        Captures the engine's back-pressure feedback (as humanity
        loses ground, the catastrophe amplifies). Adds a third lever
        so the music tracks the simulator's *driver* of escalation,
        not just its outputs.

    Result clamps to [0.25, 1.0] so PLAYING always carries some
    baseline tension. Smoothed audio-side by an asymmetric IIR
    (~1 s attack / ~3 s release) so big jumps fade in instead of
    clicking on the music bed.

    Phase overrides (title/picker/outro/cinematic) are flat — the
    ramping logic only matters once the simulation is actually
    running. The picker step ramp (0.10 → 0.42) hands the music
    upward as the player commits.
    """
    # MP4 cinematic owns the moment — dampen the soundtrack so the player's
    # focus is the video, not the ambient bed. The bed returns to normal as
    # soon as the clip ends or is skipped.
    if game.cinematic_playing is not None:
        return 0.0
    if game.phase.value == "title":
        return 0.0
    if game.phase.value == "picker":
        # Picker wizard ramp: each step nudges intensity higher so the
        # soundtrack swells as the player approaches LANCER.
        step = max(-1, min(2, getattr(game, "picker_step", 0)))
        return {-1: 0.10, 0: 0.18, 1: 0.28, 2: 0.42}.get(step, 0.15)
    if game.phase.value == "outro":
        return 1.0
    countries = list(game.world.countries.values())
    if not countries:
        return 0.25
    pop = sum(c.population for c in countries)
    if pop <= 0:
        return 0.25
    # 1) Population-weighted critical share — *people* in critical
    # regions, not country count. Mirrors ``_global_critical_share``
    # in game.py so the music's "uh-oh" trigger matches the engine's.
    crit_pop = sum(c.population for c in countries if c.state >= 0.5)
    crit_share = crit_pop / pop
    # 2) Mortality share (already pop-weighted).
    dead = sum(c.dead for c in countries)
    dead_share = dead / pop
    # 3) Catastrophe intensity normalised — ``intensity`` ramps from
    # 1.0 (humans winning) to 3.0 (humans losing ground), so the (i-1)/2
    # normalisation gives a clean 0..1 escalation lever.
    intensity_norm = max(
        0.0, min(1.0, (game.gaia.active.intensity - 1.0) / 2.0),
    )
    tension = max(crit_share, dead_share * 1.2, intensity_norm)
    computed = max(0.0, min(1.0, 0.25 + 0.75 * tension))
    # Menu duck — halve intensity when the player has opened a
    # reading/configuration modal over gameplay (pause / help /
    # settings / tutorial). Signals "stepped out of the simulation"
    # without snapping to silence. The audio IIR's slow release
    # (~3 s) turns the half-step into a graceful settle when the
    # menu opens and the fast attack (~1 s) lifts it back when the
    # menu closes — the asymmetry I tuned earlier for in-game
    # tension dynamics now also covers menu-mode transitions.
    #
    # Excluded by design:
    #   * ``evolution_open`` — skill-tree overlay is active strategy,
    #     not a reading break; music should still reflect tension.
    #   * ``info_panel_visible`` — country details pane is gameplay
    #     context, not a modal.
    menu_open = (
        getattr(game, "pause_menu_open", False)
        or getattr(game, "help_open", False)
        or getattr(game, "settings_open", False)
        or getattr(game, "tutorial_open", False)
    )
    if menu_open:
        computed *= 0.5
    return computed


# Per-event audio routing — same two samples, varied volume/sound choice so
# each kind of event has distinct sonic weight. UI clicks are quiet so they
# don't fatigue during rapid interaction; dramatic events get full volume.
_EVENT_AUDIO: dict[GameEvent, tuple[str, float]] = {
    GameEvent.BUTTON_CLICK:        ("click",  0.55),
    GameEvent.PATIENT_ZERO:        ("effect", 1.00),
    GameEvent.COUNTRY_CRITICAL:    ("effect", 0.75),
    GameEvent.EVOLUTION_PURCHASED: ("click",  1.00),
    GameEvent.MILESTONE:           ("effect", 0.85),
    GameEvent.VICTORY:             ("effect", 1.00),
    GameEvent.DEFEAT:              ("effect", 1.00),
}


def _drain_audio_events(game: Game, audio: AudioManager | None) -> None:
    """Empty the game's event queue and route events to the audio manager.

    Dedupes per drain so a turn that critically tips multiple countries plays
    a single chime, not a barrage. Safe when audio is unavailable.
    """
    if not game.events:
        return
    if audio is None or not audio.available:
        game.events.clear()
        return
    seen: set[GameEvent] = set()
    while game.events:
        event = game.events.popleft()
        if event in seen:
            continue
        seen.add(event)
        mapping = _EVENT_AUDIO.get(event)
        if mapping is None:
            continue
        sound_name, volume_scale = mapping
        audio.play_sound(sound_name, volume_scale=volume_scale)


if __name__ == "__main__":
    sys.exit(run())
