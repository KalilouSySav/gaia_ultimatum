"""Smoke tests for the audio layer (headless)."""

from __future__ import annotations

from gaia_ultimatum.audio import AudioManager
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
