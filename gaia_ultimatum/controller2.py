import pygame
import sys
import math
import pygame
from typing import List, Tuple
import random
import colorsys
from pygame import gfxdraw
import time as global_time
import json
import pyproj
from enum import Enum
from utils import load_competence
# Constantes pour l'ensemble du projet
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (20, 24, 32)
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (60, 66, 77)
BUTTON_HOVER_COLOR = (75, 83, 96)
ACCENT_COLOR = (92, 184, 92)
DISABLED_COLOR = (128, 128, 128)
PROGRESS_BAR_BG = (70, 77, 90)
PROGRESS_BAR_FILL = (92, 184, 92)
NOTIFICATION_BG = (50, 55, 64)
SLIDER_BG_COLOR = (45, 50, 60)
SLIDER_ACTIVE_COLOR = (92, 184, 92)
SLIDER_HANDLE_COLOR = (220, 220, 220)
INPUT_BG_COLOR = (30, 34, 42)
PLACEHOLDER_COLOR = (128, 128, 128)
GRID_COLOR = (40, 44, 52)
#Couleurs specifique des bouttons
BUTTON_BORDER_COLOR = (101, 111, 128)

# Couleurs spécifiques pour les catastrophes
CATASTROPHE_COLORS = {
    "Eau": (64, 164, 223),
    "Feu": (235, 83, 83),
    "Air": (188, 231, 253),
    "Terre": (141, 110, 99),
    "Vie": (92, 184, 92)
}

WATER_COLOR = (64, 164, 223)

# Couleurs pour les victoires
VICTORY_RED = (220, 20, 20)
DARK_RED = (120, 20, 20)
VICTORY_COLOR = (64, 209, 124)
GOLDEN_COLOR = (255, 215, 0)

# Couleurs pour les options
ACCENT_COLOR_2 = (72, 144, 192)

# Remplissage des sliders
SLIDER_FILL = (92, 184, 92)
SLIDER_BG = (45, 50, 60)

# Polices
pygame.font.init()
TITLE_FONT = pygame.font.Font(None, 72)
FONT = pygame.font.Font(None, 36)
SMALL_FONT = pygame.font.Font(None, 28)
DESCRIPTION_FONT = pygame.font.Font(None, 24)
ICON_FONT = pygame.font.Font(None, 36)


# Dimensions de la fenêtre
largeur, hauteur = 1200, 600
fenetre = pygame.display.set_mode((largeur, hauteur))

# Couleurs
BLANC = (255, 255, 255)
NOIR = (0, 0, 0)
VERT = (0, 255, 0)
BLEU = (173, 216, 230)
ROUGE = (255, 0, 0)


# Initialisation de Pygame
pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Gaia Ultimatum")

def draw_text(surface, text, font, color, x, y, align="center"):
    """Dessine un texte sur une surface avec une option d'alignement."""
    text_obj = font.render(text, True, color)
    text_rect = text_obj.get_rect()
    if align == "center":
        text_rect.centerx = x
        text_rect.centery = y
    elif align == "left":
        text_rect.left = x
        text_rect.centery = y
    surface.blit(text_obj, text_rect)

def draw_rounded_rect(surface, color, rect, radius):
    """Dessine un rectangle arrondi sur une surface."""
    x, y, width, height = rect
    gfxdraw.aacircle(surface, x + radius, y + radius, radius, color)
    gfxdraw.aacircle(surface, x + width - radius - 1, y + radius, radius, color)
    gfxdraw.aacircle(surface, x + radius, y + height - radius - 1, radius, color)
    gfxdraw.aacircle(surface, x + width - radius - 1, y + height - radius - 1, radius, color)
    gfxdraw.filled_circle(surface, x + radius, y + radius, radius, color)
    gfxdraw.filled_circle(surface, x + width - radius - 1, y + radius, radius, color)
    gfxdraw.filled_circle(surface, x + radius, y + height - radius - 1, radius, color)
    gfxdraw.filled_circle(surface, x + width - radius - 1, y + height - radius - 1, radius, color)
    pygame.draw.rect(surface, color, (x + radius, y, width - 2 * radius, height))
    pygame.draw.rect(surface, color, (x, y + radius, width, height - 2 * radius))

