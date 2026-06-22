"""Generate transition pad WAVs that bridge between playing-stage tracks.

The 8 bundled playing tracks are 2–6 minute remixed pieces composed in
different keys, tempos, and textures — hard cuts between them feel
jarring even with the 150 ms within-playlist crossfade the AudioManager
applies. This tool extracts each track's *tail* (where the music is
naturally winding down through reverb decay), heavily processes it into
a spectrally-bridging pad, and saves the result to
``gaia_ultimatum/sounds/playlists/playing/transitions/``.

The AudioManager (``advance_track``) plays one pad between every two
regular tracks: regular → pad → regular → pad → … . Because the pad is
heavily low-passed (rolls off above ~3.5 kHz) and lengthened with extra
reverb, it sits perceptually "underneath" whatever two regular tracks
sandwich it — its spectrum overlaps both tails, so the listener hears a
continuous gradient instead of a tonal jump.

Run from the repo root::

    python tools/generate_playing_transitions.py

DSP chain (per source track):
  1. Take the last ``TAIL_S`` seconds.
  2. Apply mood-warm processing — low-pass 3.5 kHz, mild tape saturation.
  3. Add a long reverb tail (decay 1.2 s @ 38 % wet) — the bridge.
  4. Stereo widen modestly (1.15×) for spatial spread.
  5. RMS-normalize to ``TARGET_RMS`` (slightly below the regular tracks
     so the pad sits underneath, not on top).
  6. Soft-limit peaks; trim end to a zero crossing.
  7. Long fade-in (``FADE_IN_S``) and fade-out (``FADE_OUT_S``) — these
     are wide because the pad is meant to *blend*, not announce itself.
  8. TPDF dither, write as 16-bit stereo 44.1 kHz WAV.

Reuses the DSP primitives from ``cut_playlist_from_background.py`` so
the pads share the same spectral character as the rest of the playlist.
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
    _one_pole_lp,
    _peak_limit_tanh,
    _remove_dc,
    _reverb_tail,
    _stereo_widen,
    _tape_saturate,
    _tpdf_dither,
    _trim_to_zero_crossing,
    _write_wav,
)

PLAYING_DIR = SOUNDS_DIR / "playlists" / "playing"
TRANSITIONS_DIR = PLAYING_DIR / "transitions"

# Length of the source-track tail to lift as raw material. Long enough
# to contain real musical decay (drum hits, vocal tails, reverb wash)
# but short enough that the resulting pad reads as a *bridge* rather
# than a regular track.
TAIL_S = 15.0

# Fade-in / fade-out durations applied to the pad's own envelope.
# Wider than the AudioManager's 150 ms within-playlist crossfade so the
# pad's silent edges absorb whatever residual tail the previous track
# leaves behind. Asymmetric fade out > fade in because the listener
# perceives slow fade-outs as "natural decay" and slow fade-ins as
# "music is starting" — we want the pad to feel like the previous
# track's lingering wash, not the start of a new piece.
FADE_IN_S = 4.0
FADE_OUT_S = 6.0

# Target RMS for pads. Set ~12 % below the playing-playlist target
# (4600) so the pad sits perceptually *under* the surrounding tracks.
# A pad at equal RMS would compete with the regular tracks; at this
# level it reads as ambient bridge material, the same way the bed
# under a film cue sits below the dialogue.
TARGET_RMS = 4000.0


def _read_wav(path: Path) -> np.ndarray:
    """Read stereo 16-bit WAV as ``(N, 2)`` int16 numpy array."""
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


def _normalize_to_rms(stereo: np.ndarray, target: float) -> np.ndarray:
    """RMS-normalize with peak guard.

    Same idea as ``cut_playlist_from_background._normalize_rms`` but
    inlined to avoid importing — kept local so the pad pipeline doesn't
    depend on the regular track's RMS schedule.
    """
    f = stereo.astype(np.float32)
    rms = float(np.sqrt(np.mean(f * f)))
    if rms < 1.0:
        return stereo
    gain = target / rms
    peak = float(np.max(np.abs(f)))
    if peak > 0 and peak * gain > 32600.0:
        gain = 32600.0 / peak
    return np.clip(f * gain, -32768, 32767).astype(np.int16)


def _make_pad(
    source: np.ndarray, target_rms: float = TARGET_RMS,
) -> np.ndarray:
    """Apply the pad-DSP chain to a source-track tail.

    ``target_rms`` parameter added so the same chain can be reused for
    title/picker/outro playlists (each at its own baseline RMS) — see
    ``tools/generate_other_transitions.py`` which scans every non-playing
    playlist's mean track RMS and passes 87 % of it here.
    """
    n_target = int(TAIL_S * SAMPLE_RATE)
    if source.shape[0] <= n_target:
        # Source is shorter than the requested tail (unlikely for the
        # 2-6 min remixed tracks but defensive against future short
        # additions); take the whole thing.
        tail = source.copy()
    else:
        tail = source[-n_target:].copy()

    # 1. Low-pass at 3.5 kHz — strips brightness so two unrelated source
    #    tracks share spectral envelope through the bridge.
    out = _one_pole_lp(tail, cutoff_hz=3500.0)
    # 2. Tape saturation restores the body the LP removed.
    out = _tape_saturate(out, drive=0.10)
    # 3. Long reverb wash — the actual bridge mechanism. 1.2 s decay at
    #    38 % wet gives the pad an enveloping tail that smooths over
    #    the cut to the next track.
    out = _reverb_tail(out, decay_s=1.2, mix=0.38)
    # 4. Modest stereo widen for spatial spread (1.15×, below the 1.30×
    #    used on the regular tracks — pads stay narrower so they don't
    #    fight the surrounding wider tracks).
    out = _stereo_widen(out, amount=1.15)
    # 5. Standard mastering hygiene before the level stage.
    out = _high_pass_filter(out, cutoff_hz=60.0)
    out = _remove_dc(out)
    out = _bass_mono(out, cutoff_hz=200.0)
    # 6. RMS to the pad target (under the regular tracks' level).
    out = _normalize_to_rms(out, target_rms)
    out = _peak_limit_tanh(out, ceiling=0.95)
    out = _trim_to_zero_crossing(out, max_trim=400)
    # 7. Long blend envelopes — asymmetric, fade-out wider than fade-in
    #    so the pad reads as a previous-track tail extension rather than
    #    a new piece starting.
    out = _apply_fades(out, fade_in_s=FADE_IN_S, fade_out_s=FADE_OUT_S)
    # 8. TPDF dither last.
    out = _tpdf_dither(out, amplitude=1.0)
    return out


def main() -> None:
    if not PLAYING_DIR.is_dir():
        raise FileNotFoundError(
            f"Playing directory missing: {PLAYING_DIR}",
        )
    TRANSITIONS_DIR.mkdir(parents=True, exist_ok=True)
    sources = sorted(
        p for p in PLAYING_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".wav"
    )
    if not sources:
        print(f"No .wav files in {PLAYING_DIR}")
        return
    print(f"Source: {PLAYING_DIR.relative_to(REPO_ROOT)}")
    print(f"Target: {TRANSITIONS_DIR.relative_to(REPO_ROOT)}")
    print(f"Pad params: tail={TAIL_S:.0f}s, fade_in={FADE_IN_S:.0f}s, "
          f"fade_out={FADE_OUT_S:.0f}s, rms={TARGET_RMS:.0f}")
    print()
    for path in sources:
        audio = _read_wav(path)
        source_s = audio.shape[0] / SAMPLE_RATE
        pad = _make_pad(audio)
        pad_s = pad.shape[0] / SAMPLE_RATE
        # Output name encodes the source stem so a content browser can
        # see which source produced which pad without playing them.
        out_path = TRANSITIONS_DIR / f"pad_{path.stem}.wav"
        _write_wav(out_path, pad)
        print(f"  {path.name}: {source_s:.1f}s tail -> "
              f"{out_path.name} ({pad_s:.1f}s)")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
