"""Procedural app icon generator for Terre Vivante.

Design — "living planet":
    A centred Earth disc (deep ocean blue gradient + simplified continent
    shapes) under a green crescent / leaf arc that reads as a stylised
    living shoot rising over the horizon. The crescent is the visual
    payload: it's what reads at every size from the 16 px taskbar pixel
    to the 256 px file-explorer thumbnail.

Outputs (written into ``gaia_ultimatum/data/images/``):
    * ``app_icon.png``  — 256x256, transparent background, master
                          rendition used at runtime by ``pygame.display
                          .set_icon`` and as the social-share preview.
    * ``app_icon.ico``  — Windows multi-resolution bundle (16, 32, 48,
                          64, 128, 256). What Windows reads for the
                          taskbar / window decoration / file association.

Run from repo root::

    python tools/generate_app_icon.py

Re-runs are idempotent — atomic write through a temp file so a sync
daemon (OneDrive / Dropbox) can't catch a half-written ICO.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = Path("gaia_ultimatum/data/images")
PNG_OUT = OUT_DIR / "app_icon.png"
ICO_OUT = OUT_DIR / "app_icon.ico"

SIZE = 256
CX = SIZE // 2
CY = SIZE // 2


def _blend(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(c1[0] * (1 - t) + c2[0] * t),
        int(c1[1] * (1 - t) + c2[1] * t),
        int(c1[2] * (1 - t) + c2[2] * t),
    )


def _draw_atmosphere_glow(img: Image.Image, *, disc_r: int) -> None:
    """Soft cyan halo radiating outside the disc — reads as atmosphere.

    Implemented as a solid bright disc, gaussian-blurred, then composited
    under the Earth disc. Drawing concentric outlines (as a first try)
    gave visible discrete rings at the icon's resolution; a true soft
    falloff requires a real blur kernel.
    """
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    halo_color = (105, 175, 235)
    # Bright but partially-transparent solid disc, slightly larger than
    # the Earth disc, then heavily blurred. The blur turns the hard edge
    # into a soft radial falloff.
    halo_r = disc_r + 30
    draw.ellipse(
        (CX - halo_r, CY - halo_r, CX + halo_r, CY + halo_r),
        fill=(*halo_color, 110),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(radius=22))
    img.alpha_composite(glow)


def _draw_earth_disc(img: Image.Image, *, disc_r: int) -> None:
    """Radial-gradient ocean disc + a few stylised continent shapes.

    Continents are drawn as polygons inside the disc and then alpha-
    masked by a slightly-inset disc so they can never poke past the
    Earth's silhouette (mirrors the same belt-and-braces idea used by
    ``_draw_title_planet`` in the renderer).
    """
    disc = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(disc)

    # Radial gradient — bright cyan toward upper-left, deep navy toward
    # lower-right. Built from concentric circles with shifting tint.
    deep = (12, 32, 58)
    bright = (65, 145, 205)
    light_x = CX - disc_r // 3
    light_y = CY - disc_r // 2
    for r in range(disc_r, 0, -1):
        t = 1 - (r / disc_r)
        # Blend deep → bright toward the lit pole. The offset to (light_x,
        # light_y) is approximated by drawing the gradient relative to the
        # disc centre — close enough at icon resolution.
        col = _blend(deep, bright, min(1.0, t * 0.95 + 0.05))
        draw.ellipse(
            (CX - r, CY - r, CX + r, CY + r),
            fill=(*col, 255),
        )

    # Continents — fractional coordinates relative to disc_r so the
    # shapes scale if SIZE changes later. Africa / Eurasia / Americas
    # silhouettes, kept abstract since they need to read at 16 px.
    continent_color = (88, 145, 105)
    continent_edge = (52, 95, 70)
    polys = [
        # Africa-ish lower-right
        [(0.12, -0.18), (0.28, -0.08), (0.30, 0.18), (0.20, 0.36),
         (0.08, 0.28), (0.02, 0.10), (0.05, -0.10)],
        # Eurasia-ish upper arc
        [(-0.25, -0.42), (-0.05, -0.45), (0.20, -0.40), (0.36, -0.28),
         (0.30, -0.18), (0.10, -0.22), (-0.10, -0.28), (-0.25, -0.30)],
        # Americas-ish left band
        [(-0.50, -0.28), (-0.42, -0.10), (-0.40, 0.12), (-0.45, 0.32),
         (-0.55, 0.18), (-0.58, -0.05), (-0.55, -0.22)],
        # Australia / small mass lower-right
        [(0.38, 0.18), (0.48, 0.20), (0.45, 0.30), (0.36, 0.28)],
    ]
    for poly_fr in polys:
        pts = [
            (CX + int(dx * disc_r), CY + int(dy * disc_r))
            for dx, dy in poly_fr
        ]
        draw.polygon(pts, fill=(*continent_color, 240))
        draw.polygon(pts, outline=(*continent_edge, 220), width=1)

    # Mask to the disc — any continent pixel outside the silhouette gets
    # alpha-multiplied to zero.
    mask = Image.new("L", (SIZE, SIZE), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse(
        (CX - disc_r, CY - disc_r, CX + disc_r, CY + disc_r),
        fill=255,
    )
    disc.putalpha(
        Image.eval(
            Image.merge("L", [mask]).filter(ImageFilter.GaussianBlur(0.6)),
            lambda v: v,
        )
    )

    img.alpha_composite(disc)


def _draw_life_arc(img: Image.Image, *, disc_r: int) -> None:
    """Green leaf rising over the Earth — the icon's visual payload.

    Built as a pointed-tip leaf with two parabolic arcs meeting at left
    and right tips. The leaf sits diagonally, tip toward the upper-left,
    base toward the lower-right — reads as a stylised shoot tilted by
    the planet's curvature, not a horizontal banner across the top
    (which the previous version produced and looked like an awkward
    crown).

    Parametrisation:
        t = 0 → left tip (meeting point of upper and lower arcs)
        t = 0.5 → centre of leaf (upper arc at peak, lower arc at base)
        t = 1 → right tip

    Upper arc bows away from the leaf axis by ``up_amp``; lower arc
    bows away by ``lo_amp``. Both arcs are pure parabolas so the tips
    meet cleanly without a visible seam.
    """
    arc = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(arc)

    # Leaf geometry in its OWN axis-aligned coordinate space, then
    # rotated. Length runs along the leaf's spine, width perpendicular.
    leaf_length = int(disc_r * 1.40)
    leaf_width = int(disc_r * 0.38)
    segments = 96

    # Build the upper and lower arcs in (along-spine, perpendicular)
    # coordinates, centred at (0, 0).
    spine_pts = []
    upper_pts = []
    lower_pts = []
    for i in range(segments + 1):
        t = i / segments
        along = -leaf_length // 2 + int(t * leaf_length)
        # Parabolic envelope, 0 at the tips (t=0, t=1), 1 at the centre.
        envelope = 1 - 4 * (t - 0.5) ** 2
        # Asymmetric widths: more curve on the top (more "leafy"), less
        # on the bottom (subtler camber).
        up = -int(envelope * leaf_width * 0.55)
        lo = int(envelope * leaf_width * 0.45)
        upper_pts.append((along, up))
        lower_pts.append((along, lo))
        spine_pts.append((along, (up + lo) // 2))

    # Rotate by -38° (tilted toward upper-left) and translate so the
    # leaf sits above the Earth, slightly to the right of the disc's
    # centre axis — gives it a "rising over the horizon" feel.
    angle_deg = -38
    angle = math.radians(angle_deg)
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    # Anchor: a point slightly above and to the right of the disc top.
    anchor_x = CX + int(disc_r * 0.05)
    anchor_y = CY - disc_r + int(disc_r * 0.04)

    def project(p):
        x, y = p
        return (
            anchor_x + int(x * cos_a - y * sin_a),
            anchor_y + int(x * sin_a + y * cos_a),
        )

    upper_proj = [project(p) for p in upper_pts]
    lower_proj = [project(p) for p in lower_pts]
    spine_proj = [project(p) for p in spine_pts]
    leaf_pts = upper_proj + list(reversed(lower_proj))

    bright_green = (90, 220, 130)
    deep_green = (40, 130, 75)

    # Base fill in deep green.
    draw.polygon(leaf_pts, fill=(*deep_green, 250))

    # Highlight wash: a brighter green gradient along the spine,
    # strongest at the centre and fading toward the tips. Implemented by
    # drawing transparent ellipses at sample spine points and then
    # masking by the leaf silhouette.
    wash = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    wash_draw = ImageDraw.Draw(wash)
    for i in range(0, len(spine_proj), 2):
        t = i / max(1, len(spine_proj) - 1)
        # Brighter near the centre of the leaf (around t = 0.5).
        intensity = 1 - 2 * abs(t - 0.45)
        if intensity <= 0:
            continue
        alpha = int(200 * intensity ** 1.4)
        r = max(4, int(leaf_width * 0.45 * intensity))
        cx_, cy_ = spine_proj[i]
        wash_draw.ellipse(
            (cx_ - r, cy_ - r, cx_ + r, cy_ + r),
            fill=(*bright_green, alpha),
        )
    wash = wash.filter(ImageFilter.GaussianBlur(radius=4))
    # Mask to the leaf silhouette.
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).polygon(leaf_pts, fill=255)
    wash.putalpha(mask)
    arc.alpha_composite(wash)

    # Spine vein: thin lighter-green line down the middle.
    vein_color = (*_blend(bright_green, (255, 255, 255), 0.30), 230)
    for i in range(len(spine_proj) - 1):
        draw.line([spine_proj[i], spine_proj[i + 1]], fill=vein_color, width=2)

    # Crisp outline so the leaf reads against the dark Earth disc even
    # at 16 px (when the wash blurs into ambiguity).
    outline_color = (*_blend(deep_green, (0, 0, 0), 0.25), 200)
    for i in range(len(upper_proj) - 1):
        draw.line(
            [upper_proj[i], upper_proj[i + 1]],
            fill=outline_color, width=1,
        )
    for i in range(len(lower_proj) - 1):
        draw.line(
            [lower_proj[i], lower_proj[i + 1]],
            fill=outline_color, width=1,
        )

    img.alpha_composite(arc)


def build_icon() -> Image.Image:
    """Compose the icon: atmosphere → Earth disc → life crescent."""
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    disc_r = 88
    _draw_atmosphere_glow(img, disc_r=disc_r)
    _draw_earth_disc(img, disc_r=disc_r)
    _draw_life_arc(img, disc_r=disc_r)
    return img


def _atomic_write(path: Path, payload: bytes) -> None:
    """Write through a temp sibling, then rename — sync-daemon safe."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(payload)
    tmp.replace(path)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    img = build_icon()

    # PNG master.
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    _atomic_write(PNG_OUT, buf.getvalue())
    print(f"Wrote {PNG_OUT} ({PNG_OUT.stat().st_size:,} B)")

    # ICO bundle — Pillow generates the standard taskbar / Explorer sizes.
    buf = io.BytesIO()
    img.save(
        buf, format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    _atomic_write(ICO_OUT, buf.getvalue())
    print(f"Wrote {ICO_OUT} ({ICO_OUT.stat().st_size:,} B)")


if __name__ == "__main__":
    main()