def draw_button(surface, rect, color, border_color, text, font, text_color, hover=False):
    """Dessine un bouton avec un effet de survol."""
    x, y, width, height = rect
    mouse_pos = pygame.mouse.get_pos()
    if rect.collidepoint(mouse_pos):
        color = BUTTON_HOVER_COLOR if hover else color
    draw_rounded_rect(surface, border_color, rect, 10)
    draw_rounded_rect(surface, color, (x + 2, y + 2, width - 4, height - 4), 8)
    text_surf = font.render(text, True, text_color)
    text_rect = text_surf.get_rect(center=(x + width // 2, y + height // 2))
    surface.blit(text_surf, text_rect)

def draw_button_world_map(x, y, width, height, color, border_color, text, font, text_color, surface, hover=False):
    button_rect = pygame.Rect(x, y, width, height)
    mouse_pos = pygame.mouse.get_pos()

    if button_rect.collidepoint(mouse_pos):
        color = BUTTON_HOVER_COLOR if hover else color

    draw_rounded_rect(surface, border_color, (x, y, width, height), 10)
    draw_rounded_rect(surface, color, (x + 2, y + 2, width - 4, height - 4), 8)

    text_surf = font.render(text, True, text_color)
    text_rect = text_surf.get_rect(center=(x + width//2, y + height//2))
    surface.blit(text_surf, text_rect)

    return button_rect

def draw_progress_bar(surface, x, y, width, height, progress, max_value, bar_color=PROGRESS_BAR_FILL):
    """Dessine une barre de progression avec un effet arrondi."""
    draw_rounded_rect(surface, PROGRESS_BAR_BG, (x, y, width, height), 5)
    progress_width = int((progress / max_value) * (width - 4))
    if progress_width > 0:
        draw_rounded_rect(surface, bar_color, (x + 2, y + 2, progress_width, height - 4), 4)
    percentage = f"{int(progress / max_value * 100)}%"
    draw_text(surface, percentage, SMALL_FONT, TEXT_COLOR, x + width // 2, y + height // 2)

class ParticleSystem:
    """Système de particules pour des effets visuels."""
    def __init__(self):
        self.particles = []
        self.emitters = [(SCREEN_WIDTH // 4, 0), (SCREEN_WIDTH // 2, 0), (3 * SCREEN_WIDTH // 4, 0)]
        for _ in range(150):
            emitter = random.choice(self.emitters)
            self.particles.append({
                'x': emitter[0] + random.randint(-100, 100),
                'y': random.randint(0, SCREEN_HEIGHT),
                'size': random.uniform(0.5, 3),
                'speed': random.uniform(0.5, 2),
                'angle': random.uniform(0, math.pi * 2),
                'color': random.choice([ACCENT_COLOR, VICTORY_COLOR]),
                'alpha': random.randint(50, 150)
            })

    def update(self, time):
        for p in self.particles:
            p['y'] += math.sin(time * 0.001 + p['angle']) * 0.5 + p['speed']
            p['x'] += math.cos(time * 0.001 + p['angle']) * 0.5
            p['alpha'] = int(100 + math.sin(time * 0.002 + p['y'] * 0.1) * 50)
            if p['y'] > SCREEN_HEIGHT:
                emitter = random.choice(self.emitters)
                p['y'] = 0
                p['x'] = emitter[0] + random.randint(-100, 100)

    def draw(self, surface):
        for p in self.particles:
            gfxdraw.filled_circle(surface, int(p['x']), int(p['y']), int(p['size']), (*p['color'], p['alpha']))

class MenuButton:
    """Bouton de menu avec effets de survol et de clic."""
    def __init__(self, x, y, width, height, text, action):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.action = action
        self.hover = 0
        self.animation = 0
        self.shake_offset = [0, 0]

    def update_shake(self, time):
        if self.hover > 0.5:
            intensity = 0.5 * self.hover
            self.shake_offset = [math.sin(time * 0.1) * intensity, math.cos(time * 0.1) * intensity]
        else:
            self.shake_offset = [0, 0]

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)
        self.update_shake(time)

        # Appliquer l'effet de tremblement
        rect = self.rect.copy()
        rect.x += self.shake_offset[0]
        rect.y += self.shake_offset[1]

        # Effet de pulsation
        pulse = math.sin(time * 0.003) * 4

        # Couleur dynamique pour l'effet de survol
        hue = (math.sin(time * 0.001) * 0.05 + 0.6) % 1.0
        dynamic_color = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.6, 0.8))

        # Effet de lueur
        glow_radius = 15 + pulse * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_rect = rect.inflate(i * 2, i * 2)
            glow_color = (*dynamic_color, alpha) if hover else (*BUTTON_COLOR, alpha)
            pygame.draw.rect(surface, glow_color, glow_rect, border_radius=15)

        # Bouton principal avec couleur de survol
        color = [int(c1 + (c2 - c1) * self.hover) for c1, c2 in zip(BUTTON_COLOR, BUTTON_HOVER_COLOR)]
        pygame.draw.rect(surface, color, rect, border_radius=15)

        # Bordure animée
        border_color = dynamic_color if hover else ACCENT_COLOR
        pygame.draw.rect(surface, border_color, rect, 2, border_radius=15)

        # Texte avec effets d'ombre et de lueur
        font = pygame.font.Font(None, 36)
        shadow_offset = 2
        shadow_surf = font.render(self.text, True, (0, 0, 0))
        shadow_rect = shadow_surf.get_rect(center=(rect.centerx + shadow_offset, rect.centery + shadow_offset))
        surface.blit(shadow_surf, shadow_rect)

        if hover:
            for offset in range(3):
                glow_surf = font.render(self.text, True, dynamic_color)
                glow_surf.set_alpha(100 - offset * 30)
                glow_rect = glow_surf.get_rect(center=(rect.centerx + math.sin(time * 0.01) * 2,
                                                       rect.centery + math.cos(time * 0.01) * 2))
                surface.blit(glow_surf, glow_rect)

        text_surf = font.render(self.text, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=rect.center)
        surface.blit(text_surf, text_rect)

def draw_title(surface, time):
    """Dessine le titre principal avec des effets d'animation."""
    title = "GAIA ULTIMATUM"
    font = pygame.font.Font(None, 92)
    wave_height = 12
    wave_length = 0.1
    wave_speed = 0.005
    glow_intensity = int(128 + math.sin(time * 0.01) * 64)

    total_width = sum(font.size(char)[0] for char in title)
    start_x = SCREEN_WIDTH // 2 - total_width // 2
    current_x = start_x

    for i, char in enumerate(title):
        offset_y = math.sin(time * wave_speed + i * wave_length) * wave_height
        offset_x = math.cos(time * wave_speed * 0.5 + i * wave_length) * 3

        char_surf = font.render(char, True, TEXT_COLOR)
        char_width = font.size(char)[0]
        x = current_x + offset_x
        y = 150 + offset_y

        for glow_offset in range(3):
            glow_surf = font.render(char, True, ACCENT_COLOR)
            glow_surf.set_alpha(glow_intensity - glow_offset * 40)
            surface.blit(glow_surf, (x + glow_offset, y + glow_offset))
            surface.blit(glow_surf, (x - glow_offset, y - glow_offset))

        surface.blit(char_surf, (x, y))
        current_x += char_width

def draw_background_effect(surface, time):
    """Dessine un effet de grille en perspective en arrière-plan."""
    num_lines = 20
    for i in range(num_lines):
        progress = (time * 0.001 + i) % num_lines / num_lines
        y = SCREEN_HEIGHT * progress
        alpha = int(255 * (1 - progress))

        start_pos = (0, y)
        end_pos = (SCREEN_WIDTH, y)
        pygame.draw.line(surface, (*ACCENT_COLOR, alpha // 4), start_pos, end_pos)

        for x in range(0, SCREEN_WIDTH, 100):
            vanishing_point = SCREEN_HEIGHT // 2
            start_y = y
            end_y = vanishing_point + (y - vanishing_point) * 1.2
            pygame.draw.line(surface, (*ACCENT_COLOR, alpha // 4), (x, start_y), (x, end_y))

def main_menu():
    """Fonction principale pour afficher le menu principal du jeu."""
    clock = pygame.time.Clock()
    particle_system = ParticleSystem()

    button_width = 300
    button_spacing = 80
    start_y = 300
    buttons = [
        MenuButton(SCREEN_WIDTH // 2 - button_width // 2, start_y, button_width, 60, "Nouvelle Partie", "new_game"),
        MenuButton(SCREEN_WIDTH // 2 - button_width // 2, start_y + button_spacing, button_width, 60, "Continuer", "continue"),
        MenuButton(SCREEN_WIDTH // 2 - button_width // 2, start_y + button_spacing * 2, button_width, 60, "Options", "options"),
        MenuButton(SCREEN_WIDTH // 2 - button_width // 2, start_y + button_spacing * 3, button_width, 60, "Quitter", "quit")
    ]

    time = 0
    while True:
        time += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                for button in buttons:
                    if button.rect.collidepoint(event.pos):
                        if button.action == "quit":
                            pygame.quit()
                            sys.exit()
                        elif button.action == "new_game":
                            new_game_menu()  # Appel de la fonction pour le menu de nouvelle partie
                        elif button.action == "continue":
                            load_game_screen()
                            print("Continuer")
                        elif button.action == "options":
                            options_screen()
                            print("Options")

        particle_system.update(time)
        screen.fill(BACKGROUND_COLOR)
        draw_background_effect(screen, time)
        particle_system.draw(screen)
        draw_title(screen, time)

        font_small = pygame.font.Font(None, 28)
        subtitle = "L'avenir de la Terre est entre vos mains"
        alpha = int(128 + math.sin(time * 0.005) * 64)
        subtitle_surf = font_small.render(subtitle, True, TEXT_COLOR)
        subtitle_surf.set_alpha(alpha)
        subtitle_rect = subtitle_surf.get_rect(center=(SCREEN_WIDTH // 2, 240))
        screen.blit(subtitle_surf, subtitle_rect)

        for button in buttons:
            button.draw(screen, time)

        version_text = "v1.0.0"
        version_alpha = int(128 + math.sin(time * 0.01) * 64)
        version_surf = font_small.render(version_text, True, ACCENT_COLOR)
        version_surf.set_alpha(version_alpha)
        screen.blit(version_surf, (20, SCREEN_HEIGHT - 30))

        pygame.display.flip()
        clock.tick(60)

class ElementButton:
    """Bouton pour la sélection d'un élément dans le menu de nouvelle partie."""
    def __init__(self, x, y, width, height, color, hover_color, text, description):
        self.rect = pygame.Rect(x, y, width, height)
        self.color = color
        self.hover_color = hover_color
        self.text = text
        self.description = description
        self.animation = 0
        self.selected = False

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)
        pulse = math.sin(time * 0.005) * 4

        if hover:
            self.animation = min(1, self.animation + 0.1)
        else:
            self.animation = max(0, self.animation - 0.1)

        current_color = tuple(int(c1 + (c2 - c1) * self.animation) for c1, c2 in zip(self.color, self.hover_color))
        glow_radius = 10 + pulse
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_color = (*current_color, alpha)
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, glow_color, glow_rect, border_radius=15)

        pygame.draw.rect(surface, current_color, self.rect, border_radius=15)
        pygame.draw.rect(surface, (*current_color, 150), self.rect, 3, border_radius=15)

        text_surf = FONT.render(self.text, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

        if hover:
            desc_surf = DESCRIPTION_FONT.render(self.description, True, TEXT_COLOR)
            desc_rect = desc_surf.get_rect(midtop=(self.rect.centerx, self.rect.bottom + 10))
            surface.blit(desc_surf, desc_rect)

def draw_background_particles(surface, time):
    """Dessine des particules en arrière-plan pour un effet visuel."""
    particles = []
    for i in range(50):
        x = (time * (i % 5 + 1) * 0.5 + i * 50) % SCREEN_WIDTH
        y = (math.sin(time * 0.001 + i) * 50 + i * 20) % SCREEN_HEIGHT
        particles.append((x, y))

    for x, y in particles:
        size = (math.sin(time * 0.003 + x * 0.1) + 2) * 2
        alpha = int(128 + math.sin(time * 0.002 + y * 0.1) * 64)
    gfxdraw.filled_circle(surface, int(x), int(y), int(size), (*BUTTON_COLOR, alpha))

def new_game_menu():
    """Menu de sélection de la catastrophe pour une nouvelle partie."""
    clock = pygame.time.Clock()
    time = 0

    element_buttons = [
        ElementButton(150, 250, 150, 150, CATASTROPHE_COLORS["Eau"], (*CATASTROPHE_COLORS["Eau"], 150), "Eau",
                      "Inondations et montée des eaux"),
        ElementButton(400, 250, 150, 150, CATASTROPHE_COLORS["Feu"], (*CATASTROPHE_COLORS["Feu"], 150), "Feu",
                      "Incendies et réchauffement global"),
        ElementButton(650, 250, 150, 150, CATASTROPHE_COLORS["Air"], (*CATASTROPHE_COLORS["Air"], 150), "Air",
                      "Tempêtes et catastrophes"),
        ElementButton(900, 250, 150, 150, CATASTROPHE_COLORS["Terre"], (*CATASTROPHE_COLORS["Terre"], 150), "Terre",
                      "Séismes et volcans"),
        ElementButton(525, 480, 150, 150, CATASTROPHE_COLORS["Vie"], (*CATASTROPHE_COLORS["Vie"], 150), "Vie",
                      "Pandémies et mutations")
    ]

    back_button = pygame.Rect(50, 700, 200, 50)

    while True:
        time += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = event.pos
                if back_button.collidepoint(mouse_pos):
                    return "main_menu"
                for button in element_buttons:
                    if button.rect.collidepoint(mouse_pos):
                        button.selected = True
                        # Logique pour démarrer le jeu avec l'élément sélectionné
                        if button.text == "Eau":
                            world_map_screen("Eau")
                        elif button.text == "Feu":
                            world_map_screen("Feu")
                        elif button.text == "Air":
                            world_map_screen("Air")
                        elif button.text == "Terre":
                            world_map_screen("Terre")
                        elif button.text == "Vie":
                            world_map_screen("Vie")


        screen.fill(BACKGROUND_COLOR)
        draw_background_particles(screen, time)

        for offset in range(2):
            color = (0, 0, 0) if offset == 0 else TEXT_COLOR
            pos_offset = offset * 2
            draw_text(screen, "Nouvelle Partie", TITLE_FONT, color, SCREEN_WIDTH / 2 + pos_offset, 100 + pos_offset)
            draw_text(screen, "Choisissez une Catastrophe", FONT, color, SCREEN_WIDTH / 2 + pos_offset, 180 + pos_offset)

        for button in element_buttons:
            button.draw(screen, time)

        pygame.draw.rect(screen, BUTTON_COLOR, back_button, border_radius=10)
        pygame.draw.rect(screen, BUTTON_BORDER_COLOR, back_button, 2, border_radius=10)
        draw_text(screen, "Retour", FONT, TEXT_COLOR, 150, 725)

        pygame.display.flip()
        clock.tick(60)

def draw_notification_panel(surface, x, y, width, height, notifications):
    """Dessine un panneau de notifications avec les dernières notifications."""
    draw_rounded_rect(surface, NOTIFICATION_BG, (x, y, width, height), 10)
    draw_text(surface, "Notifications", FONT, TEXT_COLOR, x + width // 2, y + 25)
    for i, notification in enumerate(notifications[-3:]):
        draw_text(surface, notification, SMALL_FONT, TEXT_COLOR, x + 10, y + 60 + i * 30, "left")

def draw_world_map(surface):
    """Dessine une carte du monde stylisée avec une grille."""
    cells = 20
    cell_width = 600 // cells
    cell_height = 400 // cells
    start_x = 100
    start_y = 150

    for i in range(cells):
        for j in range(cells):
            x = start_x + i * cell_width
            y = start_y + j * cell_height
            color = (60 + (i + j) % 3 * 10, 66 + (i + j) % 3 * 10, 77 + (i + j) % 3 * 10)
            pygame.draw.rect(surface, color, (x, y, cell_width - 1, cell_height - 1))

import pygame
import math
import sys
from pygame import gfxdraw

# ... (Code précédent pour les constantes, classes, fonctions, etc.)

def world_map_screen(choix_catastrophe):
    """Écran de la carte du monde avec les informations et les actions possibles."""
    notifications = ["Nouvelle technologie découverte!", "Population: 1M habitants", "Ressources: Stables"]
    evolution_points = 10
    humanity_progress = 50

    # Charger l'image de la carte du monde
    world_map_image = pygame.image.load("data/images/world_map.png")
    world_map_image = pygame.transform.scale(world_map_image, (600, 400))  # Ajuster la taille si nécessaire
    world_map_rect = world_map_image.get_rect(topleft=(100, 150))

    # Bouton "Voir la carte"
    view_map_button = pygame.Rect(100, 560, 200, 50)  # Ajuster la position en bas de l'image

    # Bouton "Améliorer compétence"
    improve_skills_button = pygame.Rect(400, 560, 250, 50)  # Ajuster la position en bas de l'image

    pause_button_rect = pygame.Rect(1000, 700, 150, 50)


    clock = pygame.time.Clock()

    while True:
        screen.fill(BACKGROUND_COLOR)

        # Titre
        draw_text(screen, "Carte du Monde", TITLE_FONT, TEXT_COLOR, SCREEN_WIDTH // 2, 50)

        # Afficher l'image de la carte du monde
        screen.blit(world_map_image, world_map_rect)

        # Barre de progression de l'humanité
        draw_progress_bar(screen, 850, 100, 300, 30, humanity_progress, 100)
        draw_text(screen, "Progrès de l'Humanité", SMALL_FONT, TEXT_COLOR, 1000, 80)

        # Points d'évolution
        draw_text(screen, f"Points d'Évolution : {evolution_points}", FONT, TEXT_COLOR, 900, 180)

        # Panel de notifications
        draw_notification_panel(screen, 850, 220, 300, 150, notifications)

        # Bouton Menu Pause
        pause_button = draw_button_world_map(1000, 560, 150, 50, BUTTON_COLOR, BUTTON_BORDER_COLOR, "Pause", FONT, TEXT_COLOR, screen, hover=True)

        # Bouton "Voir la carte"
        draw_button_world_map(100, 560, 200, 50, BUTTON_COLOR, BUTTON_BORDER_COLOR, "Voir la carte", FONT, TEXT_COLOR, screen, hover=True)

        # Bouton "Améliorer compétence"
        draw_button_world_map(400, 560, 250, 50, BUTTON_COLOR, BUTTON_BORDER_COLOR, "Améliorer Compétence", FONT, TEXT_COLOR, screen, hover=True)

        pygame.display.flip()
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if pause_button.collidepoint(event.pos):
                    pause_menu()
                elif view_map_button.collidepoint(event.pos):
                    detailed_map_screen()
                elif improve_skills_button.collidepoint(event.pos):
                    catastrophe_upgrades_screen(choix_catastrophe)
def pause_menu():
    """Menu de pause avec options de reprise, sauvegarde, chargement, etc."""
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))

    buttons = [
        ("Reprendre", 120),
        ("Options", 180),
        ("Sauvegarder", 240),
        ("Charger", 300),
        ("Menu Principal", 360),
        ("Quitter", 420)
    ]

    while True:
        screen.blit(overlay, (0, 0))
        draw_text(screen, "Pause", TITLE_FONT, TEXT_COLOR, SCREEN_WIDTH // 2, 80)

        button_rects = []
        for text, y in buttons:
            button_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, y, 200, 40)
            draw_button_world_map(button_rect.x, button_rect.y, button_rect.width, button_rect.height, BUTTON_COLOR, BUTTON_BORDER_COLOR, text, FONT, TEXT_COLOR, screen, hover=True)
            button_rects.append((button_rect, text))

        pygame.display.flip()

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


# Charger les données GeoJSON
with open("data/zones.geo.json", "r", encoding="utf-8") as f:
    donnees_geojson = json.load(f)

# Dictionnaire pour associer les pays à leurs polygones et à leurs informations supplémentaires
pays_polygones = {}

# Définir les projections
projection_entree = pyproj.CRS("EPSG:4326")
projection_sortie = pyproj.CRS("EPSG:3857")
transformer = pyproj.Transformer.from_crs(projection_entree, projection_sortie, always_xy=True)

# Fonction pour projeter et adapter les coordonnées
def projeter_et_adapter(coordonnees, largeur, hauteur):
    points_proj = []
    for coordonnee in coordonnees:
        if isinstance(coordonnee[0], list):
            for sous_coord in coordonnee:
                x_proj, y_proj = transformer.transform(sous_coord[0], sous_coord[1])
                x = (x_proj + 20000000) * largeur / 40000000
                y = hauteur - (y_proj + 20000000) * hauteur / 40000000
                points_proj.append((x, y))
        else:
            x_proj, y_proj = transformer.transform(coordonnee[0], coordonnee[1])
            x = (x_proj + 20000000) * largeur / 40000000
            y = hauteur - (y_proj + 20000000) * hauteur / 40000000
            points_proj.append((x, y))
    return points_proj

# Remplir le dictionnaire avec les polygones projetés des pays et d'autres informations
for feature in donnees_geojson["features"]:
    if feature["geometry"]["type"] == "Polygon":
        pays_nom = feature["properties"]["name"]
        polygone_proj = projeter_et_adapter(feature["geometry"]["coordinates"], largeur, hauteur)

        informations = {
            "nom": pays_nom,
            "personnes_affectees": "Non renseigné",  # Champ supplémentaire
            "personnes_mortes": "Non renseigné",  # Champ supplémentaire
            "population": feature["properties"].get("pop_est", "Non renseignée"),
            "indicateur_technologique": "Non renseigné",  # Champ supplémentaire
            "indicateur_evolutif": "Non renseigné",  # Champ supplémentaire
            "indicateur_ecologique": "Non renseigné",  # Champ supplémentaire
            "indicateur_societal": "Non renseigné",  # Champ supplémentaire
            "polygone": polygone_proj,
        }

        pays_polygones[pays_nom] = informations
    elif feature["geometry"]["type"] == "MultiPolygon":
        pays_nom = feature["properties"]["name"]
        polygones_proj = []
        for polygone in feature["geometry"]["coordinates"]:
            polygones_proj.append(projeter_et_adapter(polygone, largeur, hauteur))

        informations = {
            "nom": pays_nom,
            "personnes_affectees": "Non renseigné",  # Champ supplémentaire
            "personnes_mortes": "Non renseigné",  # Champ supplémentaire
            "population": feature["properties"].get("pop_est", "Non renseignée"),
            "indicateur_technologique": "Non renseigné",  # Champ supplémentaire
            "indicateur_evolutif": "Non renseigné",  # Champ supplémentaire
            "indicateur_ecologique": "Non renseigné",  # Champ supplémentaire
            "indicateur_societal": "Non renseigné",  # Champ supplémentaire
            "polygones": polygones_proj,
        }

        pays_polygones[pays_nom] = informations

# Fonction pour vérifier si un clic est à l'intérieur d'un polygone
def est_dans_polygone(clique, polygone):
    x, y = clique
    n = len(polygone)
    inside = False
    p1x, p1y = polygone[0]
    for i in range(n + 1):
        p2x, p2y = polygone[i % n]
        if y > min(p1y, p2y):
            if y <= max(p1y, p2y):
                if x <= max(p1x, p2x):
                    if p1y != p2y:
                        xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                    if p1x == p2x or x <= xinters:
                        inside = not inside
        p1x, p1y = p2x, p2y
    return inside

# Fonction pour vérifier si le clic est dans la zone du bouton "X"
def est_dans_bouton_fermeture(clic):
    x, y = clic
    return 450 <= x <= 475 and 55 <= y <= 80  # Placer le bouton "X" dans un rectangle

# Définir la fonction de formatage de texte pour l'info contextuelle
def formater_texte(cle, valeur):
    # retirer les underscores et mettre en majuscule la première lettre
    cle = cle.replace("_", " ").capitalize()
    # Mettre le PIB en majuscules
    if cle == "Pib":
        cle = "PIB"
    # groupe de 3 chiffres avec des espaces pour les grandes valeurs
    if cle == "Population":
        valeur = "{:,}".format(valeur)  # Formater la population avec des espaces
    # Ajouter les symboles de devise pour le PIB
    if cle == "PIB":
        valeur = str(valeur) + " $"

    return f"{cle}: {valeur}"

def detailed_map_screen():
    """Écran de la carte détaillée avec informations et actions spécifiques."""
    clock = pygame.time.Clock()
    time = 0

    info_contextuelle = None  # Pour afficher l'info contextuelle
    close_button_rect = None  # Rectangle du bouton de fermeture
    encours = True
    while encours:
        time += 1
        screen.fill(BACKGROUND_COLOR)

        for evenement in pygame.event.get():
            if evenement.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if evenement.type == pygame.KEYDOWN:
                if evenement.key == pygame.K_ESCAPE:
                    encours = False
            elif evenement.type == pygame.MOUSEBUTTONDOWN and encours:
                souris_x, souris_y = pygame.mouse.get_pos()

                if 30 <= souris_x <= 150 and 30 <= souris_y <= 80:
                    encours= False

                if info_contextuelle:
                    if close_button_rect.collidepoint(souris_x, souris_y):
                        info_contextuelle = None  # Fermer la fenêtre contextuelle en cliquant sur "X"
                    elif not pygame.Rect(window_x, window_y, window_width, window_height).collidepoint(souris_x, souris_y):
                        info_contextuelle = None  # Fermer la fenêtre contextuelle si clic en dehors de la fenêtre

                # Vérifier quel pays a été cliqué
                for pays, info in pays_polygones.items():
                    polygones = info.get("polygones", [info.get("polygone")])
                    for polygone in polygones:
                        if est_dans_polygone((souris_x, souris_y), polygone):
                            info_contextuelle = info  # Afficher l'info contextuelle du pays cliqué
                            # Calculer la position de la fenêtre d'information
                            window_x = souris_x + 20
                            window_y = souris_y + 20
                            # Ajuster la position si la fenêtre sort de l'écran
                            if window_x + 700 > SCREEN_WIDTH:
                                window_x = SCREEN_WIDTH - 700
                            if window_y + 700 > SCREEN_HEIGHT:
                                window_y = SCREEN_HEIGHT - 700
                            close_button_rect = pygame.Rect(window_x + 400 + window_x // 4, window_y + 10, 30, 30)
                            break

        # Dessiner chaque polygone projeté
        for pays, info in pays_polygones.items():
            polygones = info.get("polygones", [info.get("polygone")])
            for polygone in polygones:
                pygame.draw.polygon(fenetre, BLEU, polygone)
                pygame.draw.polygon(fenetre, NOIR, polygone, 2)

        # Dessiner bouton retour

        pygame.draw.rect(fenetre, BLEU, (30, 30, 120, 50), border_radius=15)
        draw_text(fenetre, "Retour", FONT, BLANC, 87, 58)
        # Animer le bouton de retour
        pulse = math.sin(time * 0.1) * 2
        pygame.draw.rect(fenetre, (0, 0, 0), (30 - pulse, 30 - pulse, 120 + pulse * 2, 50 + pulse * 2), 2, border_radius=15)

        # hover effect
        mouse_pos = pygame.mouse.get_pos()
        if 30 <= mouse_pos[0] <= 150 and 30 <= mouse_pos[1] <= 80:
            pygame.draw.rect(fenetre, (0, 0, 0), (30, 30, 120, 50), 2, border_radius=15)

        # Si une fenêtre contextuelle est ouverte, afficher les informations
        if info_contextuelle:
            # Copie du code de dessin de country_info_window, mais sur la position calculée
            window_width = 600
            window_height = 500
            # Couleurs
            background_color = (248, 248, 248)
            border_color = (70, 130, 180)
            text_color = (50, 50, 50)
            indicator_text_color = (70, 130, 180)

            # Données du pays (remplacer par les données réelles du pays sélectionné)
            demo_data = [
                ("Population", info.get("population")),
                ("Personnes affectées", 1280000),  # Exemple de données
                ("Morts", 22000),  # Exemple de données
            ]

            indicators = [
                ("Résilience Technologique", 20),
                ("Stabilité Sociétale", 33),
                ("Régénération Écologique", 70),
                ("Adaptation Évolution", 50)
            ]
            # Dessiner le fond de la fenêtre
            pygame.draw.rect(screen, background_color, (window_x, window_y, window_width, window_height), border_radius=15)
            pygame.draw.rect(screen, border_color, (window_x, window_y, window_width, window_height), 2, border_radius=15)

            # En-tête
            pygame.draw.rect(screen, border_color, (window_x, window_y, window_width, 80), border_radius=15)
            draw_text(screen, info_contextuelle['nom'], TITLE_FONT, background_color, window_x + window_width // 2, window_y + 25, "center")

            # Bouton de fermeture

            pygame.draw.rect(screen, ACCENT_COLOR, close_button_rect)
            draw_text(screen, "X", FONT, background_color, close_button_rect.centerx, close_button_rect.centery, "center")

            # Données démographiques
            y_offset = window_y + 100
            draw_text(screen, "Données Démographiques", FONT, border_color, window_x + window_width // 3, y_offset)
            pygame.draw.line(screen, (112, 128, 144), (window_x + 20, y_offset + 25), (window_x + window_width - 20, y_offset + 25), 1)

            for i, (label, value) in enumerate(demo_data):
                y = y_offset + 40 + i * 30
                draw_text(screen, f"{label}:", SMALL_FONT, text_color, window_x + window_width // 3, y)
                draw_text(screen, str(value), FONT, indicator_text_color, window_x + window_width * 3 // 4, y)

            # Indicateurs d'équilibre
            y_offset = window_y + 250
            draw_text(screen, "Indicateurs d'Équilibre", FONT, border_color, window_x + window_width // 3, y_offset)
            pygame.draw.line(screen, (112, 128, 144), (window_x + 20, y_offset + 25), (window_x + window_width - 20, y_offset + 25), 1)

            for i, (label, value) in enumerate(indicators):
                y = y_offset + 40 + i * 50
                draw_text(screen, f"{label}:", SMALL_FONT, text_color, window_x + window_width // 3, y)
                draw_progress_bar(screen, window_x + window_width * 1 // 8, y + 20, 340, 15, int(value), 100, get_indicator_color(int(value)))
                draw_text(screen, f"{value}%", SMALL_FONT, text_color, window_x + window_width * 7 // 8, y + 15, "center")

        pygame.display.flip()
        clock.tick(60)

class WaterEffect:
    def __init__(self):
        self.waves = [(random.random() * SCREEN_WIDTH,
                       random.random() * SCREEN_HEIGHT)
                      for _ in range(50)]

    def draw(self, surface, time):
        for i, (x, y) in enumerate(self.waves):
            radius = 20 + math.sin(time * 0.002 + i * 0.1) * 10
            alpha = int(100 + math.sin(time * 0.003 + i * 0.2) * 50)

            for r in range(int(radius), 0, -2):
                color = (*WATER_COLOR, int(alpha * (r/radius)))
                gfxdraw.filled_circle(surface, int(x), int(y), r, color)

class InfoPanel:
    def __init__(self):
        self.selected_skill = None
        self.panel_width = 300
        self.panel_height = 400
        self.margin = 20
        self.line_height = 25
        self.max_line_length = 40  # Nombre maximum de caractères par ligne

    def wrap_text(self, text: str, max_length: int) -> List[str]:
        """Découpe le texte en lignes de longueur maximale donnée."""
        words = text.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            word_length = len(word)
            if current_length + word_length + 1 <= max_length:
                current_line.append(word)
                current_length += word_length + 1
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = word_length + 1

        if current_line:
            lines.append(' '.join(current_line))

        return lines

    def draw(self, screen: pygame.Surface, points_available: int) -> None:
        if not self.selected_skill:
            return

        # Position du panneau
        panel_x = screen.get_width() - self.panel_width - self.margin
        panel_y = screen.get_height() - self.panel_height - self.margin

        # Dessiner le fond du panneau
        panel_rect = pygame.Rect(panel_x, panel_y, self.panel_width, self.panel_height)
        pygame.draw.rect(screen, (32, 82, 111), panel_rect)
        pygame.draw.rect(screen, (255, 255, 255), panel_rect, 2)

        # Configuration du texte
        font = pygame.font.Font(None, 28)
        title_font = pygame.font.Font(None, 36)
        y_offset = panel_y + self.margin

        # Titre (numéro de la compétence)
        title_text = f"Compétence {self.selected_skill.name}"
        title_surf = title_font.render(title_text, True, (255, 255, 255))
        screen.blit(title_surf, (panel_x + self.margin, y_offset))
        y_offset += self.line_height + 10

        # Nom complet de la compétence
        name_text = self.selected_skill.full_name
        name_surf = font.render(name_text, True, (200, 200, 200))
        screen.blit(name_surf, (panel_x + self.margin, y_offset))
        y_offset += self.line_height + 10

        # Description découpée en lignes
        description_lines = self.wrap_text(self.selected_skill.description, self.max_line_length)
        for line in description_lines:
            text_surf = font.render(line, True, (255, 255, 255))
            screen.blit(text_surf, (panel_x + self.margin, y_offset))
            y_offset += self.line_height

        # Informations sur le niveau et le coût
        y_offset += self.line_height
        level_text = f"Niveau: {self.selected_skill.level}/{self.selected_skill.max_level}"
        level_surf = font.render(level_text, True, (255, 255, 255))
        screen.blit(level_surf, (panel_x + self.margin, y_offset))
        y_offset += self.line_height

        cost_text = f"Coût: {self.selected_skill.cost} points"
        cost_surf = font.render(cost_text, True, (255, 255, 255))
        screen.blit(cost_surf, (panel_x + self.margin, y_offset))
        y_offset += self.line_height

        points_text = f"Points disponibles: {points_available}"
        points_surf = font.render(points_text, True, (255, 255, 255))
        screen.blit(points_surf, (panel_x + self.margin, y_offset))
class SkillType(Enum):
    FOUNDATION = "Fondation"
    AMPLIFICATION = "Amplification"
    TRANSFORMATION = "Transformation"

class SkillBranch:
    def __init__(self, name, color, position):
        self.name = name
        self.color = color
        self.position = position
        self.skills = []
        self.rect = pygame.Rect(position[0], position[1], 200, 40)

class SkillNode:
    def __init__(self, x, y, width, height, name, description, cost, levels, full_name, skill_type, level=0, max_level=5):
        self.rect = pygame.Rect(x, y, width, height)
        self.name = name
        self.description = description
        self.cost = cost
        self.level = level
        self.max_level = max_level
        self.skill_type = skill_type
        self.levels = levels
        self.is_hovered = False
        self.is_selected = False
        self.prerequisites = []
        self.full_name = full_name

    def draw(self, screen, time, camera_offset, zoom):
        x = (self.rect.x + camera_offset[0]) * zoom
        y = (self.rect.y + camera_offset[1]) * zoom
        width = self.rect.width * zoom
        height = self.rect.height * zoom

        # Couleur de base selon le type de compétence
        base_color = {
            SkillType.FOUNDATION: (32, 82, 111),
            SkillType.AMPLIFICATION: (82, 32, 111),
            SkillType.TRANSFORMATION: (111, 82, 32)
        }[self.skill_type]

        # Effet de pulsation pour le survol
        pulse = math.sin(time * 0.05) * 20
        color = tuple(min(255, c + (30 if self.is_hovered else 0) + (pulse if self.is_selected else 0)) for c in base_color)

        # Dessin du nœud
        pygame.draw.rect(screen, color, (x, y, width, height), border_radius=10)
        if self.level > 0:
            progress_width = (width - 4) * (self.level / self.max_level)
            pygame.draw.rect(screen, CATASTROPHE_COLORS["Eau"],
                             (x + 2, y + height - 8, progress_width, 6),
                             border_radius=3)

        # Texte
        font = pygame.font.Font(None, int(36 * zoom))
        name_surf = font.render(self.name, True, TEXT_COLOR)
        level_surf = font.render(f"Niveau {self.level}/{self.max_level}", True, TEXT_COLOR)

        screen.blit(name_surf, (x + width//2 - name_surf.get_width()//2, y + 10))
        screen.blit(level_surf, (x + width//2 - level_surf.get_width()//2, y + height - 30))

class Camera:
    def __init__(self):
        self.x = 0
        self.y = 0
        self.zoom = 1.0
        self.dragging = False
        self.last_mouse_pos = None

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 2:  # Bouton du milieu
                self.dragging = True
                self.last_mouse_pos = event.pos
            elif event.button == 4:  # Molette vers le haut
                self.zoom = min(2.0, self.zoom + 0.1)
            elif event.button == 5:  # Molette vers le bas
                self.zoom = max(0.5, self.zoom - 0.1)

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 2:
                self.dragging = False

        elif event.type == pygame.MOUSEMOTION and self.dragging:
            dx = event.pos[0] - self.last_mouse_pos[0]
            dy = event.pos[1] - self.last_mouse_pos[1]
            self.x += dx / self.zoom
            self.y += dy / self.zoom
            self.last_mouse_pos = event.pos


def get_skill(skills, name):
    return skills.get(name)

def is_niveau_fondations(skill):
    return skill["niveau"] == "Fondations"

def is_niveau_amplification(skill):
    return skill["niveau"] == "Amplification"
def is_niveau_transformation(skill):
    return skill["niveau"] == "Transformation"

def is_levels_intensite(skill):
    return skill.levels == "Intensite"
def is_levels_duree(skill):
    return skill.levels == "Duree"
def is_levels_portee(skill):
    return skill.levels == "Portee"
def is_levels_impact(skill):
    return skill.levels == "Impact Ecologique"


def catastrophe_upgrades_screen(choix_catastrophe):
    """Écran d'améliorations pour la catastrophe sélectionnée."""
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    clock = pygame.time.Clock()
    water_effect = WaterEffect()

    # Initialisation des éléments
    camera = Camera()
    info_panel = InfoPanel()
    points_available = 15
    time = 0
    scroll_offset = 0
    SCROLL_SPEED = 20

    # Création des branches verticales
    branch_spacing = 120
    branches = [
        SkillBranch("Intensité", (32, 82, 111), (SCREEN_WIDTH - SCREEN_WIDTH * 15 // 16, 100)),
        SkillBranch("Portée", (32, 82, 111), (SCREEN_WIDTH - SCREEN_WIDTH * 15 // 16, 100 + branch_spacing)),
        SkillBranch("Durée", (32, 82, 111), (SCREEN_WIDTH - SCREEN_WIDTH * 15 // 16, 100 + branch_spacing * 2)),
        SkillBranch("Impact", (32, 82, 111), (SCREEN_WIDTH - SCREEN_WIDTH * 15 // 16, 100 + branch_spacing * 3))
    ]

    # branche active
    intensite_branch = branches[0]
    portee_branch = branches[1]
    duree_branch = branches[2]
    impact_branch = branches[3]

    active_branch = intensite_branch

    skills_dict = load_competence(choix_catastrophe)
    # Récupération des compétences par type
    skills_by_type = {
        "foundation": {name: details for name, details in skills_dict.items() if is_niveau_fondations(details)},
        "amplification": {name: details for name, details in skills_dict.items() if is_niveau_amplification(details)},
        "transformation": {name: details for name, details in skills_dict.items() if is_niveau_transformation(details)}
    }

    # Configuration des compétences
    skills = []
    skill_number = 1
    x_start = SCREEN_WIDTH - SCREEN_WIDTH *14 //20  # Déplacé vers la droite
    width = 200  # Rectangle élargi
    height = 100
    y_spacing = 120

    # Création des compétences numérotées
    for skill_type, skill_group in skills_by_type.items():
        y = 80
        x = x_start + (300 if skill_type == "amplification" else (600 if skill_type == "transformation" else 0))

        for name, details in skill_group.items():
            skill = SkillNode(
                x, y, width, height,
                str(skill_number),  # Numéro au lieu du nom
                details["description"],
                details["cost"],
                details["type"],
                skill_type=getattr(SkillType, skill_type.upper()),
                full_name=name  # Stockage du nom complet pour le tooltip
            )
            skills.append(skill)
            skill_number += 1
            y += y_spacing

    while True:
        time += 1
        mouse_pos = pygame.mouse.get_pos()
        keys = pygame.key.get_pressed()

        # Gestion du défilement avec les touches
        if keys[pygame.K_UP]:
            scroll_offset = min(0, scroll_offset + SCROLL_SPEED)
        if keys[pygame.K_DOWN]:
            max_scroll = -max(skill.rect.bottom for skill in skills) + SCREEN_HEIGHT *3 // 5
            scroll_offset = max(max_scroll, scroll_offset - SCROLL_SPEED)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            camera.handle_event(event)

            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    # Gestion du clic sur le bouton retour
                    return_button = pygame.Rect(20, 20, 150, 50)  # Bouton élargi
                    if return_button.collidepoint(mouse_pos):
                        return

                    # Gestion du clic sur les branches pour changer de branche active
                    for branch in branches:
                        if branch.rect.collidepoint(mouse_pos):
                            active_branch = branch  # Mise à jour de la branche active
                            break

                    # Vérification des clics sur les compétences
                    clicked_on_skill = False
                    for skill in skills:
                        skill_screen_pos = (
                            (skill.rect.x + camera.x) * camera.zoom,
                            (skill.rect.y + camera.y + scroll_offset) * camera.zoom
                        )
                        skill_screen_rect = pygame.Rect(
                            skill_screen_pos[0], skill_screen_pos[1],
                            skill.rect.width * camera.zoom,
                            skill.rect.height * camera.zoom
                        )

                        if skill_screen_rect.collidepoint(mouse_pos):
                            clicked_on_skill = True
                            if info_panel.selected_skill == skill:
                                if points_available >= skill.cost and skill.level < skill.max_level:
                                    skill.level += 1
                                    points_available -= skill.cost
                            else:
                                info_panel.selected_skill = skill
                            break

                    # Fermeture du panneau d'information si clic à l'extérieur
                    if not clicked_on_skill and not return_button.collidepoint(mouse_pos):
                        info_panel.selected_skill = None

                elif event.button == 3:  # Clic droit pour régresser
                    for skill in skills:
                        skill_screen_pos = (
                            (skill.rect.x + camera.x) * camera.zoom,
                            (skill.rect.y + camera.y + scroll_offset) * camera.zoom
                        )
                        skill_screen_rect = pygame.Rect(
                            skill_screen_pos[0], skill_screen_pos[1],
                            skill.rect.width * camera.zoom,
                            skill.rect.height * camera.zoom
                        )
                        if skill_screen_rect.collidepoint(mouse_pos) and skill.level > 0:
                            skill.level -= 1
                            points_available += skill.cost
                            break


        # Effet d'eau en arrière-plan
        water_effect.draw(screen, time)
        # Mise à jour du survol
        for skill in skills:
            skill_screen_pos = (
                (skill.rect.x + camera.x) * camera.zoom,
                (skill.rect.y + camera.y + scroll_offset) * camera.zoom
            )
            skill_screen_rect = pygame.Rect(
                skill_screen_pos[0], skill_screen_pos[1],
                skill.rect.width * camera.zoom,
                skill.rect.height * camera.zoom
            )
            skill.is_hovered = skill_screen_rect.collidepoint(mouse_pos)
            skill.is_selected = skill == info_panel.selected_skill

        # Dessin
        screen.fill(BACKGROUND_COLOR)

        # Bouton retour
        return_button = pygame.Rect(20, 20, 150, 50)  # Bouton élargi
        pygame.draw.rect(screen, (0, 100, 200), return_button, border_radius=10)  # Bleu avec coins arrondis
        font = pygame.font.Font(None, 36)
        return_text = font.render("Retour", True, (255, 255, 255))
        text_rect = return_text.get_rect(center=return_button.center)
        screen.blit(return_text, text_rect)

        # Menu latéral pour les branches
        for branch in branches:
            # On change la couleur pour l'indicateur de branche active
            color = (255, 100, 100) if branch == active_branch else branch.color
            pygame.draw.rect(screen, color,
                             (branch.rect.x, branch.rect.y, branch.rect.width, branch.rect.height),
                             border_radius=10)
            text_surf = font.render(branch.name, True, TEXT_COLOR)
            text_rect = text_surf.get_rect(center=(branch.rect.centerx, branch.rect.centery))
            screen.blit(text_surf, text_rect)

        # filtered_skills = [skill for skill in skills if skill.levels == active_branch.name]
        # Zone principale des compétences avec scroll
        for skill in skills:
            # Filtrage des compétences en fonction de la branche active
            if (active_branch.name == "Intensité" and is_levels_intensite(skill)) or \
                (active_branch.name == "Portée" and is_levels_portee(skill)) or \
                (active_branch.name == "Durée" and is_levels_duree(skill)) or \
                (active_branch.name == "Impact" and is_levels_impact(skill)):

                skill.rect.y += scroll_offset
                skill.draw(screen, time, (camera.x, camera.y), camera.zoom)
                if skill.is_hovered:
                    # Affichage du tooltip
                    tooltip_font = pygame.font.Font(None, 24)
                    tooltip_text = tooltip_font.render(skill.full_name, True, (255, 255, 255))
                    tooltip_bg = pygame.Rect(mouse_pos[0], mouse_pos[1] - 30, tooltip_text.get_width() + 20, 25)
                    pygame.draw.rect(screen, (0, 0, 0, 128), tooltip_bg)
                    screen.blit(tooltip_text, (mouse_pos[0] + 10, mouse_pos[1] - 25))
                skill.rect.y -= scroll_offset

        # Panneau d'information
        if info_panel.selected_skill:
            info_panel.draw(screen, points_available)

        pygame.display.flip()
        clock.tick(60)
def get_indicator_color(value):
    """Retourne la couleur de l'indicateur en fonction de sa valeur."""
    if value >= 70:
        return (46, 204, 113)  # Vert
    elif value >= 40:
        return (241, 196, 15)  # Jaune
    return (231, 76, 60)  # Rouge

def country_info_window(country_name="Nom du Pays"):
    """Fenêtre d'information sur un pays avec ses données démographiques et indicateurs."""
    screen = pygame.display.set_mode((400, 500))
    pygame.display.set_caption("Information Pays")

    while True:
        screen.fill((248, 248, 248))
        pygame.draw.rect(screen, (70, 130, 180), (0, 0, 400, 500), border_radius=15)
        pygame.draw.rect(screen, (248, 248, 248), (2, 2, 396, 496), border_radius=15)
        pygame.draw.rect(screen, (70, 130, 180), (0, 0, 400, 80), border_radius=15)
        draw_text(screen, country_name, TITLE_FONT, (248, 248, 248), 200, 25, "center")
        draw_button(screen, (360, 10, 30, 30), (255, 99, 71), (248, 248, 248), "X", FONT, (248, 248, 248), screen)

        y_offset = 100
        draw_text(screen, "Données Démographiques", FONT, (70, 130, 180), 20, y_offset)
        pygame.draw.line(screen, (112, 128, 144), (20, y_offset + 25), (380, y_offset + 25), 1)

        demo_data = [
            ("Population", "10,000,000"),
            ("Personnes affectées", "1,000,000"),
            ("Morts", "100,000")
        ]

        for i, (label, value) in enumerate(demo_data):
            y = y_offset + 40 + i * 30
            draw_text(screen, f"{label}:", SMALL_FONT, (50, 50, 50), 30, y)
            draw_text(screen, value, FONT, (70, 130, 180), 200, y)

        y_offset = 250
        draw_text(screen, "Indicateurs d'Équilibre", FONT, (70, 130, 180), 20, y_offset)
        pygame.draw.line(screen, (112, 128, 144), (20, y_offset + 25), (380, y_offset + 25), 1)

        indicators = [
            ("Résilience Technologique", 60),
            ("Stabilité Sociétale", 75),
            ("Régénération Écologique", 40),
            ("Adaptation Évolution", 65)
        ]

        for i, (label, value) in enumerate(indicators):
            y = y_offset + 40 + i * 50
            draw_text(screen, f"{label}:", SMALL_FONT, (50, 50, 50), 30, y)
            draw_progress_bar(screen, 30, y + 20, 340, 15, value, 100, get_indicator_color(value))
            draw_text(screen, f"{value}%", SMALL_FONT, (50, 50, 50), 375, y + 15, "center")

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_x, mouse_y = event.pos
                if 360 <= mouse_x <= 390 and 10 <= mouse_y <= 40:
                    return

class Button:
    """Bouton standard pour les interfaces utilisateur."""
    def __init__(self, x, y, width, height, text, icon=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.icon = icon
        self.is_hovered = False
        self.animation_start = 0

    def draw(self, surface):
        hover_offset = 0
        if self.is_hovered:
            current_time = global_time.time()
            if self.animation_start == 0:
                self.animation_start = current_time
            hover_offset = math.sin((current_time - self.animation_start) * 5) * 3
        else:
            self.animation_start = 0

        color = (100, 149, 237) if self.is_hovered else (70, 130, 180)
        pygame.draw.rect(surface, color, (self.rect.x, self.rect.y - hover_offset, self.rect.width, self.rect.height), border_radius=15)

        highlight_rect = pygame.Rect(self.rect.x, self.rect.y - hover_offset, self.rect.width, self.rect.height // 2)
        highlight_color = (*[min(255, c + 30) for c in color], 100)
        pygame.draw.rect(surface, highlight_color, highlight_rect, border_radius=15)

        if self.icon:
            icon_surf = ICON_FONT.render(self.icon, True, (240, 242, 245))
            icon_rect = icon_surf.get_rect(midright=(self.rect.centerx - 10, self.rect.centery - hover_offset))
            surface.blit(icon_surf, icon_rect)

        text_surf = FONT.render(self.text, True, (240, 242, 245))
        text_rect = text_surf.get_rect(center=(self.rect.centerx + (15 if self.icon else 0), self.rect.centery - hover_offset))
        surface.blit(text_surf, text_rect)

def draw_title_line(surface, text, y):
    """Dessine un titre avec une ligne décorative en dessous."""
    title_surface = TITLE_FONT.render(text, True, (50, 50, 50))
    title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, y))
    line_y = title_rect.bottom + 10
    pygame.draw.line(surface, (70, 130, 180), (SCREEN_WIDTH // 4, line_y), (3 * SCREEN_WIDTH // 4, line_y), 2)
    surface.blit(title_surface, title_rect)

def options_screen():
    """Écran des options avec des boutons pour différents paramètres."""
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Options")

    buttons = [
        Button(SCREEN_WIDTH // 2 - 150, 180, 300, 60, "Graphismes", "🎨"),
        Button(SCREEN_WIDTH // 2 - 150, 260, 300, 60, "Son", "🔊"),
        Button(SCREEN_WIDTH // 2 - 150, 340, 300, 60, "Jouabilité", "🎮"),
        Button(SCREEN_WIDTH // 2 - 150, 420, 300, 60, "Commandes", "⌨"),
        Button(50, SCREEN_HEIGHT - 80, 200, 50, "Retour", "←")
    ]

    while True:
        screen.fill((240, 242, 245))

        for i in range(3):
            pygame.draw.circle(screen, (*(70, 130, 180), 30), (0, SCREEN_HEIGHT // 2 + i * 100), 100 + i * 50)
            pygame.draw.circle(screen, (*(65, 105, 225), 30), (SCREEN_WIDTH, SCREEN_HEIGHT // 2 - i * 100), 100 + i * 50)

        draw_title_line(screen, "Options", 100)

        mouse_pos = pygame.mouse.get_pos()
        for button in buttons:
            button.is_hovered = button.rect.collidepoint(mouse_pos)
            button.draw(screen)

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                for button in buttons:
                    if button.rect.collidepoint(event.pos):
                        if button.text == "Retour":
                            return
                        elif button.text == "Graphismes":
                            graphics_options_screen()
                        elif button.text == "Son":
                            sound_options_screen()
                        elif button.text == "Jouabilité":
                            playability_options_screen()
                        elif button.text == "Commandes":
                            controls_options_screen()

class SettingOption:
    """Option de paramètre avec une liste de valeurs possibles."""
    def __init__(self, x, y, width, height, title, options, current_value):
        self.rect = pygame.Rect(x, y, width, height)
        self.title = title
        self.options = options
        self.current_value = current_value
        self.hover = 0
        self.animation = 0
        self.selected = False

    def draw(self, surface, time):
        title_font = pygame.font.Font(None, 32)
        title_surf = title_font.render(self.title, True, TEXT_COLOR)
        surface.blit(title_surf, (150, self.rect.centery - 30))

        value_rect = pygame.Rect(self.rect.x, self.rect.y, self.rect.width, self.rect.height)
        mouse_over = value_rect.collidepoint(pygame.mouse.get_pos())

        if mouse_over:
            self.hover = min(1, self.hover + 0.1)
        else:
            self.hover = max(0, self.hover - 0.1)

        pulse = math.sin(time * 0.003) * 2
        glow_radius = 8 + pulse * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_color = (*ACCENT_COLOR, alpha) if mouse_over else (*ACCENT_COLOR_2, alpha // 2)
            glow_rect = value_rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, glow_color, glow_rect, border_radius=10)

        base_color = [int(c1 + (c2 - c1) * self.hover) for c1, c2 in zip(ACCENT_COLOR_2, ACCENT_COLOR)]
        pygame.draw.rect(surface, base_color, value_rect, border_radius=10)
        pygame.draw.rect(surface, ACCENT_COLOR, value_rect, 2, border_radius=10)

        value_font = pygame.font.Font(None, 28)
        value_text = str(self.current_value)
        value_surf = value_font.render(value_text, True, TEXT_COLOR)
        value_rect = value_surf.get_rect(center=value_rect.center)
        shadow_surf = value_font.render(value_text, True, (0, 0, 0))
        shadow_rect = shadow_surf.get_rect(center=(value_rect.centerx + 1, value_rect.centery + 1))
        surface.blit(shadow_surf, shadow_rect)
        surface.blit(value_surf, value_rect)

        if len(self.options) > 1:
            arrow_color = ACCENT_COLOR if mouse_over else DISABLED_COLOR
        left_arrow = [(self.rect.x - 30, self.rect.centery),
                      (self.rect.x - 20, self.rect.centery - 10),
                      (self.rect.x - 20, self.rect.centery + 10)]
        pygame.draw.polygon(surface, arrow_color, left_arrow)

        right_arrow = [(self.rect.right + 30, self.rect.centery),
                       (self.rect.right + 20, self.rect.centery - 10),
                       (self.rect.right + 20, self.rect.centery + 10)]
        pygame.draw.polygon(surface, arrow_color, right_arrow)

class PreviewWindow:
    """Fenêtre de prévisualisation pour les options graphiques."""
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
        self.particles = [(random.randint(0, width), random.randint(0, height)) for _ in range(50)]
        self.particle_speeds = [(random.uniform(-1, 1), random.uniform(-1, 1)) for _ in range(50)]

    def update(self):
        for i in range(len(self.particles)):
            x, y = self.particles[i]
            dx, dy = self.particle_speeds[i]
            x = (x + dx) % self.rect.width
            y = (y + dy) % self.rect.height
            self.particles[i] = (x, y)

    def draw(self, surface, time):
        for i in range(self.rect.height):
            progress = i / self.rect.height
            color = [int(c1 + (c2 - c1) * progress) for c1, c2 in zip(BACKGROUND_COLOR, ACCENT_COLOR_2)]
            pygame.draw.line(surface, color, (self.rect.left, self.rect.top + i), (self.rect.right, self.rect.top + i))

        for i, (x, y) in enumerate(self.particles):
            particle_color = (*ACCENT_COLOR, int(128 + math.sin(time * 0.01 + i) * 64))
            pos = (int(self.rect.left + x), int(self.rect.top + y))
            size = 2 + math.sin(time * 0.005 + i) * 1
            gfxdraw.filled_circle(surface, pos[0], pos[1], int(size), particle_color)

def graphics_options_screen():
    """Écran des options graphiques avec des paramètres ajustables."""
    clock = pygame.time.Clock()
    preview = PreviewWindow(600, 150, 500, 400)

    settings = [
        SettingOption(350, 160, 200, 40, "Résolution", ["1280x720", "1920x1080", "2560x1440"], "1280x720"),
        SettingOption(350, 220, 200, 40, "Plein écran", ["Oui", "Non"], "Oui"),
        SettingOption(350, 280, 200, 40, "Qualité des textures", ["Basse", "Moyenne", "Haute"], "Haute"),
        SettingOption(350, 340, 200, 40, "Effets visuels", ["Désactivés", "Basiques", "Complets"], "Complets"),
        SettingOption(350, 400, 200, 40, "Anti-aliasing", ["Désactivé", "x2", "x4", "x8"], "x4"),
        SettingOption(350, 460, 200, 40, "Ombres", ["Désactivées", "Basses", "Moyennes", "Hautes"], "Hautes")
    ]

    time = 0
    while True:
        time += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = event.pos
                for setting in settings:
                    if setting.rect.collidepoint(mouse_pos):
                        current_index = setting.options.index(setting.current_value)
                        if event.button == 1:
                            current_index = (current_index + 1) % len(setting.options)
                        elif event.button == 3:
                            current_index = (current_index - 1) % len(setting.options)
                        setting.current_value = setting.options[current_index]

                if pygame.Rect(50, 520, 200, 50).collidepoint(mouse_pos):
                    return

        preview.update()
        screen.fill(BACKGROUND_COLOR)

        title_font = pygame.font.Font(None, 64)
        title = "Options Graphiques"
        title_glow = title_font.render(title, True, ACCENT_COLOR)
        title_glow.set_alpha(int(128 + math.sin(time * 0.01) * 64))
        title_rect = title_glow.get_rect(center=(SCREEN_WIDTH // 2, 100))
        screen.blit(title_glow, title_rect.move(2, 2))

        title_main = title_font.render(title, True, TEXT_COLOR)
        screen.blit(title_main, title_rect)

        preview.draw(screen, time)
        preview_title = pygame.font.Font(None, 32).render("Prévisualisation", True, TEXT_COLOR)
        screen.blit(preview_title, (preview.rect.centerx - preview_title.get_width() // 2, preview.rect.top - 30))

        for setting in settings:
            setting.draw(screen, time)

        back_rect = pygame.Rect(50, 520, 200, 50)
        mouse_over_back = back_rect.collidepoint(pygame.mouse.get_pos())
        back_color = ACCENT_COLOR if mouse_over_back else ACCENT_COLOR_2
        pygame.draw.rect(screen, back_color, back_rect, border_radius=10)
        pygame.draw.rect(screen, ACCENT_COLOR, back_rect, 2, border_radius=10)
        back_text = pygame.font.Font(None, 32).render("Retour", True, TEXT_COLOR)
        back_rect = back_text.get_rect(center=(150, 545))
        screen.blit(back_text, back_rect)

        apply_rect = pygame.Rect(SCREEN_WIDTH - 250, 520, 200, 50)
        pygame.draw.rect(screen, ACCENT_COLOR_2, apply_rect, border_radius=10)
        pygame.draw.rect(screen, ACCENT_COLOR, apply_rect, 2, border_radius=10)
        apply_text = pygame.font.Font(None, 32).render("Appliquer", True, TEXT_COLOR)
        apply_rect = apply_text.get_rect(center=(SCREEN_WIDTH - 150, 545))
        screen.blit(apply_text, apply_rect)

        pygame.display.flip()
        clock.tick(60)

class VolumeSlider:
    """Curseur de volume pour ajuster les niveaux sonores."""
    def __init__(self, x, y, width, height, initial_value=0.5):
        self.rect = pygame.Rect(x, y, width, height)
        self.value = initial_value
        self.dragging = False
        self.hover = 0
        self.animation = 0

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        mouse_over = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if mouse_over else max(0, self.hover - 0.1)

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if mouse_over:
                    self.dragging = True
            elif event.type == pygame.MOUSEBUTTONUP:
                self.dragging = False
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                self.value = (mouse_pos[0] - self.rect.x) / self.rect.width
                self.value = max(0, min(1, self.value))

    def draw(self, surface, time):
        glow_radius = 5 + math.sin(time * 0.005) * 2 * self.hover
        for i in range(int(glow_radius)):
            alpha = int(50 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*SLIDER_BG_COLOR, alpha), glow_rect, border_radius=8)

        pygame.draw.rect(surface, SLIDER_BG_COLOR, self.rect, border_radius=8)

        active_width = int(self.rect.width * self.value)
        active_rect = pygame.Rect(self.rect.x, self.rect.y, active_width, self.rect.height)

        for i in range(active_width):
            progress = i / self.rect.width
            color = (
                int(SLIDER_ACTIVE_COLOR[0] * (1 - progress) + ACCENT_COLOR[0] * progress),
                int(SLIDER_ACTIVE_COLOR[1] * (1 - progress) + ACCENT_COLOR[1] * progress),
                int(SLIDER_ACTIVE_COLOR[2] * (1 - progress) + ACCENT_COLOR[2] * progress)
            )
            line_rect = pygame.Rect(self.rect.x + i, self.rect.y, 1, self.rect.height)
            pygame.draw.rect(surface, color, line_rect)

        handle_pos = (self.rect.x + active_width, self.rect.centery)
        handle_radius = 12 + self.hover * 2
        for i in range(5):
            alpha = 150 - i * 30
            pygame.draw.circle(surface, (*SLIDER_HANDLE_COLOR, alpha), handle_pos, handle_radius + i)

        pygame.draw.circle(surface, SLIDER_HANDLE_COLOR, handle_pos, handle_radius)

        font = pygame.font.Font(None, 24)
        percentage = f"{int(self.value * 100)}%"
        text_surf = font.render(percentage, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(midleft=(self.rect.right + 20, self.rect.centery))
        surface.blit(text_surf, text_rect)

class BackButton:
    """Bouton de retour stylisé."""
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
        self.hover = 0

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)

        glow_radius = 10 + math.sin(time * 0.005) * 2
        for i in range(int(glow_radius)):
            alpha = int(50 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*ACCENT_COLOR, alpha), glow_rect, border_radius=10)

        color = (
            int(SLIDER_BG_COLOR[0] + (ACCENT_COLOR[0] - SLIDER_BG_COLOR[0]) * self.hover),
            int(SLIDER_BG_COLOR[1] + (ACCENT_COLOR[1] - SLIDER_BG_COLOR[1]) * self.hover),
            int(SLIDER_BG_COLOR[2] + (ACCENT_COLOR[2] - SLIDER_BG_COLOR[2]) * self.hover)
        )
        pygame.draw.rect(surface, color, self.rect, border_radius=10)

        font = pygame.font.Font(None, 36)
        text_surf = font.render("Retour", True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

def draw_title_sound_options(surface, time):
    """Dessine le titre pour l'écran des options sonores."""
    title = "Options Sonores"
    font = pygame.font.Font(None, 72)
    wave_height = 5
    wave_length = 0.1
    wave_speed = 0.005
    glow_intensity = int(128 + math.sin(time * 0.01) * 64)

    total_width = sum(font.size(char)[0] for char in title)
    start_x = SCREEN_WIDTH // 2 - total_width // 2
    current_x = start_x

    for i, char in enumerate(title):
        offset = math.sin(time * wave_speed + i * wave_length) * wave_height
        char_surf = font.render(char, True, TEXT_COLOR)
        char_width = font.size(char)[0]
        glow_surf = font.render(char, True, ACCENT_COLOR)
        glow_surf.set_alpha(glow_intensity)
        surface.blit(glow_surf, (current_x + 2, 100 + offset + 2))
        surface.blit(char_surf, (current_x, 100 + offset))
        current_x += char_width

def sound_options_screen():
    """Écran des options sonores avec des curseurs de volume."""
    clock = pygame.time.Clock()

    sliders = {
        "Volume Général": VolumeSlider(350, 180, 300, 20, 0.5),
        "Musique": VolumeSlider(350, 260, 300, 20, 0.25),
        "Effets Sonores": VolumeSlider(350, 340, 300, 20, 0.75),
        "Son Ambiant": VolumeSlider(350, 420, 300, 20, 0.4)
    }

    back_button = BackButton(50, 600, 200, 50)

    time = 0
    while True:
        time += 1
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.rect.collidepoint(event.pos):
                    return

        for slider in sliders.values():
            slider.update(events)

        screen.fill(BACKGROUND_COLOR)
        draw_title_sound_options(screen, time)

        y_position = 180
        for label, slider in sliders.items():
            font = pygame.font.Font(None, 36)
            label_surf = font.render(label, True, TEXT_COLOR)
            label_rect = label_surf.get_rect(midright=(320, y_position + 10))
            glow_surf = font.render(label, True, ACCENT_COLOR)
            glow_surf.set_alpha(50)
            screen.blit(glow_surf, (label_rect.x + 2, label_rect.y + 2))
            screen.blit(label_surf, label_rect)
            slider.draw(screen, time)
            y_position += 80

        back_button.draw(screen, time)

        pygame.display.flip()
        clock.tick(60)

class Slider:
    """Curseur générique pour les options de jouabilité."""
    def __init__(self, x, y, width, height, min_val=0, max_val=100, current=50):
        self.rect = pygame.Rect(x, y, width, height)
        self.min_val = min_val
        self.max_val = max_val
        self.current = current
        self.dragging = False
        self.hover = 0

    def get_current_pos(self):
        range_size = self.max_val - self.min_val
        current_pos = (self.current - self.min_val) / range_size
        return self.rect.x + (self.rect.width * current_pos)

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        mouse_over = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if mouse_over else max(0, self.hover - 0.1)

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and mouse_over:
                self.dragging = True
            elif event.type == pygame.MOUSEBUTTONUP:
                self.dragging = False
            elif event.type == pygame.MOUSEMOTION and self.dragging:
                relative_x = max(0, min(1, (mouse_pos[0] - self.rect.x) / self.rect.width))
                self.current = self.min_val + (self.max_val - self.min_val) * relative_x

    def draw(self, surface, time):
        glow_radius = 5 + math.sin(time * 0.003) * 2 * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*SLIDER_FILL, alpha), glow_rect, border_radius=5)

        pygame.draw.rect(surface, SLIDER_BG, self.rect, border_radius=5)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, self.get_current_pos() - self.rect.x, self.rect.height)
        pygame.draw.rect(surface, SLIDER_FILL, fill_rect, border_radius=5)

        handle_pos = (self.get_current_pos(), self.rect.centery)
        handle_radius = 10 + math.sin(time * 0.003) * 2 * self.hover
        pygame.draw.circle(surface, TEXT_COLOR, handle_pos, handle_radius)

class ToggleButton:
    """Bouton à bascule pour activer ou désactiver une option."""
    def __init__(self, x, y, width, height, text, initial_state=True):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.state = initial_state
        self.hover = 0
        self.animation = 0

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        mouse_over = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if mouse_over else max(0, self.hover - 0.1)
        self.animation = min(1, self.animation + 0.1) if self.state else max(0, self.animation - 0.1)

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and mouse_over:
                self.state = not self.state

    def draw(self, surface, time):
        off_color = BUTTON_COLOR
        on_color = ACCENT_COLOR
        current_color = tuple(int(c1 + (c2 - c1) * self.animation) for c1, c2 in zip(off_color, on_color))

        glow_radius = 5 + math.sin(time * 0.003) * 2 * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*current_color, alpha), glow_rect, border_radius=10)

        pygame.draw.rect(surface, current_color, self.rect, border_radius=10)
        circle_x = self.rect.x + 5 + (self.rect.width - 25) * self.animation
        circle_y = self.rect.centery
        pygame.draw.circle(surface, TEXT_COLOR, (circle_x, circle_y), 10)

class DifficultySelector:
    """Sélecteur de difficulté avec plusieurs niveaux."""
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
        self.difficulties = ["Facile", "Normal", "Difficile", "Expert"]
        self.current_index = 1
        self.hover = 0

    def update(self, events):
        mouse_pos = pygame.mouse.get_pos()
        mouse_over = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if mouse_over else max(0, self.hover - 0.1)

        for event in events:
            if event.type == pygame.MOUSEBUTTONDOWN and mouse_over:
                self.current_index = (self.current_index + 1) % len(self.difficulties)

    def draw(self, surface, time):
        current_diff = self.difficulties[self.current_index]

        glow_radius = 5 + math.sin(time * 0.003) * 2 * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*BUTTON_COLOR, alpha), glow_rect, border_radius=10)

        pygame.draw.rect(surface, BUTTON_COLOR, self.rect, border_radius=10)

        font = pygame.font.Font(None, 36)
        text_surf = font.render(current_diff, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

def draw_background_pattern(surface, time):
    """Dessine un motif hexagonal en arrière-plan."""
    hex_size = 50
    hex_points = []
    for x in range(-hex_size, SCREEN_WIDTH + hex_size, hex_size * 2):
        for y in range(-hex_size, SCREEN_HEIGHT + hex_size, hex_size * 2):
            points = []
            for i in range(6):
                angle = math.pi / 3 * i + time * 0.0001
                px = x + math.cos(angle) * hex_size
                py = y + math.sin(angle) * hex_size
                points.append((px, py))
            hex_points.append(points)

    for points in hex_points:
        pygame.draw.lines(surface, (*BUTTON_COLOR, 30), True, points, 1)

def playability_options_screen():
    """Écran des options de jouabilité avec des curseurs et des boutons à bascule."""
    clock = pygame.time.Clock()

    difficulty_selector = DifficultySelector(350, 160, 200, 40)
    game_speed_slider = Slider(350, 220, 200, 30, min_val=0.5, max_val=2.0, current=1.0)
    tutorial_toggle = ToggleButton(350, 280, 60, 30, "Tutorial")
    notifications_toggle = ToggleButton(350, 340, 60, 30, "Notifications")

    time = 0
    while True:
        time += 1
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = event.pos
                if 50 <= mouse_pos[0] <= 250 and 520 <= mouse_pos[1] <= 570:
                    return

        difficulty_selector.update(events)
        game_speed_slider.update(events)
        tutorial_toggle.update(events)
        notifications_toggle.update(events)

        screen.fill(BACKGROUND_COLOR)
        draw_background_pattern(screen, time)

        title = "Options de Jouabilité"
        font_title = pygame.font.Font(None, 64)
        title_color = tuple(int(c * (0.8 + math.sin(time * 0.003) * 0.2)) for c in (255, 255, 255))
        title_surf = font_title.render(title, True, title_color)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 100))
        screen.blit(title_surf, title_rect)

        font = pygame.font.Font(None, 36)
        labels = [
            ("Difficulté :", (150, 180)),
            ("Vitesse du Jeu :", (150, 240)),
            ("Didacticiel :", (150, 300)),
            ("Notifications :", (150, 360))
        ]

        for text, pos in labels:
            label_surf = font.render(text, True, TEXT_COLOR)
            label_rect = label_surf.get_rect(midleft=pos)
            screen.blit(label_surf, label_rect)

        difficulty_selector.draw(screen, time)
        game_speed_slider.draw(screen, time)
        tutorial_toggle.draw(screen, time)
        notifications_toggle.draw(screen, time)

        back_rect = pygame.Rect(50, 520, 200, 50)
        pygame.draw.rect(screen, BUTTON_COLOR, back_rect, border_radius=10)
        back_text = font.render("Retour", True, TEXT_COLOR)
        back_text_rect = back_text.get_rect(center=back_rect.center)
        screen.blit(back_text, back_text_rect)

        pygame.display.flip()
        clock.tick(60)

class KeyBindButton:
    """Bouton pour la configuration des touches avec effets visuels."""
    def __init__(self, x, y, width, height, key, is_alternative=False):
        self.rect = pygame.Rect(x, y, width, height)
        self.key = key
        self.is_alternative = is_alternative
        self.hover = 0
        self.listening = False
        self.pulse = 0

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)
        self.pulse = (math.sin(time * 0.005) + 1) * 0.5 if self.listening else 0

        base_color = [int(c1 + (c2 - c1) * self.hover) for c1, c2 in zip(BUTTON_COLOR, BUTTON_HOVER_COLOR)]
        glow_radius = 10 if self.listening else 5
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_color = (*ACCENT_COLOR, alpha) if self.listening else (*base_color, alpha)
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, glow_color, glow_rect, border_radius=10)

        pygame.draw.rect(surface, base_color, self.rect, border_radius=10)
        border_color = ACCENT_COLOR if self.listening else (169, 169, 169)
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=10)

        font = pygame.font.Font(None, 32)
        text = "..." if self.listening else (self.key if self.key else "Non assigné")
        text_color = ACCENT_COLOR if self.listening else TEXT_COLOR
        text_surf = font.render(text, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)

        if self.listening:
            text_rect.y += math.sin(time * 0.01) * 3

        surface.blit(text_surf, text_rect)

def draw_background_grid(surface, time):
    """Dessine une grille en arrière-plan pour l'écran des contrôles."""
    cell_size = 50
    offset = (time * 0.5) % cell_size

    for y in range(0, SCREEN_HEIGHT + cell_size, cell_size):
        alpha = int(20 + math.sin(y * 0.01 + time * 0.001) * 10)
        pygame.draw.line(surface, (*GRID_COLOR, alpha), (0, y + offset), (SCREEN_WIDTH, y + offset))

    for x in range(0, SCREEN_WIDTH + cell_size, cell_size):
        alpha = int(20 + math.sin(x * 0.01 + time * 0.001) * 10)
        pygame.draw.line(surface, (*GRID_COLOR, alpha), (x + offset, 0), (x + offset, SCREEN_HEIGHT))

def draw_section_header(surface, text, x, y, width):
    """Dessine un en-tête de section avec une ligne décorative."""
    font = pygame.font.Font(None, 36)
    text_surf = font.render(text, True, TEXT_COLOR)
    text_rect = text_surf.get_rect(centerx=x + width // 2, centery=y)

    line_y = y + text_rect.height // 2
    pygame.draw.line(surface, ACCENT_COLOR, (x, line_y), (x + width, line_y), 2)

    padding = 10
    bg_rect = text_rect.inflate(padding * 2, padding)
    bg_rect.centerx = x + width // 2
    pygame.draw.rect(surface, BACKGROUND_COLOR, bg_rect)

    surface.blit(text_surf, text_rect)

# def controls_options_screen():
#     """Écran des options de contrôles pour configurer les touches."""
#     clock = pygame.time.Clock()
#     time = 0
#
#     control_buttons = [
#         ("Mettre en pause", [
#             KeyBindButton(380, 220, 150, 40, "Échap"),
#             KeyBindButton(580, 220, 150, 40, "", True)
#         ]),
#         ("Afficher/Masquer Infos Pays", [
#             KeyBindButton(380, 290, 150, 40, "Espace"),
#             KeyBindButton(580, 290, 150, 40, "", True)
#         ]),
#         ("Ouvrir Menu Améliorations", [
#             KeyBindButton(380, 360, 150, 40, "A"),
#             KeyBindButton(580, 360, 150, 40, "", True)
#         ])
#     ]
#
#     back_button = pygame.Rect(50, 520, 200, 50)
#
#     while True:
#         time += 1
#         screen.fill(BACKGROUND_COLOR)
#         draw_background_grid(screen, time)
#
#         font_title = pygame.font.Font(None, 64)
#         title_text = "Options des Contrôles"
#     title_y = 100 + math.sin(time * 0.005) * 3
#
#     shadow_surf = font_title.render(title_text, True, (0, 0, 0))
#     shadow_rect = shadow_surf.get_rect(center=(SCREEN_WIDTH // 2 + 2, title_y + 2))
#     screen.blit(shadow_surf, shadow_rect)
#
#     title_surf = font_title.render(title_text, True, TEXT_COLOR)
#     title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, title_y))
#     screen.blit(title_surf, title_rect)
#
#     headers = [("Action", 100), ("Touche", 400), ("Alternative", 600)]
#     for text, x in headers:
#         draw_section_header(screen, text, x - 50, 180, 100)
#
#     for i, (action, buttons) in enumerate(control_buttons):
#         action_y = 240 + i * 70
#         text_surf = pygame.font.Font(None, 36).render(action, True, TEXT_COLOR)
#         text_rect = text_surf.get_rect(left=100, centery=action_y)
#         screen.blit(text_surf, text_rect)
#
#         for button in buttons:
#             button.draw(screen, time)
#
#     hover = back_button.collidepoint(pygame.mouse.get_pos())
#     color = BUTTON_HOVER_COLOR if hover else BUTTON_COLOR
#     pygame.draw.rect(screen, color, back_button, border_radius=10)
#     pygame.draw.rect(screen, ACCENT_COLOR, back_button, 2, border_radius=10)
#
#     back_text = pygame.font.Font(None, 36).render("Retour", True, TEXT_COLOR)
#     back_rect = back_text.get_rect(center=back_button.center)
#     screen.blit(back_text, back_rect)
#
#     pygame.display.flip()
#     clock.tick(60)
#
#     for event in pygame.event.get():
#         if event.type == pygame.QUIT:
#             pygame.quit()
#             sys.exit()
#         if event.type == pygame.MOUSEBUTTONDOWN:
#             if back_button.collidepoint(event.pos):
#                 return
#             for _, buttons in control_buttons:
#                 for button in buttons:
#                     if button.rect.collidepoint(event.pos):
#                         button.listening = True
#         if event.type == pygame.KEYDOWN:
#             for _, buttons in control_buttons:
#                 for button in buttons:
#                     if button.listening:
#                         button.key = pygame.key.name(event.key).upper()
#                         button.listening = False
def controls_options_screen():
    clock = pygame.time.Clock()
    time = 0

    # Création des boutons de contrôle
    control_buttons = [
        ("Mettre en pause", [
            KeyBindButton(380, 220, 150, 40, "Échap"),
            KeyBindButton(580, 220, 150, 40, "", True)
        ]),
        ("Afficher/Masquer Infos Pays", [
            KeyBindButton(380, 290, 150, 40, "Espace"),
            KeyBindButton(580, 290, 150, 40, "", True)
        ]),
        ("Ouvrir Menu Améliorations", [
            KeyBindButton(380, 360, 150, 40, "A"),
            KeyBindButton(580, 360, 150, 40, "", True)
        ])
    ]

    # Bouton retour
    back_button = pygame.Rect(50, 520, 200, 50)

    while True:
        time += 1
        screen.fill(BACKGROUND_COLOR)

        # Grille d'arrière-plan
        draw_background_grid(screen, time)

        # Titre avec effet de lueur
        font_title = pygame.font.Font(None, 64)
        title_text = "Options des Contrôles"
        title_y = 100 + math.sin(time * 0.005) * 3

        # Ombre du titre
        shadow_surf = font_title.render(title_text, True, (0, 0, 0))
        shadow_rect = shadow_surf.get_rect(center=(SCREEN_WIDTH//2 + 2, title_y + 2))
        screen.blit(shadow_surf, shadow_rect)

        # Titre principal
        title_surf = font_title.render(title_text, True, TEXT_COLOR)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, title_y))
        screen.blit(title_surf, title_rect)

        # En-têtes de colonnes
        headers = [("Action", 100), ("Touche", 400), ("Alternative", 600)]
        for text, x in headers:
            draw_section_header(screen, text, x-50, 180, 100)

        # Contrôles
        for i, (action, buttons) in enumerate(control_buttons):
            # Action
            action_y = 240 + i * 70
            text_surf = pygame.font.Font(None, 36).render(action, True, TEXT_COLOR)
            text_rect = text_surf.get_rect(left=100, centery=action_y)
            screen.blit(text_surf, text_rect)

            # Boutons
            for button in buttons:
                button.draw(screen, time)

        # Bouton retour
        hover = back_button.collidepoint(pygame.mouse.get_pos())
        color = BUTTON_HOVER_COLOR if hover else BUTTON_COLOR
        pygame.draw.rect(screen, color, back_button, border_radius=10)
        pygame.draw.rect(screen, ACCENT_COLOR, back_button, 2, border_radius=10)

        back_text = pygame.font.Font(None, 36).render("Retour", True, TEXT_COLOR)
        back_rect = back_text.get_rect(center=back_button.center)
        screen.blit(back_text, back_rect)

        pygame.display.flip()
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if back_button.collidepoint(event.pos):
                    return
                for _, buttons in control_buttons:
                    for button in buttons:
                        if button.rect.collidepoint(event.pos):
                            button.listening = True
            if event.type == pygame.KEYDOWN:
                for _, buttons in control_buttons:
                    for button in buttons:
                        if button.listening:
                            button.key = pygame.key.name(event.key).upper()
                            button.listening = False

class SaveSlot:
    """Slot de sauvegarde avec affichage des informations de la partie."""
    def __init__(self, x, y, width, height, save_data):
        self.rect = pygame.Rect(x, y, width, height)
        self.save_data = save_data
        self.hover = 0
        self.selected = False
        self.animation = 0

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)

        base_color = CATASTROPHE_COLORS.get(self.save_data['catastrophe'], BUTTON_COLOR)
        glow_radius = 10 + math.sin(time * 0.003) * 2
        for i in range(int(glow_radius)):
            alpha = int(60 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*base_color, alpha), glow_rect, border_radius=15)

        color = [int(c1 + (c2 - c1) * self.hover) for c1, c2 in zip(BUTTON_COLOR, BUTTON_HOVER_COLOR)]
        pygame.draw.rect(surface, color, self.rect, border_radius=15)

        border_color = (*base_color, 255) if self.selected else (*base_color, 150)
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=15)

        font = pygame.font.Font(None, 36)
        small_font = pygame.font.Font(None, 24)

        title = f"Sauvegarde {self.save_data['id']}"
        title_surf = font.render(title, True, TEXT_COLOR)
        surface.blit(title_surf, (self.rect.x + 20, self.rect.y + 10))

        icon_size = 30
        icon_rect = pygame.Rect(self.rect.x + 20, self.rect.y + 45, icon_size, icon_size)
        pygame.draw.rect(surface, base_color, icon_rect, border_radius=5)

        info_x = self.rect.x + 60
        info_y = self.rect.y + 45
        catastrophe_text = f"Catastrophe : {self.save_data['catastrophe']}"
        catastrophe_surf = small_font.render(catastrophe_text, True, base_color)
        surface.blit(catastrophe_surf, (info_x, info_y))

        tour_text = f"Tour : {self.save_data['tour']}"
        tour_surf = small_font.render(tour_text, True, TEXT_COLOR)
        surface.blit(tour_surf, (info_x + 250, info_y))

        date_text = f"Dernière sauvegarde : {self.save_data['date']}"
        date_surf = small_font.render(date_text, True, TEXT_COLOR)
        surface.blit(date_surf, (info_x + 400, info_y))

class ButtonHover:
    """Bouton standard avec effet de survol."""
    def __init__(self, x, y, width, height, text):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.hover = 0

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)

        glow_radius = 8 + math.sin(time * 0.003) * 2
        for i in range(int(glow_radius)):
            alpha = int(60 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (100, 100, 100, alpha), glow_rect, border_radius=10)

        color = [int(c1 + (c2 - c1) * self.hover) for c1, c2 in zip(BUTTON_COLOR, BUTTON_HOVER_COLOR)]
        pygame.draw.rect(surface, color, self.rect, border_radius=10)
        pygame.draw.rect(surface, TEXT_COLOR, self.rect, 2, border_radius=10)

        font = pygame.font.Font(None, 36)
        text_surf = font.render(self.text, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

def load_game_screen():
    """Écran de chargement de partie avec les slots de sauvegarde disponibles."""
    clock = pygame.time.Clock()

    saves = [
        {'id': 1, 'catastrophe': 'Eau', 'tour': 25, 'date': '23/12/2024 15:30'},
        {'id': 2, 'catastrophe': 'Feu', 'tour': 12, 'date': '23/12/2024 14:45'},
        {'id': 3, 'catastrophe': 'Air', 'tour': 48, 'date': '22/12/2024 20:15'}
    ]

    save_slots = [SaveSlot(150, 180 + i * 100, 900, 80, save) for i, save in enumerate(saves)]
    load_button = Button(SCREEN_WIDTH // 2 - 100, 520, 200, 50, "Charger")
    back_button = Button(50, 520, 200, 50, "Retour")
    selected_save = None
    time = 0

    while True:
        time += 1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = event.pos
                if back_button.rect.collidepoint(mouse_pos):
                    return
                if load_button.rect.collidepoint(mouse_pos) and selected_save:
                    print(f"Chargement de la sauvegarde {selected_save['id']}")
                for slot in save_slots:
                    if slot.rect.collidepoint(mouse_pos):
                        for s in save_slots:
                            s.selected = False
                        slot.selected = True
                        selected_save = slot.save_data

        screen.fill(BACKGROUND_COLOR)
        draw_background_grid(screen, time)

        font_title = pygame.font.Font(None, 64)
        title_text = "Charger une Partie"
        title_shadow = font_title.render(title_text, True, (30, 30, 30))
        title = font_title.render(title_text, True, TEXT_COLOR)
        shadow_offset = abs(math.sin(time * 0.002)) * 3 + 2
        screen.blit(title_shadow, (SCREEN_WIDTH // 2 - title.get_width() // 2 + shadow_offset, 100 + shadow_offset))
        screen.blit(title, (SCREEN_WIDTH // 2 - title.get_width() // 2, 100))

        for slot in save_slots:
            slot.draw(screen, time)

        load_button.draw(screen, time)
        back_button.draw(screen, time)

        pygame.display.flip()
        clock.tick(60)

class TextInput:
    """Champ de saisie de texte pour la sauvegarde de la partie."""
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = ""
        self.active = False
        self.cursor_visible = True
        self.cursor_timer = 0
        self.placeholder = "Entrez un nom de sauvegarde..."
        self.animation = 0.0
        self.shake_offset = [0, 0]
        self.error = False
        self.last_key_time = 0
        self.key_cooldown = 50

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            if self.active:
                self.animation = 0.0

        if self.active and event.type == pygame.KEYDOWN:
            current_time = global_time.time() * 1000
            if current_time - self.last_key_time > self.key_cooldown:
                if event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                    self.shake_offset = [-3, 0]
                elif event.key == pygame.K_RETURN:
                    self.active = False
                elif len(self.text) < 30:
                    self.text += event.unicode
                    self.animation = 0.0
                self.last_key_time = current_time

    def update(self, current_time):
        if current_time % 1000 < 500:
            self.cursor_visible = True
        else:
            self.cursor_visible = False

        if self.active:
            self.animation = min(1.0, self.animation + 0.1)
        else:
            self.animation = max(0.0, self.animation - 0.1)

        self.shake_offset[0] *= 0.8
        self.shake_offset[1] *= 0.8

    def draw(self, surface, current_time):
        glow_rect = self.rect.inflate(4, 4)
        glow_color = (*ACCENT_COLOR, int(128 * self.animation))
        pygame.draw.rect(surface, glow_color, glow_rect, border_radius=10)

        pygame.draw.rect(surface, INPUT_BG_COLOR, self.rect, border_radius=8)

        border_color = [int(c1 + (c2 - c1) * self.animation) for c1, c2 in zip(BUTTON_COLOR, ACCENT_COLOR)]
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=8)

        font = pygame.font.Font(None, 36)
        if self.text:
            text_surface = font.render(self.text, True, TEXT_COLOR)
        else:
            text_surface = font.render(self.placeholder, True, PLACEHOLDER_COLOR)

        text_pos = (self.rect.x + 10 + self.shake_offset[0],
                    self.rect.centery - text_surface.get_height() // 2 + self.shake_offset[1])
        surface.blit(text_surface, text_pos)

        if self.active and self.cursor_visible:
            cursor_x = self.rect.x + 10 + font.size(self.text)[0]
            cursor_color = (*TEXT_COLOR, int(255 * (0.5 + math.sin(current_time * 0.01) * 0.5)))
            pygame.draw.line(surface, cursor_color, (cursor_x, self.rect.y + 10), (cursor_x, self.rect.bottom - 10), 2)

class SaveSlot:
    """Slot de sauvegarde avec affichage des informations de la partie."""
    def __init__(self, x, y, width, height, save_data=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.save_data = save_data
        self.hover = 0.0
        self.selected = False

    def draw(self, surface, current_time):
        hover_color = (*BUTTON_HOVER_COLOR, int(255 * self.hover))
        pygame.draw.rect(surface, BUTTON_COLOR, self.rect, border_radius=10)
        pygame.draw.rect(surface, hover_color, self.rect, border_radius=10)

        if self.selected:
            border_color = (ACCENT_COLOR[0], ACCENT_COLOR[1], ACCENT_COLOR[2], int(128 + math.sin(current_time * 0.01) * 64))
            pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=10)

        if self.save_data:
            font = pygame.font.Font(None, 32)
            name_text = font.render(self.save_data["name"], True, TEXT_COLOR)
            date_text = font.render(self.save_data["date"], True, (*TEXT_COLOR, 180))
            surface.blit(name_text, (self.rect.x + 20, self.rect.y + 15))
            surface.blit(date_text, (self.rect.x + 20, self.rect.y + 45))

def save_game_screen():
    """Écran de sauvegarde de la partie avec un champ de saisie et des slots de sauvegarde."""
    clock = pygame.time.Clock()
    text_input = TextInput(150, 230, 500, 50)

    save_slots = [
        SaveSlot(150, 320 + i * 80, 500, 70, {"name": f"Sauvegarde {i+1}", "date": f"2024/12/{20+i} 14:30"}) for i in range(3)
    ]

    current_time = 0

    while True:
        current_time += 1

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            text_input.handle_event(event)

            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = event.pos

                for slot in save_slots:
                    if slot.rect.collidepoint(mouse_pos):
                        text_input.text = slot.save_data["name"]
                        slot.selected = True
                        for other_slot in save_slots:
                            if other_slot != slot:
                                other_slot.selected = False

                if 50 <= mouse_pos[0] <= 250 and 520 <= mouse_pos[1] <= 570:
                    return "pause_menu"

        text_input.update(current_time)

        mouse_pos = pygame.mouse.get_pos()
        for slot in save_slots:
            if slot.rect.collidepoint(mouse_pos):
                slot.hover = min(1.0, slot.hover + 0.1)
            else:
                slot.hover = max(0.0, slot.hover - 0.1)

        screen.fill(BACKGROUND_COLOR)

        title = "Sauvegarder la Partie"
        title_font = pygame.font.Font(None, 64)
        for offset in range(3):
            alpha = 255 - offset * 50
            title_surf = title_font.render(title, True, (*ACCENT_COLOR, alpha))
            screen.blit(title_surf, (SCREEN_WIDTH // 2 - title_surf.get_width() // 2 + offset, 100 + offset))
        title_surf = title_font.render(title, True, TEXT_COLOR)
        screen.blit(title_surf, (SCREEN_WIDTH // 2 - title_surf.get_width() // 2, 100))

        font = pygame.font.Font(None, 36)
        label = font.render("Nom de la sauvegarde :", True, TEXT_COLOR)
        screen.blit(label, (150, 200))

        text_input.draw(screen, current_time)

        for slot in save_slots:
            slot.draw(screen, current_time)

        mouse_pos = pygame.mouse.get_pos()
        save_hover = 300 <= mouse_pos[0] <= 500 and 620 <= mouse_pos[1] <= 670
        cancel_hover = 50 <= mouse_pos[0] <= 250 and 520 <= mouse_pos[1] <= 570

        for button_data in [((300, 620, 200, 50), "Sauvegarder", save_hover), ((50, 520, 200, 50), "Annuler", cancel_hover)]:
            rect, text, hovering = button_data
            if hovering:
                glow_rect = pygame.Rect(*rect).inflate(8, 8)
                pygame.draw.rect(screen, (*ACCENT_COLOR, 100), glow_rect, border_radius=10)

            color = BUTTON_HOVER_COLOR if hovering else BUTTON_COLOR
            pygame.draw.rect(screen, color, rect, border_radius=8)
            pygame.draw.rect(screen, ACCENT_COLOR, rect, 2, border_radius=8)

            text_surf = font.render(text, True, TEXT_COLOR)
            text_rect = text_surf.get_rect(center=(rect[0] + rect[2] // 2, rect[1] + rect[3] // 2))
            screen.blit(text_surf, text_rect)

        pygame.display.flip()
        clock.tick(60)

class Particle:
    """Particule individuelle pour l'écran de victoire de la catastrophe."""
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.size = random.uniform(1, 4)
        self.speed = random.uniform(1, 3)
        self.life = 255
        self.decay = random.uniform(0.5, 2)
        self.color = VICTORY_RED
        self.angle = random.uniform(0, math.pi * 2)

    def update(self):
        self.y += math.cos(self.angle) * self.speed
        self.x += math.sin(self.angle) * self.speed
        self.life -= self.decay
        return self.life > 0

    def draw(self, surface):
        alpha = int(self.life)
        gfxdraw.filled_circle(surface, int(self.x), int(self.y), int(self.size), (*self.color, alpha))

class VictoryScreen:
    """Écran de victoire pour la catastrophe avec effets visuels et statistiques."""
    def __init__(self):
        self.particles = []
        self.time = 0
        self.stats = {'turns': 58, 'population': 0, 'destruction': 100, 'time_elapsed': "2:15:30"}

    def create_particles(self):
        if random.random() < 0.3:
            x = random.randint(0, SCREEN_WIDTH)
            y = random.randint(0, SCREEN_HEIGHT)
            self.particles.append(Particle(x, y))

    def draw_victory_text(self, surface, time):
        title = "VICTOIRE"
        title_font = pygame.font.Font(None, 120)

        current_x = SCREEN_WIDTH // 2 - title_font.size(title)[0] // 2
        for i, char in enumerate(title):
            scale = 1 + math.sin(time * 0.005 + i * 0.5) * 0.2
            angle = math.sin(time * 0.003 + i * 0.4) * 5
            char_surf = title_font.render(char, True, VICTORY_RED)
            scaled_size = (int(char_surf.get_width() * scale), int(char_surf.get_height() * scale))
            char_surf = pygame.transform.scale(char_surf, scaled_size)
            char_surf = pygame.transform.rotate(char_surf, angle)
            glow_surf = title_font.render(char, True, DARK_RED)
            glow_surf = pygame.transform.scale(glow_surf, scaled_size)
            glow_surf = pygame.transform.rotate(glow_surf, angle)
            char_rect = char_surf.get_rect(center=(current_x + title_font.size(char)[0] // 2, 200 + math.sin(time * 0.004 + i) * 10))

            for offset in range(3):
                offset_rect = char_rect.copy()
                offset_rect.x += math.sin(time * 0.01) * 2
                offset_rect.y += math.cos(time * 0.01) * 2
                glow_surf.set_alpha(100 - offset * 30)
                surface.blit(glow_surf, offset_rect)

            surface.blit(char_surf, char_rect)
            current_x += title_font.size(char)[0]

    def draw_stats(self, surface, time):
        stats_font = pygame.font.Font(None, 36)
        y_pos = 380

        stats_text = [
            f"Nombre de tours : {self.stats['turns']}",
            f"Population restante : {self.stats['population']}",
            f"Destruction totale : {self.stats['destruction']}%",
            f"Temps écoulé : {self.stats['time_elapsed']}"
        ]

        for i, text in enumerate(stats_text):
            alpha = min(255, time * 2 - i * 100)
            offset = math.sin(time * 0.005 + i * 0.5) * 5
            shadow_surf = stats_font.render(text, True, (0, 0, 0))
            shadow_surf.set_alpha(alpha // 2)
            surface.blit(shadow_surf, (SCREEN_WIDTH // 2 - shadow_surf.get_width() // 2 + 2, y_pos + i * 40 + 2))
            text_surf = stats_font.render(text, True, TEXT_COLOR)
            text_surf.set_alpha(alpha)
            surface.blit(text_surf, (SCREEN_WIDTH // 2 - text_surf.get_width() // 2 + offset, y_pos + i * 40))

    def draw_background_effect(self, surface, time):
        for i in range(20):
            progress = (time * 0.5 + i) % 20 / 20
            y = SCREEN_HEIGHT * progress
            alpha = int(255 * (1 - progress))
            pygame.draw.line(surface, (*DARK_RED, alpha // 4), (0, y), (SCREEN_WIDTH, y))
            for x in range(0, SCREEN_WIDTH, 100):
                end_y = SCREEN_HEIGHT // 2 + (y - SCREEN_HEIGHT // 2) * 1.2
                pygame.draw.line(surface, (*DARK_RED, alpha // 4), (x, y), (x, end_y))

    def run(self):
        clock = pygame.time.Clock()
        buttons = {'replay': pygame.Rect(450, 550, 300, 50), 'menu': pygame.Rect(450, 620, 300, 50)}
        subtitle_font = pygame.font.Font(None, 48)
        button_font = pygame.font.Font(None, 36)

        while True:
            self.time += 1
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if buttons['replay'].collidepoint(event.pos):
                        return "replay"
                    elif buttons['menu'].collidepoint(event.pos):
                        return "menu"

            self.create_particles()
            self.particles = [p for p in self.particles if p.update()]

            screen.fill(BACKGROUND_COLOR)
            self.draw_background_effect(screen, self.time)

            for particle in self.particles:
                particle.draw(screen)

            self.draw_victory_text(screen, self.time)

            subtitle = "La Catastrophe a Triomphé"
            alpha = int(128 + math.sin(self.time * 0.05) * 64)
            subtitle_surf = subtitle_font.render(subtitle, True, VICTORY_RED)
            subtitle_surf.set_alpha(alpha)
            subtitle_rect = subtitle_surf.get_rect(center=(SCREEN_WIDTH // 2, 300))
            screen.blit(subtitle_surf, subtitle_rect)

            self.draw_stats(screen, self.time)

            mouse_pos = pygame.mouse.get_pos()
            for text, button in zip(['Rejouer', 'Menu Principal'], buttons.values()):
                hover = button.collidepoint(mouse_pos)
                glow_color = VICTORY_RED if hover else DARK_RED
                for i in range(5):
                    glow_rect = button.inflate(i * 2, i * 2)
                    pygame.draw.rect(screen, (*glow_color, 50 - i * 10), glow_rect, border_radius=10)

                pygame.draw.rect(screen, BACKGROUND_COLOR, button, border_radius=8)
                pygame.draw.rect(screen, VICTORY_RED, button, 2, border_radius=8)

                text_surf = button_font.render(text, True, TEXT_COLOR)
                text_rect = text_surf.get_rect(center=button.center)
                if hover:
                    text_rect.y += math.sin(self.time * 0.1) * 2
                screen.blit(text_surf, text_rect)

            pygame.display.flip()
            clock.tick(60)

def catastrophe_victory_screen():
    """Fonction pour lancer l'écran de victoire de la catastrophe."""
    victory_screen = VictoryScreen()
    return victory_screen.run()

class VictoryParticle:
    """Particule individuelle pour l'écran de victoire de l'humanité."""
    def __init__(self):
        self.reset()
        self.y = random.randint(0, SCREEN_HEIGHT)

    def reset(self):
        self.x = random.randint(0, SCREEN_WIDTH)
        self.y = -10
        self.speed = random.uniform(2, 5)
        self.size = random.uniform(2, 4)
        self.color = random.choice([VICTORY_COLOR, GOLDEN_COLOR])
        self.alpha = random.randint(100, 200)

    def update(self, time):
        self.y += self.speed
        self.x += math.sin(time * 0.01 + self.y * 0.1) * 0.5
        self.alpha = int(150 + math.sin(time * 0.005) * 50)
        if self.y > SCREEN_HEIGHT:
            self.reset()

    def draw(self, surface):
        gfxdraw.filled_circle(surface, int(self.x), int(self.y), int(self.size), (*self.color, self.alpha))

class AnimatedText:
    """Texte animé pour l'écran de victoire de l'humanité."""
    def __init__(self, text, font, base_y):
        self.text = text
        self.font = font
        self.base_y = base_y
        self.chars = []
        self.init_chars()

    def init_chars(self):
        x = SCREEN_WIDTH // 2
        for i, char in enumerate(self.text):
            self.chars.append({
                'char': char,
                'x': x,
                'y': self.base_y,
                'offset': random.uniform(0, math.pi * 2),
                'speed': random.uniform(0.03, 0.05)
            })
            x += self.font.size(char)[0]

    def update(self, time):
        center_x = SCREEN_WIDTH // 2
        total_width = sum(self.font.size(char['char'])[0] for char in self.chars)
        current_x = center_x - total_width // 2
        for char in self.chars:
            char['x'] = current_x
            char['y'] = self.base_y + math.sin(time * char['speed'] + char['offset']) * 5
            current_x += self.font.size(char['char'])[0]

    def draw(self, surface, time):
        for char in self.chars:
            glow_color = VICTORY_COLOR
            glow_alpha = int(128 + math.sin(time * 0.01) * 64)
            for offset in range(3):
                glow_surf = self.font.render(char['char'], True, glow_color)
                glow_surf.set_alpha(glow_alpha // (offset + 1))
                for dx, dy in [(offset, 0), (-offset, 0), (0, offset), (0, -offset)]:
                    surface.blit(glow_surf, (char['x'] + dx, char['y'] + dy))

            text_surf = self.font.render(char['char'], True, TEXT_COLOR)
            surface.blit(text_surf, (char['x'], char['y']))

class VictoryButton:
    """Bouton stylisé pour l'écran de victoire de l'humanité."""
    def __init__(self, x, y, width, height, text):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.hover = 0
        self.pulse = 0

def draw(self, surface, time):
    mouse_pos = pygame.mouse.get_pos()
    hover = self.rect.collidepoint(mouse_pos)

    self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)
    self.pulse = math.sin(time * 0.005) * 4

    glow_radius = 10 + self.pulse
    for i in range(int(glow_radius)):
        alpha = int(100 * (1 - i / glow_radius))
        glow_rect = self.rect.inflate(i * 2, i * 2)
        glow_color = VICTORY_COLOR if hover else (100, 100, 100)
        pygame.draw.rect(surface, (*glow_color, alpha), glow_rect, border_radius=15)

    color = (80, 180, 100) if hover else (60, 66, 77)
    pygame.draw.rect(surface, color, self.rect, border_radius=15)
    pygame.draw.rect(surface, VICTORY_COLOR, self.rect, 2, border_radius=15)

    font = pygame.font.Font(None, 36)
    if hover:
        for offset in [-1, 1]:
            text_glow = font.render(self.text, True, VICTORY_COLOR)
            text_rect = text_glow.get_rect(center=(self.rect.centerx + offset, self.rect.centery + offset))
            surface.blit(text_glow, text_rect)

    text_surf = font.render(self.text, True, TEXT_COLOR)
    text_rect = text_surf.get_rect(center=self.rect.center)
    surface.blit(text_surf, text_rect)

def draw_earth(surface, time):
    """Dessine une Terre stylisée avec une animation."""
    center_x, center_y = SCREEN_WIDTH // 2, 120
    radius = 60

    for i in range(20):
        alpha = int(100 * (1 - i / 20))
        glow_radius = radius + i * 2
        glow_color = (*VICTORY_COLOR, alpha)
        pygame.draw.circle(surface, glow_color, (center_x, center_y), glow_radius)

    pygame.draw.circle(surface, (100, 200, 255), (center_x, center_y), radius)

    for i in range(5):
        angle = time * 0.001 + i * math.pi / 2.5
        x = center_x + math.cos(angle) * radius * 0.7
        y = center_y + math.sin(angle) * radius * 0.7
        size = random.randint(10, 20)
        pygame.draw.circle(surface, (64, 209, 124), (int(x), int(y)), size)

def humanity_victory_screen():
    """Écran de victoire pour l'humanité avec effets visuels et statistiques."""
    clock = pygame.time.Clock()
    particles = [VictoryParticle() for _ in range(100)]

    title = AnimatedText("VICTOIRE DE L'HUMANITÉ", pygame.font.Font(None, 72), 200)
    subtitle = AnimatedText("L'équilibre écologique est atteint!", pygame.font.Font(None, 48), 300)

    retry_button = VictoryButton(450, 550, 300, 50, "Réessayer")
    menu_button = VictoryButton(450, 620, 300, 50, "Menu Principal")

    time = 0
    stats_fade_in = 0

    while True:
        time += 1
        stats_fade_in = min(255, stats_fade_in + 2)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_pos = event.pos
                if retry_button.rect.collidepoint(mouse_pos):
                    print("Réessayer")
                    return "new_game"
                elif menu_button.rect.collidepoint(mouse_pos):
                    print("Menu Principal")
                    return "main_menu"

        for particle in particles:
            particle.update(time)
        title.update(time)
        subtitle.update(time)

        screen.fill(BACKGROUND_COLOR)

        for particle in particles:
            particle.draw(screen)

        draw_earth(screen, time)
        title.draw(screen, time)
        subtitle.draw(screen, time)

        font = pygame.font.Font(None, 36)
        stats_texts = [
            f"Nombre de tours : 85",
            f"Population restante : 4,500,000,000"
        ]
        for i, text in enumerate(stats_texts):
            stats_surf = font.render(text, True, TEXT_COLOR)
            stats_surf.set_alpha(stats_fade_in)
            stats_rect = stats_surf.get_rect(center=(SCREEN_WIDTH // 2, 400 + i * 40))
            screen.blit(stats_surf, stats_rect)

        retry_button.draw(screen, time)
        menu_button.draw(screen, time)

        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    main_menu()