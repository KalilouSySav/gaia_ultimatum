"""Asset path resolution.

Resolves paths to bundled resources (GeoJSON, sounds, fonts, images) relative to
the installed package so the game runs from any working directory.
"""

from __future__ import annotations

from pathlib import Path

PACKAGE_ROOT: Path = Path(__file__).resolve().parent

DATA_DIR: Path = PACKAGE_ROOT / "data"
SOUNDS_DIR: Path = PACKAGE_ROOT / "sounds"
CINEMATICS_DIR: Path = PACKAGE_ROOT / "cinematics"
IMAGES_DIR: Path = DATA_DIR / "images"
FONTS_DIR: Path = DATA_DIR / "fonts"

ZONES_GEOJSON: Path = DATA_DIR / "zones.geojson"


def asset(relative_path: str | Path) -> Path:
    """Return an absolute path to an asset under the package root."""
    return PACKAGE_ROOT / relative_path
