"""Generate "warm sibling" companions for each playing-stage track.

The playing playlist holds 8 tracks (~5 min each, ~43 min total).
On 30-60 min play sessions the listener cycles through them at least
once and starts hearing the same tracks again. The prior attempt at
addressing this — importing variants from title/picker/outro — broke
the playing-stage tonal home; calm reflective material processed
through energy DSP still sounded like a *different mood* than what
players expect from the playing phase.

This tool stays inside the playing tonal home. For each of the 8
existing tracks it produces a sibling — same source musical material,
processed through a **warm / analog / focused** DSP recipe rather than
the existing tracks' **bright / wide** signature. Siblings stay in the
energy/tension mood band (filename keeps the source's mood keywords)
so the mood-weighted picker treats them as equivalent options to their
parents, but the timbral character is unambiguously distinct:

  * Pitch shift -1 semitone — deeper, more resonant
  * Tape saturation @ drive 0.20 — analog warmth, 2nd-harmonic richness
  * Mid-low boost (+2 dB @ 400 Hz via mid_presence) — body weight
  * Mid-high attenuation (-1.5 dB via complementary high-shelf cut)
    — moves the perceived focus down from the parent's 3.5 kHz
    presence-boost zone
  * Stereo widen 1.25× — narrower than the 1.45× parent setting,
    more focused/intimate image
  * Subtle reverb (0.3 s decay, 0.18 mix) — sustained space without
    the parent's brightness-forward character

Result: 16 playing-stage tracks total (8 originals + 8 warm siblings),
all sharing tonal home. Same RMS target (4500) so playback level
stays cohesive — siblings sit beside their parents in the picker,
not on a separate level tier.

Naming convention: ``<idx>_<source_stem>_warm.wav``. Sorts adjacent
to the parent in ``discover_playlists``' alphabetical scan, so
related material clusters in directory listings.

Run from the repo root::

    python tools/generate_playing_siblings.py

After running, re-run ``tools/generate_playing_transitions.py`` to
produce matching transition pads for the new siblings.
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

from tools.cut_playlist_from_background import (  # noqa: E402
    SAMPLE_RATE,
    _apply_fades,
    _bass_mono,
    _high_pass_filter,
    _mid_presence,
    _normalize_rms,
    _one_pole_lp,
    _peak_limit_tanh,
    _pitch_shift,
    _remove_dc,
    _reverb_tail,
    _stereo_widen,
    _tape_saturate,
    _tpdf_dither,
    _trim_to_zero_crossing,
    _write_wav,
)

PLAYING_DIR = SOUNDS_DIR / "playlists" / "playing"

# RMS target matches the parent tracks' baseline (4500). Siblings sit
# at the same playback level as their parents so the rotation never
# produces a perceived loudness jump.
TARGET_RMS = 4500.0

# Suffix that marks a sibling vs its parent. Kept short so the
# filename stays readable in directory listings; "_warm" is also
# the most accurate one-word description of the new DSP character.
SIBLING_SUFFIX = "warm"


def _read_wav(path: Path) -> np.ndarray:
    """Read a stereo 16-bit WAV as ``(N, 2)`` int16 array."""
    with wave.open(str(path), "rb") as w:
        nch = w.getnchannels()
        sw = w.getsampwidth()
        fr = w.getframerate()
        nf = w.getnframes()
        raw = w.readframes(nf)
    if sw != 2:
        raise ValueError(f"{path}: expected 16-bit, got {sw * 8}-bit")
    if fr != SAMPLE_RATE:
        raise ValueError(f"{path}: expected {SAMPLE_RATE} Hz, got {fr}")
    arr = np.frombuffer(raw, dtype=np.int16)
    if nch == 1:
        arr = np.column_stack([arr, arr])
    elif nch == 2:
        arr = arr.reshape(-1, 2)
    else:
        raise ValueError(f"{path}: expected 1 or 2 channels, got {nch}")
    return arr.copy()


def _high_shelf_cut(stereo: np.ndarray, cutoff_hz: float, gain_db: float) -> np.ndarray:
    """High-shelf attenuation via complementary low-pass mixing.

    Inverse of ``_high_shelf_boost``: ``out = x - g * (x - LP(x))`` with
    ``g = 1 - 10**(gain_db / 20)`` for negative ``gain_db``. Removes the
    upper-frequency presence the parent's +3 dB shelf added, so the
    sibling's spectral centre of gravity sits lower than the parent's.
    """
    if gain_db >= 0:
        return stereo
    # gain_db is negative; we want to subtract a fraction of the
    # high-frequency content. Convert dB to linear *cut* factor.
    g = 1.0 - 10.0 ** (gain_db / 20.0)  # 0..1
    low = _one_pole_lp(stereo, cutoff_hz).astype(np.float32)
    high = stereo.astype(np.float32) - low
    out = stereo.astype(np.float32) - g * high
    return np.clip(out, -32768, 32767).astype(np.int16)


def _make_sibling(source: np.ndarray) -> np.ndarray:
    """Apply the warm-sibling DSP chain to a source track."""
    # 1. Pitch shift -1 semitone — deeper register without dropping
    #    a full tone (which would feel like a different track).
    out = _pitch_shift(source, semitones=-1.0)
    # 2. Tape saturation at higher drive than the parents (0.20 vs the
    #    cut tool's 0.14-0.18 range) — adds 2nd-harmonic richness, the
    #    "analog warmth" character. The bias asymmetry in ``_tape_-
    #    saturate`` produces real even-order content here.
    out = _tape_saturate(out, drive=0.20)
    # 3. Mid-low presence — gentle +2 dB bump around 400 Hz adds body
    #    weight where the parents emphasised 3.5 kHz presence. Uses
    #    the same band-pass-additive approach as the cut tool's
    #    mid_presence, just centred lower.
    out = _mid_presence(out, center_hz=400.0, gain_db=2.0)
    # 4. High-shelf cut at 3.5 kHz to roll back the parents' +3 dB
    #    boost — siblings lead with the mid-low warmth instead of
    #    the high-shelf brightness, completing the inverse tonal
    #    balance vs the parents.
    out = _high_shelf_cut(out, cutoff_hz=3500.0, gain_db=-1.5)
    # 5. Stereo widen 1.25× — between the parents' 1.45× (wide) and
    #    the cut tool's reflect-mood 1.30×. Reads as focused rather
    #    than wide, giving the sibling a more intimate stereo image
    #    while staying clearly stereo (not narrowed to near-mono).
    out = _stereo_widen(out, amount=1.25)
    # 6. Short reverb wash for sustain — 0.3 s decay at 18 % wet.
    #    Smaller than the spacious-variant 0.5 s / 22 % in the remix
    #    tool; the sibling's space is intimate, not enveloping.
    out = _reverb_tail(out, decay_s=0.3, mix=0.18)
    return out


def _master(stereo: np.ndarray) -> np.ndarray:
    """Standard master chain — same fingerprint as the parent tracks."""
    out = _high_pass_filter(stereo, cutoff_hz=60.0)
    out = _remove_dc(out)
    out = _bass_mono(out, cutoff_hz=200.0)
    out = _normalize_rms(out, target_rms=TARGET_RMS)
    out = _peak_limit_tanh(out, ceiling=0.95)
    out = _trim_to_zero_crossing(out, max_trim=400)
    out = _apply_fades(out, fade_in_s=0.5, fade_out_s=1.0)
    return _tpdf_dither(out, amplitude=1.0)


def main() -> None:
    if not PLAYING_DIR.is_dir():
        raise FileNotFoundError(f"Playing directory missing: {PLAYING_DIR}")
    # Find parent tracks: files in playing/ that don't already carry
    # the sibling suffix (so re-running is idempotent).
    parents = sorted(
        p for p in PLAYING_DIR.iterdir()
        if p.is_file()
        and p.suffix.lower() == ".wav"
        and not p.stem.endswith(f"_{SIBLING_SUFFIX}")
    )
    if not parents:
        print(f"No parent tracks found in {PLAYING_DIR}")
        return
    print(f"Source: {PLAYING_DIR.relative_to(REPO_ROOT)}")
    print(f"Parents: {len(parents)} tracks")
    print(f"Target RMS: {TARGET_RMS:.0f} (matches parents)")
    print(f"Sibling suffix: '_{SIBLING_SUFFIX}'")
    print()
    for parent in parents:
        audio = _read_wav(parent)
        parent_s = audio.shape[0] / SAMPLE_RATE
        sibling = _make_sibling(audio)
        sibling = _master(sibling)
        sibling_s = sibling.shape[0] / SAMPLE_RATE
        out_path = PLAYING_DIR / f"{parent.stem}_{SIBLING_SUFFIX}.wav"
        _write_wav(out_path, sibling)
        print(
            f"  {parent.name} ({parent_s:.0f}s) -> "
            f"{out_path.name} ({sibling_s:.0f}s)"
        )
    print()
    print("Done. Next: re-run tools/generate_playing_transitions.py to")
    print("create matching transition pads for the new siblings.")


if __name__ == "__main__":
    main()
