import unittest
import pygame

from ..audio import AudioManager

class TestAudioManager(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.audio_manager = AudioManager()

    def tearDown(self):
        pygame.quit()

    def test_play_sound(self):
        self.audio_manager.play_sound('click')
        self.assertTrue(pygame.mixer.get_busy())

    def test_stop_sound(self):
        self.audio_manager.play_sound('click')
        self.audio_manager.stop_sound('click')
        self.assertFalse(pygame.mixer.get_busy())

    def test_play_music(self):
        self.audio_manager.load_music('sounds/background.mp3')
        self.audio_manager.play_music()
        self.assertTrue(pygame.mixer.music.get_busy())

    def test_stop_music(self):
        self.audio_manager.load_music('sounds/background.mp3')
        self.audio_manager.play_music()
        self.audio_manager.stop_music()
        self.assertFalse(pygame.mixer.music.get_busy())

    def test_set_volume(self):
        self.audio_manager.set_volume(0.5)
        self.assertEqual(pygame.mixer.music.get_volume(), 0.5)

if __name__ == '__main__':
    unittest.main()
