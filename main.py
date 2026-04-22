"""Pygbag web entry point.

Pygbag looks for ``main.py`` at the project root and bundles everything in
that directory (including the ``gaia_ultimatum`` package and its assets) into
a WebAssembly payload served as a static site.

The loop is driven by ``asyncio.run`` so it cooperates with the browser's
event loop. See ``gaia_ultimatum.app.run_async`` for the actual game loop.
"""

from __future__ import annotations

import asyncio
import sys

from gaia_ultimatum.app import run_async
from gaia_ultimatum.assets import ZONES_GEOJSON_LIGHT


def _web_argv() -> list[str]:
    """Default CLI arguments tuned for the browser build.

    - Use the smaller 1 MB GeoJSON (``zones.geo.json``) instead of the full
      24 MB version, to keep the initial download reasonable.
    - Disable audio by default: pygame's mixer may not be available in all
      browsers, and the player can still unmute via config.
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


asyncio.run(run_async(_web_argv()))
sys.exit(0)
