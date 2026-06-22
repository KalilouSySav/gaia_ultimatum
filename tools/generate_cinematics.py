"""Procedural intro/outro MP4 generator.

Renders the two cinematic clips that ship with the game directly from the
in-game palette + Inter font, so the cinematics share the same visual
language as the menus (deep indigo backdrop, blue title glow, particle
field, procedural Earth). The output drops into ``gaia_ultimatum/cinematics/``
where ``CinematicLibrary`` picks it up at runtime.

Run from the repo root::

    python tools/generate_cinematics.py

Requires ``opencv-python`` and ``pygame-ce`` (both already in requirements).
Idempotent — produces the same bytes on the same machine for the same code.
"""

from __future__ import annotations

import math
import os
import random
import sys
from pathlib import Path
from typing import Callable

import numpy as np
import pygame

# Make the package importable without installing it.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Headless rendering — no SDL window required for offline generation.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import cv2  # noqa: E402 — must come after env-var nudge

from gaia_ultimatum.assets import CINEMATICS_DIR, FONTS_DIR  # noqa: E402

INTER_FILE = FONTS_DIR / "Inter-Regular.ttf"

W, H = 960, 540
FPS = 30


# ---------------------------------------------------------- shared helpers


def _font(size: int, bold: bool = False) -> pygame.font.Font:
    """Load Inter at ``size``, falling back to a sysfont if missing."""
    if INTER_FILE.is_file():
        font = pygame.font.Font(str(INTER_FILE), size)
        font.set_bold(bold)
        return font
    return pygame.font.SysFont(
        "Segoe UI,Inter,Helvetica Neue,Arial", size, bold=bold,
    )


def _blend(
    a: tuple[int, int, int],
    b: tuple[int, int, int],
    ratio: float,
) -> tuple[int, int, int]:
    ratio = max(0.0, min(1.0, ratio))
    return (
        int(a[0] + (b[0] - a[0]) * ratio),
        int(a[1] + (b[1] - a[1]) * ratio),
        int(a[2] + (b[2] - a[2]) * ratio),
    )


def _gradient_bg(
    top: tuple[int, int, int], bottom: tuple[int, int, int],
) -> pygame.Surface:
    """Cached vertical gradient backdrop, matching the title screen."""
    surf = pygame.Surface((W, H))
    for y in range(H):
        t = y / max(1, H - 1)
        col = _blend(top, bottom, t)
        pygame.draw.line(surf, col, (0, y), (W, y))
    return surf


def _draw_grid(surface: pygame.Surface, alpha: int) -> None:
    """Faint lat/long grid lines, mirroring the in-game map's ocean grid."""
    if alpha <= 0:
        return
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    minor = (24, 30, 46, alpha)
    major = (38, 48, 70, alpha)
    step = 60
    for x in range(0, W, step):
        color = major if (x % (step * 2) == 0) else minor
        pygame.draw.line(layer, color, (x, 0), (x, H), 1)
    for y in range(0, H, step):
        color = major if (y % (step * 2) == 0) else minor
        pygame.draw.line(layer, color, (0, y), (W, y), 1)
    surface.blit(layer, (0, 0))


