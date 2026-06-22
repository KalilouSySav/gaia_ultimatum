"""Extend each short playing-stage track into a longer multi-pass remix.

The playing playlist used to feel repetitive: short tracks (22-39 s)
rotated every few seconds, so a 10-minute session looped the same
5-track set ~15 times. Just looping each track inside pygame's player
(``play(loops=N)``) makes that worse — every loop is a hard restart,
no variation.

This tool composes a *real remix* per source track:

* concatenates 2-4 mood-variant passes (original -> deeper -> brighter ->
  reverb-tail -> back to original) with equal-power crossfades, so the
  listener hears an evolving piece, not a hard restart.
* seamless-loop-wraps the final composite so the AudioManager's
  natural advance still hands off cleanly at the end.
* re-normalises RMS + soft-limits so the output level matches the
  rest of the playing playlist.

Runs in-place on ``gaia_ultimatum/sounds/playlists/playing/*.wav`` —
each file is replaced with its longer remix. Tracks already at or
above ``TARGET_DURATION_S`` are left untouched (the long
``06_cinematic_drive.wav`` / ``07_dark_pulse.wav`` already have
plenty of body).

Run from the repo root::

    python tools/extend_playing_remixes.py

The shared DSP primitives (pitch shift, LP, reverb, RMS normalise,
loop wrap, tape saturate) are imported from
``cut_playlist_from_background`` so the remix character matches the
generation pipeline that produced the source files in the first place.
"""

from __future__ import annotations

import math
import os
import sys
import wave
from pathlib import Path

import numpy as np

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from gaia_ultimatum.assets import SOUNDS_DIR  # noqa: E402

# Reuse the DSP toolkit already used to generate the playlist — same
# spectral character end-to-end, no audible discontinuity between an
# untouched-source track and a remixed one.
from tools.cut_playlist_from_background import (  # noqa: E402
    SAMPLE_RATE,
    _apply_fades,
    _bass_mono,
    _high_pass_filter,
    _high_shelf_boost,
    _mid_presence,
    _normalize_rms,
    _one_pole_lp,
    _peak_limit_tanh,
    _pitch_shift,
    _remove_dc,
    _reverb_tail,
    _seamless_loop_wrap,
    _stereo_widen,
    _tape_saturate,
    _tpdf_dither,
    _trim_to_zero_crossing,
    _write_wav,
)

PLAYING_DIR = SOUNDS_DIR / "playlists" / "playing"
# 240 s (~4 min) per track. First pass of the tool aimed at 120 s but
# the user still felt the playlist looped too quickly during long
# sessions — at 8 tracks × 2 min the full playlist cycled every
# ~18 min, so a 30-min play could hit the same track twice. 4 min
# per track gives ~32 min per full pass; combined with the
# mood-weighted shuffle each track lands in a fresh emotional slot
# inside its 4-min window so the listener doesn't perceive the
# extension as padding.
TARGET_DURATION_S = 240.0
XFADE_S = 2.5               # cross-fade between passes
LOOP_WRAP_S = 1.5           # tail->head fade for the final composite
# Mid-tier mastering target — matches the "energy" mood the playing
# bed sits in (cut_playlist_from_background uses 3800 for energy mood,
# but the existing playing files measured 4194-5046 RMS so the bed had
# already been pushed higher in a later pass; matching that target
# avoids a level dip after remixing).
TARGET_RMS = 4600.0


# Per-pass character variants. Each entry is a callable applied to a
# fresh copy of the source. The remix cycles through these in order:
# original (pass 0) -> deeper (pass 1) -> brighter (pass 2) -> spacious
# (pass 3) -> back to original on pass 4, etc. Wrapping back to original
# at pass 4 closes the loop emotionally — the listener returns home.
def _variant_original(audio: np.ndarray) -> np.ndarray:
    """No DSP — return as-is. Pass 0 + wrap-around home position."""
    return audio


def _variant_deeper(audio: np.ndarray) -> np.ndarray:
    """Drop a tone, soften the top, add tape body.

    Pitch shift -2 semitones widens the perceived spectral content
    downward; the 6 kHz one-pole low-pass removes air which would
    otherwise make the deeper register read as muddy. Tape saturate at
    drive 0.12 brings back the harmonic body the LP just removed, so
    the variant reads as "warmer / more contemplative" rather than
    "muffled".
    """
    out = _pitch_shift(audio, semitones=-2.0)
    out = _one_pole_lp(out, cutoff_hz=6000.0)
    out = _tape_saturate(out, drive=0.12)
    return out


