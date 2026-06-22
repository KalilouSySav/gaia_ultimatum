# /// script
# dependencies = [
#   "pygame-ce",
# ]
# ///
"""Pygbag + buildozer entry point.

Pygbag (mobile-web build) AND python-for-android (native APK build)
both look for ``main.py`` at the project root and treat it as the
program entry. This file dispatches at boot to the correct argv set
based on which one is running.

  * pygbag / emscripten → ``_web_argv`` + asyncio-driven loop
    (cooperates with the browser event loop).
  * Android / p4a       → ``_android_argv`` + normal sync ``run``
    (audio works, no autoplay constraint, light geojson keeps APK
    install fast and battery use sane).
  * Desktop (rare — most desktop runs use ``python -m gaia_ultimatum``)
    → forward sys.argv unchanged.

Structure: ONE top-level ``asyncio.run(main())`` so pygbag's
``check_code`` detects the async entry point AND its run() helper
recognises the canonical ``main`` coroutine name (special-cased in
``pygbag/support/cross/aio/__init__.py:378``). The earlier version
branched into ``asyncio.run(run_async(...))`` inside an ``if`` block —
the coro name was "run_async", which pygbag scheduled but tore down
mid-startup, crashing with ``AttributeError: module 'pygame' has no
attribute 'init'``. Wrapping the per-platform branches inside ``main``
keeps pygbag happy on web and stays equivalent on Android / desktop
(where ``asyncio.run`` is the standard blocking implementation).
"""

from __future__ import annotations

import asyncio
import os
import sys

from gaia_ultimatum.assets import ZONES_GEOJSON_LIGHT


def _is_android() -> bool:
    """Robust Android detection across p4a variants.

    ``sys.platform`` is reported as ``"android"`` on some p4a/SDL2
    bootstraps but as ``"linux"`` on others (the SDL2 bootstrap inherits
    the underlying Linux kernel signature unless p4a's runtime
    explicitly overrides it). The ``ANDROID_ARGUMENT`` env var is set
    by every p4a bootstrap regardless of bootstrap type. ``getandroidapilevel``
    is exposed on the standard library starting in Python 3.7's Android
    cross-build. Any one of the three being truthy means we're on
    Android — and we want all three checks because relying on
    ``sys.platform`` alone would silently fall through to the desktop
    branch and load the 24 MB ``zones.geojson`` (excluded from the APK
    by ``buildozer.spec``), crashing the app with FileNotFoundError on
    boot.
    """
    if sys.platform == "android":
        return True
    if "ANDROID_ARGUMENT" in os.environ:
        return True
    if hasattr(sys, "getandroidapilevel"):
        return True
    return False


def _web_argv() -> list[str]:
    """Default CLI arguments tuned for the browser build.

    - Use the smaller 1 MB GeoJSON (``zones.geo.json``) instead of the full
      24 MB version, to keep the initial download reasonable.
    - Disable audio by default: pygame's mixer may not be available in all
      browsers, and the player can still unmute via config. ``--no-audio``
      is LOAD-BEARING on WASM — without it, ``audio.AudioManager``
      instantiates and calls ``pygame.mixer.pre_init`` + ``init`` at boot.
      Pygame-web's mixer is unreliable across browsers (autoplay policy
      blocks until first user gesture) and an init failure here would
      crash the whole game before the title screen renders. Even if
      mixer init succeeded, ``pygame.mixer.music.set_endevent`` posts a
      USEREVENT integer that desktop pygame_ce and WASM pygame number
      differently (see ``audio.MUSIC_END_EVENT``'s getattr fallback) —
      cross-target audio is not worth the risk for the web demo.
    - Seed the RNG so refreshes produce reproducible games (remove the seed
      if you prefer random runs).
    """
    return [
        "--map",
        str(ZONES_GEOJSON_LIGHT),
        "--no-audio",
        "--seed",
        "42",
    ]


def _android_argv() -> list[str]:
    """Default CLI arguments tuned for the native Android build.

    - Light GeoJSON — same reason as web: the full 24 MB is excluded
      from the APK by ``buildozer.spec``'s ``source.exclude_patterns``,
      so loading the heavy variant would fail with FileNotFoundError
      regardless. Keep main.py and buildozer.spec in lockstep.
    - Audio enabled — Android has a working mixer and no browser
      autoplay constraint. The audio dispatcher waits for the
      AudioManager init in ``app.py`` to gate first play_playlist.
    - No fixed seed — a tap-launch on a phone wants a fresh run, not
      a replay of seed 42 every time.
    """
    return [
        "--map",
        str(ZONES_GEOJSON_LIGHT),
    ]


async def main() -> int:
    """Single async entry point dispatched per platform.

    The coroutine MUST be named ``main`` — pygbag's
    ``aio/__init__.py:run`` special-cases this name to wrap the call
    in ``aio.fetch.preload`` and keep the browser event loop alive
    until the coroutine returns.
    """
    from gaia_ultimatum.app import run_async

    if sys.platform == "emscripten":
        return await run_async(_web_argv())
    if _is_android():
        return await run_async(_android_argv())
    return await run_async(sys.argv[1:])


# One top-level ``asyncio.run(main())`` — the pattern pygbag's
# ``check_code`` (``cpythonrc.py:778``) scans for. On desktop this is
# the standard blocking implementation; on emscripten pygbag's patched
# version schedules the coroutine on the browser event loop and the
# loop drives it from there.
asyncio.run(main())
