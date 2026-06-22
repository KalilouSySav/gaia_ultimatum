"""Smoke tests for the audio layer (headless)."""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

from gaia_ultimatum.audio import (
    AudioManager,
    _loops_for,
    _ogg_duration_s,
    _track_duration_s,
    _wav_duration_s,
)
from gaia_ultimatum.config import AudioConfig


def test_audio_manager_initialises_gracefully() -> None:
    manager = AudioManager(AudioConfig())
    # Calls must be no-ops on bad paths rather than raising.
    manager.load_sound("missing", "no_such_file.wav")
    manager.play_sound("missing")
    manager.stop_sound("missing")
    manager.load_music("no_such_music.mp3")
    manager.play_music()
    manager.stop_music()


def test_effective_volume_respects_mute() -> None:
    manager = AudioManager(AudioConfig(muted=True))
    assert manager._effective(1.0) == 0.0
    manager = AudioManager(AudioConfig(master_volume=0.5))
    assert manager._effective(0.5) == 0.25


# ---------------------------------------------------------------------------
# Track duration parsing — load-bearing for the Android OGG path because
# ``_loops_for`` returns 0 (play-once) when duration is unknown, and the
# playing-bed's 90 s minimum playtime would silently fail to extend
# short tracks.
# ---------------------------------------------------------------------------


def _write_synthetic_wav(path: Path, duration_s: float, rate: int = 44100) -> None:
    n = int(duration_s * rate)
    samples = b"".join(
        struct.pack("<h", int(20000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(n)
    )
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples)


def _write_synthetic_ogg(
    path: Path, total_samples: int, rate: int, channels: int = 2,
) -> None:
    """Hand-craft a minimal OGG byte sequence carrying just enough
    structure for ``_ogg_duration_s`` to parse a rate and granule.

    NOT a valid OGG stream for playback — only the markers the parser
    looks for (``\\x01vorbis`` + sample rate at the canonical offset,
    final ``OggS`` page + granule position at offset 6). pygame would
    refuse to decode this, but the duration parser doesn't need that.
    """
    id_packet = (
        b"\x01vorbis"
        + (0).to_bytes(4, "little")        # vorbis_version
        + bytes([channels])                # audio_channels
        + rate.to_bytes(4, "little")       # audio_sample_rate
    )
    # Fake first page: 28 bytes of stub OGG page header + the ID packet.
    first_page = (
        b"OggS\x00\x02"
        + (0).to_bytes(8, "little")        # granule
        + b"\x00" * 13                     # serial + sequence + checksum + segs
        + bytes([len(id_packet)])
        + id_packet
    )
    # Final page: only the capture pattern + version + header_type +
    # granule position are read by the parser. Pad with 18 zero bytes so
    # the structure resembles a real page tail.
    last_page = (
        b"OggS\x00\x04"
        + total_samples.to_bytes(8, "little", signed=True)
        + b"\x00" * 18
    )
    # 4 KB of padding between forces the parser's backward scan to find
    # the *last* OggS, not the first — a regression guard.
    path.write_bytes(first_page + b"\x00" * 4096 + last_page)


def test_wav_duration_parses_correctly(tmp_path: Path) -> None:
    p = tmp_path / "tone.wav"
    _write_synthetic_wav(p, duration_s=2.5)
    assert _wav_duration_s(p) == 2.5
    # Dispatcher routes .wav to _wav_duration_s.
    assert _track_duration_s(p) == 2.5


def test_ogg_duration_parses_correctly(tmp_path: Path) -> None:
    p = tmp_path / "synth.ogg"
    _write_synthetic_ogg(p, total_samples=44100 * 5, rate=44100)
    assert _ogg_duration_s(p) == 5.0
    # Dispatcher routes .ogg to _ogg_duration_s.
    assert _track_duration_s(p) == 5.0


def test_ogg_duration_uses_last_page_granule(tmp_path: Path) -> None:
    """The granule reported must come from the LAST ``OggS`` page, not
    the first — Vorbis encodes the final cumulative sample count there,
    while the first page's granule is 0."""
    p = tmp_path / "synth2.ogg"
    _write_synthetic_ogg(p, total_samples=22050 * 12, rate=22050)
    assert _ogg_duration_s(p) == 12.0


def test_ogg_duration_returns_none_on_junk(tmp_path: Path) -> None:
    p = tmp_path / "fake.ogg"
    p.write_bytes(b"not an ogg file at all")
    assert _ogg_duration_s(p) is None


def test_ogg_duration_returns_none_on_missing(tmp_path: Path) -> None:
    assert _ogg_duration_s(tmp_path / "does_not_exist.ogg") is None


def test_track_duration_returns_none_for_unsupported_format(
    tmp_path: Path,
) -> None:
    """MP3 has no stdlib path; the dispatcher must return None so
    ``_loops_for`` falls through to play-once for that format."""
    p = tmp_path / "track.mp3"
    p.write_bytes(b"\xff\xfb\x90\x44any old mp3 header")
    assert _track_duration_s(p) is None


def test_loops_for_extends_short_ogg_to_playlist_minimum(
    tmp_path: Path,
) -> None:
    """A 30 s OGG track on the 90 s playing minimum should loop 2× extra
    (= 3 plays = 90 s). Regression for the Android OGG path: without
    OGG duration parsing, _loops_for returned 0 for every Vorbis track
    and the playing-bed never extended short material."""
    p = tmp_path / "short.ogg"
    _write_synthetic_ogg(p, total_samples=44100 * 30, rate=44100)
    assert _loops_for(p, "playing") == 2


def test_loops_for_does_not_extend_long_ogg(tmp_path: Path) -> None:
    """A 120 s track on the 90 s playing minimum needs no extension."""
    p = tmp_path / "long.ogg"
    _write_synthetic_ogg(p, total_samples=44100 * 120, rate=44100)
    assert _loops_for(p, "playing") == 0


def test_loops_for_caps_extension(tmp_path: Path) -> None:
    """Hard cap at 5 extra loops protects against a 1 s file pinning the
    player to one track for minutes."""
    p = tmp_path / "tiny.ogg"
    _write_synthetic_ogg(p, total_samples=44100, rate=44100)  # 1.0 s
    assert _loops_for(p, "playing") == 5
