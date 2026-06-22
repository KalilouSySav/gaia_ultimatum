"""Font loading.

Prefers the bundled Inter family (SIL OFL) for clean modern UI typography,
falling back to system fonts when the file isn't available (e.g. running
from a stripped install).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pygame

from gaia_ultimatum.assets import FONTS_DIR

logger = logging.getLogger(__name__)

INTER_FILE = FONTS_DIR / "Inter-Regular.ttf"
ICONS_FILE = FONTS_DIR / "fontawesome-webfont.ttf"
SYSFONT_FALLBACK = "Segoe UI,Inter,Helvetica Neue,Cantarell,DejaVu Sans,Arial"
# Extended with Linux-default monospace fonts. The prior list
# (``Cascadia Code, JetBrains Mono, Consolas, Menlo, Courier New``)
# covered Windows (Cascadia / Consolas / Courier New) and macOS
# (Menlo) but had **no Linux default match** — Courier New requires
# the ``msttcorefonts`` package, which Debian/Ubuntu no longer
# install by default since the licence change. A default-install
# Linux user fell all the way through to pygame's ``freesansbold``
# default, which is **not monospaced**, and every stat column in
# the HUD (``"62 %"``, ``"1,4 G"``, ``"Jour 12"``) lost tabular-
# figure alignment. ``DejaVu Sans Mono`` ships with virtually every
# modern Linux distro; ``Liberation Mono`` covers RHEL/Fedora;
# ``Ubuntu Mono`` covers Ubuntu's default-snap path. Order kept
# Windows/macOS first so users with the original fonts still hit
# their preferred match before the Linux fallbacks.
MONO_SYSFONT = (
    "Cascadia Code,JetBrains Mono,Consolas,Menlo,Courier New,"
    "DejaVu Sans Mono,Liberation Mono,Ubuntu Mono"
)


# FontAwesome 4.x glyph code points in the private-use area. Only the
# three currently-wired glyphs are kept — the renderer used to import
# PLAY / PAUSE / FORWARD too, but speed control rendering switched
# to procedural pip-and-numeral buttons, so those imports went stale.
ICON_VOLUME_UP = ""
ICON_VOLUME_OFF = ""
ICON_QUESTION = ""


def _ui_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Load Inter at ``size``; fall back to a system sans on failure."""
    if INTER_FILE.is_file():
        try:
            font = pygame.font.Font(str(INTER_FILE), size)
            if bold:
                font.set_bold(True)
            return font
        except (pygame.error, OSError) as exc:
            logger.warning("Failed to load %s: %s — falling back to system font", INTER_FILE, exc)
    return pygame.font.SysFont(SYSFONT_FALLBACK, size, bold=bold)


def _mono_font(size: int, bold: bool = False) -> pygame.font.Font:
    """Load a system mono font; fall back to Inter when SysFont fails.

    ``pygame.font.SysFont`` resolves family names via ``fontconfig``
    (``fc-list``) on Linux. Android has no ``fc-list`` binary and the
    app sandbox refuses to execute arbitrary binaries — calling
    ``SysFont`` there raises ``PermissionError: [Errno 13] Permission
    denied: 'fc-list'`` and kills the process. Same shape on minimal
    Linux containers without fontconfig. Catching this means desktop
    keeps its tabular-figures mono and Android silently degrades to
    Inter (proportional). The visual regression on Android — stat
    columns no longer perfectly aligned — is the price of avoiding a
    separate bundled mono TTF; revisit if that becomes a complaint.
    """
    try:
        return pygame.font.SysFont(MONO_SYSFONT, size, bold=bold)
    except (pygame.error, OSError, PermissionError) as exc:
        logger.warning(
            "SysFont(%s) unavailable (%s); falling back to Inter",
            MONO_SYSFONT, exc,
        )
        return _ui_font(size, bold=bold)


def _icons_font(size: int) -> pygame.font.Font | None:
    """Load FontAwesome at ``size``. Returns None when the file is unavailable."""
    if not ICONS_FILE.is_file():
        return None
    try:
        return pygame.font.Font(str(ICONS_FILE), size)
    except (pygame.error, OSError) as exc:
        logger.warning("Failed to load %s: %s", ICONS_FILE, exc)
        return None


@dataclass
class Fonts:
    small: pygame.font.Font
    medium: pygame.font.Font
    large: pygame.font.Font
    title: pygame.font.Font
    mono: pygame.font.Font
    label: pygame.font.Font
    hero: pygame.font.Font  # large display number for stat panels
    giant: pygame.font.Font  # 60pt+ for title screens
    icons: pygame.font.Font | None  # FontAwesome glyphs (None when missing)

    @classmethod
    def create(cls) -> Fonts:
        if not pygame.font.get_init():
            pygame.font.init()
        # Sizes tuned for a 960×640 default canvas. The modular scale (12 → 14
        # → 17 → 22 → 30 → 60) gives clear hierarchy: body / caption / detail
        # / section / display / title. Label stays the tracked-out 12pt
        # uppercase for chip rows and tab caps.
        return cls(
            small=_ui_font(14),         # was 13
            medium=_ui_font(17),        # was 16
            large=_ui_font(22),
            title=_ui_font(30, bold=True),  # was 28
            # Mono stays a system mono — Inter isn't monospaced, and stat
            # columns benefit from tabular figures. On Android (and any
            # host without fontconfig) ``_mono_font`` silently falls back
            # to Inter; see the helper for the rationale.
            mono=_mono_font(19, bold=True),  # was 18
            label=_ui_font(12, bold=True),  # was 11 — better small-caps legibility
            hero=_mono_font(30, bold=True),  # was 28
            giant=_ui_font(62, bold=True),  # was 60
            icons=_icons_font(16),
        )
