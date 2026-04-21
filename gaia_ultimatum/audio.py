"""Audio playback manager.

Thin wrapper around ``pygame.mixer`` that loads/plays named effects and a
background music track. Safe to use in headless environments (all operations
degrade gracefully if the mixer fails to initialise).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pygame

from gaia_ultimatum.assets import SOUNDS_DIR
from gaia_ultimatum.config import AudioConfig

logger = logging.getLogger(__name__)


class AudioManager:
    """Loads and plays named sound effects plus a single music track."""

    def __init__(self, config: AudioConfig) -> None:
        self._config = config
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        self._music_loaded = False
        self._available = self._init_mixer()

    @staticmethod
    def _init_mixer() -> bool:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            return True
        except pygame.error as exc:
            logger.warning("Audio disabled: %s", exc)
            return False

    @property
    def available(self) -> bool:
        return self._available

    def load_sound(self, name: str, path: str | Path) -> None:
        if not self._available:
            return
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = SOUNDS_DIR / resolved
        if not resolved.is_file():
            logger.warning("Sound file not found: %s", resolved)
            return
        try:
            sound = pygame.mixer.Sound(str(resolved))
        except pygame.error as exc:
            logger.warning("Failed to load sound %s: %s", resolved, exc)
            return
        sound.set_volume(self._effective(self._config.effects_volume))
        self._sounds[name] = sound

    def play_sound(self, name: str) -> None:
        sound = self._sounds.get(name)
        if sound is not None:
            sound.play()

    def stop_sound(self, name: str) -> None:
        sound = self._sounds.get(name)
        if sound is not None:
            sound.stop()

    def load_music(self, path: str | Path) -> None:
        if not self._available:
            return
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = SOUNDS_DIR / resolved
        if not resolved.is_file():
            logger.warning("Music file not found: %s", resolved)
            return
        try:
            pygame.mixer.music.load(str(resolved))
            pygame.mixer.music.set_volume(self._effective(self._config.music_volume))
            self._music_loaded = True
        except pygame.error as exc:
            logger.warning("Failed to load music %s: %s", resolved, exc)

    def play_music(self, loops: int = -1) -> None:
        if self._available and self._music_loaded:
            pygame.mixer.music.play(loops)

    def stop_music(self) -> None:
        if self._available:
            pygame.mixer.music.stop()

    def _effective(self, volume: float) -> float:
        if self._config.muted:
            return 0.0
        return max(0.0, min(1.0, volume * self._config.master_volume))
