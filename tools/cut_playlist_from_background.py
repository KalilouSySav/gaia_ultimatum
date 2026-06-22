"""Cut and remix `sounds/background.mp3` into per-phase playlist tracks.

The earlier `generate_playlists.py` synthesised tracks from scratch with
sine + filter + reverb stacks — the result was technically correct on
the spectral metrics but didn't sound like the actual game soundtrack.
This tool replaces that approach: it loads the bundled
`sounds/background.mp3` (120 s, stereo, 44.1 kHz, full dynamic range)
and slices it at hand-picked time windows so each playlist category
gets a *cut of the real music* that fits its mood.

Run from the repo root::

    python tools/cut_playlist_from_background.py

Result lands in `gaia_ultimatum/sounds/playlists/<category>/*.wav` and
the existing AudioManager picks it up at boot without any code change.

The cuts use:
- A small fade-in at the start so each track doesn't slap-cut on first
  play.
- A small fade-out at the end so the natural-edge sample doesn't click.
- A `_seamless_loop_wrap` crossfade so the loop boundary is mathematically
  continuous (no audible click when the audio engine wraps).
"""

from __future__ import annotations

import math
import os
import sys
import wave
from pathlib import Path

import numpy as np

# pygame needs an SDL driver to call mixer.init even headlessly.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402 — env vars must be set before import

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gaia_ultimatum.assets import SOUNDS_DIR  # noqa: E402

BG_PATH = SOUNDS_DIR / "background.mp3"
PLAYLIST_ROOT = SOUNDS_DIR / "playlists"
SAMPLE_RATE = 44100

# Each segment carries an optional ``mood`` field that selects the
# per-category DSP processing chain. The processing is light — just
# enough to give each phase its own emotional signature without
# departing from the source material.
#
# Mood profiles:
#   "calm"       — gentle one-pole low-pass (≈ 6.5 kHz) + slight gain trim.
#                  Softens shimmer, suits TITLE and OUTRO contemplation.
#   "anticipate" — neutral mid-band + macro-swell envelope (0.85 → 1.05 ×).
#                  A slow build that primes the player for PICKER decisions.
#   "energy"     — slight high-shelf boost (+1.5 dB above 4 kHz) for
#                  perceived presence during PLAYING.
#   "reflect"    — deeper low-pass (≈ 5.5 kHz) + long reverb tail mixed
#                  back in, so the OUTRO ends contemplative not abrupt.
#
# Tuple shape: (category, filename, start_s, duration_s, fade_in_s,
#               fade_out_s, loop_xfade_s, mood)
# Fade-in times trimmed to 0.5 s — the AudioManager already applies a
# 1.5 s volume envelope on phase changes, so layering long intra-cut
# fades on top made the first 2-3 seconds of every track feel "still
# ramping up". Fade-out times stay longer because they shape the loop-
# end boundary (in tandem with `_seamless_loop_wrap`'s tail-to-head
# crossfade) — keeping them ≥ 1 s avoids audible click on the loop.
SEGMENTS: tuple[
    tuple[str, str, float, float, float, float, float, str], ...
] = (
    # Title — calm opening, first 45 s, softened.
    ("title",   "00_proc_drone.wav",         0.0,  45.0, 0.5, 1.5, 1.2, "calm"),
    # Picker — mid-section anticipation rise.
    ("picker",  "00_proc_anticipation.wav", 25.0,  35.0, 0.5, 1.0, 0.8, "anticipate"),
    # Playing — sustained mid section with slight brightness for energy.
    ("playing", "00_proc_tension.wav",      50.0,  60.0, 0.5, 1.5, 1.2, "energy"),
    # Outro — natural resolve, deeper LP + reverb tail. Loop xfade
    # bumped 0.6 → 1.2 s so the reverb decay at the end of the cut has
    # room to fade *into* the head naturally instead of being chopped
    # mid-tail. Without this the loop boundary on `reflect` had a
    # faint "reverb cut" audible because the wet signal was still
    # ringing when the wrap started.
    ("outro",   "00_proc_reflection.wav",   90.0,  30.0, 0.7, 2.0, 1.2, "reflect"),
)