def _draw_planet(
    surface: pygame.Surface,
    center: tuple[int, int],
    radius: int,
    cracked: bool = False,
) -> None:
    """Procedural Earth — blue oceans, green landmasses, crescent shadow.

    ``cracked`` adds a few red fissure lines for the outro variant so the
    same shape can read as "stressed planet" without a separate asset.
    """
    cx, cy = center
    if radius < 6:
        return
    # Ocean body — radial gradient from a brighter top-left to a deeper edge.
    body = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        t = r / radius
        col = _blend((90, 145, 215), (16, 44, 90), 1.0 - t)
        pygame.draw.circle(body, (*col, 255), (radius + 1, radius + 1), r)
    surface.blit(body, (cx - radius - 1, cy - radius - 1))
    # Procedural landmasses — fixed seed for stable output across runs. Each
    # continent is a cluster of 3–6 overlapping ovals rather than a single
    # circle, so the silhouette reads as continents instead of dots. Sampled
    # in polar coordinates so the points are spread evenly across the disc
    # instead of clustering in the centre.
    rng = random.Random(2026)
    inner = radius - 16
    if inner > 8:
        light_green = (88, 158, 110)
        dark_green = (54, 100, 72)
        n_continents = 6 if radius < 80 else 8
        for _ in range(n_continents):
            r_polar = rng.uniform(0.05, 0.85) * inner
            theta = rng.uniform(0, math.pi * 2)
            lcx = int(cx + math.cos(theta) * r_polar)
            lcy = int(cy + math.sin(theta) * r_polar)
            blob_count = rng.randint(3, 5)
            base_size = max(4, int(radius * rng.uniform(0.05, 0.13)))
            green = _blend(light_green, dark_green, rng.random())
            for _b in range(blob_count):
                bx = lcx + rng.randint(-base_size, base_size)
                by = lcy + rng.randint(-base_size, base_size)
                # Clip to disc using the *maximum* draw radius of the
                # blob (``base_size``) rather than a flat 2-px buffer.
                # Was ``> radius - 2``: a blob centred at distance
                # ``radius - 5`` with draw radius up to 10 leaked into
                # space by 5 px, producing green continents floating
                # off the disc. Using ``radius - base_size`` keeps
                # every blob's extent inside the limb. Slight density
                # drop near the rim is the right tradeoff — land at
                # the limb reads as "land near the limb", not as
                # "land floating in the void".
                if math.hypot(bx - cx, by - cy) > radius - base_size:
                    continue
                bsize = rng.randint(
                    max(3, base_size // 2),
                    max(5, base_size),
                )
                pygame.draw.circle(surface, green, (bx, by), bsize)
    # Specular highlight — directional hot spot upper-left, anti-
    # symmetric to the crescent shadow's lower-right offset, so the
    # apparent light source comes from the upper-left across every
    # cinematic the planet appears in. Was missing entirely: the
    # body's centred radial gradient gave a vignette feel
    # ("uniform with darker edges") rather than 3D form ("lit from
    # a direction"). The cubic alpha falloff (``(1-t)**1.6``) keeps
    # the hot spot tight at the centre and fades smoothly outward
    # instead of producing a flat ring of brightness. White-blue
    # tint (235, 240, 255) sits in the ocean colour family so the
    # highlight reads as illumination on the ocean rather than as
    # a separate object.
    if radius >= 14:
        hl_r = max(4, int(radius * 0.35))
        hl_offset_x = -int(radius * 0.30)
        hl_offset_y = -int(radius * 0.28)
        highlight = pygame.Surface(
            (hl_r * 2 + 4, hl_r * 2 + 4), pygame.SRCALPHA,
        )
        for r in range(hl_r, 0, -1):
            t = r / hl_r
            a = int(70 * (1.0 - t) ** 1.6)
            if a < 1:
                continue
            pygame.draw.circle(
                highlight, (235, 240, 255, a),
                (hl_r + 2, hl_r + 2), r,
            )
        surface.blit(
            highlight,
            (cx + hl_offset_x - hl_r - 2,
             cy + hl_offset_y - hl_r - 2),
        )
    # Crescent shadow — soft right-side fade for depth. Drawn AFTER
    # the highlight so the dark side stays dark even where it
    # overlaps the highlight's outer falloff (rare, since the
    # highlight is offset upper-left and the shadow lower-right).
    shadow = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
    for r in range(radius, 0, -2):
        t = r / radius
        a = int(110 * t ** 2)
        pygame.draw.circle(
            shadow, (4, 6, 12, a),
            (radius + 2 + int(radius * 0.25), radius + 2),
            r,
        )
    surface.blit(shadow, (cx - radius - 2, cy - radius - 2))
    # Outer atmosphere glow.
    glow = pygame.Surface((radius * 2 + 40, radius * 2 + 40), pygame.SRCALPHA)
    for r in range(radius + 20, radius, -1):
        t = (r - radius) / 20
        a = int(80 * (1.0 - t))
        if a < 1:
            continue
        pygame.draw.circle(
            glow, (110, 160, 230, a),
            (radius + 20, radius + 20), r, 1,
        )
    surface.blit(glow, (cx - radius - 20, cy - radius - 20))
    # Outro variant — sparse red fissures suggesting a stressed planet.
    if cracked and radius > 40:
        rng2 = random.Random(7)
        for _ in range(4):
            angle = rng2.random() * math.pi * 2
            length = rng2.randint(30, max(31, radius - 12))
            sx = int(cx + math.cos(angle) * 10)
            sy = int(cy + math.sin(angle) * 10)
            ex = int(cx + math.cos(angle) * length)
            ey = int(cy + math.sin(angle) * length)
            pygame.draw.line(surface, (220, 80, 70), (sx, sy), (ex, ey), 2)


def _draw_particles(
    surface: pygame.Surface,
    particles: list[dict],
    tint: tuple[int, int, int],
) -> None:
    """Persistent particle field with a symmetric birth/death envelope.

    Previously a single ``_blend(dark, tint, ratio)`` where ``ratio``
    went 1.0→0.0 across the particle's lifetime. That meant particles
    were drawn at *full tint* on their very first frame (ratio=1) and
    only the death-side faded — every particle popped into existence.

    Now a 15 % fade-in / 55 % hold / 30 % fade-out envelope multiplies
    the blend factor, so particles emerge from the background colour
    instead of materialising at full saturation. Asymmetric weights
    (fade-out longer than fade-in) match how natural mist / dust
    behaves: presence accumulates quickly, dissipates slowly.

    Implemented via colour-blend (not SRCALPHA + alpha multiply) so
    cost stays at one ``draw.circle`` per particle — ~50 calls/frame
    at steady state, negligible.
    """
    for p in particles:
        ratio = p["lifetime"] / max(1, p["max_lifetime"])  # 1 at birth → 0 at death
        # Envelope: (1-ratio)/0.15 during fade-in (ratio in [0.85, 1]),
        # 1.0 during hold (ratio in [0.30, 0.85]), ratio/0.30 during
        # fade-out (ratio in [0, 0.30]).
        if ratio > 0.85:
            env = (1.0 - ratio) / 0.15
        elif ratio > 0.30:
            env = 1.0
        else:
            env = ratio / 0.30
        if env <= 0:
            continue
        color = _blend((16, 16, 24), tint, env)
        pygame.draw.circle(
            surface, color, (int(p["x"]), int(p["y"])), p["size"],
        )


def _step_particles(particles: list[dict], spawn_rate: float = 0.18) -> list[dict]:
    """Advance particles by one tick. Wraps at canvas edges instead of killing.

    Previously particles that exited the canvas (any of the 4 edges)
    were killed instantly, which combined badly with the ``vy = -0.18``
    upward drift: particles spawned in the top ~50 px of the canvas
    died in 1-3 frames before their lifetime envelope could play, and
    the top of the canvas thinned out over a cinematic's runtime.

    Edge-wrapping (exit-left → enter-right etc.) keeps the field
    continuous. The visible effect is a slow "atmospheric mist"
    that drifts upward forever — particles that drift off the top
    re-enter at the bottom and keep contributing to the field
    until their lifetime naturally expires. Matches the cinematic
    intent ("ambient particle field"), not the prior accidental
    behaviour ("particles die at the edges").
    """
    if random.random() < spawn_rate and len(particles) < 90:
        lifetime = random.randint(140, 280)
        particles.append({
            "x": random.uniform(0.0, W),
            "y": random.uniform(0.0, H),
            "vx": (random.random() * 2.0 - 1.0) * 0.55,
            "vy": (random.random() * 2.0 - 1.0) * 0.55 - 0.18,
            "lifetime": lifetime,
            "max_lifetime": lifetime,
            "size": random.randint(1, 3),
        })
    survivors: list[dict] = []
    for p in particles:
        p["x"] += p["vx"]
        p["y"] += p["vy"]
        p["lifetime"] -= 1
        if p["lifetime"] <= 0:
            continue
        # Edge wrap — keeps the field continuous across the entire
        # particle's lifetime regardless of how strong its drift is.
        if p["x"] < 0:
            p["x"] += W
        elif p["x"] >= W:
            p["x"] -= W
        if p["y"] < 0:
            p["y"] += H
        elif p["y"] >= H:
            p["y"] -= H
        survivors.append(p)
    return survivors


def _draw_text_centered(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    y: int,
    color: tuple[int, int, int],
    *,
    alpha: int = 255,
    glow_color: tuple[int, int, int] | None = None,
) -> int:
    """Render ``text`` horizontally centred at ``y``, returns bottom-y.

    Glow is rendered as 8 offset ghosts (4 cardinals + 4 diagonals)
    instead of the prior 4-direction cross. Cardinal offsets sit at
    1.0 px from the text centre; diagonal offsets sit at
    sqrt(2) ≈ 1.41 px. Scaling diagonal ghost alpha by 1/sqrt(2)
    matches the physical distance ratio, producing a properly
    radial Gaussian-shaped halo — neither a sharp octagon (uniform
    8-direction would over-emphasise diagonals on the diagonal-axis
    rays) nor a sharp plus-cross (the old 4-direction left visible
    empty diagonals on every cinematic title, especially at giant
    font sizes).
    """
    rendered = font.render(text, True, color)
    rect_x = (W - rendered.get_width()) // 2
    if glow_color is not None and alpha > 0:
        glow = font.render(text, True, glow_color)
        base_alpha = min(alpha, 180)
        # 1/sqrt(2) ≈ 0.707 — proper inverse-distance falloff for
        # diagonals at the same nominal 1-px offset radius.
        diag_alpha = int(base_alpha * 0.707)
        for dx, dy, ghost_alpha in (
            (-1,  0, base_alpha), ( 1,  0, base_alpha),
            ( 0, -1, base_alpha), ( 0,  1, base_alpha),
            (-1, -1, diag_alpha), ( 1, -1, diag_alpha),
            (-1,  1, diag_alpha), ( 1,  1, diag_alpha),
        ):
            ghost = glow.copy()
            ghost.set_alpha(ghost_alpha)
            surface.blit(ghost, (rect_x + dx, y + dy))
    if alpha < 255:
        rendered = rendered.copy()
        rendered.set_alpha(alpha)
    surface.blit(rendered, (rect_x, y))
    return y + rendered.get_height()


def _ease_in_out(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


def _surface_to_bgr_frame(surface: pygame.Surface) -> np.ndarray:
    """Convert a pygame surface to a BGR numpy array that cv2 can write."""
    # surfarray.array3d gives shape (W, H, 3) in RGB; transpose to (H, W, 3).
    arr = pygame.surfarray.array3d(surface)
    arr = arr.swapaxes(0, 1)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _encode_clip(
    out_path: Path,
    duration_s: float,
    frame_fn: Callable[[int, float], pygame.Surface],
) -> None:
    """Drive the frame loop and write the resulting MP4 to ``out_path``."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total = int(duration_s * FPS)
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, FPS, (W, H))
    if not writer.isOpened():
        raise RuntimeError(f"cv2.VideoWriter could not open {out_path}")
    try:
        for i in range(total):
            t = i / max(1, total - 1)
            surface = frame_fn(i, t)
            writer.write(_surface_to_bgr_frame(surface))
    finally:
        writer.release()
    print(f"  wrote {out_path}  ({total} frames @ {FPS} fps, {duration_s:.1f}s)")


# ----------------------------------------------------------------- intro


def _build_intro() -> None:
    """Data-driven mission brief — three rising stats then a call to action.

    Replaces the previous title-screen-echo intro: this version doesn't try
    to repeat the menu visuals. Instead it tells a one-shot story in three
    beats — population, warming, biodiversity loss — and lands on the
    decision prompt "Vous décidez de la suite." Pacing is deliberate:
    each beat holds for ~1 s after the count-up completes so the viewer
    has time to read both the number and the caption before the next stat
    swaps in.
    """
    pygame.font.init()
    pygame.display.init()

    # 9 s total: 3 beats × 2.5 s reading time + 1.5 s CTA. Was 6 s with
    # 1.5 s beats which felt blink-and-miss-it.
    duration_s = 9.0
    fonts = {
        "stat": _font(72, bold=True),
        "stat_unit": _font(20, bold=True),
        "label": _font(12, bold=True),
        "caption": _font(17),
        "cta": _font(40, bold=True),
    }
    particles: list[dict] = []
    bg = _gradient_bg((20, 24, 40), (8, 10, 18))

    # Three sequential beats — each 2.5 s, last beat is the CTA.
    BEAT_S = 2.5
    BEATS = (
        # (label, value_target, unit, caption, accent)
        ("POPULATION MONDIALE",       8.1,  "milliards",
         "Près d'un humain sur deux vit en zone à risque.",
         (140, 170, 235)),
        ("RÉCHAUFFEMENT MOYEN",       1.2,  "°C depuis 1900",
         "Le seuil de 1,5 °C reste atteignable, mais étroit.",
         (235, 150, 90)),
        ("BIODIVERSITÉ EFFONDRÉE",    69,   "% des vertébrés depuis 1970",
         "Source: Living Planet Index 2022.",
         (110, 200, 130)),
    )

    def make_frame(i: int, t: float) -> pygame.Surface:
        nonlocal particles
        surface = pygame.Surface((W, H))
        surface.blit(bg, (0, 0))

        # 1) Faint grid, always-on but very dim.
        _draw_grid(surface, alpha=46)

        # 2) Particle field — neutral cool tint to match the briefing tone.
        particles = _step_particles(particles, spawn_rate=0.18)
        _draw_particles(surface, particles, tint=(130, 160, 220))

        # 3) Beat machine — which stat are we on, and how far through?
        total_beats = len(BEATS)
        beats_total_s = total_beats * BEAT_S
        clip_s = duration_s
        beat_phase = t * clip_s / BEAT_S  # 0 → total_beats over the beat span
        beat_idx = int(min(total_beats - 1, beat_phase))
        within = beat_phase - beat_idx
        # 0 → fade-in, 1 → hold + count-up complete, > 1 → fade out for next.
        beat_t = max(0.0, min(1.0, within))
        cta_start_s = beats_total_s
        is_cta = (t * clip_s) >= cta_start_s

        if not is_cta:
            label, target, unit, caption, accent = BEATS[beat_idx]
            # Count-up easing for the big number.
            value_t = _ease_in_out(min(1.0, beat_t / 0.7))
            displayed = target * value_t
            # Label — top, uppercase tracked label like dashboard sections.
            label_alpha = int(255 * _ease_in_out(min(1.0, beat_t / 0.25)))
            label_drift = int((1.0 - min(1.0, beat_t / 0.25)) * -16)
            label_surf = fonts["label"].render(label, True, accent)
            label_surf.set_alpha(label_alpha)
            surface.blit(
                label_surf,
                ((W - label_surf.get_width()) // 2,
                 int(H * 0.20) + label_drift),
            )
            # Hero numeric — formatted to one decimal for the floats.
            if isinstance(target, float):
                value_str = f"{displayed:.1f}".replace(".", ",")
            else:
                value_str = f"{int(displayed)}"
            value_surf = fonts["stat"].render(
                value_str, True, (245, 248, 255),
            )
            # Scale pulse — marks the moment the count-up *lands*. The
            # count-up easing (value_t) reaches 1.0 at beat_t = 0.7, so
            # the number is settled by then. Bell-curve pulse over the
            # next 20 % of the beat (beat_t 0.70 → 0.90) gently scales
            # the value 1.00 → 1.06 → 1.00 — small enough to feel like
            # natural emphasis, big enough that the eye registers the
            # number's arrival. Without this the value just stopped
            # animating and held flat; the beat felt half-finished.
            pulse_start = 0.70
            pulse_end = 0.90
            base_y_top = int(H * 0.30)
            value_h_base = value_surf.get_height()
            value_w_base = value_surf.get_width()
            if pulse_start <= beat_t <= pulse_end:
                pulse_local = (beat_t - pulse_start) / (pulse_end - pulse_start)
                # Bell: 4·t·(1−t) peaks at t = 0.5.
                bell = 4.0 * pulse_local * (1.0 - pulse_local)
                scale = 1.0 + 0.06 * bell
                new_w = int(value_w_base * scale)
                new_h = int(value_h_base * scale)
                value_surf = pygame.transform.smoothscale(
                    value_surf, (new_w, new_h),
                )
            # Anchor by the value's natural centre so the scale pulse
            # doesn't shift the layout.
            center_x = W // 2
            center_y = base_y_top + value_h_base // 2
            surface.blit(
                value_surf,
                (center_x - value_surf.get_width() // 2,
                 center_y - value_surf.get_height() // 2),
            )
            unit_surf = fonts["stat_unit"].render(
                unit, True, accent,
            )
            # Anchor the unit relative to the *base* value height, not
            # the post-pulse scaled height, so the unit doesn't bob with
            # the pulse animation.
            surface.blit(
                unit_surf,
                ((W - unit_surf.get_width()) // 2,
                 base_y_top + value_h_base - 4),
            )
            # Caption beneath — text-rich line for context. Drop shadow
            # for legibility against the grid + grain backdrop.
            caption_alpha = int(255 * _ease_in_out(min(1.0, (beat_t - 0.10) / 0.35)))
            if caption_alpha > 0:
                _draw_subtitle(
                    surface, caption, fonts["caption"],
                    (200, 210, 230), int(H * 0.66),
                    alpha=caption_alpha,
                )
            # Beat indicator dots at the bottom — visual progress through
            # the 3-beat brief. Filled = past, ring = current.
            # Connector line beneath the dots makes the rhythm visible —
            # past segments stay bright white, the current segment fills
            # progressively as the beat advances (acts as a tiny inline
            # progress bar through the brief), future segments stay dim.
            # The dots used to read as three disconnected pips; the
            # connector turns them into a *path* the player is walking.
            dot_y = H - 60
            dot_total_w = total_beats * 18 + (total_beats - 1) * 10
            dot_left = (W - dot_total_w) // 2
            # Connector segments drawn before dots so the circles sit on top.
            for d in range(total_beats - 1):
                cx_a = dot_left + d * 28 + 9 + 6   # +6 to clear dot radius
                cx_b = dot_left + (d + 1) * 28 + 9 - 6
                if d < beat_idx:
                    # Past segment — fully traversed, bright.
                    pygame.draw.line(
                        surface, (245, 248, 255),
                        (cx_a, dot_y), (cx_b, dot_y), 2,
                    )
                elif d == beat_idx:
                    # Active segment — fill grows with within (0..1).
                    fill_x = cx_a + int((cx_b - cx_a) * within)
                    if fill_x > cx_a:
                        pygame.draw.line(
                            surface, accent,
                            (cx_a, dot_y), (fill_x, dot_y), 2,
                        )
                    if fill_x < cx_b:
                        pygame.draw.line(
                            surface, (60, 70, 90),
                            (fill_x, dot_y), (cx_b, dot_y), 1,
                        )
                else:
                    # Future segment — dim hairline.
                    pygame.draw.line(
                        surface, (60, 70, 90),
                        (cx_a, dot_y), (cx_b, dot_y), 1,
                    )
            for d in range(total_beats):
                cx = dot_left + d * 28 + 9
                if d < beat_idx:
                    pygame.draw.circle(surface, (245, 248, 255), (cx, dot_y), 5)
                elif d == beat_idx:
                    pygame.draw.circle(surface, accent, (cx, dot_y), 6, 2)
                else:
                    pygame.draw.circle(surface, (90, 100, 120), (cx, dot_y), 4, 1)
        else:
            # CTA beat — "Vous décidez de la suite." plays after the brief.
            cta_t = _ease_in_out(min(1.0, (t * clip_s - cta_start_s) / 0.6))
            label_alpha = int(255 * cta_t)
            cta_drift = int((1.0 - cta_t) * 20)
            tag = fonts["label"].render(
                "SIMULATION TERRE VIVANTE", True, (180, 195, 235),
            )
            tag.set_alpha(label_alpha)
            surface.blit(
                tag,
                ((W - tag.get_width()) // 2, int(H * 0.30) + cta_drift),
            )
            cta = fonts["cta"].render(
                "Vous décidez de la suite.", True, (245, 248, 255),
            )
            cta_layer = pygame.Surface(
                (cta.get_width() + 4, cta.get_height() + 4),
                pygame.SRCALPHA,
            )
            # Soft glow ghost — matches the title-screen halo idiom.
            glow = fonts["cta"].render(
                "Vous décidez de la suite.", True, (90, 110, 220),
            )
            for off in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                ghost = glow.copy()
                ghost.set_alpha(min(label_alpha, 160))
                cta_layer.blit(ghost, (2 + off[0], 2 + off[1]))
            cta_layer.blit(cta, (2, 2))
            cta_layer.set_alpha(label_alpha)
            surface.blit(
                cta_layer,
                ((W - cta.get_width()) // 2 - 2,
                 int(H * 0.38) + cta_drift),
            )

        # 4) Shared cinematic envelope — corner vignette + film grain.
        _apply_cinematic_envelope(surface, i)

        # 5) Animated letterbox bars — slide in during the fade-in and
        # out during the fade-out for a "curtain rises / falls" moment.
        _draw_animated_letterbox(surface, t=t, accent=(60, 80, 130))

        # 6) Fade-in / fade-out veils.
        if t < 0.05:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (1.0 - t / 0.05))))
            surface.blit(veil, (0, 0))
        elif t > 0.93:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (t - 0.93) / 0.07)))
            surface.blit(veil, (0, 0))

        return surface

    _encode_clip(CINEMATICS_DIR / "intro.mp4", duration_s, make_frame)


# ----------------------------------------------------------------- outro


def _build_outro() -> None:
    pygame.font.init()
    pygame.display.init()

    duration_s = 5.0
    fonts = {
        "title": _font(34, bold=True),
        "medium": _font(17),
        "label": _font(12, bold=True),
    }
    particles: list[dict] = []
    bg = _gradient_bg((28, 22, 38), (10, 10, 18))

    # Layout — planet lifted into the upper half, text stacked below in a
    # tag → question → reflection column. No overlap at any frame.
    PLANET_CY = int(H * 0.36)
    TAG_Y = int(H * 0.62)
    QUESTION_Y = TAG_Y + 28
    LINE_Y = QUESTION_Y + 70

    def make_frame(i: int, t: float) -> pygame.Surface:
        nonlocal particles
        surface = pygame.Surface((W, H))
        surface.blit(bg, (0, 0))

        # 1) Soft radial bloom in a reflective amber tone (between victory
        # green and defeat red so the clip stays neutral re: outcome).
        bloom_t = _ease_in_out(min(1.0, t / 0.30))
        bloom_alpha_max = int(70 * bloom_t)
        if bloom_alpha_max > 4:
            bloom_r = int(min(W, H) * 0.55)
            bloom = pygame.Surface((bloom_r * 2, bloom_r * 2), pygame.SRCALPHA)
            tint = (220, 170, 90)
            for r in range(bloom_r, 0, -3):
                rt = r / bloom_r
                a = int(bloom_alpha_max * (1 - rt) ** 1.8)
                if a < 1:
                    continue
                pygame.draw.circle(bloom, (*tint, a), (bloom_r, bloom_r), r)
            surface.blit(
                bloom, (W // 2 - bloom_r, PLANET_CY - bloom_r),
            )

        # 2) Stressed Earth — same procedural planet with light fissures.
        planet_t = _ease_in_out(min(1.0, max(0.0, (t - 0.05) / 0.30)))
        planet_radius = int(110 * planet_t)
        if planet_radius > 6:
            _draw_planet(
                surface,
                (W // 2, PLANET_CY),
                planet_radius,
                cracked=True,
            )

        # 3) Particle field — ascending warm motes ("memories rising").
        particles = _step_particles(particles, spawn_rate=0.16)
        for p in particles:
            p["vy"] -= 0.012  # drift upward across the clip
        _draw_particles(surface, particles, tint=(220, 170, 90))

        # 4) Section tag fades in first — drop shadow for legibility
        # over the amber bloom + planet body.
        tag_t = _ease_in_out(min(1.0, max(0.0, (t - 0.20) / 0.20)))
        if tag_t > 0:
            _draw_subtitle(
                surface, "ÉPILOGUE", fonts["label"],
                (220, 170, 90), TAG_Y,
                alpha=int(255 * tag_t),
            )

        # 5) Reflective question — main piece of text (title-size, fits 960 px).
        q_t = _ease_in_out(min(1.0, max(0.0, (t - 0.32) / 0.28)))
        if q_t > 0:
            _draw_text_centered(
                surface,
                "L'HUMANITÉ AURA-T-ELLE APPRIS ?",
                font=fonts["title"],
                y=QUESTION_Y + int((1.0 - q_t) * 14),
                color=(245, 240, 230),
                alpha=int(255 * q_t),
                glow_color=(180, 110, 60),
            )

        # 6) Closing line — fades in last, drifts up subtly. Drop
        # shadow for legibility over the amber-bloomed planet field.
        line_t = _ease_in_out(min(1.0, max(0.0, (t - 0.55) / 0.25)))
        if line_t > 0:
            _draw_subtitle(
                surface,
                "Chaque jour est une leçon. Chaque partie, un avertissement.",
                fonts["medium"],
                (210, 210, 220),
                LINE_Y + int((1.0 - line_t) * 8),
                alpha=int(255 * line_t),
            )

        # 7) Shared cinematic envelope — corner vignette + film grain.
        _apply_cinematic_envelope(surface, i)

        # 8) Fade-in / fade-out veils.
        if t < 0.06:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (1.0 - t / 0.06))))
            surface.blit(veil, (0, 0))
        elif t > 0.90:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (t - 0.90) / 0.10)))
            surface.blit(veil, (0, 0))

        return surface

    _encode_clip(CINEMATICS_DIR / "outro.mp4", duration_s, make_frame)


def _build_midgame() -> None:
    """In-game cinematic — fires once per session at the first major
    threshold crossing (e.g. half the world in critical state).

    Extended from 2.5 s to 3.5 s so the player has time to read both the
    title and the caption. Ascending warm sparks drift upward through the
    frame for tension; the central warning glyph beats softly; the rings
    cascade outward as before.
    """
    pygame.font.init()
    pygame.display.init()
    duration_s = 3.5
    fonts = {
        "label": _font(12, bold=True),
        "title": _font(38, bold=True),
        "caption": _font(17),
    }
    bg = _gradient_bg((36, 18, 22), (10, 6, 10))
    sparks: list[dict] = []
    seed_rng = random.Random(2026)

    def _step_sparks() -> None:
        # Ascending warm sparks — burns + smoke vibe. Deterministic seed so
        # the same clip is reproducible across runs.
        if seed_rng.random() < 0.28 and len(sparks) < 36:
            lifetime = seed_rng.randint(40, 90)
            sparks.append({
                "x": seed_rng.uniform(0.0, W),
                "y": seed_rng.uniform(H * 0.55, H + 20),
                "vx": (seed_rng.random() * 2.0 - 1.0) * 0.4,
                "vy": -seed_rng.uniform(0.6, 1.6),
                "lifetime": lifetime,
                "max_lifetime": lifetime,
                "size": seed_rng.randint(1, 3),
            })
        survivors: list[dict] = []
        for p in sparks:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["lifetime"] -= 1
            if p["lifetime"] > 0 and 0 <= p["x"] < W:
                survivors.append(p)
        sparks.clear()
        sparks.extend(survivors)

    def make_frame(i: int, t: float) -> pygame.Surface:
        surface = pygame.Surface((W, H))
        surface.blit(bg, (0, 0))
        _draw_grid(surface, alpha=44)

        # Ascending sparks (warm tone, behind the rings).
        _step_sparks()
        for p in sparks:
            ratio = p["lifetime"] / max(1, p["max_lifetime"])
            color = _blend((16, 10, 10), (235, 165, 95), ratio)
            pygame.draw.circle(
                surface, color, (int(p["x"]), int(p["y"])), p["size"],
            )

        # Pulsing red rings at screen centre — three cascading outward.
        cx, cy = W // 2, H // 2 - 24
        for ring_i in range(3):
            ring_phase = (t + ring_i * 0.33) % 1.0
            if ring_phase > 0.85:
                continue
            ring_r = int(60 + ring_phase * 280)
            ring_alpha = int(190 * (1.0 - ring_phase))
            if ring_alpha < 4:
                continue
            ring_layer = pygame.Surface(
                (ring_r * 2 + 6, ring_r * 2 + 6), pygame.SRCALPHA,
            )
            pygame.draw.circle(
                ring_layer, (220, 90, 80, ring_alpha),
                (ring_r + 3, ring_r + 3), ring_r, 3,
            )
            surface.blit(ring_layer, (cx - ring_r - 3, cy - ring_r - 3))

        # Centre warning glyph — triangle with !, breathing softly via a
        # quick sine scale so the moment feels alive.
        beat = 1.0 + 0.07 * math.sin(t * math.pi * 6)
        tri_r = int(30 * beat)
        tri = [
            (cx, cy - tri_r),
            (cx + int(tri_r * 0.95), cy + int(tri_r * 0.7)),
            (cx - int(tri_r * 0.95), cy + int(tri_r * 0.7)),
        ]
        pygame.draw.polygon(surface, (220, 90, 80), tri, 3)
        bang = fonts["title"].render("!", True, (235, 95, 85))
        surface.blit(
            bang,
            (cx - bang.get_width() // 2, cy - bang.get_height() // 2 + 2),
        )

        # Text block below the ring — label, headline, caption.
        # Drop-shadow on label + caption for legibility over the
        # red-ring backdrop and grain.
        label_t = _ease_in_out(min(1.0, t / 0.20))
        _draw_subtitle(
            surface, "POINT DE BASCULE", fonts["label"],
            (230, 145, 115),
            cy + 60, alpha=int(255 * label_t),
        )
        title_t = _ease_in_out(min(1.0, max(0.0, (t - 0.10) / 0.25)))
        title_alpha = int(255 * title_t)
        title_drift = int((1.0 - title_t) * 18)
        title_text = "Moitié du monde en crise."
        title_y = cy + 80 + title_drift
        title_surf = fonts["title"].render(
            title_text, True, (245, 235, 230),
        )
        if title_alpha < 255:
            title_surf.set_alpha(title_alpha)
        surface.blit(
            title_surf,
            ((W - title_surf.get_width()) // 2, title_y),
        )
        # Title underline — accent rule that draws in after the title
        # settles. Same idiom as the element cards' hero underline.
        _draw_title_underline(
            surface,
            t=t, title_y=title_y, title_text=title_text,
            font=fonts["title"], accent=(220, 90, 80),
            width_ratio=0.50,
        )
        cap_t = _ease_in_out(min(1.0, max(0.0, (t - 0.30) / 0.25)))
        if cap_t > 0:
            _draw_subtitle(
                surface, "Chaque jour pèse plus lourd. Recalibrez.",
                fonts["caption"], (210, 200, 215),
                cy + 134, alpha=int(255 * cap_t),
            )

        # Shared cinematic envelope — corner vignette + film grain.
        _apply_cinematic_envelope(surface, i)

        # Animated letterbox — red-tinted hairline.
        _draw_animated_letterbox(surface, t=t, accent=(90, 50, 50))

        # Fade in / out veils.
        if t < 0.06:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (1.0 - t / 0.06))))
            surface.blit(veil, (0, 0))
        elif t > 0.90:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (t - 0.90) / 0.10)))
            surface.blit(veil, (0, 0))
        return surface

    _encode_clip(CINEMATICS_DIR / "midgame.mp4", duration_s, make_frame)


def _build_victory() -> None:
    """Outcome-specific cinematic — fires on a VICTORY transition before the
    neutral epilogue. Ascending sparks, sage-green palette, a tag + headline
    + reflective closer mirroring the outro layout so the two clips read as
    a pair, not strangers.
    """
    pygame.font.init()
    pygame.display.init()
    duration_s = 3.5
    fonts = {
        "label": _font(12, bold=True),
        "title": _font(40, bold=True),
        "caption": _font(17),
    }
    bg = _gradient_bg((16, 30, 24), (4, 12, 10))
    sparks: list[dict] = []
    seed_rng = random.Random(7)

    def _step_sparks() -> None:
        if seed_rng.random() < 0.30 and len(sparks) < 50:
            lifetime = seed_rng.randint(60, 130)
            sparks.append({
                "x": seed_rng.uniform(0.0, W),
                "y": seed_rng.uniform(H * 0.55, H + 20),
                "vx": (seed_rng.random() * 2.0 - 1.0) * 0.35,
                # Victory: sparks rise *faster* than midgame's tension sparks
                # so the motion reads as "ascending hope" rather than embers.
                "vy": -seed_rng.uniform(0.9, 1.9),
                "lifetime": lifetime,
                "max_lifetime": lifetime,
                "size": seed_rng.randint(1, 3),
            })
        survivors: list[dict] = []
        for p in sparks:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["lifetime"] -= 1
            if p["lifetime"] > 0 and 0 <= p["x"] < W:
                survivors.append(p)
        sparks.clear()
        sparks.extend(survivors)

    def make_frame(i: int, t: float) -> pygame.Surface:
        surface = pygame.Surface((W, H))
        surface.blit(bg, (0, 0))
        _draw_grid(surface, alpha=44)

        # Soft green radial bloom behind the central glyph.
        bloom_t = _ease_in_out(min(1.0, t / 0.30))
        bloom_alpha_max = int(90 * bloom_t)
        if bloom_alpha_max > 4:
            bloom_r = int(min(W, H) * 0.50)
            bloom = pygame.Surface((bloom_r * 2, bloom_r * 2), pygame.SRCALPHA)
            tint = (110, 195, 130)
            for r in range(bloom_r, 0, -3):
                rt = r / bloom_r
                a = int(bloom_alpha_max * (1 - rt) ** 1.8)
                if a < 1:
                    continue
                pygame.draw.circle(bloom, (*tint, a), (bloom_r, bloom_r), r)
            surface.blit(bloom, (W // 2 - bloom_r, H // 2 - 24 - bloom_r))

        _step_sparks()
        for p in sparks:
            ratio = p["lifetime"] / max(1, p["max_lifetime"])
            color = _blend((10, 14, 12), (160, 220, 170), ratio)
            pygame.draw.circle(
                surface, color, (int(p["x"]), int(p["y"])), p["size"],
            )

        # Central "shield" glyph — concentric hex-arc opening upward.
        cx, cy = W // 2, H // 2 - 24
        beat = 1.0 + 0.06 * math.sin(t * math.pi * 5)
        radius = int(34 * beat)
        # Outer arc — full hexagon traced as a polygon outline.
        hex_pts = [
            (cx + int(math.cos(math.radians(60 * k - 30)) * radius),
             cy + int(math.sin(math.radians(60 * k - 30)) * radius))
            for k in range(6)
        ]
        pygame.draw.polygon(surface, (140, 220, 160), hex_pts, 3)
        # Centre tick — short vertical line + tilted arc forming a check mark.
        pygame.draw.lines(
            surface, (200, 245, 210), False,
            [
                (cx - 10, cy + 2),
                (cx - 2, cy + 10),
                (cx + 12, cy - 8),
            ],
            3,
        )

        # Text — tag / title / caption stack with drop shadows for
        # legibility against the green bloom + grain layers.
        label_t = _ease_in_out(min(1.0, t / 0.20))
        _draw_subtitle(
            surface, "ÉQUILIBRE RÉTABLI", fonts["label"],
            (130, 220, 150),
            cy + 60, alpha=int(255 * label_t),
        )
        title_t = _ease_in_out(min(1.0, max(0.0, (t - 0.10) / 0.25)))
        title_drift = int((1.0 - title_t) * 18)
        title_text = "Bascule contenue."
        title_y = cy + 80 + title_drift
        title_surf = fonts["title"].render(
            title_text, True, (240, 250, 240),
        )
        if title_t < 1.0:
            title_surf.set_alpha(int(255 * title_t))
        surface.blit(
            title_surf,
            ((W - title_surf.get_width()) // 2, title_y),
        )
        # Sage-tinted underline matching the victory palette.
        _draw_title_underline(
            surface,
            t=t, title_y=title_y, title_text=title_text,
            font=fonts["title"], accent=(140, 220, 160),
            width_ratio=0.45,
        )
        cap_t = _ease_in_out(min(1.0, max(0.0, (t - 0.30) / 0.30)))
        if cap_t > 0:
            _draw_subtitle(
                surface, "Vos choix ont tenu le monde en équilibre.",
                fonts["caption"], (200, 215, 200),
                cy + 134, alpha=int(255 * cap_t),
            )

        # Shared cinematic envelope — corner vignette + film grain.
        _apply_cinematic_envelope(surface, i)

        # Animated letterbox — sage-tinted hairline (victory palette).
        _draw_animated_letterbox(surface, t=t, accent=(60, 100, 75))

        # Fade in / out veils.
        if t < 0.06:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (1.0 - t / 0.06))))
            surface.blit(veil, (0, 0))
        elif t > 0.90:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (t - 0.90) / 0.10)))
            surface.blit(veil, (0, 0))
        return surface

    _encode_clip(CINEMATICS_DIR / "victory.mp4", duration_s, make_frame)


def _build_defeat() -> None:
    """Outcome-specific cinematic for a DEFEAT transition. Mirrors the
    victory layout so the two clips feel like a pair — but with a
    desaturated red palette, descending particles, and a broken-triangle
    glyph instead of a shield.
    """
    pygame.font.init()
    pygame.display.init()
    duration_s = 3.5
    fonts = {
        "label": _font(12, bold=True),
        "title": _font(40, bold=True),
        "caption": _font(17),
    }
    bg = _gradient_bg((36, 14, 18), (10, 4, 6))
    embers: list[dict] = []
    seed_rng = random.Random(13)

    def _step_embers() -> None:
        if seed_rng.random() < 0.32 and len(embers) < 60:
            lifetime = seed_rng.randint(50, 110)
            embers.append({
                "x": seed_rng.uniform(0.0, W),
                # Defeat: embers *fall* from the top → "descending order".
                "y": seed_rng.uniform(-20.0, H * 0.35),
                "vx": (seed_rng.random() * 2.0 - 1.0) * 0.25,
                "vy": seed_rng.uniform(0.6, 1.5),
                "lifetime": lifetime,
                "max_lifetime": lifetime,
                "size": seed_rng.randint(1, 3),
            })
        survivors: list[dict] = []
        for p in embers:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["lifetime"] -= 1
            if p["lifetime"] > 0 and p["y"] < H + 8:
                survivors.append(p)
        embers.clear()
        embers.extend(survivors)

    def make_frame(i: int, t: float) -> pygame.Surface:
        surface = pygame.Surface((W, H))
        surface.blit(bg, (0, 0))
        _draw_grid(surface, alpha=44)

        # Dim red radial bloom.
        bloom_t = _ease_in_out(min(1.0, t / 0.30))
        bloom_alpha_max = int(95 * bloom_t)
        if bloom_alpha_max > 4:
            bloom_r = int(min(W, H) * 0.55)
            bloom = pygame.Surface((bloom_r * 2, bloom_r * 2), pygame.SRCALPHA)
            tint = (210, 80, 75)
            for r in range(bloom_r, 0, -3):
                rt = r / bloom_r
                a = int(bloom_alpha_max * (1 - rt) ** 1.8)
                if a < 1:
                    continue
                pygame.draw.circle(bloom, (*tint, a), (bloom_r, bloom_r), r)
            surface.blit(bloom, (W // 2 - bloom_r, H // 2 - 24 - bloom_r))

        _step_embers()
        for p in embers:
            ratio = p["lifetime"] / max(1, p["max_lifetime"])
            color = _blend((10, 6, 6), (220, 110, 90), ratio)
            pygame.draw.circle(
                surface, color, (int(p["x"]), int(p["y"])), p["size"],
            )

        # Broken triangle glyph — top tip + base, missing left edge.
        cx, cy = W // 2, H // 2 - 24
        beat = 1.0 + 0.05 * math.sin(t * math.pi * 5)
        r = int(30 * beat)
        # Right edge.
        pygame.draw.line(
            surface, (220, 100, 90),
            (cx, cy - r),
            (cx + int(r * 0.95), cy + int(r * 0.7)),
            3,
        )
        # Base.
        pygame.draw.line(
            surface, (220, 100, 90),
            (cx + int(r * 0.95), cy + int(r * 0.7)),
            (cx - int(r * 0.4), cy + int(r * 0.7)),
            3,
        )
        # Left edge interrupted — two short segments suggesting a break.
        pygame.draw.line(
            surface, (220, 100, 90),
            (cx, cy - r),
            (cx - int(r * 0.45), cy - int(r * 0.05)),
            3,
        )
        pygame.draw.line(
            surface, (220, 100, 90),
            (cx - int(r * 0.7), cy + int(r * 0.4)),
            (cx - int(r * 0.4), cy + int(r * 0.7)),
            3,
        )

        label_t = _ease_in_out(min(1.0, t / 0.20))
        _draw_subtitle(
            surface, "POINT DE NON-RETOUR", fonts["label"],
            (225, 130, 115),
            cy + 60, alpha=int(255 * label_t),
        )
        title_t = _ease_in_out(min(1.0, max(0.0, (t - 0.10) / 0.25)))
        title_drift = int((1.0 - title_t) * 18)
        title_text = "Bascule franchie."
        title_y = cy + 80 + title_drift
        title_surf = fonts["title"].render(
            title_text, True, (250, 235, 230),
        )
        if title_t < 1.0:
            title_surf.set_alpha(int(255 * title_t))
        surface.blit(
            title_surf,
            ((W - title_surf.get_width()) // 2, title_y),
        )
        # Red-tinted underline matching the defeat palette.
        _draw_title_underline(
            surface,
            t=t, title_y=title_y, title_text=title_text,
            font=fonts["title"], accent=(220, 100, 90),
            width_ratio=0.45,
        )
        cap_t = _ease_in_out(min(1.0, max(0.0, (t - 0.30) / 0.30)))
        if cap_t > 0:
            _draw_subtitle(
                surface, "Le monde a basculé. Rejouez pour comprendre.",
                fonts["caption"], (215, 200, 200),
                cy + 134, alpha=int(255 * cap_t),
            )

        # Shared cinematic envelope — corner vignette + film grain.
        _apply_cinematic_envelope(surface, i)

        # Animated letterbox — red-tinted hairline (defeat palette).
        _draw_animated_letterbox(surface, t=t, accent=(90, 45, 45))

        if t < 0.06:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (1.0 - t / 0.06))))
            surface.blit(veil, (0, 0))
        elif t > 0.90:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (t - 0.90) / 0.10)))
            surface.blit(veil, (0, 0))
        return surface

    _encode_clip(CINEMATICS_DIR / "defeat.mp4", duration_s, make_frame)


# --------------------------------------------------- element domain cards
#
# Five 4 s cards announcing the chosen catastrophe (Eau / Feu / Terre /
# Air / Vie) on the PICKER → PLAYING transition. Built from the same
# parts as intro/midgame/outro — gradient bg, faint grid, particle field,
# 8-direction text halo, letterbox bars, fade veils — so the new clips
# inherit the existing visual language instead of looking imported.
#
# Each card carries:
#   * Element palette (matches arc_color used by the in-game catastrophe).
#   * Procedural glyph at screen centre, drawn with the same line-art
#     vocabulary as ``view/renderer.py``'s ``_draw_element_icon``.
#   * Particle motion oriented per element (water drips, fire rises,
#     earth shakes, air swirls, life rises slowly).
#   * Section tag → element name → subtitle stack, identical layout to
#     the midgame/victory/defeat text block so the cards feel native.


def _draw_eau_glyph(surface, cx, cy, r, color):
    """Three stacked wave lines — same shape as the in-game Eau badge."""
    thick = max(2, r // 8)
    for i, y_off in enumerate((-r // 2, 0, r // 2)):
        span = r - i * (r // 6)
        y = cy + y_off
        pts = [
            (cx - span, y),
            (cx - span // 3, y - thick * 2),
            (cx + span // 3, y + thick * 2),
            (cx + span, y),
        ]
        pygame.draw.lines(surface, color, False, pts, thick)


def _draw_feu_glyph(surface, cx, cy, r, color):
    """Flame teardrop with an inner notch — Feu badge shape."""
    thick = max(2, r // 8)
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


def _draw_terre_glyph(surface, cx, cy, r, color):
    """Two overlapping mountain peaks — Terre badge shape."""
    thick = max(2, r // 8)
    big = [
        (cx - r, cy + r // 2),
        (cx - r // 6, cy - r // 2),
        (cx + r // 2, cy + r // 2),
    ]
    small = [
        (cx, cy + r // 2),
        (cx + r // 3, cy - r // 6),
        (cx + r, cy + r // 2),
    ]
    pygame.draw.polygon(surface, color, big, thick)
    pygame.draw.polygon(surface, color, small, thick)


def _draw_air_glyph(surface, cx, cy, r, color):
    """Two stacked S-curves — Air badge shape (wind streams)."""
    thick = max(2, r // 8)
    steps = 24
    for amp_y, base_y in ((r // 2, -r // 2), (r // 3, r // 4)):
        pts = []
        for s in range(steps + 1):
            tt = s / steps
            px = cx - r + int(tt * 2 * r)
            py = cy + base_y + int(math.sin(tt * math.pi * 2) * amp_y // 2)
            pts.append((px, py))
        pygame.draw.lines(surface, color, False, pts, thick)


def _draw_vie_glyph(surface, cx, cy, r, color):
    """Twin DNA-style helices crossing twice — Vie badge shape."""
    thick = max(2, r // 8)
    steps = 20
    for direction in (1, -1):
        pts: list[tuple[int, int]] = []
        for s in range(steps + 1):
            tt = s / steps
            py = cy - r + int(tt * 2 * r)
            px = cx + int(direction * math.sin(tt * math.pi * 2) * r * 0.7)
            pts.append((px, py))
        pygame.draw.lines(surface, color, False, pts, thick)


# ---------------------------------------------------------------------------
# Element atmosphere — per-element background motifs that establish elemental
# identity *behind* the bloom, particles, and rings. Each motif is subtle
# (low alpha) so it reads as ambience, not noise, but distinct enough that a
# muted EAU card is still unmistakably water, a muted FEU card unmistakably
# fire — even before the glyph appears. All five take ``(surface, t, accent)``
# and render in place onto the surface.


def _draw_atmosphere_eau(surface: pygame.Surface, t: float, accent: tuple[int, int, int]) -> None:
    """Three horizontal wave bands drifting slowly across the canvas — the
    elemental signature of water moving through the frame."""
    drift = t * 36
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for i, base_y in enumerate((H * 0.18, H * 0.48, H * 0.78)):
        amplitude = 6 + i * 3
        wavelength = 220 + i * 60
        pts = []
        for x in range(-40, W + 40, 6):
            wx = x + drift * (1 + i * 0.35)
            wy = base_y + math.sin(wx / wavelength * math.pi * 2) * amplitude
            pts.append((int(x), int(wy)))
        if len(pts) >= 2:
            pygame.draw.lines(layer, (*accent, 38), False, pts, 1)
    surface.blit(layer, (0, 0))


def _draw_atmosphere_feu(surface: pygame.Surface, t: float, accent: tuple[int, int, int]) -> None:
    """Vertical heat columns rising from the bottom — bright at the floor,
    fading to nothing at the top. Reads as flame-light filling the room."""
    cols = 9
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for i in range(cols):
        x = int(W / cols * i + W / (cols * 2)
                + math.sin(t * math.pi * 2 + i * 0.8) * 10)
        col_w = 28
        for y in range(H - 36, 36, -6):
            ratio = (H - 36 - y) / (H - 72)
            a = int(60 * ratio ** 1.6)
            if a < 1:
                continue
            pygame.draw.line(
                layer, (*accent, a),
                (x - col_w // 2, y), (x + col_w // 2, y),
            )
    surface.blit(layer, (0, 0))


def _draw_atmosphere_terre(surface: pygame.Surface, t: float, accent: tuple[int, int, int]) -> None:
    """Angular fault-line fragments scattered across the canvas — the
    geometric signature of cracking rock. Positions are fixed via a stable
    seed so the motif reads as 'fault lines', not 'flickering noise'."""
    rng = random.Random(2028)
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for _ in range(10):
        x1 = rng.randint(20, W - 20)
        y1 = rng.randint(20, H - 20)
        angle = rng.uniform(-math.pi / 6, math.pi / 6) + rng.choice((0, math.pi / 2))
        length = rng.randint(80, 160)
        x2 = x1 + int(math.cos(angle) * length)
        y2 = y1 + int(math.sin(angle) * length)
        # Subtle pulse on alpha so the lines breathe instead of being static.
        pulse = 0.7 + 0.3 * math.sin(t * math.pi * 3 + rng.random() * 6)
        a = int(36 * pulse)
        if a < 1:
            continue
        pygame.draw.line(layer, (*accent, a), (x1, y1), (x2, y2), 1)
    surface.blit(layer, (0, 0))


def _draw_atmosphere_air(surface: pygame.Surface, t: float, accent: tuple[int, int, int]) -> None:
    """Two large sweeping curves spanning the canvas — jet-stream lines.
    Drift horizontally so the motion reads as wind in transit."""
    drift = t * 58
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for i, base_y in enumerate((H * 0.28, H * 0.66)):
        amplitude = 28 + i * 8
        wavelength = 180
        pts = []
        for x in range(-50, W + 50, 8):
            wx = x + drift * (1 + i * 0.45)
            wy = base_y + math.sin(wx / wavelength * math.pi * 2) * amplitude
            pts.append((int(x), int(wy)))
        if len(pts) >= 2:
            pygame.draw.lines(layer, (*accent, 36), False, pts, 2)
    surface.blit(layer, (0, 0))


def _draw_atmosphere_vie(surface: pygame.Surface, t: float, accent: tuple[int, int, int]) -> None:
    """Five cell-like organic blooms slowly pulsing in place — biological
    ambience for the Vie card."""
    rng = random.Random(2030)
    blooms = [
        (rng.randint(80, W - 80), rng.randint(80, H - 80),
         rng.randint(55, 95), rng.random() * 6)
        for _ in range(5)
    ]
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    for cx, cy, base_r, phase in blooms:
        pulse = 1.0 + 0.12 * math.sin(t * math.pi * 2 + phase)
        r = int(base_r * pulse)
        for ring_r in range(r, 0, -4):
            rt = ring_r / r
            a = int(28 * (1 - rt) ** 1.8)
            if a < 1:
                continue
            pygame.draw.circle(layer, (*accent, a), (cx, cy), ring_r)
    surface.blit(layer, (0, 0))


_ATMOSPHERE_BY_ELEMENT: dict[str, Callable] = {
    "eau":   _draw_atmosphere_eau,
    "feu":   _draw_atmosphere_feu,
    "terre": _draw_atmosphere_terre,
    "air":   _draw_atmosphere_air,
    "vie":   _draw_atmosphere_vie,
}


def _build_corner_vignette() -> pygame.Surface:
    """Cached soft corner-darkening vignette — drawn last so the eye is
    pulled toward the centre of the card. Identical every frame."""
    layer = pygame.Surface((W, H), pygame.SRCALPHA)
    max_r = math.hypot(W, H) / 2
    inner_r = int(max_r * 0.55)
    cx, cy = W // 2, H // 2
    for r in range(int(max_r), inner_r, -6):
        rt = (r - inner_r) / (max_r - inner_r)
        a = int(70 * rt ** 1.8)
        if a < 1:
            continue
        pygame.draw.circle(layer, (0, 0, 0, a), (cx, cy), r, 6)
    return layer


_CORNER_VIGNETTE: pygame.Surface | None = None


def _build_grain_frames() -> list[pygame.Surface]:
    """3 cycled film-grain frames — low-alpha noise that adds cinematic
    texture without competing with content. Cycling 3 deterministic
    seeds gives the grain a "live" shimmer instead of a frozen pattern
    (the same 3 frames repeat across each clip at 30 fps → grain
    refreshes every frame).
    """
    frames: list[pygame.Surface] = []
    for seed in (4001, 4002, 4003):
        rng = random.Random(seed)
        layer = pygame.Surface((W, H), pygame.SRCALPHA)
        # ~0.35 % pixel density at low alpha — present-but-subtle film
        # texture. Higher density reads as static, lower disappears.
        for _ in range(1800):
            x = rng.randint(0, W - 1)
            y = rng.randint(0, H - 1)
            brightness = rng.randint(120, 200)
            a = rng.randint(12, 26)
            layer.set_at((x, y), (brightness, brightness, brightness, a))
        frames.append(layer)
    return frames


_GRAIN_FRAMES: list[pygame.Surface] | None = None


def _apply_cinematic_envelope(surface: pygame.Surface, i: int) -> None:
    """Apply the shared cinematic envelope: corner vignette + film grain.

    Called by each cinematic builder just before the letterbox bars and
    fade veils so the unified look is consistent across every clip in
    the library (intro / midgame / outro / victory / defeat / 10 element
    cards / point-de-non-retour). Cached layers — one vignette + 3
    cycled grain frames — so the per-frame cost is one or two blits.
    """
    global _CORNER_VIGNETTE, _GRAIN_FRAMES
    if _CORNER_VIGNETTE is None:
        _CORNER_VIGNETTE = _build_corner_vignette()
    surface.blit(_CORNER_VIGNETTE, (0, 0))
    if _GRAIN_FRAMES is None:
        _GRAIN_FRAMES = _build_grain_frames()
    surface.blit(_GRAIN_FRAMES[i % len(_GRAIN_FRAMES)], (0, 0))


def _draw_subtitle(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: tuple[int, int, int],
    y: int,
    *,
    alpha: int = 255,
    x: int | None = None,
) -> tuple[int, int]:
    """Centred (or x-positioned) text with a soft 1-px drop shadow.

    Lighter touch than the 8-direction title halo used by
    ``_draw_text_centered``: just one offset shadow at ~55 % of the
    text alpha, sitting 1 px down. Designed for the *secondary* text
    layer (labels, subtitles, captions) that sit on top of the
    atmosphere + grain layers and would otherwise dissolve into busy
    backgrounds.

    Returns the (x, y) where the text was drawn so callers can
    chain layout decisions off it.
    """
    rendered = font.render(text, True, color)
    text_x = x if x is not None else (W - rendered.get_width()) // 2
    # Shadow first — same text rendered black, offset 1 px down, lower alpha.
    shadow = font.render(text, True, (0, 0, 0))
    sh_alpha = int(alpha * 0.55)
    if sh_alpha > 0:
        shadow.set_alpha(sh_alpha)
        surface.blit(shadow, (text_x + 1, y + 1))
    # Foreground text.
    if alpha < 255:
        rendered = rendered.copy()
        rendered.set_alpha(alpha)
    surface.blit(rendered, (text_x, y))
    return text_x, y


def _draw_animated_letterbox(
    surface: pygame.Surface,
    *,
    t: float,
    accent: tuple[int, int, int],
    max_h: int = 36,
    slide_in: float = 0.08,
    slide_out: float = 0.08,
) -> None:
    """Animated letterbox bars — slide in during the first ``slide_in``
    fraction of the clip and out during the last ``slide_out`` fraction.

    Was a static 36 px black band on every cinematic — invisible but
    flat, the bars just sat there. Animating them gives every clip a
    classic "curtain opens / closes" moment that lands right on top of
    the existing black-veil fade-in/out, so the player reads the
    cinematic as a deliberate sequence (curtain rises → content → curtain
    falls) instead of "video appears, then disappears".

    Accent hairline on each inner edge fades in only once the bars are
    nearly full, so it never sits mid-slide as a floating coloured line.
    """
    if t < slide_in:
        env = _ease_in_out(t / slide_in)
    elif t > 1.0 - slide_out:
        env = _ease_in_out((1.0 - t) / slide_out)
    else:
        env = 1.0
    bar_h = int(max_h * env)
    if bar_h <= 0:
        return
    pygame.draw.rect(surface, (0, 0, 0), (0, 0, W, bar_h))
    pygame.draw.rect(surface, (0, 0, 0), (0, H - bar_h, W, bar_h))
    # Inner-edge accent hairline — only render when bars are settled
    # (env > 0.9) so the line doesn't appear mid-slide where it would
    # read as a floating coloured stripe.
    if env > 0.9:
        line_alpha = int(255 * (env - 0.9) / 0.1)
        layer = pygame.Surface((W, 1), pygame.SRCALPHA)
        layer.fill((*accent, line_alpha))
        surface.blit(layer, (0, bar_h))
        surface.blit(layer, (0, H - bar_h - 1))


def _draw_title_underline(
    surface: pygame.Surface,
    *,
    t: float,
    title_y: int,
    title_text: str,
    font: pygame.font.Font,
    accent: tuple[int, int, int],
    fade_start: float = 0.28,
    fade_duration: float = 0.22,
    width_ratio: float = 0.55,
) -> None:
    """Animated accent rule beneath a centred title.

    Same idiom as the element-card title underline (triangular alpha
    envelope, expands outward from centre, accent-tinted). Pulls older
    cinematics' hero titles into the unified vocabulary — they used
    to sit with the 8-direction glow halo but no horizontal anchor,
    while the new element cards have both. This helper adds the
    horizontal anchor for any centred title.
    """
    underline_t = _ease_in_out(
        min(1.0, max(0.0, (t - fade_start) / fade_duration))
    )
    if underline_t <= 0:
        return
    title_w = font.size(title_text)[0]
    max_w = max(64, int(title_w * width_ratio))
    underline_w = int(max_w * underline_t)
    if underline_w <= 4:
        return
    u_y = title_y + font.get_height() + 8
    u_x = (W - underline_w) // 2
    layer = pygame.Surface((underline_w, 2), pygame.SRCALPHA)
    for px in range(underline_w):
        tt = 1.0 - abs(px - underline_w / 2) / (underline_w / 2)
        a = int(220 * tt ** 1.2 * underline_t)
        if a <= 0:
            continue
        pygame.draw.line(layer, (*accent, a), (px, 0), (px, 1))
    surface.blit(layer, (u_x, u_y))


def _build_element_card(
    *,
    key: str,
    label: str,
    subtitle: str,
    section_tag: str,
    accent: tuple[int, int, int],
    bg_top: tuple[int, int, int],
    bg_bottom: tuple[int, int, int],
    glyph_fn: Callable,
    particle_drift_y: float,
    spark_palette: tuple[int, int, int],
    seed: int,
    out_name: str,
) -> None:
    """Shared body for every element card — palette / glyph / subtitle /
    section tag / particle seed all parameterised so the same builder
    produces all 20 variants (5 elements × 2 sides × 2 subtitle takes).
    """
    pygame.font.init()
    pygame.display.init()
    duration_s = 4.0
    fonts = {
        "label": _font(12, bold=True),
        "title": _font(56, bold=True),  # bigger than midgame's 38 — element
                                        # name is the whole story of the card.
        "caption": _font(17),
    }
    bg = _gradient_bg(bg_top, bg_bottom)
    particles: list[dict] = []
    seed_rng = random.Random(seed)
    atmosphere_fn = _ATMOSPHERE_BY_ELEMENT.get(key)
    global _CORNER_VIGNETTE
    if _CORNER_VIGNETTE is None:
        _CORNER_VIGNETTE = _build_corner_vignette()

    def _step_element_sparks() -> None:
        if seed_rng.random() < 0.24 and len(particles) < 60:
            lifetime = seed_rng.randint(60, 130)
            particles.append({
                "x": seed_rng.uniform(0.0, W),
                "y": seed_rng.uniform(0.0, H),
                "vx": (seed_rng.random() * 2.0 - 1.0) * 0.35,
                "vy": particle_drift_y
                + (seed_rng.random() * 2.0 - 1.0) * 0.25,
                "lifetime": lifetime,
                "max_lifetime": lifetime,
                "size": seed_rng.randint(1, 3),
            })
        survivors: list[dict] = []
        for p in particles:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["lifetime"] -= 1
            if p["lifetime"] <= 0:
                continue
            # Wrap horizontally so the field stays continuous.
            if p["x"] < 0:
                p["x"] += W
            elif p["x"] >= W:
                p["x"] -= W
            if p["y"] < -8 or p["y"] >= H + 8:
                continue
            survivors.append(p)
        particles.clear()
        particles.extend(survivors)

    def make_frame(i: int, t: float) -> pygame.Surface:
        surface = pygame.Surface((W, H))
        surface.blit(bg, (0, 0))
        _draw_grid(surface, alpha=46)

        # Element atmosphere — per-element background motif (wave bands /
        # heat columns / fault lines / jet-stream curves / cell blooms).
        # Establishes elemental identity behind the bloom and rings; fades
        # in over the first 25 % of the clip so it emerges from the
        # darkness instead of being there at frame 0.
        if atmosphere_fn is not None:
            atmo_t = _ease_in_out(min(1.0, t / 0.25))
            if atmo_t > 0:
                atmo_surface = pygame.Surface((W, H), pygame.SRCALPHA)
                atmosphere_fn(atmo_surface, t, accent)
                atmo_surface.set_alpha(int(255 * atmo_t))
                surface.blit(atmo_surface, (0, 0))

        # Soft radial bloom behind the glyph — same idiom as
        # midgame/victory/defeat. Element-tinted.
        bloom_t = _ease_in_out(min(1.0, t / 0.30))
        bloom_alpha_max = int(95 * bloom_t)
        if bloom_alpha_max > 4:
            bloom_r = int(min(W, H) * 0.55)
            bloom = pygame.Surface((bloom_r * 2, bloom_r * 2), pygame.SRCALPHA)
            for r in range(bloom_r, 0, -3):
                rt = r / bloom_r
                a = int(bloom_alpha_max * (1 - rt) ** 1.8)
                if a < 1:
                    continue
                pygame.draw.circle(bloom, (*accent, a), (bloom_r, bloom_r), r)
            surface.blit(bloom, (W // 2 - bloom_r, H // 2 - 30 - bloom_r))

        # Element-themed particles.
        _step_element_sparks()
        for p in particles:
            ratio = p["lifetime"] / max(1, p["max_lifetime"])
            # Envelope so particles emerge / dissolve instead of popping.
            if ratio > 0.85:
                env = (1.0 - ratio) / 0.15
            elif ratio > 0.30:
                env = 1.0
            else:
                env = ratio / 0.30
            if env <= 0:
                continue
            color = _blend((10, 12, 18), spark_palette, env)
            pygame.draw.circle(
                surface, color, (int(p["x"]), int(p["y"])), p["size"],
            )

        # Three cascading rings — element-tinted version of midgame's
        # warning rings, but slower (one phase per ~1.4 s) so the
        # cinematic feels announcement-paced, not alarm-paced.
        cx, cy = W // 2, H // 2 - 30
        for ring_i in range(3):
            ring_phase = ((t * (duration_s / 1.4)) + ring_i * 0.33) % 1.0
            if ring_phase > 0.85:
                continue
            ring_r = int(70 + ring_phase * 260)
            ring_alpha = int(170 * (1.0 - ring_phase))
            if ring_alpha < 4:
                continue
            ring_layer = pygame.Surface(
                (ring_r * 2 + 6, ring_r * 2 + 6), pygame.SRCALPHA,
            )
            pygame.draw.circle(
                ring_layer, (*accent, ring_alpha),
                (ring_r + 3, ring_r + 3), ring_r, 2,
            )
            surface.blit(ring_layer, (cx - ring_r - 3, cy - ring_r - 3))

        # Central element glyph — three layered passes for depth:
        #   1. Soft halo disc behind the glyph (radial accent glow,
        #      ~24 px wider than the glyph) — anchors the glyph as
        #      *lit* against the darker outer ring zone instead of
        #      sitting on bare gradient.
        #   2. Tight accent ring just outside the glyph — frames the
        #      element shape and matches the ring vocabulary of the
        #      cascading expansion rings drawn earlier.
        #   3. The procedural glyph itself, beating softly so the
        #      moment feels alive (1 + 0.06·sin(πt·4)).
        beat = 1.0 + 0.06 * math.sin(t * math.pi * 4)
        glyph_r = int(48 * beat)
        # Halo disc — fades in with the bloom.
        halo_pad = 22
        halo_r = glyph_r + halo_pad
        halo_t = _ease_in_out(min(1.0, t / 0.30))
        halo_layer = pygame.Surface(
            (halo_r * 2 + 4, halo_r * 2 + 4), pygame.SRCALPHA,
        )
        halo_alpha_max = int(135 * halo_t)
        if halo_alpha_max > 4:
            for r in range(halo_r, 0, -1):
                rt = r / halo_r
                a = int(halo_alpha_max * (1 - rt) ** 1.7)
                if a < 1:
                    continue
                pygame.draw.circle(
                    halo_layer, (*accent, a),
                    (halo_r + 2, halo_r + 2), r,
                )
            surface.blit(halo_layer, (cx - halo_r - 2, cy - halo_r - 2))
        # Tight accent ring — 1 px outline ~10 px outside the glyph.
        ring_color = _blend(accent, (255, 255, 255), 0.45)
        pygame.draw.circle(surface, ring_color, (cx, cy), glyph_r + 10, 1)
        # Glyph (existing procedural draw).
        glyph_color = _blend(accent, (255, 255, 255), 0.30)
        glyph_fn(surface, cx, cy, glyph_r, glyph_color)

        # Section tag → element name → subtitle stack.
        # Section tag (small uppercase, accent-coloured). "DOMAINE" for
        # the Gaia side ("which catastrophe domain"), "CONTRE-MESURE"
        # for the Humanité side ("which response front"). Drop-shadow
        # so the small label reads cleanly over the atmosphere + grain.
        tag_t = _ease_in_out(min(1.0, t / 0.18))
        _draw_subtitle(
            surface, section_tag, fonts["label"],
            _blend(accent, (255, 255, 255), 0.20),
            cy + 60, alpha=int(255 * tag_t),
        )
        # Element name — hero, with the 8-direction glow halo.
        name_t = _ease_in_out(min(1.0, max(0.0, (t - 0.12) / 0.28)))
        name_drift = int((1.0 - name_t) * 22)
        title_y = cy + 82 + name_drift
        _draw_text_centered(
            surface, label,
            font=fonts["title"],
            y=title_y,
            color=(245, 248, 255),
            alpha=int(255 * name_t),
            glow_color=accent,
        )
        # Title underline — short accent rule expanding outward from the
        # title centre, anchoring the hero text the way the picker hero
        # header carries its accent rule. Draws in after the title has
        # settled (so the eye reads the word first, then the underline
        # arrives), peaks ~120 px wide at full expansion.
        underline_t = _ease_in_out(
            min(1.0, max(0.0, (t - 0.28) / 0.22))
        )
        if underline_t > 0:
            # Title font is 56 px bold; measure the rendered width so
            # the underline matches each element name's actual extent
            # (EAU narrow, TRANSFORMATION-tier names wider).
            label_w = fonts["title"].size(label)[0]
            max_w = max(64, int(label_w * 0.65))
            underline_w = int(max_w * underline_t)
            if underline_w > 4:
                u_y = title_y + fonts["title"].get_height() + 8
                u_x = (W - underline_w) // 2
                u_layer = pygame.Surface(
                    (underline_w, 2), pygame.SRCALPHA,
                )
                # Triangular alpha envelope — peak in the middle, taper
                # to 0 at the ends. Same fade idiom as the picker title
                # accent rule + the section header rule in the sidebar.
                for px in range(underline_w):
                    tt = 1.0 - abs(px - underline_w / 2) / (underline_w / 2)
                    a = int(220 * tt ** 1.2 * underline_t)
                    if a <= 0:
                        continue
                    pygame.draw.line(
                        u_layer, (*accent, a), (px, 0), (px, 1),
                    )
                surface.blit(u_layer, (u_x, u_y))
        # Subtitle — short editorial line per element, with drop-shadow
        # so the small text reads cleanly over the atmosphere motif.
        sub_t = _ease_in_out(min(1.0, max(0.0, (t - 0.35) / 0.30)))
        if sub_t > 0:
            _draw_subtitle(
                surface, subtitle, fonts["caption"],
                _blend(accent, (255, 255, 255), 0.55),
                cy + 156, alpha=int(255 * sub_t),
            )

        # Shared cinematic envelope — corner vignette + film grain.
        # Applied via the unified helper so the element cards stay in
        # lockstep with the rest of the library's chrome vocabulary.
        _apply_cinematic_envelope(surface, i)

        # Animated letterbox — element-tinted hairline. Same idiom as
        # midgame/victory/defeat/intro/PNR for visual continuity.
        edge_line = _blend(accent, (0, 0, 0), 0.55)
        _draw_animated_letterbox(surface, t=t, accent=edge_line)

        # Fade veils — match existing 6%/10% timing.
        if t < 0.06:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (1.0 - t / 0.06))))
            surface.blit(veil, (0, 0))
        elif t > 0.90:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (t - 0.90) / 0.10)))
            surface.blit(veil, (0, 0))
        return surface

    _encode_clip(CINEMATICS_DIR / f"{out_name}.mp4", duration_s, make_frame)


# Per-element palette + glyph + base motion. Side-agnostic.
_ELEMENT_SHAPES = {
    "eau": {
        "label": "EAU",
        "accent": (60, 140, 230),
        "bg_top": (14, 24, 44),
        "bg_bottom": (4, 10, 22),
        "glyph_fn": _draw_eau_glyph,
        "drift_y": 0.45,
        "spark_palette": (130, 180, 235),
    },
    "feu": {
        "label": "FEU",
        "accent": (235, 110, 50),
        "bg_top": (38, 14, 10),
        "bg_bottom": (12, 6, 6),
        "glyph_fn": _draw_feu_glyph,
        "drift_y": -1.1,
        "spark_palette": (240, 170, 90),
    },
    "terre": {
        "label": "TERRE",
        "accent": (200, 145, 80),
        "bg_top": (32, 22, 12),
        "bg_bottom": (10, 8, 4),
        "glyph_fn": _draw_terre_glyph,
        "drift_y": -0.05,
        "spark_palette": (220, 180, 110),
    },
    "air": {
        "label": "AIR",
        "accent": (130, 190, 235),
        "bg_top": (12, 22, 36),
        "bg_bottom": (4, 8, 18),
        "glyph_fn": _draw_air_glyph,
        "drift_y": -0.35,
        "spark_palette": (170, 215, 240),
    },
    "vie": {
        "label": "VIE",
        "accent": (120, 220, 130),
        "bg_top": (12, 28, 18),
        "bg_bottom": (4, 12, 8),
        "glyph_fn": _draw_vie_glyph,
        "drift_y": -0.55,
        "spark_palette": (165, 235, 180),
    },
}


# One subtitle per (element, side). Non-redundancy between runs comes
# from the live scenario-info overlay drawn over the cinematic at
# runtime (which country first tipped, the day count, current
# mortality, etc.) — not from pre-rendered variant matrices that
# multiply file count.
#
# Gaia voice: the catastrophe asserts itself. Humanité voice: the
# counter-measure responds.
_ELEMENT_SUBTITLES: dict[str, dict[str, str]] = {
    "eau":   {"gaia": "L'eau monte.",       "humanite": "Endiguer la crue."},
    "feu":   {"gaia": "Le feu gagne.",      "humanite": "Étouffer le brasier."},
    "terre": {"gaia": "La terre tremble.",  "humanite": "Bâtir parasismique."},
    "air":   {"gaia": "L'air se déchaîne.", "humanite": "Apaiser les vents."},
    "vie":   {"gaia": "Le vivant vacille.", "humanite": "Soigner le vivant."},
}


def _humanite_palette(
    accent: tuple[int, int, int],
    bg_top: tuple[int, int, int],
    bg_bottom: tuple[int, int, int],
    spark_palette: tuple[int, int, int],
) -> dict:
    """Cool the Gaia-side palette toward defensive blue-grey for the
    Humanité counterpart card. Same hue identity (so the player still
    recognises the element) but desaturated and shifted cool so the
    card visually reads as containment/response, not assertion."""
    cool = (95, 130, 165)  # neutral defensive blue-grey
    return {
        "accent":        _blend(accent, cool, 0.30),
        "bg_top":        _blend(bg_top, (10, 14, 22), 0.40),
        "bg_bottom":     _blend(bg_bottom, (4, 6, 12), 0.40),
        "spark_palette": _blend(spark_palette, cool, 0.35),
    }


def _build_element_cards() -> None:
    """10 element cards — 5 elements × {gaia, humanite}.

    Subtitle is fixed per (element, side); run-specific variation
    (which country tipped, what day, current mortality) is added at
    runtime by the scenario-info overlay drawn over the cinematic
    frame in the renderer.
    """
    seed_base = {"eau": 2026, "feu": 2027, "terre": 2028,
                 "air": 2029, "vie": 2030}
    for element_key, shape in _ELEMENT_SHAPES.items():
        for side in ("gaia", "humanite"):
            subtitle = _ELEMENT_SUBTITLES[element_key][side]
            section_tag = "DOMAINE" if side == "gaia" else "CONTRE-MESURE"
            if side == "gaia":
                accent = shape["accent"]
                bg_top = shape["bg_top"]
                bg_bottom = shape["bg_bottom"]
                spark_palette = shape["spark_palette"]
                drift_y = shape["drift_y"]
            else:
                cooled = _humanite_palette(
                    shape["accent"], shape["bg_top"],
                    shape["bg_bottom"], shape["spark_palette"],
                )
                accent = cooled["accent"]
                bg_top = cooled["bg_top"]
                bg_bottom = cooled["bg_bottom"]
                spark_palette = cooled["spark_palette"]
                # Invert drift on Humanité — motion reads as "response,
                # not progression" (rising containment, falling smoke).
                drift_y = -shape["drift_y"]
            out_name = f"element_{element_key}_{side}"
            seed = seed_base[element_key] * 10 + (0 if side == "gaia" else 5)
            _build_element_card(
                key=element_key, label=shape["label"], subtitle=subtitle,
                section_tag=section_tag,
                accent=accent, bg_top=bg_top, bg_bottom=bg_bottom,
                glyph_fn=shape["glyph_fn"],
                particle_drift_y=drift_y,
                spark_palette=spark_palette,
                seed=seed,
                out_name=out_name,
            )


# ----------------------------------------------------- point de non-retour


def _build_point_de_non_retour() -> None:
    """Mid-late slope card — sibling to midgame.mp4. Fires when the
    ``quarter_dead`` milestone (25 % of humanity dead) unlocks.

    Trigger moved here from ``collapse_imminent`` (60 % dead) because
    that placement sat only 5 mortality-points before defeat — the
    cinematic and the defeat cinematic fired back-to-back, two clips
    for one moment. ``quarter_dead`` puts ~30 game-days of distance
    before the defeat cinematic so each card lands as its own beat.

    Compared to midgame:
      * Deeper red palette and brighter red rings — alarm, not warning.
      * Descending sparks (embers falling) so the motion signals
        "the slope has tipped".
      * Cracking-glyph at centre — concentric circle with a deep
        zig-zag fissure cutting across it. Builds on the broken-
        triangle vocabulary from defeat.mp4 but stays distinct.
      * Title "POINT DE NON-RETOUR" + subtitle "Un humain sur quatre
        est tombé." names the 25 % milestone directly so the cinematic
        ties to the milestone banner ("Un quart de pertes humaines")
        instead of pre-staging defeat.
    """
    pygame.font.init()
    pygame.display.init()
    duration_s = 4.0
    fonts = {
        "label": _font(12, bold=True),
        "title": _font(44, bold=True),
        "caption": _font(17),
    }
    bg = _gradient_bg((42, 14, 18), (10, 4, 6))
    embers: list[dict] = []
    seed_rng = random.Random(2031)

    def _step_embers() -> None:
        if seed_rng.random() < 0.34 and len(embers) < 70:
            lifetime = seed_rng.randint(60, 140)
            embers.append({
                "x": seed_rng.uniform(0.0, W),
                "y": seed_rng.uniform(-30.0, H * 0.30),
                "vx": (seed_rng.random() * 2.0 - 1.0) * 0.30,
                "vy": seed_rng.uniform(0.7, 1.6),
                "lifetime": lifetime,
                "max_lifetime": lifetime,
                "size": seed_rng.randint(1, 3),
            })
        survivors: list[dict] = []
        for p in embers:
            p["x"] += p["vx"]
            p["y"] += p["vy"]
            p["lifetime"] -= 1
            if p["lifetime"] > 0 and p["y"] < H + 8:
                survivors.append(p)
        embers.clear()
        embers.extend(survivors)

    def make_frame(i: int, t: float) -> pygame.Surface:
        surface = pygame.Surface((W, H))
        surface.blit(bg, (0, 0))
        _draw_grid(surface, alpha=44)

        # Deep red radial bloom — heavier than midgame's bloom because
        # the moment is heavier.
        bloom_t = _ease_in_out(min(1.0, t / 0.25))
        bloom_alpha_max = int(115 * bloom_t)
        if bloom_alpha_max > 4:
            bloom_r = int(min(W, H) * 0.60)
            bloom = pygame.Surface((bloom_r * 2, bloom_r * 2), pygame.SRCALPHA)
            tint = (215, 70, 65)
            for r in range(bloom_r, 0, -3):
                rt = r / bloom_r
                a = int(bloom_alpha_max * (1 - rt) ** 1.8)
                if a < 1:
                    continue
                pygame.draw.circle(bloom, (*tint, a), (bloom_r, bloom_r), r)
            surface.blit(bloom, (W // 2 - bloom_r, H // 2 - 24 - bloom_r))

        _step_embers()
        for p in embers:
            ratio = p["lifetime"] / max(1, p["max_lifetime"])
            color = _blend((12, 6, 6), (230, 120, 100), ratio)
            pygame.draw.circle(
                surface, color, (int(p["x"]), int(p["y"])), p["size"],
            )

        # Three pulsing red rings — same cascade idiom as midgame, but
        # tighter timing (phase per ~0.85 s vs 1.0 s) so the alarm reads
        # as more urgent. Wider rings (max 300 px) match the heightened
        # severity.
        cx, cy = W // 2, H // 2 - 24
        for ring_i in range(3):
            ring_phase = ((t * (duration_s / 0.85)) + ring_i * 0.33) % 1.0
            if ring_phase > 0.85:
                continue
            ring_r = int(70 + ring_phase * 300)
            ring_alpha = int(210 * (1.0 - ring_phase))
            if ring_alpha < 4:
                continue
            ring_layer = pygame.Surface(
                (ring_r * 2 + 6, ring_r * 2 + 6), pygame.SRCALPHA,
            )
            pygame.draw.circle(
                ring_layer, (235, 95, 85, ring_alpha),
                (ring_r + 3, ring_r + 3), ring_r, 3,
            )
            surface.blit(ring_layer, (cx - ring_r - 3, cy - ring_r - 3))

        # Central cracking-circle glyph — concentric circle with a
        # jagged fissure cutting across it. Beats in a slower sine so
        # the moment lands as gravity, not panic.
        beat = 1.0 + 0.05 * math.sin(t * math.pi * 4)
        gr = int(34 * beat)
        # Outer ring.
        pygame.draw.circle(surface, (230, 110, 95), (cx, cy), gr, 3)
        # Fissure — zig-zag across the disc. Drawn in two halves so
        # the break reads as a single crack splitting the ring.
        fissure_top = [
            (cx - gr + 4, cy - int(gr * 0.5)),
            (cx - int(gr * 0.4), cy - int(gr * 0.1)),
            (cx + int(gr * 0.2), cy + int(gr * 0.2)),
            (cx + gr - 4, cy + int(gr * 0.4)),
        ]
        pygame.draw.lines(
            surface, (240, 160, 130), False, fissure_top, 3,
        )
        # Smaller secondary fissure — emphasises the "breaking apart"
        # cue without making the glyph too busy.
        fissure_short = [
            (cx - int(gr * 0.2), cy + int(gr * 0.4)),
            (cx + int(gr * 0.1), cy + int(gr * 0.7)),
        ]
        pygame.draw.lines(
            surface, (240, 160, 130), False, fissure_short, 2,
        )

        # Section tag (red), title (light), caption (dim) — drop shadows
        # on tag + caption for legibility against the deep-red bloom + grain.
        label_t = _ease_in_out(min(1.0, t / 0.18))
        _draw_subtitle(
            surface, "SEUIL CRITIQUE", fonts["label"],
            (230, 130, 110),
            cy + 70, alpha=int(255 * label_t),
        )
        title_t = _ease_in_out(min(1.0, max(0.0, (t - 0.10) / 0.28)))
        title_drift = int((1.0 - title_t) * 22)
        title_y = cy + 92 + title_drift
        _draw_text_centered(
            surface, "POINT DE NON-RETOUR",
            font=fonts["title"],
            y=title_y,
            color=(250, 240, 235),
            alpha=int(255 * title_t),
            glow_color=(180, 65, 55),
        )
        # Red underline anchoring the hero title.
        _draw_title_underline(
            surface,
            t=t, title_y=title_y, title_text="POINT DE NON-RETOUR",
            font=fonts["title"], accent=(220, 90, 80),
            fade_start=0.32, width_ratio=0.42,
        )
        cap_t = _ease_in_out(min(1.0, max(0.0, (t - 0.35) / 0.30)))
        if cap_t > 0:
            _draw_subtitle(
                surface, "Un humain sur quatre est tombé.",
                fonts["caption"], (215, 195, 195),
                cy + 154, alpha=int(255 * cap_t),
            )

        # Shared cinematic envelope — corner vignette + film grain.
        _apply_cinematic_envelope(surface, i)

        # Animated letterbox — red-tinted hairline.
        _draw_animated_letterbox(surface, t=t, accent=(100, 45, 45))

        # Fade veils.
        if t < 0.06:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (1.0 - t / 0.06))))
            surface.blit(veil, (0, 0))
        elif t > 0.90:
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, int(255 * (t - 0.90) / 0.10)))
            surface.blit(veil, (0, 0))
        return surface

    _encode_clip(CINEMATICS_DIR / "point_de_non_retour.mp4", duration_s, make_frame)


def main() -> None:
    print(f"Rendering cinematics to {CINEMATICS_DIR}")
    _build_intro()
    _build_midgame()
    _build_victory()
    _build_defeat()
    _build_outro()
    _build_element_cards()
    _build_point_de_non_retour()
    print("Done.")


if __name__ == "__main__":
    main()
