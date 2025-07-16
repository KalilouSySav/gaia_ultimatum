# view.py

import pygame
from pygame.locals import *

class View:
    def __init__(self, game_state):
        self.game_state = game_state
        self.screen = pygame.display.set_mode((1200, 800))
        pygame.display.set_caption("Gaia Ultimatum")
        self.font = pygame.font.SysFont(None, 48)

    def draw_title_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Gaia Ultimatum", True, (0, 0, 0))
        self.screen.blit(title_text, (450, 100))
        # Add buttons for New Game, Continue, Options, Quit
        pygame.draw.rect(self.screen, (211, 211, 211), (450, 300, 300, 60), 2)
        pygame.draw.rect(self.screen, (211, 211, 211), (450, 400, 300, 60), 2)
        pygame.draw.rect(self.screen, (211, 211, 211), (450, 500, 300, 60), 2)
        pygame.draw.rect(self.screen, (211, 211, 211), (450, 600, 300, 60), 2)
        button_text = self.font.render("Nouvelle Partie", True, (0, 0, 0))
        self.screen.blit(button_text, (525, 315))
        button_text = self.font.render("Continuer", True, (0, 0, 0))
        self.screen.blit(button_text, (525, 415))
        button_text = self.font.render("Options", True, (0, 0, 0))
        self.screen.blit(button_text, (525, 515))
        button_text = self.font.render("Quitter", True, (0, 0, 0))
        self.screen.blit(button_text, (525, 615))

    def draw_new_game_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Nouvelle Partie", True, (0, 0, 0))
        self.screen.blit(title_text, (450, 50))
        subtitle_text = self.font.render("Choisissez une Catastrophe", True, (0, 0, 0))
        self.screen.blit(subtitle_text, (450, 130))
        # Add buttons for different catastrophes
        pygame.draw.rect(self.screen, (211, 211, 211), (150, 250, 150, 150), 2)
        pygame.draw.rect(self.screen, (211, 211, 211), (400, 250, 150, 150), 2)
        pygame.draw.rect(self.screen, (211, 211, 211), (650, 250, 150, 150), 2)
        pygame.draw.rect(self.screen, (211, 211, 211), (900, 250, 150, 150), 2)
        button_text = self.font.render("Eau", True, (0, 0, 0))
        self.screen.blit(button_text, (200, 375))
        button_text = self.font.render("Feu", True, (0, 0, 0))
        self.screen.blit(button_text, (450, 375))
        button_text = self.font.render("Air", True, (0, 0, 0))
        self.screen.blit(button_text, (700, 375))
        button_text = self.font.render("Terre", True, (0, 0, 0))
        self.screen.blit(button_text, (950, 375))
        # Add back button
        pygame.draw.rect(self.screen, (211, 211, 211), (50, 700, 200, 50), 2)
        button_text = self.font.render("Retour", True, (0, 0, 0))
        self.screen.blit(button_text, (100, 715))

    def draw_world_map_screen(self):
        self.screen.fill((211, 211, 211))
        pygame.draw.rect(self.screen, (173, 216, 230), (50, 50, 700, 500), 2)
        map_text = self.font.render("Carte du Monde", True, (0, 0, 0))
        self.screen.blit(map_text, (400, 300))
        # Add other elements like progress bar, evolution points, notifications, pause button

    def draw_upgrade_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Améliorations", True, (0, 0, 0))
        self.screen.blit(title_text, (550, 50))
        # Add other elements like catastrophe type, available points, branches, skills, back button

    def draw_country_info_screen(self):
        self.screen.fill((240, 240, 240))
        pygame.draw.rect(self.screen, (248, 248, 255), (100, 100, 400, 350), 3)
        title_text = self.font.render("Nom du Pays", True, (0, 0, 0))
        self.screen.blit(title_text, (300, 120))
        # Add other elements like demographic data, balance indicators, close button

    def draw_pause_menu(self):
        self.screen.fill((0, 0, 0, 0.8))
        pygame.draw.rect(self.screen, (211, 211, 211), (300, 150, 600, 500), 3)
        title_text = self.font.render("Pause", True, (255, 255, 255))
        self.screen.blit(title_text, (600, 200))
        # Add buttons for Resume, Options, Save, Load, Main Menu, Quit

    def draw_options_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Options", True, (0, 0, 0))
        self.screen.blit(title_text, (400, 100))
        # Add buttons for Graphics, Sound, Gameplay, Controls, Back

    def draw_graphics_options_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Options Graphismes", True, (0, 0, 0))
        self.screen.blit(title_text, (400, 100))
        # Add options for resolution, fullscreen, texture quality, visual effects, back button

    def draw_sound_options_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Options Son", True, (0, 0, 0))
        self.screen.blit(title_text, (400, 100))
        # Add options for volume, music, sound effects, ambient sound, back button

    def draw_gameplay_options_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Options Jouabilité", True, (0, 0, 0))
        self.screen.blit(title_text, (400, 100))
        # Add options for difficulty, game speed, tutorial, notifications, back button

    def draw_controls_options_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Options Commandes", True, (0, 0, 0))
        self.screen.blit(title_text, (400, 100))
        # Add options for actions and keys, back button

    def draw_load_game_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Charger une Partie", True, (0, 0, 0))
        self.screen.blit(title_text, (400, 100))
        # Add list of saved games, load button, back button

    def draw_save_game_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Sauvegarder la Partie", True, (0, 0, 0))
        self.screen.blit(title_text, (400, 100))
        # Add input field for save name, save button, cancel button

    def draw_catastrophe_victory_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Victoire !", True, (0, 0, 0))
        self.screen.blit(title_text, (550, 150))
        subtitle_text = self.font.render("La Catastrophe a Gagné", True, (0, 0, 0))
        self.screen.blit(subtitle_text, (550, 250))
        # Add summary text, statistics, replay button, main menu button

    def draw_humanity_victory_screen(self):
        self.screen.fill((240, 240, 240))
        title_text = self.font.render("Défaite !", True, (0, 0, 0))
        self.screen.blit(title_text, (550, 150))
        subtitle_text = self.font.render("L'Humanité a Triomphé", True, (0, 0, 0))
        self.screen.blit(subtitle_text, (550, 250))
        # Add summary text, statistics, retry button, main menu button

    def draw(self):
        if self.game_state.get_screen() == "title":
            self.draw_title_screen()
        elif self.game_state.get_screen() == "new_game":
            self.draw_new_game_screen()
        elif self.game_state.get_screen() == "world_map":
            self.draw_world_map_screen()
        elif self.game_state.get_screen() == "upgrade":
            self.draw_upgrade_screen()
        elif self.game_state.get_screen() == "country_info":
            self.draw_country_info_screen()
        elif self.game_state.get_screen() == "pause":
            self.draw_pause_menu()
        elif self.game_state.get_screen() == "options":
            self.draw_options_screen()
        elif self.game_state.get_screen() == "graphics_options":
            self.draw_graphics_options_screen()
        elif self.game_state.get_screen() == "sound_options":
            self.draw_sound_options_screen()
        elif self.game_state.get_screen() == "gameplay_options":
            self.draw_gameplay_options_screen()
        elif self.game_state.get_screen() == "controls_options":
            self.draw_controls_options_screen()
        elif self.game_state.get_screen() == "load_game":
            self.draw_load_game_screen()
        elif self.game_state.get_screen() == "save_game":
            self.draw_save_game_screen()
        elif self.game_state.get_screen() == "catastrophe_victory":
            self.draw_catastrophe_victory_screen()
        elif self.game_state.get_screen() == "humanity_victory":
            self.draw_humanity_victory_screen()

    def update(self):
        pygame.display.flip()