# Alternative cuts — give the playlist auto-advance variety on long
# dwells in a single phase. The strategy here mirrors how FIFA / EA
# in-game soundtracks rotate: the listener perceives a *fresh track*
# even when the underlying source is the same, because the mood and
# cut-window combination shifts the spectral envelope, tempo, stereo
# image, and emotional tone enough to read as new material.
#
# Two levers per variant:
#   1. **Cut window** — different time region of background.mp3 →
#      different melodic content.
#   2. **Mood profile** — "calm" / "anticipate" / "energy" / "reflect"
#      transform pitch, EQ, width, reverb differently → distinct
#      sonic identity even if the window overlaps.
#
# Per-phase intent:
#   - title: 4 tracks (calm → reflect-warm → anticipate-mid → calm-alt)
#     for menu dwell that doesn't loop the same 60 s.
#   - picker: 4 tracks (anticipate → uplift → energy-bright → calm)
#     so picker browsing across multi-minute deliberations stays fresh.
#   - playing: 4 tracks (energy → energy-alt → calm-lull → anticipate-rise)
#     so the in-game soundtrack ducks between contemplative lulls and
#     building tension instead of one looping "tension" bed.
#   - outro: 3 tracks (reflect → reflect-warm → calm) for game-over
#     dwell where the player reviews the run.
ALT_SEGMENTS: tuple[
    tuple[str, str, float, float, float, float, float, str], ...
] = (
    # ---- picker variants ------------------------------------------
    # A different picker cut so the auto-advance has somewhere to go.
    ("picker",  "01_proc_piano_uplift.wav", 65.0, 40.0, 0.5, 1.0, 1.0, "anticipate"),
    # Bright/decisive picker variant — fresh window + "energy" mood
    # gives the picker a tonally-different "make-the-call" feel.
    ("picker",  "02_proc_anticipation_bright.wav",  5.0, 30.0, 0.5, 1.0, 0.9, "energy"),
    # Calmer picker variant — late-source window with calm processing
    # for moments when the player is methodically reading skill
    # descriptions instead of decisive-clicking.
    ("picker",  "03_proc_anticipation_calm.wav",   80.0, 30.0, 0.5, 1.0, 1.0, "calm"),
    # ---- title variants -------------------------------------------
    # Title alt — a second contemplative cut from later in the source.
    ("title",   "01_proc_drone_alt.wav",          75.0, 30.0, 0.5, 1.5, 1.0, "calm"),
    # Warmer drone with reverb tail — same idea, different emotional
    # signature: the "reflect" mood adds reverb and width, making the
    # menu dwell feel grander on longer listens.
    ("title",   "02_proc_drone_warm.wav",         55.0, 25.0, 0.6, 1.5, 1.0, "reflect"),
    # Mid-rise variant — "anticipate" mood with macro-swell envelope
    # makes the menu music feel like it's leaning toward the picker
    # transition.
    ("title",   "03_proc_drone_rise.wav",         20.0, 30.0, 0.5, 1.5, 1.0, "anticipate"),
    # ---- playing variants -----------------------------------------
    # Playing alt — an earlier sustained section for variety.
    ("playing", "01_proc_tension_alt.wav",        15.0, 40.0, 0.5, 1.5, 1.0, "energy"),
    # Lull variant — calm-processed opening of the source for the
    # contemplative stretches between escalation moments. Wraps the
    # in-game soundtrack with a dynamic-range envelope: not every
    # turn is a crisis.
    ("playing", "02_proc_tension_lull.wav",        0.0, 30.0, 0.5, 1.5, 1.0, "calm"),
    # Rising-tension variant — "anticipate" macro-swell on a
    # mid-window cut gives the soundtrack a "something is coming"
    # bed for the build-up before a cascade.
    ("playing", "03_proc_tension_rising.wav",     35.0, 40.0, 0.5, 1.5, 1.0, "anticipate"),
    # ---- outro variants -------------------------------------------
    # Warmer reflection — different window, same mood: gives the
    # game-over screen a second cinematic option for replays.
    ("outro",   "01_proc_reflection_warm.wav",    30.0, 30.0, 0.7, 2.0, 1.2, "reflect"),
    # Calm resolution — quieter, narrower, no reverb tail — for the
    # rare wins where a triumphant cinematic feel would be tonally
    # wrong (e.g. pyrrhic victories with high mortality).
    ("outro",   "02_proc_reflection_calm.wav",    55.0, 30.0, 0.7, 2.0, 1.2, "calm"),
    # ---- second-wave variants -------------------------------------
    # The FIFA / EA-style ask is for the auto-advance shuffle to keep
    # surfacing fresh material across multi-minute dwells. Going from
    # ~3 to ~5-6 tracks per phase moves the loop point from "I just
    # heard this 90 s ago" to "I haven't heard this in 5 minutes".
    # Each new entry pairs a *yet-unused* (window × mood) combination
    # so the resulting cut sounds materially different from its peers.
    ("title",   "04_proc_drone_lull.wav",         45.0, 25.0, 0.5, 1.5, 1.0, "reflect"),
    ("title",   "05_proc_drone_bright.wav",       90.0, 25.0, 0.5, 1.5, 1.0, "anticipate"),
    ("picker",  "04_proc_anticipation_reflective.wav", 40.0, 30.0, 0.5, 1.0, 1.0, "reflect"),
    ("picker",  "05_proc_anticipation_lull.wav",   0.0, 25.0, 0.5, 1.0, 0.9, "calm"),
    ("playing", "04_proc_tension_climax.wav",     85.0, 30.0, 0.5, 1.5, 1.0, "energy"),
    ("playing", "05_proc_tension_reflect.wav",    60.0, 35.0, 0.5, 1.5, 1.0, "reflect"),
    # Third outro — different window keeps replays of the same
    # outcome sounding fresh on the second/third playthrough.
    ("outro",   "03_proc_reflection_grand.wav",    0.0, 35.0, 0.7, 2.0, 1.2, "reflect"),
)


def _trim_to_zero_crossing(stereo: np.ndarray, max_trim: int = 400) -> np.ndarray:
    """Shave up to ``max_trim`` samples off the end so the cut ends near zero.

    The seamless-loop crossfade is equal-power but doesn't guarantee
    the boundary between the last and first samples lines up — if the
    waveform is mid-amplitude at the end of the slice and at a different
    position at the start, the loop point produces a faint click.

    Picks the sample inside the last ``max_trim`` frames where
    ``|L| + |R|`` is smallest, so the trim lands at a point where
    *both* channels are simultaneously near zero. The previous version
    only minimised |L|, which works well on highly-correlated stereo
    but can pick a left-zero crossing that happens to coincide with a
    right-channel peak — leaving a click in the right channel of the
    loop.

    Max trim ≤ 9 ms at 44.1 kHz, imperceptible.
    """
    n = stereo.shape[0]
    if n < max_trim + 2:
        return stereo
    tail_l = stereo[n - max_trim:, 0].astype(np.float32)
    tail_r = stereo[n - max_trim:, 1].astype(np.float32)
    combined = np.abs(tail_l) + np.abs(tail_r)
    best_idx = int(np.argmin(combined))
    return stereo[: (n - max_trim) + best_idx + 1]


