"""Test configuration.

Force SDL into headless mode so tests can run on CI without a display or audio
device.
"""

from __future__ import annotations

import os

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