def _variant_brighter(audio: np.ndarray) -> np.ndarray:
    """Raise a tone, lift the top, widen the stereo image.

    Pitch shift +1 semitone gives a faster, more anxious tempo. The
    +2 dB high-shelf at 3 kHz adds the perceived clarity that pairs
    naturally with the higher fundamental. 1.30× stereo widening
    extends the soundstage so the brighter pass reads as "bigger /
    more present", not just "louder".
    """
    out = _pitch_shift(audio, semitones=+1.0)
    out = _high_shelf_boost(out, cutoff_hz=3000.0, gain_db=2.0)
    out = _stereo_widen(out, amount=1.30)
    return out


def _variant_spacious(audio: np.ndarray) -> np.ndarray:
    """Reverb tail + width — a long-room remix.

    Half-second reverb at 22 % wet creates the spacious break-pass
    that lets the previous tension dissipate before the next pass
    arrives. 1.20× stereo widen adds horizontal real estate so the
    reverb tail spreads instead of stacking in the centre.
    """
    out = _reverb_tail(audio, decay_s=0.5, mix=0.22)
    out = _stereo_widen(out, amount=1.20)
    return out


# Ordered variant cycle. Index 0 must always be "original" so the very
# first pass of every remix lands on the source as-shipped (the
# listener has heard this exact bed for many sessions; the remix
# variants come *after* that recognition moment, so the new passes
# feel like development of a known theme, not replacement of it).
VARIANTS: tuple[tuple[str, callable], ...] = (
    ("original",  _variant_original),
    ("deeper",    _variant_deeper),
    ("brighter",  _variant_brighter),
    ("spacious",  _variant_spacious),
)


def _read_wav(path: Path) -> np.ndarray:
    """Read a stereo 16-bit WAV into an ``(N, 2)`` int16 numpy array."""
    with wave.open(str(path), "rb") as w:
        nch = w.getnchannels()
        sw = w.getsampwidth()
        fr = w.getframerate()
        nf = w.getnframes()
        raw = w.readframes(nf)
    if sw != 2:
        raise ValueError(f"{path}: expected 16-bit samples, got {sw * 8}-bit")
    if fr != SAMPLE_RATE:
        raise ValueError(
            f"{path}: expected {SAMPLE_RATE} Hz, got {fr} Hz",
        )
    arr = np.frombuffer(raw, dtype=np.int16)
    if nch == 1:
        # Promote mono to stereo by duplicating the channel — the DSP
        # functions expect a 2-D (frames, channels) layout.
        arr = np.column_stack([arr, arr])
    elif nch == 2:
        arr = arr.reshape(-1, 2)
    else:
        raise ValueError(f"{path}: expected 1 or 2 channels, got {nch}")
    return arr.copy()


def _equal_power_crossfade(
    a: np.ndarray, b: np.ndarray, xfade_s: float,
) -> np.ndarray:
    """Equal-power crossfade ``a`` into ``b`` over ``xfade_s`` seconds.

    Pads/truncates as needed so the result has length
    ``len(a) + len(b) - xfade_n``. Equal-power keeps perceived
    loudness constant across the overlap — a linear (sum) crossfade
    would dip by 3 dB in the middle.
    """
    xf_n = int(SAMPLE_RATE * xfade_s)
    if xf_n <= 0:
        return np.concatenate([a, b], axis=0)
    xf_n = min(xf_n, a.shape[0], b.shape[0])
    if xf_n <= 0:
        return np.concatenate([a, b], axis=0)
    angles = np.linspace(0.0, math.pi / 2.0, xf_n, dtype=np.float32)
    fade_out = np.cos(angles)[:, np.newaxis]
    fade_in = np.sin(angles)[:, np.newaxis]
    head = a[-xf_n:].astype(np.float32) * fade_out
    tail = b[:xf_n].astype(np.float32) * fade_in
    blend = head + tail
    blended = np.clip(blend, -32768, 32767).astype(np.int16)
    return np.concatenate([a[:-xf_n], blended, b[xf_n:]], axis=0)