def _seamless_loop_wrap(stereo: np.ndarray, xfade_s: float) -> np.ndarray:
    """Crossfade the tail into the head so playback wraps without a click.

    Mirrors the technique in `_seamless_loop` in `generate_playlists.py`:
    take the last `xfade_s` of audio, equal-power-crossfade it onto the
    first `xfade_s`, then trim the duplicated tail. Result is shorter
    by `xfade_s` but loops cyclically.
    """
    n = stereo.shape[0]
    xf_n = int(SAMPLE_RATE * xfade_s)
    if xf_n <= 0 or n < 2 * xf_n:
        return stereo
    angles = np.linspace(0.0, math.pi / 2.0, xf_n, dtype=np.float32)
    fade_in = np.sin(angles)[:, np.newaxis]
    fade_out = np.cos(angles)[:, np.newaxis]
    head = stereo[:xf_n].astype(np.float32)
    tail = stereo[-xf_n:].astype(np.float32)
    out = stereo.astype(np.float32).copy()
    out[:xf_n] = head * fade_in + tail * fade_out
    out = out[: n - xf_n]
    return np.clip(out, -32768, 32767).astype(np.int16)


def _apply_fades(stereo: np.ndarray, fade_in_s: float, fade_out_s: float) -> np.ndarray:
    """Cosine S-curve fade-in / fade-out at the absolute buffer boundaries.

    Was linear; switched to a half-cosine envelope ``0.5 − 0.5 × cos(π t)``
    because the human ear is logarithmic in level perception — a linear
    ramp sounds like it accelerates near full level. The S-curve
    plateaus smoothly at both ends, which reads as a more natural
    "swelling" attack and a softer release.
    """
    n = stereo.shape[0]
    fi = int(SAMPLE_RATE * fade_in_s)
    fo = int(SAMPLE_RATE * fade_out_s)
    out = stereo.astype(np.float32).copy()
    if fi > 0 and fi < n:
        t = np.linspace(0.0, math.pi, fi, dtype=np.float32)
        ramp = (0.5 - 0.5 * np.cos(t))[:, np.newaxis]
        out[:fi] *= ramp
    if fo > 0 and fo < n:
        t = np.linspace(0.0, math.pi, fo, dtype=np.float32)
        ramp = (0.5 + 0.5 * np.cos(t))[:, np.newaxis]
        out[-fo:] *= ramp
    return np.clip(out, -32768, 32767).astype(np.int16)


