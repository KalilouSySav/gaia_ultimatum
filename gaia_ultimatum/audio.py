import pygame
from config1 import AudioConfig, load_config
from utils import load_sound
from typing import Dict

class AudioManager:
    def __init__(self):
        """
        Initialise le gestionnaire audio avec les paramètres de configuration.
        """
        self.config = load_config()
        self.audio_config = AudioConfig()
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self.music_playing = False

        # Initialisation de Pygame mixer
        pygame.mixer.init()
        self.set_volume(self.audio_config.VOLUME_GENERAL)
        self.set_music_volume(self.audio_config.VOLUME_MUSIQUE)
        self.set_effects_volume(self.audio_config.VOLUME_EFFETS_SONORES)
        self.set_ambiance_volume(self.audio_config.VOLUME_AMBIANCE)

    def set_volume(self, volume: float) -> None:
        """
        Définit le volume général.

        Args:
            volume (float): Le volume général (0.0 à 1.0).
        """
        pygame.mixer.music.set_volume(volume)
        for sound in self.sounds.values():
            sound.set_volume(volume)

    def set_music_volume(self, volume: float) -> None:
        """
        Définit le volume de la musique.

        Args:
            volume (float): Le volume de la musique (0.0 à 1.0).
        """
        pygame.mixer.music.set_volume(volume)

    def set_effects_volume(self, volume: float) -> None:
        """
        Définit le volume des effets sonores.

        Args:
            volume (float): Le volume des effets sonores (0.0 à 1.0).
        """
        for sound in self.sounds.values():
            sound.set_volume(volume)

    def set_ambiance_volume(self, volume: float) -> None:
        """
        Définit le volume de l'ambiance.

        Args:
            volume (float): Le volume de l'ambiance (0.0 à 1.0).
        """
        # Assuming ambiance is part of the general sounds
        for sound in self.sounds.values():
            sound.set_volume(volume)

    def load_sound(self, name: str, filepath: str) -> None:
        """
        Charge un son et l'ajoute au dictionnaire des sons.

        Args:
            name (str): Le nom du son.
            filepath (str): Le chemin vers le fichier son.
        """
        sound = load_sound(filepath)
        sound.set_volume(self.audio_config.VOLUME_EFFETS_SONORES)
        self.sounds[name] = sound

    def play_sound(self, name: str) -> None:
        """
        Joue un son.

        Args:
            name (str): Le nom du son à jouer.
        """
        if name in self.sounds:
            self.sounds[name].play()

    def stop_sound(self, name: str) -> None:
        """
        Arrête un son.

        Args:
            name (str): Le nom du son à arrêter.
        """
        if name in self.sounds:
            self.sounds[name].stop()

    def load_music(self, filepath: str) -> None:
        """
        Charge une musique.

        Args:
            filepath (str): Le chemin vers le fichier de musique.
        """
        pygame.mixer.music.load(filepath)
        pygame.mixer.music.set_volume(self.audio_config.VOLUME_MUSIQUE)

    def play_music(self) -> None:
        """
        Joue la musique chargée.
        """
        if not self.music_playing:
            pygame.mixer.music.play(-1)  # Loop indefinitely
            self.music_playing = True

    def stop_music(self) -> None:
        """
        Arrête la musique.
        """
        if self.music_playing:
            pygame.mixer.music.stop()
            self.music_playing = False

    def toggle_mute(self) -> None:
        """
        Active ou désactive le mode muet.
        """
        self.audio_config.MUTED = not self.audio_config.MUTED
        volume = 0.0 if self.audio_config.MUTED else self.audio_config.VOLUME_GENERAL
        self.set_volume(volume)
        self.set_music_volume(volume)
        self.set_effects_volume(volume)
        self.set_ambiance_volume(volume)

# Exemple d'utilisation
if __name__ == "__main__":
    # Initialisation de Pygame
    pygame.init()

    # Création de l'instance de AudioManager
    audio_manager = AudioManager()

    # Chargement et lecture d'un son
    audio_manager.load_sound("explosion", "data/sounds/explosion.wav")
    audio_manager.play_sound("explosion")

    # Chargement et lecture de la musique
    audio_manager.load_music("data/music/background.mp3")
    audio_manager.play_music()

    # Boucle principale pour garder le programme en cours d'exécution
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_m:
                    audio_manager.toggle_mute()

    # Arrêt de la musique et fermeture de Pygame
    audio_manager.stop_music()
    pygame.quit()
