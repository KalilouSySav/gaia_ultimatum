import pygame
import sys
import math
from config import *
from controller2 import options_screen, load_game_screen, detailed_map_screen, pause_menu, catastrophe_upgrades_screen

def main_menu_handle_events(screen, clock, buttons, new_game_menu, catastrophes):
    """Gère les événements du menu principal."""
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = event.pos
            for button in buttons:
                if button.rect.collidepoint(event.pos):
                    if button.action == "quit":
                        pygame.quit()
                        sys.exit()
                    elif button.action == "new_game":
                        new_game_menu(screen, clock, mouse_pos, catastrophes)
                    elif button.action == "continue":
                        load_game_screen()
                    elif button.action == "options":
                        options_screen()

def new_game_handle_events(back_button, element_buttons, main_menu, dashboard_menu, screen, clock, catastrophes):
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if event.type == pygame.MOUSEBUTTONDOWN:
            mouse_pos = event.pos
            if back_button.rect.collidepoint(mouse_pos):
                main_menu(screen, clock, mouse_pos, catastrophes)
            for button in element_buttons:
                if button.rect.collidepoint(mouse_pos):
                    button.selected = True
                    action = button.action
                    dashboard_menu(screen, action)
    return None

def dashboard_handle_events(pause_button, view_map_button, upgrade_skills_button, choix_catastrophe):
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if event.type == pygame.MOUSEBUTTONDOWN:
            if pause_button.rect.collidepoint(event.pos):
                pause_menu()
            elif view_map_button.collidepoint(event.pos):
                detailed_map_screen()
            elif upgrade_skills_button.rect.collidepoint(event.pos):
                catastrophe_upgrades_screen(choix_catastrophe)

def pause_menu_handle_events():
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if event.type == pygame.MOUSEBUTTONDOWN:
            for rect, text in button_rects:
                if rect.collidepoint(event.pos):
                    if text == "Reprendre":
                        return
                    elif text == "Sauvegarder":
                        save_game_screen()
                    elif text == "Charger":
                        load_game_screen()
                    elif text == "Options":
                        options_screen()
                    elif text == "Menu Principal":
                        main_menu()
                    elif text == "Quitter":
                        pygame.quit()
                        sys.exit()