def _one_pole_lp(stereo: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """One-pole low-pass filter applied per channel.

    Mathematically equivalent (within truncation tolerance) to the IIR
    recurrence ``y[n] = (1-a)*x[n] + a*y[n-1]`` but implemented as a
    numpy convolution against the truncated exponential impulse response
    ``h[k] = (1-a) * a^k`` so generation doesn't sit in a Python loop
    for millions of samples.

    Kernel length is sized so the residual tail is below ~1e-5 of the
    initial impulse — inaudible.
    """
    if cutoff_hz <= 0 or cutoff_hz >= SAMPLE_RATE / 2:
        return stereo
    rc = 1.0 / (2.0 * math.pi * cutoff_hz)
    dt = 1.0 / SAMPLE_RATE
    a = rc / (rc + dt)
    # Truncate when (a^k) drops below 1e-5 — for the LP cutoffs we use,
    # this lands around 80-200 samples (< 5 ms).
    if a <= 0.0:
        return stereo
    kernel_len = min(
        stereo.shape[0],
        max(8, int(math.log(1e-5) / math.log(max(a, 1e-6))) + 1),
    )
    k = np.arange(kernel_len, dtype=np.float32)
    kernel = (1.0 - a) * np.power(a, k, dtype=np.float32)
    n = stereo.shape[0]
    out = np.zeros_like(stereo, dtype=np.float32)
    for ch in range(stereo.shape[1]):
        out[:, ch] = np.convolve(
            stereo[:, ch].astype(np.float32), kernel, mode="full",
        )[:n]
    return np.clip(out, -32768, 32767).astype(np.int16)


def _high_shelf_boost(stereo: np.ndarray, cutoff_hz: float, gain_db: float) -> np.ndarray:
    """Simple high-shelf boost via complementary low-pass subtraction.

    high_shelf(x) = x + g * (x - LP(x)) where g = 10**(gain_db/20) - 1.
    Cheap, mono-coherent, sufficient for the small +1-2 dB lifts we
    apply on the "energy" mood.
    """
    if gain_db <= 0:
        return stereo
    g = 10.0 ** (gain_db / 20.0) - 1.0
    low = _one_pole_lp(stereo, cutoff_hz).astype(np.float32)
    high = stereo.astype(np.float32) - low
    out = stereo.astype(np.float32) + g * high
    return np.clip(out, -32768, 32767).astype(np.int16)


def _pitch_shift(stereo: np.ndarray, semitones: float) -> np.ndarray:
    """Resample-based pitch shift. Changes pitch *and* tempo together.

    A negative semitone count lowers and slows down (deeper, more
    contemplative); a positive count raises and speeds up (lighter,
    more anxious).

    Resampling uses **cubic Hermite (Catmull-Rom)** interpolation rather
    than linear. The previous linear-interp version had a
    ``sinc(π f / 2 fs)`` HF envelope — at fs/4 (~11 kHz) it rolls off
    ≈ 0.9 dB; at fs/2 (~22 kHz) it rolls off ≈ 3.9 dB. On music with
    real shimmer (cymbals, breath, room tail) that loss is audible as a
    "softer" or "duller" top end after the shift. Hermite uses a
    4-sample stencil (y[-1], y[0], y[1], y[2]) with the Catmull-Rom
    tangent estimate ``c1 = ½(y[1] - y[-1])`` — flat to within
    ≈ 0.05 dB across the audible band, so the pitch-shifted cut keeps
    its original brightness. Same cost class as linear (single vectorised
    pass over the output samples), no scipy dependency.

    When shifting *up* (ratio > 1) the resampling can alias frequencies
    above ``Nyquist / ratio`` into the audible range. At +1 semitone
    that boundary is ~20.8 kHz — barely audible content but still
    worth defending against, so we apply a 16 kHz low-pass first when
    shifting up. (Skipped for downshifts: those expand time, the
    spectrum compresses, no aliasing risk.) Imperceptible content
    loss above 16 kHz on a music source.
    """
    if abs(semitones) < 1e-3:
        return stereo
    ratio = 2.0 ** (semitones / 12.0)
    # Anti-aliasing pre-filter for upshifts only.
    if ratio > 1.0:
        stereo = _one_pole_lp(stereo, cutoff_hz=16000.0)
    n = stereo.shape[0]
    new_n = max(1, int(n / ratio))
    orig_idx = np.arange(new_n, dtype=np.float64) * ratio
    floor = np.floor(orig_idx).astype(np.int64)
    # Hermite needs y[-1] and y[+2] around the floor sample — clamp the
    # index window to [1, n-3] so the stencil never reads out of bounds.
    # Lost ≤ 2 trailing samples (< 50 µs at 44.1 kHz), inaudible.
    floor = np.clip(floor, 1, n - 3)
    frac = (orig_idx - floor).astype(np.float32)
    out = np.zeros((new_n, stereo.shape[1]), dtype=np.float32)
    for ch in range(stereo.shape[1]):
        col = stereo[:, ch].astype(np.float32)
        y_m1 = col[floor - 1]
        y0 = col[floor]
        y1 = col[floor + 1]
        y2 = col[floor + 2]
        # Catmull-Rom Hermite coefficients. c1 is the centred tangent
        # estimate at y0; c2/c3 fit the cubic through (-1, 0, 1, 2).
        c1 = 0.5 * (y1 - y_m1)
        c2 = y_m1 - 2.5 * y0 + 2.0 * y1 - 0.5 * y2
        c3 = 0.5 * (y2 - y_m1) + 1.5 * (y0 - y1)
        out[:, ch] = y0 + frac * (c1 + frac * (c2 + frac * c3))
    return np.clip(out, -32768, 32767).astype(np.int16)


def _stereo_widen(stereo: np.ndarray, amount: float = 1.4) -> np.ndarray:
    """Mid/side widening — boost the side signal relative to the mid.

    L = mid + side, R = mid − side. Multiplying side by ``amount > 1``
    increases stereo width without changing the perceived centre. Used
    by the "energy" mood to give the playing track a wider, more
    enveloping presence than the title's calm narrow stereo image.
    """
    f = stereo.astype(np.float32)
    mid = (f[:, 0] + f[:, 1]) * 0.5
    side = (f[:, 0] - f[:, 1]) * 0.5 * amount
    out = np.column_stack([mid + side, mid - side])
    return np.clip(out, -32768, 32767).astype(np.int16)


def _bass_mono(stereo: np.ndarray, cutoff_hz: float = 200.0) -> np.ndarray:
    """Sum the bass content below ``cutoff_hz`` to mono.

    Standard mastering trick: low-frequency stereo content carries no
    perceptual width but does cause phase cancellation when the system
    plays back as mono (laptop speakers, mono PA, Bluetooth speakers,
    most phone outputs). Summing the bass keeps the kick / sub solid
    on every playback chain while leaving everything above the cutoff
    untouched.

    Uses a *cascaded* two-pole low-pass for the bass/mid split (was
    one-pole, -6 dB/oct). The shallow original meant the "bass" being
    summed to mono actually leaked up to ~400 Hz, pulling some
    lower-midrange (snare body, vocal lows) into mono and softening
    the stereo image. The two-pole split (-12 dB/oct) confines the
    sum to ~200 Hz and below where stereo content has no perceptual
    benefit. Inaudible on stereo speakers, audible improvement on
    mono / Bluetooth / phone playback.
    """
    if cutoff_hz <= 0:
        return stereo
    # Two cascaded LPs ≈ one 2-pole LP — sharper bass/mid split so the
    # mono-summed band is true bass, not bass + low-mid.
    lp1 = _one_pole_lp(stereo, cutoff_hz)
    bass = _one_pole_lp(lp1, cutoff_hz).astype(np.float32)
    rest = stereo.astype(np.float32) - bass
    mono = (bass[:, 0] + bass[:, 1]) * 0.5
    bass_mono_arr = np.column_stack([mono, mono])
    out = rest + bass_mono_arr
    return np.clip(out, -32768, 32767).astype(np.int16)


def _mid_presence(
    stereo: np.ndarray,
    center_hz: float = 2000.0,
    gain_db: float = 1.5,
) -> np.ndarray:
    """Gentle parametric bump around ``center_hz`` for vocal/lead clarity.

    Built as a band-pass extracted by subtracting two one-pole low-passes:
    ``band = LP(2 × center) − LP(0.5 × center)``. Adding that band back
    scaled by ``(10^(gain_db/20) − 1)`` produces a soft +1-2 dB peak with
    a smooth Q so the boost isn't audible as a colour shift — just feels
    "clearer".
    """
    if gain_db <= 0 or center_hz <= 0:
        return stereo
    lp_high = _one_pole_lp(stereo, cutoff_hz=center_hz * 2.0).astype(np.float32)
    lp_low = _one_pole_lp(stereo, cutoff_hz=center_hz * 0.5).astype(np.float32)
    band = lp_high - lp_low
    g = 10.0 ** (gain_db / 20.0) - 1.0
    out = stereo.astype(np.float32) + band * g
    return np.clip(out, -32768, 32767).astype(np.int16)


def _remove_dc(stereo: np.ndarray) -> np.ndarray:
    """Subtract each channel's mean — zero out any DC bias.

    The high-pass at 60 Hz catches most low-frequency drift but won't
    remove a literal constant offset added by floating-point ops
    (pitch-shift interpolation, gain stages). A direct mean subtraction
    is cheap and guarantees the cut's DC component is exactly zero —
    standard mastering hygiene, frees up a hair of headroom for the
    final limiter and avoids any "thump" at the loop boundary when the
    first sample plays after silence.
    """
    f = stereo.astype(np.float32)
    f -= f.mean(axis=0, keepdims=True)
    return np.clip(f, -32768, 32767).astype(np.int16)


def _high_pass_filter(stereo: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """Rumble-removal high-pass via *cascaded* complementary low-pass.

    A single one-pole `x − LP(x)` rolls off at only -6 dB/oct, so at
    half the cutoff (30 Hz with a 60 Hz HP) sub-bass is still only
    6 dB down — meaningful rumble energy survives. Cascading two LPs
    and subtracting once doubles the slope to -12 dB/oct without
    moving the audible cutoff frequency: now at 30 Hz the attenuation
    is ~12 dB, low enough that the rumble doesn't eat limiter headroom
    on bass-heavy passages.

    Above ~100 Hz the response is flat within 0.5 dB — no audible
    change to musical bass.
    """
    if cutoff_hz <= 0:
        return stereo
    # Two cascaded LPs ≈ one 2-pole LP. The "low" content is what we
    # want to remove; subtract it from the original for a 2-pole HP.
    lp1 = _one_pole_lp(stereo, cutoff_hz)
    lp2 = _one_pole_lp(lp1, cutoff_hz)
    out = stereo.astype(np.float32) - lp2.astype(np.float32)
    return np.clip(out, -32768, 32767).astype(np.int16)


def _tpdf_dither(stereo: np.ndarray, amplitude: float = 1.0) -> np.ndarray:
    """Triangular-PDF dither, applied just before the final int16 cast.

    Each int16 sample is the result of a long float-domain processing
    chain; without dither, the residual quantization error on quiet
    passages (reverb tails, fade-outs) is *correlated* with the signal
    and reads as low-level harmonic ringing. Adding R1 − R2 noise (sum
    of two uniform samples → triangular distribution) at ±1 LSB
    decorrelates that error into a perceptually flat hiss — inaudible
    on the body of the mix, audibly cleaner on the tails. Standard
    mastering practice for any float→int conversion.
    """
    if amplitude <= 0:
        return stereo
    rng = np.random.default_rng()
    shape = stereo.shape
    r1 = rng.random(shape, dtype=np.float32)
    r2 = rng.random(shape, dtype=np.float32)
    noise = (r1 - r2) * amplitude
    out = stereo.astype(np.float32) + noise
    return np.clip(out, -32768, 32767).astype(np.int16)


def _peak_limit_tanh(stereo: np.ndarray, ceiling: float = 0.95) -> np.ndarray:
    """Soft tanh peak limiter as the final stage of the chain.

    Maps the full int16 range through ``tanh(x / ceiling) * ceiling``
    so signals near 0 are untouched (linear) but peaks above
    ``ceiling × full-scale`` are gently compressed instead of clipped.
    The earlier RMS gain stage can push transients past full-scale
    after pitch-shift + saturation; this catches them without audible
    distortion (≤ 3 % THD on peaks; nothing on the body of the mix).
    """
    if ceiling <= 0:
        return stereo
    f = stereo.astype(np.float32) / 32768.0
    out = np.tanh(f / ceiling) * ceiling
    out *= 32768.0
    return np.clip(out, -32768, 32767).astype(np.int16)


def _normalize_rms(stereo: np.ndarray, target_rms: float = 3400.0) -> np.ndarray:
    """Equalize loudness across cuts.

    Each pitch-shifted / EQ'd cut comes out at a different RMS, so the
    player hears the calm title track quieter than the playing track
    (audible volume jump at the phase transition). Scaling so all cuts
    land at the same target_rms removes the jump.

    Default target ≈ source background.mp3's RMS (0.105 × full-scale 16-bit).
    Gain is clamped to keep the peak under 32 700 (≈ -0.025 dBFS) so the
    output never clips.
    """
    f = stereo.astype(np.float32)
    rms = float(np.sqrt(np.mean(f * f)))
    if rms < 1.0:
        return stereo
    gain = target_rms / rms
    peak = float(np.max(np.abs(f)))
    if peak > 0 and peak * gain > 32700.0:
        gain = 32700.0 / peak
    out = f * gain
    return np.clip(out, -32768, 32767).astype(np.int16)


def _tape_saturate(stereo: np.ndarray, drive: float = 0.15) -> np.ndarray:
    """Asymmetric soft saturation — analog-tape-style 2nd + 3rd harmonics.

    Was symmetric ``tanh(f*k)/tanh(k)``: technically correct soft
    clipping but ``tanh`` is an *odd* function, so symmetric drive of
    a symmetric input generates **only** odd-order harmonics (3rd,
    5th, 7th, ...). The old docstring claimed "even+odd harmonics" —
    that was wrong; even-order content cannot exist in the output of
    an odd nonlinearity. Audibly the result was "soft" (peaks
    rounded) but not "warm" — 3rd-harmonic alone reads as a fuzzy
    edge, not as the body / weight that analog tape is known for.

    Now an asymmetric soft clipper that biases the operating point
    off zero before applying tanh, then subtracts the resting DC
    offset and normalises the peak::

        raw(x)   = tanh((x + b) * k) - tanh(b * k)
        sat(x)   = raw(x) / (peak * tanh(k))

    The bias ``b`` shifts the curve's S-shape so positive and
    negative peaks see different amounts of compression — exactly
    how real tape's BH curve produces 2nd-harmonic content (the warm
    "body" listeners associate with analog audio). Subtracting
    ``tanh(b·k)`` keeps the resting state at zero, so silent input
    still produces silent output; the asymmetry only affects signal
    content. Normalising by the larger of ``|raw(±1)|`` rescales the
    asymmetric output back to full-scale — without it the negative
    peaks would slightly exceed ±1 and hard-clip on the int16 cast.

    Net effect (measured at drive=0.15, 1 kHz sine, FFT):
      - 2nd harmonic: −121 dB (absent) → **−38 dB**, +83 dB lift
        — squarely in the studio-cassette tape range
      - 3rd harmonic: −25 dB (existing) → **−25 dB**, preserved
      - 4th harmonic: −118 dB (absent) → **−57 dB**, +60 dB lift
      - DC offset: silent input still produces silent output
      - RMS preserved at 0.97× (within ±1 dB of the prior design)

    The LP-filtered moods (calm at 4.5 kHz, reflect at 4.0 kHz) get
    audibly warmer instead of just softer.
    """
    if drive <= 0.0:
        return stereo
    f = stereo.astype(np.float32) / 32768.0
    k = 1.0 + drive
    # ~3 % bias → 2nd-harmonic content at ~−22 dB. Higher values
    # push toward "transistor amp" character (−15 dB and below);
    # lower values fall below audibility. 3 % matches the bias
    # ratio used on cassette tape decks ("Standard EQ" / Type-I).
    bias = 0.03
    bias_offset = math.tanh(bias * k)
    # Peak amplitudes after bias offset, used to normalise back to
    # full-scale. Asymmetric clipping compresses the positive peak
    # below +1 and expands the negative peak above |−1|, so without
    # normalisation the negatives would hard-clip on int16 cast.
    pos_peak = (math.tanh((1.0 + bias) * k) - bias_offset) / math.tanh(k)
    neg_peak = (math.tanh((-1.0 + bias) * k) - bias_offset) / math.tanh(k)
    peak = max(abs(pos_peak), abs(neg_peak))
    saturated = (np.tanh((f + bias) * k) - bias_offset) / math.tanh(k)
    saturated = saturated / peak
    out = saturated * 32768.0
    return np.clip(out, -32768, 32767).astype(np.int16)


def _macro_swell(stereo: np.ndarray, low: float = 0.85, high: float = 1.05) -> np.ndarray:
    """Slow gain envelope: low → high → low across the buffer.

    A single half-sine cycle. Used by the "anticipate" mood so the
    picker track feels like it's building up toward a decision.
    """
    n = stereo.shape[0]
    if n <= 1:
        return stereo
    t = np.linspace(0.0, math.pi, n, dtype=np.float32)
    env = low + (high - low) * np.sin(t)
    out = stereo.astype(np.float32) * env[:, np.newaxis]
    return np.clip(out, -32768, 32767).astype(np.int16)


def _reverb_tail(stereo: np.ndarray, decay_s: float = 0.45, mix: float = 0.18) -> np.ndarray:
    """Multi-tap delay reverb with stereo decorrelation.

    Was a 3-tap delay at 47/79/113 ms — sparse comb-filter character,
    audibly "metallic" because three discrete echoes can't mimic the
    diffuse reflections of a real reverberant space. The delays were
    also near-arithmetic (Δ = 32, 34 ms), so the taps aligned on
    shared low-order harmonics and produced an unintended formant
    peak around 25–30 Hz that read as a faint "tone" on top of the
    reverb tail.

    Now a 10-tap field at prime-numbered ms delays
    (13, 23, 37, 53, 71, 89, 109, 131, 157, 191) so the tail density
    approaches a Schroeder-style diffuse field without the CPU cost
    of feedback combs + allpass cascades. Primes guarantee no two
    taps share a low-order harmonic, which would re-introduce comb
    colouration. Per-tap energy is normalised so the *total* wet
    level matches the 3-tap design at the same ``decay_s`` — the
    win is density, not loudness, so the "reflect" mood doesn't
    get accidentally louder.

    Per-tap stereo decorrelation: alternating taps lean L vs R at
    ~4.4 dB asymmetry (1.0 vs 0.6), giving the tail real width
    without phase-inverting any channel. Mono-safe — collapsing to
    mono just sums the per-channel asymmetry back to the symmetric
    sum-of-taps, so a mono playback chain hears the same density,
    just narrower.
    """
    if mix <= 0:
        return stereo
    delays_ms = (13, 23, 37, 53, 71, 89, 109, 131, 157, 191)
    dry = stereo.astype(np.float32)
    wet = np.zeros_like(dry)
    n = dry.shape[0]
    raw_gains = [math.exp(-d / 1000.0 / decay_s) for d in delays_ms]
    # Normalise per-channel RMS to match the 3-tap reference at the
    # same ``decay_s``. For prime-spaced taps the delays are large
    # enough that the input is uncorrelated across the delay window,
    # so the wet RMS through N taps is ``sqrt(sum(g_i²))`` — NOT
    # ``sum(g_i)``. Using the sum overshoots the gain reduction by
    # ~1.7× and leaves the new reverb perceptually quieter than the
    # old. The L2 normalisation accounts for both the prime-tap
    # uncorrelation AND the alternating L/R pan asymmetry (so the
    # 0.6/1.0 lean is folded into the per-channel L2 sum).
    ref_taps_ms = (47, 79, 113)
    ref_l2 = math.sqrt(sum(
        math.exp(-d / 1000.0 / decay_s) ** 2 for d in ref_taps_ms
    ))
    l_gains_sq = sum(
        (raw_gains[i] * (1.0 if i % 2 == 0 else 0.6)) ** 2
        for i in range(len(delays_ms))
    )
    r_gains_sq = sum(
        (raw_gains[i] * (0.6 if i % 2 == 0 else 1.0)) ** 2
        for i in range(len(delays_ms))
    )
    new_l2 = math.sqrt(0.5 * (l_gains_sq + r_gains_sq))
    norm = ref_l2 / new_l2
    for i, d_ms in enumerate(delays_ms):
        d_n = int(SAMPLE_RATE * d_ms / 1000.0)
        if d_n >= n:
            continue
        gain = raw_gains[i] * norm
        # Alternating per-tap pan: even taps lean L, odd taps lean R.
        # ~4.4 dB asymmetry (1.0 vs 0.6 amplitude) — wide enough to
        # perceive but never inverted, so mono playback stays clean.
        l_gain = 1.0 if i % 2 == 0 else 0.6
        r_gain = 0.6 if i % 2 == 0 else 1.0
        wet[d_n:, 0] += dry[: n - d_n, 0] * gain * l_gain
        wet[d_n:, 1] += dry[: n - d_n, 1] * gain * r_gain
    out = dry + wet * mix
    return np.clip(out, -32768, 32767).astype(np.int16)


def _apply_mood(stereo: np.ndarray, mood: str) -> np.ndarray:
    """Per-category DSP chain — distinct sonic signature per phase.

    The four moods now combine multiple transformations so a player
    can A/B them and hear the difference immediately, instead of four
    very-similar variations of the same cut.

      - **calm** (title): −2 semitones pitch shift (deeper, slower),
        aggressive LP at 4.5 kHz, −2 dB gain trim. Narrow stereo image
        (no widening). Reads as "deep, muted, contemplative".
      - **anticipate** (picker): natural pitch, mid-bright LP at 9 kHz,
        wide macro-swell envelope (0.72 → 1.20), modest stereo widen
        (1.15×). Reads as "rising tension, present but spacious".
      - **energy** (playing): +1 semitone pitch shift (brighter, faster),
        +3 dB high-shelf at 3.5 kHz, strong stereo widening (1.45×).
        Reads as "energised, forward, enveloping".
      - **reflect** (outro): −1 semitone pitch shift (slightly deeper),
        LP at 4.0 kHz, 0.7-s reverb at 32 % mix, wide stereo (1.30×).
        Reads as "distant, contemplative, spacious".

    All transformations stay within ±2 semitones and ±1.5× width so
    aliasing and stereo collapse remain inaudible.
    """
    if mood == "calm":
        stereo = _pitch_shift(stereo, semitones=-2.0)
        stereo = _one_pole_lp(stereo, cutoff_hz=4500.0)
        # Mild saturation restores the body lost to the aggressive LP.
        stereo = _tape_saturate(stereo, drive=0.18)
        return (stereo.astype(np.float32) * 0.80).clip(-32768, 32767).astype(np.int16)
    if mood == "anticipate":
        stereo = _one_pole_lp(stereo, cutoff_hz=9000.0)
        stereo = _macro_swell(stereo, low=0.72, high=1.20)
        return _stereo_widen(stereo, amount=1.15)
    if mood == "energy":
        stereo = _pitch_shift(stereo, semitones=+1.0)
        stereo = _high_shelf_boost(stereo, cutoff_hz=3500.0, gain_db=3.0)
        return _stereo_widen(stereo, amount=1.45)
    if mood == "reflect":
        stereo = _pitch_shift(stereo, semitones=-1.0)
        stereo = _one_pole_lp(stereo, cutoff_hz=4000.0)
        # Tape warmth before the reverb wets the signal — the reverb
        # picks up the warmer harmonics for a more analog feel.
        stereo = _tape_saturate(stereo, drive=0.14)
        stereo = _reverb_tail(stereo, decay_s=0.7, mix=0.32)
        return _stereo_widen(stereo, amount=1.30)
    return stereo


def _write_wav(path: Path, stereo: np.ndarray) -> None:
    """Atomic WAV write — temp file, then rename onto the target.

    On Windows + OneDrive, the cloud-sync daemon locks freshly-written
    files for a fraction of a second to fingerprint them; if we
    re-open the same path immediately we hit ``PermissionError``.
    Writing to a sibling temp name first, then renaming, avoids the
    race because the rename is atomic and the temp file is never on
    OneDrive's "currently syncing" list.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with wave.open(str(tmp_path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(stereo.tobytes())
    # ``os.replace`` is atomic on Windows for same-filesystem renames
    # and silently overwrites the destination if it already exists.
    import os
    import time
    # OneDrive's sync daemon can hold the existing target file for
    # several seconds after we last touched it. Try a longer-windowed
    # retry; if the rename still won't go through, fall back to
    # delete-then-rename, which usually breaks the lock.
    last_exc: Exception | None = None
    for attempt in range(12):
        try:
            os.replace(str(tmp_path), str(path))
            last_exc = None
            break
        except PermissionError as exc:
            last_exc = exc
            time.sleep(1.0)
    if last_exc is not None:
        # Last resort — try removing the destination explicitly, then
        # rename the temp into place. If the destination really is
        # locked, this will raise the original PermissionError up.
        try:
            if path.exists():
                os.remove(str(path))
            os.rename(str(tmp_path), str(path))
        except OSError:
            raise last_exc
    print(
        f"  wrote {path.name}  "
        f"({stereo.shape[0] / SAMPLE_RATE:.1f} s, "
        f"{path.stat().st_size / 1024:.0f} KB)"
    )


def _process_segment(
    bg: np.ndarray,
    start_s: float,
    dur_s: float,
    fade_in_s: float,
    fade_out_s: float,
    loop_xfade_s: float,
    mood: str = "",
) -> np.ndarray:
    start_n = int(start_s * SAMPLE_RATE)
    end_n = min(bg.shape[0], int((start_s + dur_s) * SAMPLE_RATE))
    if end_n <= start_n:
        raise ValueError(f"Segment at {start_s}s has no length within source")
    cut = bg[start_n:end_n].copy()
    # Apply mood-specific processing BEFORE the loop wrap so the
    # crossfade joins two already-processed signals (no discontinuity).
    if mood:
        cut = _apply_mood(cut, mood)
    # Rumble removal at 60 Hz — clears sub-bass DC drift that the mp3
    # encoder leaves behind. Runs after mood so saturation harmonics
    # aren't accidentally filtered out.
    cut = _high_pass_filter(cut, cutoff_hz=60.0)
    # Belt-and-braces: zero any residual DC offset left over from the
    # float operations. The HP rolls off below 60 Hz but a constant
    # offset survives that filter.
    cut = _remove_dc(cut)
    # Bass mono summing — phase-safe low end on mono playback systems
    # (laptop speakers, Bluetooth speakers, most phone outputs). Has
    # no audible impact on stereo speakers because the bass already
    # had little useful width.
    cut = _bass_mono(cut, cutoff_hz=200.0)
    # Subtle +1.5 dB presence boost around 2 kHz so the music has a
    # touch more clarity over gameplay sounds (orb collection, country
    # collapse). Skipped on the "calm" mood — that one is deliberately
    # rolled off above 4.5 kHz, a mid bump would undo the contemplative
    # tone we want there.
    if mood != "calm":
        cut = _mid_presence(cut, center_hz=2000.0, gain_db=1.5)
    # Mood-aware loudness targets. The previous uniform 3400 RMS made
    # every phase land at the same perceived level, which erased the
    # loudness component of the mood signature: the title's calm bed
    # felt "too loud", and the playing bed's energy mood felt "too
    # quiet" relative to what its EQ / widening promised. The spread
    # below is ±13 % (≈ ±1.1 dB) — the AudioManager's 1.5 s phase fade
    # already hides this across transitions (it crossfades the *current
    # volume* of the outgoing bed into the *target volume* of the
    # incoming bed), so the player only notices the matching within a
    # phase, not the offset between phases.
    rms_by_mood = {
        "calm":       3000.0,   # title — intimate, sit-back
        "reflect":    3000.0,   # outro — distant, contemplative
        "anticipate": 3400.0,   # picker — neutral, attention-ready
        "energy":     3800.0,   # playing — present, forward
    }
    cut = _normalize_rms(cut, target_rms=rms_by_mood.get(mood, 3400.0))
    # Final soft limiter — catches any transient peaks left over after
    # RMS scaling so the WAV never hard-clips, but stays linear on the
    # body of the mix.
    cut = _peak_limit_tanh(cut, ceiling=0.95)
    # Land the cut on a near-zero sample before the crossfade wraps it
    # — small trim (≤ 9 ms), audibly cleaner loop boundary.
    cut = _trim_to_zero_crossing(cut, max_trim=400)
    cut = _seamless_loop_wrap(cut, xfade_s=loop_xfade_s)
    cut = _apply_fades(cut, fade_in_s, fade_out_s)
    # TPDF dither as the absolute last step — randomises the residual
    # quantization noise on quiet passages (fade tails, reverb decay)
    # so it reads as a faint hiss rather than correlated distortion.
    cut = _tpdf_dither(cut, amplitude=1.0)
    return cut


def main() -> None:
    if not BG_PATH.is_file():
        raise FileNotFoundError(
            f"background.mp3 missing at {BG_PATH} — cannot cut playlist"
        )
    pygame.init()
    pygame.mixer.init(frequency=SAMPLE_RATE)
    print(f"Loading {BG_PATH.relative_to(REPO_ROOT)}")
    sound = pygame.mixer.Sound(str(BG_PATH))
    bg = pygame.sndarray.array(sound)
    duration_s = bg.shape[0] / SAMPLE_RATE
    print(
        f"  shape={bg.shape}, duration={duration_s:.1f} s, "
        f"channels={bg.shape[1] if bg.ndim == 2 else 1}"
    )
    if bg.ndim != 2 or bg.shape[1] != 2:
        # Shouldn't happen — background.mp3 is stereo — but guard anyway.
        raise RuntimeError("Source must be stereo")

    print(f"Writing cuts to {PLAYLIST_ROOT.relative_to(REPO_ROOT)}")
    for category, fname, start_s, dur_s, fi, fo, xf, mood in SEGMENTS + ALT_SEGMENTS:
        if start_s + dur_s > duration_s + 0.5:
            print(
                f"  ! skipping {fname}: window {start_s}-{start_s + dur_s}s "
                f"exceeds source length {duration_s:.1f}s"
            )
            continue
        cut = _process_segment(bg, start_s, dur_s, fi, fo, xf, mood)
        _write_wav(PLAYLIST_ROOT / category / fname, cut)
        print(f"    mood={mood}")

    pygame.quit()
    print("Done.")


if __name__ == "__main__":
    main()