def _remix_extend(
    source: np.ndarray, target_s: float, file_label: str,
) -> tuple[np.ndarray, list[str]]:
    """Build the multi-pass remix.

    Determines how many passes are needed to reach ``target_s`` after
    accounting for crossfade overlap, then concatenates the variant
    cycle with equal-power crossfades. Returns the composite + the
    list of pass labels for logging.
    """
    source_s = source.shape[0] / SAMPLE_RATE
    if source_s <= 0:
        raise ValueError("Empty source")
    # Each additional pass contributes (source_s - XFADE_S) of new
    # material (the crossfade overlap is shared between the outgoing
    # tail and the incoming head). Solve:
    #   total = source_s + (passes - 1) * (source_s - XFADE_S) ≥ target_s
    # -> passes ≥ 1 + (target_s - source_s) / (source_s - XFADE_S)
    if source_s >= target_s:
        return source, ["original"]
    new_per_pass = max(0.5, source_s - XFADE_S)
    passes_needed = 1 + max(1, int(math.ceil(
        (target_s - source_s) / new_per_pass
    )))
    # Cap at 6 passes — beyond that the listener has heard every
    # variant 1.5× and the remix starts feeling padded rather than
    # composed. With 4 variants in the cycle, 6 passes = original ->
    # deeper -> brighter -> spacious -> original -> deeper, ending on a
    # variant matches the "go further, don't return home" feel that
    # suits a 2-min playing-bed cut.
    passes_needed = min(6, passes_needed)

    # Build pass list — index modulo len(VARIANTS) so the cycle wraps.
    composite = source.copy()
    labels: list[str] = ["original"]
    for i in range(1, passes_needed):
        variant_name, variant_fn = VARIANTS[i % len(VARIANTS)]
        variant_audio = variant_fn(source)
        composite = _equal_power_crossfade(
            composite, variant_audio, XFADE_S,
        )
        labels.append(variant_name)
    return composite, labels


def _master(composite: np.ndarray) -> np.ndarray:
    """Final mastering pass — bass-mono / RMS / limit / dither.

    Matches the master chain ``cut_playlist_from_background`` runs at
    the end of every cut so the remix output sits at the same level,
    same headroom, same noise floor as the rest of the playlist.
    The mid-presence bump is skipped here — the variant passes
    already add presence via the high-shelf boost on the "brighter"
    pass, so a second bump on every sample would push the upper-mid
    register into harshness.
    """
    out = _high_pass_filter(composite, cutoff_hz=60.0)
    out = _remove_dc(out)
    out = _bass_mono(out, cutoff_hz=200.0)
    out = _normalize_rms(out, target_rms=TARGET_RMS)
    out = _peak_limit_tanh(out, ceiling=0.95)
    out = _trim_to_zero_crossing(out, max_trim=400)
    out = _seamless_loop_wrap(out, xfade_s=LOOP_WRAP_S)
    # Short fades at the absolute buffer edges so the first/last
    # samples ramp from silence — covers MUSIC_END_EVENT delivery
    # latency on natural advance.
    out = _apply_fades(out, fade_in_s=0.5, fade_out_s=1.0)
    out = _tpdf_dither(out, amplitude=1.0)
    return out


def main() -> None:
    if not PLAYING_DIR.is_dir():
        raise FileNotFoundError(
            f"Playing directory missing: {PLAYING_DIR}",
        )
    sources = sorted(
        p for p in PLAYING_DIR.iterdir()
        if p.suffix.lower() == ".wav"
    )
    if not sources:
        print(f"No .wav files in {PLAYING_DIR}")
        return
    print(f"Source: {PLAYING_DIR.relative_to(REPO_ROOT)}")
    print(f"Target duration: {TARGET_DURATION_S:.0f}s")
    print()
    for path in sources:
        audio = _read_wav(path)
        source_s = audio.shape[0] / SAMPLE_RATE
        if source_s >= TARGET_DURATION_S:
            print(f"  {path.name}: {source_s:.1f}s — already long enough, skipping")
            continue
        composite, labels = _remix_extend(audio, TARGET_DURATION_S, path.name)
        mastered = _master(composite)
        new_s = mastered.shape[0] / SAMPLE_RATE
        _write_wav(path, mastered)
        print(
            f"  {path.name}: {source_s:.1f}s -> {new_s:.1f}s  "
            f"[{ ' -> '.join(labels) }]"
        )
    print()
    print("Done.")


if __name__ == "__main__":
    main()
