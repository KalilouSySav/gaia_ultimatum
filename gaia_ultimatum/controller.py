import pygame
import sys

# Initialisation de Pygame
pygame.init()

# Dimensions de la fenêtre
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800

# Couleurs
BACKGROUND_COLOR = (240, 240, 240)
BUTTON_COLOR = (211, 211, 211)
BUTTON_BORDER_COLOR = (169, 169, 169)
TEXT_COLOR = (0, 0, 0)

# Police de caractères
FONT = pygame.font.SysFont("Arial", 36)
TITLE_FONT = pygame.font.SysFont("Arial", 72, bold=True)

# Création de la fenêtre
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Gaia Ultimatum")

def draw_text(text, font, color, surface, x, y):
    textobj = font.render(text, True, color)
    textrect = textobj.get_rect()
    textrect.center = (x, y)
    surface.blit(textobj, textrect)

def draw_button(x, y, width, height, color, border_color, text, font, text_color, surface):
    pygame.draw.rect(surface, color, (x, y, width, height), border_radius=10)
    pygame.draw.rect(surface, border_color, (x, y, width, height), 2, border_radius=10)
    draw_text(text, font, text_color, surface, x + width / 2, y + height / 2)

import pygame
import math
import random
from pygame import gfxdraw
import colorsys

# Constantes améliorées
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (15, 18, 25)
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (45, 50, 60)
BUTTON_HOVER_COLOR = (65, 70, 85)
ACCENT_COLOR = (178, 34, 34)
ACCENT_COLOR_2 = (255, 89, 89)

class ParticleSystem:
    def __init__(self):
        self.particles = []
        self.emitters = [(SCREEN_WIDTH // 4, 0), (SCREEN_WIDTH // 2, 0),
                         (3 * SCREEN_WIDTH // 4, 0)]

        for _ in range(150):
            emitter = random.choice(self.emitters)
            self.particles.append({
                'x': emitter[0] + random.randint(-100, 100),
                'y': random.randint(0, SCREEN_HEIGHT),
                'size': random.uniform(0.5, 3),
                'speed': random.uniform(0.5, 2),
                'angle': random.uniform(0, math.pi * 2),
                'color': random.choice([ACCENT_COLOR, ACCENT_COLOR_2]),
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
            gfxdraw.filled_circle(surface, int(p['x']), int(p['y']),
                                  int(p['size']), (*p['color'], p['alpha']))

class MenuButton:
    def __init__(self, x, y, width, height, text, action):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.action = action
        self.hover = 0
        self.animation = 0
        self.shake_offset = [0, 0]
        self.shake_time = 0

    def update_shake(self, time):
        if self.hover > 0.5:
            intensity = 0.5 * self.hover
            self.shake_offset = [
                math.sin(time * 0.1) * intensity,
                math.cos(time * 0.1) * intensity
            ]
        else:
            self.shake_offset = [0, 0]

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)

        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)
        self.update_shake(time)

        # Position avec tremblement
        rect = self.rect.copy()
        rect.x += self.shake_offset[0]
        rect.y += self.shake_offset[1]

        # Effet de pulsation
        pulse = math.sin(time * 0.003) * 4

        # Couleur dynamique
        hue = (math.sin(time * 0.001) * 0.05 + 0.6) % 1.0
        dynamic_color = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, 0.6, 0.8))

        # Effet de lueur
        glow_radius = 15 + pulse * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_rect = rect.inflate(i * 2, i * 2)
            if hover:
                glow_color = (*dynamic_color, alpha)
            else:
                glow_color = (*BUTTON_COLOR, alpha)
            pygame.draw.rect(surface, glow_color, glow_rect, border_radius=15)

        # Bouton principal
        color = [int(c1 + (c2 - c1) * self.hover)
                 for c1, c2 in zip(BUTTON_COLOR, BUTTON_HOVER_COLOR)]
        pygame.draw.rect(surface, color, rect, border_radius=15)

        # Bordure animée
        border_color = dynamic_color if hover else ACCENT_COLOR
        pygame.draw.rect(surface, border_color, rect, 2, border_radius=15)

        # Texte avec effets
        font = pygame.font.Font(None, 36)
        shadow_offset = 2

        # Ombre du texte
        shadow_surf = font.render(self.text, True, (0, 0, 0))
        shadow_rect = shadow_surf.get_rect(center=(rect.centerx + shadow_offset,
                                                   rect.centery + shadow_offset))
        surface.blit(shadow_surf, shadow_rect)

        # Texte principal avec effet de lueur
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
    title = "GAIA ULTIMATUM"
    font = pygame.font.Font(None, 92)

    # Paramètres d'animation
    wave_height = 12
    wave_length = 0.1
    wave_speed = 0.005
    glow_intensity = int(128 + math.sin(time * 0.01) * 64)

    # Calcul de la largeur totale
    total_width = sum(font.size(char)[0] for char in title)
    start_x = SCREEN_WIDTH // 2 - total_width // 2

    # Dessin de chaque caractère
    current_x = start_x
    for i, char in enumerate(title):
        # Animation verticale
        offset_y = math.sin(time * wave_speed + i * wave_length) * wave_height
        # Animation horizontale
        offset_x = math.cos(time * wave_speed * 0.5 + i * wave_length) * 3

        char_surf = font.render(char, True, TEXT_COLOR)
        char_width = font.size(char)[0]
        x = current_x + offset_x
        y = 150 + offset_y

        # Effets de lueur multiples
        for glow_offset in range(3):
            glow_surf = font.render(char, True, ACCENT_COLOR)
            glow_surf.set_alpha(glow_intensity - glow_offset * 40)
            surface.blit(glow_surf, (x + glow_offset, y + glow_offset))
            surface.blit(glow_surf, (x - glow_offset, y - glow_offset))

        # Caractère principal
        surface.blit(char_surf, (x, y))
        current_x += char_width

def draw_background_effect(surface, time):
    # Création d'un motif de grille en perspective
    num_lines = 20
    for i in range(num_lines):
        progress = (time * 0.001 + i) % num_lines / num_lines
        y = SCREEN_HEIGHT * progress
        alpha = int(255 * (1 - progress))

        # Lignes horizontales
        start_pos = (0, y)
        end_pos = (SCREEN_WIDTH, y)
        pygame.draw.line(surface, (*ACCENT_COLOR, alpha // 4), start_pos, end_pos)

        # Lignes verticales en perspective
        for x in range(0, SCREEN_WIDTH, 100):
            vanishing_point = SCREEN_HEIGHT // 2
            start_y = y
            end_y = vanishing_point + (y - vanishing_point) * 1.2
            pygame.draw.line(surface, (*ACCENT_COLOR, alpha // 4),
                             (x, start_y), (x, end_y))

def main_menu():
    clock = pygame.time.Clock()
    particle_system = ParticleSystem()

    # Création des boutons
    button_width = 300
    button_spacing = 80
    start_y = 300
    buttons = [
        MenuButton(SCREEN_WIDTH//2 - button_width//2, start_y, button_width, 60,
                   "Nouvelle Partie", "new_game"),
        MenuButton(SCREEN_WIDTH//2 - button_width//2, start_y + button_spacing,
                   button_width, 60, "Continuer", "continue"),
        MenuButton(SCREEN_WIDTH//2 - button_width//2, start_y + button_spacing * 2,
                   button_width, 60, "Options", "options"),
        MenuButton(SCREEN_WIDTH//2 - button_width//2, start_y + button_spacing * 3,
                   button_width, 60, "Quitter", "quit")
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
                            print("Nouvelle Partie")
                        elif button.action == "continue":
                            print("Continuer")
                        elif button.action == "options":
                            print("Options")

        # Mises à jour
        particle_system.update(time)

        # Dessin
        screen.fill(BACKGROUND_COLOR)
        draw_background_effect(screen, time)
        particle_system.draw(screen)
        draw_title(screen, time)

        # Sous-titre avec effet de fondu
        font_small = pygame.font.Font(None, 28)
        subtitle = "L'avenir de la Terre est entre vos mains"
        alpha = int(128 + math.sin(time * 0.005) * 64)
        subtitle_surf = font_small.render(subtitle, True, TEXT_COLOR)
        subtitle_surf.set_alpha(alpha)
        subtitle_rect = subtitle_surf.get_rect(center=(SCREEN_WIDTH // 2, 240))
        screen.blit(subtitle_surf, subtitle_rect)

        # Dessin des boutons
        for button in buttons:
            button.draw(screen, time)

        # Version avec effet de lueur
        version_text = "v1.0.0"
        version_alpha = int(128 + math.sin(time * 0.01) * 64)
        version_surf = font_small.render(version_text, True, ACCENT_COLOR)
        version_surf.set_alpha(version_alpha)
        screen.blit(version_surf, (20, SCREEN_HEIGHT - 30))

        pygame.display.flip()
        clock.tick(60)


import pygame
import math
import sys
from pygame import gfxdraw

# Constantes des couleurs
BACKGROUND_COLOR = (40, 44, 52)
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (60, 66, 77)
BUTTON_HOVER_COLOR = (75, 83, 96)
BUTTON_BORDER_COLOR = (101, 111, 128)

# Couleurs spécifiques pour chaque élément
WATER_COLOR = (64, 164, 223)
FIRE_COLOR = (235, 83, 83)
AIR_COLOR = (188, 231, 253)
EARTH_COLOR = (141, 110, 99)
LIFE_COLOR = (92, 184, 92)

# Configuration
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
TITLE_FONT = pygame.font.Font(None, 64)
FONT = pygame.font.Font(None, 36)
DESCRIPTION_FONT = pygame.font.Font(None, 24)

class ElementButton:
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

        # Animation de pulsation
        pulse = math.sin(time * 0.005) * 4

        # Animation de survol
        if hover:
            self.animation = min(1, self.animation + 0.1)
        else:
            self.animation = max(0, self.animation - 0.1)

        # Calcul des couleurs d'interpolation
        current_color = tuple(int(c1 + (c2 - c1) * self.animation)
                              for c1, c2 in zip(self.color, self.hover_color))

        # Dessin du bouton avec effet de lueur
        glow_radius = 10 + pulse
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_color = (*current_color, alpha)
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, glow_color, glow_rect, border_radius=15)

        # Bouton principal
        pygame.draw.rect(surface, current_color, self.rect, border_radius=15)
        pygame.draw.rect(surface, (*current_color, 150), self.rect, 3, border_radius=15)

        # Texte
        text_surf = FONT.render(self.text, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

        # Description lors du survol
        if hover:
            desc_surf = DESCRIPTION_FONT.render(self.description, True, TEXT_COLOR)
            desc_rect = desc_surf.get_rect(midtop=(self.rect.centerx, self.rect.bottom + 10))
            surface.blit(desc_surf, desc_rect)

def draw_background_particles(surface, time):
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
    clock = pygame.time.Clock()
    time = 0

    # Création des boutons d'éléments
    element_buttons = [
        ElementButton(150, 250, 150, 150, WATER_COLOR, (*WATER_COLOR, 150), "Eau",
                      "Inondations et montée des eaux"),
        ElementButton(400, 250, 150, 150, FIRE_COLOR, (*FIRE_COLOR, 150), "Feu",
                      "Incendies et réchauffement global"),
        ElementButton(650, 250, 150, 150, AIR_COLOR, (*AIR_COLOR, 150), "Air",
                      "Tempêtes et catastrophes atmosphériques"),
        ElementButton(900, 250, 150, 150, EARTH_COLOR, (*EARTH_COLOR, 150), "Terre",
                      "Séismes et éruptions volcaniques"),
        ElementButton(525, 480, 150, 150, LIFE_COLOR, (*LIFE_COLOR, 150), "Vie",
                      "Pandémies et mutations biologiques")
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
                        # Ici, vous pouvez ajouter la logique pour démarrer le jeu
                        # avec l'élément sélectionné

        # Dessin
        screen.fill(BACKGROUND_COLOR)
        draw_background_particles(screen, time)

        # Titre et sous-titre avec effet d'ombre
        for offset in range(2):
            color = (0, 0, 0) if offset == 0 else TEXT_COLOR
            pos_offset = offset * 2
            draw_text("Nouvelle Partie", TITLE_FONT, color, screen,
                      SCREEN_WIDTH / 2 + pos_offset, 100 + pos_offset)
            draw_text("Choisissez une Catastrophe", FONT, color, screen,
                      SCREEN_WIDTH / 2 + pos_offset, 180 + pos_offset)

        # Dessin des boutons d'éléments
        for button in element_buttons:
            button.draw(screen, time)

        # Bouton retour
        pygame.draw.rect(screen, BUTTON_COLOR, back_button, border_radius=10)
        pygame.draw.rect(screen, BUTTON_BORDER_COLOR, back_button, 2, border_radius=10)
        draw_text("Retour", FONT, TEXT_COLOR, screen, 150, 725)

        pygame.display.flip()
        clock.tick(60)

def draw_text(text, font, color, surface, x, y):
    text_obj = font.render(text, True, color)
    text_rect = text_obj.get_rect(center=(x, y))
    surface.blit(text_obj, text_rect)

import pygame
import sys
from pygame import gfxdraw
import math

# Initialisation de Pygame
pygame.init()

# Constantes
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (40, 44, 52)
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (60, 66, 77)
BUTTON_HOVER_COLOR = (75, 83, 96)
BUTTON_BORDER_COLOR = (101, 111, 128)
PROGRESS_BAR_BG = (70, 77, 90)
PROGRESS_BAR_FILL = (92, 184, 92)
NOTIFICATION_BG = (50, 55, 64)

# Polices
TITLE_FONT = pygame.font.Font(None, 64)
FONT = pygame.font.Font(None, 36)
SMALL_FONT = pygame.font.Font(None, 24)

# Configuration de l'écran
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Simulation d'Évolution Mondiale")

def draw_text(text, font, color, surface, x, y, align="center"):
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
    x, y, width, height = rect

    # Dessiner les coins arrondis
    gfxdraw.aacircle(surface, x + radius, y + radius, radius, color)
    gfxdraw.aacircle(surface, x + width - radius - 1, y + radius, radius, color)
    gfxdraw.aacircle(surface, x + radius, y + height - radius - 1, radius, color)
    gfxdraw.aacircle(surface, x + width - radius - 1, y + height - radius - 1, radius, color)

    # Remplir les coins
    gfxdraw.filled_circle(surface, x + radius, y + radius, radius, color)
    gfxdraw.filled_circle(surface, x + width - radius - 1, y + radius, radius, color)
    gfxdraw.filled_circle(surface, x + radius, y + height - radius - 1, radius, color)
    gfxdraw.filled_circle(surface, x + width - radius - 1, y + height - radius - 1, radius, color)

    # Remplir le reste
    pygame.draw.rect(surface, color, (x + radius, y, width - 2 * radius, height))
    pygame.draw.rect(surface, color, (x, y + radius, width, height - 2 * radius))

def draw_button(x, y, width, height, color, border_color, text, font, text_color, surface, hover=False):
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

def draw_progress_bar(surface, x, y, width, height, progress, max_value):
    # Fond de la barre
    draw_rounded_rect(surface, PROGRESS_BAR_BG, (x, y, width, height), 5)

    # Barre de progression
    progress_width = int((progress / max_value) * (width - 4))
    if progress_width > 0:
        draw_rounded_rect(surface, PROGRESS_BAR_FILL, (x + 2, y + 2, progress_width, height - 4), 4)

    # Texte du pourcentage
    percentage = f"{int(progress / max_value * 100)}%"
    draw_text(percentage, SMALL_FONT, TEXT_COLOR, surface, x + width//2, y + height//2)

def draw_notification_panel(surface, x, y, width, height, notifications):
    draw_rounded_rect(surface, NOTIFICATION_BG, (x, y, width, height), 10)
    draw_text("Notifications", FONT, TEXT_COLOR, surface, x + width//2, y + 25)

    for i, notification in enumerate(notifications[-3:]):  # Afficher les 3 dernières notifications
        draw_text(notification, SMALL_FONT, TEXT_COLOR, surface, x + 10, y + 60 + i * 30, "left")

def draw_world_map(surface):
    # Dessiner une grille stylisée pour représenter la carte
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

def world_map_screen():
    notifications = ["Nouvelle technologie découverte!", "Population: 1M habitants", "Ressources: Stables"]
    evolution_points = 10
    humanity_progress = 50

    clock = pygame.time.Clock()

    while True:
        screen.fill(BACKGROUND_COLOR)

        # Titre
        draw_text("Carte du Monde", TITLE_FONT, TEXT_COLOR, screen, SCREEN_WIDTH // 2, 50)

        # Carte du monde
        draw_world_map(screen)

        # Barre de progression de l'humanité
        draw_progress_bar(screen, 850, 100, 300, 30, humanity_progress, 100)
        draw_text("Progrès de l'Humanité", SMALL_FONT, TEXT_COLOR, screen, 1000, 80)

        # Points d'évolution
        draw_text(f"Points d'Évolution : {evolution_points}", FONT, TEXT_COLOR, screen, 900, 180)

        # Panel de notifications
        draw_notification_panel(screen, 850, 220, 300, 150, notifications)

        # Bouton Menu Pause
        pause_button = draw_button(1000, 700, 150, 50, BUTTON_COLOR, BUTTON_BORDER_COLOR, "Pause",
                                   FONT, TEXT_COLOR, screen, hover=True)

        pygame.display.flip()
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if pause_button.collidepoint(event.pos):
                    pause_menu()

def pause_menu():
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
        draw_text("Pause", TITLE_FONT, TEXT_COLOR, screen, SCREEN_WIDTH // 2, 80)

        button_rects = []
        for text, y in buttons:
            button_rect = draw_button(SCREEN_WIDTH//2 - 100, y, 200, 40, BUTTON_COLOR,
                                      BUTTON_BORDER_COLOR, text, FONT, TEXT_COLOR, screen, hover=True)
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
                        elif text == "Quitter":
                            pygame.quit()
                            sys.exit()

import pygame
import math
import colorsys
from pygame import gfxdraw

# Constantes
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (15, 18, 25)
TEXT_COLOR = (255, 255, 255)
WATER_COLOR = (64, 164, 223)
WATER_DARK = (32, 82, 111)
LOCKED_COLOR = (60, 66, 77)

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

class SkillNode:
    def __init__(self, x, y, width, height, title, description, cost, level=0, max_level=3):
        self.rect = pygame.Rect(x, y, width, height)
        self.title = title
        self.description = description
        self.cost = cost
        self.level = level
        self.max_level = max_level
        self.hover = 0
        self.pulse = 0

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)
        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)
        self.pulse = math.sin(time * 0.003) * 4

        # Effet de lueur de base
        glow_radius = 10 + self.pulse
        for i in range(int(glow_radius)):
            alpha = int(80 * (1 - i/glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            glow_color = WATER_COLOR if self.level > 0 else LOCKED_COLOR
            pygame.draw.rect(surface, (*glow_color, alpha), glow_rect, border_radius=15)

        # Corps principal du bouton
        main_color = WATER_COLOR if self.level > 0 else LOCKED_COLOR
        pygame.draw.rect(surface, main_color, self.rect, border_radius=15)
        pygame.draw.rect(surface, WATER_DARK, self.rect, 2, border_radius=15)

        # Indicateurs de niveau
        level_width = 20
        level_spacing = 5
        total_width = (level_width * self.max_level) + (level_spacing * (self.max_level - 1))
        start_x = self.rect.centerx - total_width // 2

        for i in range(self.max_level):
            level_rect = pygame.Rect(start_x + i * (level_width + level_spacing),
                                     self.rect.bottom - 25,
                                     level_width, 10)
            color = WATER_COLOR if i < self.level else LOCKED_COLOR
            pygame.draw.rect(surface, color, level_rect, border_radius=3)

        # Texte
        font = pygame.font.Font(None, 28)
        title_surf = font.render(self.title, True, TEXT_COLOR)
        surface.blit(title_surf, (self.rect.centerx - title_surf.get_width()//2,
                                  self.rect.y + 20))

        if hover:
            # Info-bulle
            desc_font = pygame.font.Font(None, 24)
            desc_lines = self.description.split('\n')
            tooltip_height = 60 + len(desc_lines) * 25
            tooltip_rect = pygame.Rect(mouse_pos[0], mouse_pos[1] - tooltip_height,
                                       300, tooltip_height)

            # Ajustement pour garder l'info-bulle dans l'écran
            if tooltip_rect.right > SCREEN_WIDTH:
                tooltip_rect.right = SCREEN_WIDTH - 10
            if tooltip_rect.top < 0:
                tooltip_rect.top = 10

            pygame.draw.rect(surface, (30, 34, 40, 200), tooltip_rect, border_radius=10)
            pygame.draw.rect(surface, WATER_COLOR, tooltip_rect, 1, border_radius=10)

            y_offset = tooltip_rect.y + 10
            cost_text = f"Coût: {self.cost} points"
            cost_surf = desc_font.render(cost_text, True, WATER_COLOR)
            surface.blit(cost_surf, (tooltip_rect.x + 10, y_offset))

            for line in desc_lines:
                y_offset += 25
                line_surf = desc_font.render(line, True, TEXT_COLOR)
                surface.blit(line_surf, (tooltip_rect.x + 10, y_offset))

def draw_branch_connector(surface, start_pos, end_pos, progress, time):
    points = []
    num_points = 50
    amplitude = 5
    frequency = 0.1

    for i in range(num_points):
        t = i / (num_points - 1)
        x = start_pos[0] + (end_pos[0] - start_pos[0]) * t
        y = start_pos[1] + (end_pos[1] - start_pos[1]) * t
        offset = math.sin(t * math.pi * 2 + time * 0.005) * amplitude
        points.append((x + offset, y))

    if len(points) >= 2:
        color = WATER_COLOR
        for i in range(len(points) - 1):
            if i / len(points) <= progress:
                pygame.draw.line(surface, color, points[i], points[i + 1], 2)

def catastrophe_upgrades_screen():
    clock = pygame.time.Clock()
    water_effect = WaterEffect()

    # Création des nœuds de compétences
    skills = [
        SkillNode(100, 380, 250, 100, "Vague Initiale",
                  "Augmente la puissance de la vague initiale\nDégâts: +20% par niveau", 5, 1),
        SkillNode(400, 380, 250, 100, "Flux Primordial",
                  "Étend la zone d'effet des inondations\nPortée: +15% par niveau", 8),
        SkillNode(700, 380, 250, 100, "Pulsion Liquide",
                  "Accélère la propagation de l'eau\nVitesse: +25% par niveau", 10)
    ]

    branches = [
        {"text": "Intensité", "rect": pygame.Rect(150, 250, 200, 40)},
        {"text": "Portée", "rect": pygame.Rect(400, 250, 200, 40)},
        {"text": "Durée", "rect": pygame.Rect(650, 250, 200, 40)},
        {"text": "Impact", "rect": pygame.Rect(900, 250, 200, 40)}
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
                if 50 <= mouse_pos[0] <= 250 and 700 <= mouse_pos[1] <= 750:
                    return

        screen.fill(BACKGROUND_COLOR)

        # Effet d'eau en arrière-plan
        water_effect.draw(screen, time)

        # Titre avec effet de lueur
        font_title = pygame.font.Font(None, 64)
        shadow_offset = 2
        for offset in range(3):
            alpha = 255 - offset * 60
            shadow_surf = font_title.render("Améliorations", True, (*WATER_COLOR, alpha))
            screen.blit(shadow_surf, (SCREEN_WIDTH//2 - shadow_surf.get_width()//2 + offset,
                                      80 + offset))

        title_surf = font_title.render("Améliorations", True, TEXT_COLOR)
        screen.blit(title_surf, (SCREEN_WIDTH//2 - title_surf.get_width()//2, 80))

        # Sous-titre
        font = pygame.font.Font(None, 36)
        draw_text("Catastrophe : Eau", font, WATER_COLOR, screen, 100, 150)

        # Points disponibles avec effet de pulsation
        points_text = "Points Disponibles : 15"
        alpha = int(200 + math.sin(time * 0.05) * 55)
        points_surf = font.render(points_text, True, WATER_COLOR)
        points_surf.set_alpha(alpha)
        screen.blit(points_surf, (750, 150))

        # Branches
        draw_text("Branches :", font, TEXT_COLOR, screen, 150, 220)
        for branch in branches:
            pygame.draw.rect(screen, WATER_DARK, branch["rect"], border_radius=10)
            text_surf = font.render(branch["text"], True, TEXT_COLOR)
            text_rect = text_surf.get_rect(center=branch["rect"].center)
            screen.blit(text_surf, text_rect)

        # Connexions entre les compétences
        draw_branch_connector(screen, (225, 290), (225, 380), 1, time)
        draw_branch_connector(screen, (225, 290), (525, 380), 0.7, time)
        draw_branch_connector(screen, (225, 290), (825, 380), 0.4, time)

        # Compétences
        draw_text("Compétences (Intensité) :", font, TEXT_COLOR, screen, 100, 350)
        for skill in skills:
            skill.draw(screen, time)

        # Bouton retour
        back_rect = pygame.Rect(50, 700, 200, 50)
        pygame.draw.rect(screen, WATER_DARK, back_rect, border_radius=10)
        back_text = font.render("Retour", True, TEXT_COLOR)
        screen.blit(back_text, (back_rect.centerx - back_text.get_width()//2,
                                back_rect.centery - back_text.get_height()//2))

        pygame.display.flip()
        clock.tick(60)

import pygame
import sys

# Couleurs
BACKGROUND_COLOR = (248, 248, 248)
PRIMARY_COLOR = (70, 130, 180)  # Bleu acier
SECONDARY_COLOR = (112, 128, 144)  # Gris ardoise
ACCENT_COLOR = (255, 99, 71)  # Rouge tomate
TEXT_COLOR = (50, 50, 50)
INDICATOR_COLORS = {
    "high": (46, 204, 113),  # Vert
    "medium": (241, 196, 15),  # Jaune
    "low": (231, 76, 60)  # Rouge
}

# Polices
pygame.font.init()
TITLE_FONT = pygame.font.Font(None, 36)
FONT = pygame.font.Font(None, 28)
SMALL_FONT = pygame.font.Font(None, 24)

def draw_text(text, font, color, surface, x, y, align="left"):
    text_surface = font.render(text, True, color)
    text_rect = text_surface.get_rect()
    if align == "center":
        text_rect.centerx = x
    else:
        text_rect.x = x
    text_rect.y = y
    surface.blit(text_surface, text_rect)

def draw_progress_bar(surface, x, y, width, height, progress, color):
    # Fond de la barre
    pygame.draw.rect(surface, SECONDARY_COLOR, (x, y, width, height), border_radius=height//2)
    # Barre de progression
    progress_width = int(width * progress / 100)
    if progress_width > 0:
        pygame.draw.rect(surface, color, (x, y, progress_width, height),
                         border_radius=height//2)

def draw_button(x, y, width, height, color, border_color, text, font, text_color, surface):
    pygame.draw.rect(surface, color, (x, y, width, height), border_radius=10)
    pygame.draw.rect(surface, border_color, (x, y, width, height), border_radius=10, width=2)
    text_surface = font.render(text, True, text_color)
    text_rect = text_surface.get_rect(center=(x + width//2, y + height//2))
    surface.blit(text_surface, text_rect)

def get_indicator_color(value):
    if value >= 70:
        return INDICATOR_COLORS["high"]
    elif value >= 40:
        return INDICATOR_COLORS["medium"]
    return INDICATOR_COLORS["low"]

def country_info_window(country_name="Nom du Pays"):
    screen = pygame.display.set_mode((400, 500))
    pygame.display.set_caption("Information Pays")

    while True:
        screen.fill(BACKGROUND_COLOR)

        # Cadre principal
        pygame.draw.rect(screen, PRIMARY_COLOR, (0, 0, 400, 500), border_radius=15)
        pygame.draw.rect(screen, BACKGROUND_COLOR, (2, 2, 396, 496), border_radius=15)

        # En-tête
        pygame.draw.rect(screen, PRIMARY_COLOR, (0, 0, 400, 80), border_radius=15)
        draw_text(country_name, TITLE_FONT, BACKGROUND_COLOR, screen, 200, 25, "center")
        draw_button(360, 10, 30, 30, ACCENT_COLOR, BACKGROUND_COLOR, "X", FONT, BACKGROUND_COLOR, screen)

        # Données démographiques
        y_offset = 100
        draw_text("Données Démographiques", FONT, PRIMARY_COLOR, screen, 20, y_offset)
        pygame.draw.line(screen, SECONDARY_COLOR, (20, y_offset + 25), (380, y_offset + 25), 1)

        demo_data = [
            ("Population", "10,000,000"),
            ("Personnes affectées", "1,000,000"),
            ("Morts", "100,000")
        ]

        for i, (label, value) in enumerate(demo_data):
            y = y_offset + 40 + i * 30
            draw_text(f"{label}:", SMALL_FONT, TEXT_COLOR, screen, 30, y)
            draw_text(value, FONT, PRIMARY_COLOR, screen, 200, y)

        # Indicateurs d'équilibre
        y_offset = 250
        draw_text("Indicateurs d'Équilibre", FONT, PRIMARY_COLOR, screen, 20, y_offset)
        pygame.draw.line(screen, SECONDARY_COLOR, (20, y_offset + 25), (380, y_offset + 25), 1)

        indicators = [
            ("Résilience Technologique", 60),
            ("Stabilité Sociétale", 75),
            ("Régénération Écologique", 40),
            ("Adaptation Évolution", 65)
        ]

        for i, (label, value) in enumerate(indicators):
            y = y_offset + 40 + i * 50
            draw_text(f"{label}:", SMALL_FONT, TEXT_COLOR, screen, 30, y)
            draw_progress_bar(screen, 30, y + 20, 340, 15, value, get_indicator_color(value))
            draw_text(f"{value}%", SMALL_FONT, TEXT_COLOR, screen, 375, y + 15, "center")

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                mouse_x, mouse_y = event.pos
                if 360 <= mouse_x <= 390 and 10 <= mouse_y <= 40:
                    return  # Retour à l'écran précédent

import pygame
import sys
from math import sin
import time

# Constantes
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
BACKGROUND_COLOR = (240, 242, 245)
PRIMARY_COLOR = (70, 130, 180)
SECONDARY_COLOR = (112, 128, 144)
ACCENT_COLOR = (65, 105, 225)
TEXT_COLOR = (50, 50, 50)
HOVER_COLOR = (100, 149, 237)

# Initialisation de Pygame
pygame.font.init()
TITLE_FONT = pygame.font.Font(None, 48)
FONT = pygame.font.Font(None, 32)
ICON_FONT = pygame.font.Font(None, 36)

class Button:
    def __init__(self, x, y, width, height, text, icon=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.icon = icon
        self.is_hovered = False
        self.animation_start = 0

    def draw(self, surface):
        # Animation de survol
        hover_offset = 0
        if self.is_hovered:
            current_time = time.time()
            if self.animation_start == 0:
                self.animation_start = current_time
            hover_offset = sin((current_time - self.animation_start) * 5) * 3
        else:
            self.animation_start = 0

        # Dessiner le fond du bouton
        color = HOVER_COLOR if self.is_hovered else PRIMARY_COLOR
        pygame.draw.rect(surface, color,
                         (self.rect.x, self.rect.y - hover_offset,
                          self.rect.width, self.rect.height),
                         border_radius=15)

        # Effet de brillance
        highlight_rect = pygame.Rect(self.rect.x, self.rect.y - hover_offset,
                                     self.rect.width, self.rect.height // 2)
        highlight_color = (*[min(255, c + 30) for c in color], 100)
        pygame.draw.rect(surface, highlight_color, highlight_rect,
                         border_radius=15)

        # Icône et texte
        if self.icon:
            icon_surf = ICON_FONT.render(self.icon, True, BACKGROUND_COLOR)
            icon_rect = icon_surf.get_rect(
                midright=(self.rect.centerx - 10, self.rect.centery - hover_offset))
            surface.blit(icon_surf, icon_rect)

        text_surf = FONT.render(self.text, True, BACKGROUND_COLOR)
        text_rect = text_surf.get_rect(
            center=(self.rect.centerx + (15 if self.icon else 0),
                    self.rect.centery - hover_offset))
        surface.blit(text_surf, text_rect)

def draw_title(surface, text, y):
    # Fond décoratif du titre
    title_surface = TITLE_FONT.render(text, True, TEXT_COLOR)
    title_rect = title_surface.get_rect(center=(SCREEN_WIDTH // 2, y))

    # Ligne décorative
    line_y = title_rect.bottom + 10
    pygame.draw.line(surface, PRIMARY_COLOR,
                     (SCREEN_WIDTH // 4, line_y),
                     (3 * SCREEN_WIDTH // 4, line_y), 2)

    surface.blit(title_surface, title_rect)

def options_screen():
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Options")

    # Création des boutons avec icônes
    buttons = [
        Button(SCREEN_WIDTH//2 - 150, 180, 300, 60, "Graphismes", "🎨"),
        Button(SCREEN_WIDTH//2 - 150, 260, 300, 60, "Son", "🔊"),
        Button(SCREEN_WIDTH//2 - 150, 340, 300, 60, "Jouabilité", "🎮"),
        Button(SCREEN_WIDTH//2 - 150, 420, 300, 60, "Commandes", "⌨"),
        Button(50, SCREEN_HEIGHT - 80, 200, 50, "Retour", "←")
    ]

    while True:
        screen.fill(BACKGROUND_COLOR)

        # Dessin du fond décoratif
        for i in range(3):
            pygame.draw.circle(screen,
                               (*PRIMARY_COLOR, 30),
                               (0, SCREEN_HEIGHT//2 + i*100),
                               100 + i*50)
            pygame.draw.circle(screen,
                               (*ACCENT_COLOR, 30),
                               (SCREEN_WIDTH, SCREEN_HEIGHT//2 - i*100),
                               100 + i*50)

        draw_title(screen, "Options", 100)

        # Mise à jour et dessin des boutons
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
                            return  # Retour au menu principal
                        # Gérer les autres boutons ici

import pygame
import math
from pygame import gfxdraw

# Constantes améliorées
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (20, 24, 32)
TEXT_COLOR = (255, 255, 255)
ACCENT_COLOR = (92, 184, 232)
ACCENT_COLOR_2 = (72, 144, 192)
DISABLED_COLOR = (128, 128, 128)

class SettingOption:
    def __init__(self, x, y, width, height, title, options, current_value):
        self.rect = pygame.Rect(x, y, width, height)
        self.title = title
        self.options = options
        self.current_value = current_value
        self.hover = 0
        self.animation = 0
        self.selected = False

    def draw(self, surface, time):
        # Dessiner le titre
        title_font = pygame.font.Font(None, 32)
        title_surf = title_font.render(self.title, True, TEXT_COLOR)
        surface.blit(title_surf, (150, self.rect.centery - 30))

        # Dessiner la valeur actuelle avec effet de lueur
        value_rect = pygame.Rect(self.rect.x, self.rect.y, self.rect.width, self.rect.height)
        mouse_over = value_rect.collidepoint(pygame.mouse.get_pos())

        # Animation de survol
        if mouse_over:
            self.hover = min(1, self.hover + 0.1)
        else:
            self.hover = max(0, self.hover - 0.1)

        # Effet de pulsation
        pulse = math.sin(time * 0.003) * 2

        # Effet de lueur
        glow_radius = 8 + pulse * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_color = (*ACCENT_COLOR, alpha) if mouse_over else (*ACCENT_COLOR_2, alpha // 2)
            glow_rect = value_rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, glow_color, glow_rect, border_radius=10)

        # Fond du bouton
        base_color = [int(c1 + (c2 - c1) * self.hover) for c1, c2 in zip(ACCENT_COLOR_2, ACCENT_COLOR)]
        pygame.draw.rect(surface, base_color, value_rect, border_radius=10)
        pygame.draw.rect(surface, ACCENT_COLOR, value_rect, 2, border_radius=10)

        # Texte de la valeur
        value_font = pygame.font.Font(None, 28)
        value_text = str(self.current_value)
        value_surf = value_font.render(value_text, True, TEXT_COLOR)
        value_rect = value_surf.get_rect(center=value_rect.center)

        # Ombre du texte
        shadow_surf = value_font.render(value_text, True, (0, 0, 0))
        shadow_rect = shadow_surf.get_rect(center=(value_rect.centerx + 1, value_rect.centery + 1))
        surface.blit(shadow_surf, shadow_rect)
        surface.blit(value_surf, value_rect)

        # Flèches de navigation si plusieurs options
        if len(self.options) > 1:
            arrow_color = ACCENT_COLOR if mouse_over else DISABLED_COLOR
            # Flèche gauche
            left_arrow = [(self.rect.x - 30, self.rect.centery),
                          (self.rect.x - 20, self.rect.centery - 10),
                          (self.rect.x - 20, self.rect.centery + 10)]
            pygame.draw.polygon(surface, arrow_color, left_arrow)

            # Flèche droite
            right_arrow = [(self.rect.right + 30, self.rect.centery),
                           (self.rect.right + 20, self.rect.centery - 10),
                           (self.rect.right + 20, self.rect.centery + 10)]
            pygame.draw.polygon(surface, arrow_color, right_arrow)

class PreviewWindow:
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
        # Fond avec effet de dégradé
        for i in range(self.rect.height):
            progress = i / self.rect.height
            color = [int(c1 + (c2 - c1) * progress) for c1, c2 in zip(BACKGROUND_COLOR, ACCENT_COLOR_2)]
            pygame.draw.line(surface, color,
                             (self.rect.left, self.rect.top + i),
                             (self.rect.right, self.rect.top + i))

        # Particules avec effet de brillance
        for i, (x, y) in enumerate(self.particles):
            particle_color = (*ACCENT_COLOR, int(128 + math.sin(time * 0.01 + i) * 64))
            pos = (int(self.rect.left + x), int(self.rect.top + y))
            size = 2 + math.sin(time * 0.005 + i) * 1
            gfxdraw.filled_circle(surface, pos[0], pos[1], int(size), particle_color)

def graphics_options_screen():
    clock = pygame.time.Clock()
    preview = PreviewWindow(600, 150, 500, 400)

    settings = [
        SettingOption(350, 160, 200, 40, "Résolution",
                      ["1280x720", "1920x1080", "2560x1440"], "1280x720"),
        SettingOption(350, 220, 200, 40, "Plein écran",
                      ["Oui", "Non"], "Oui"),
        SettingOption(350, 280, 200, 40, "Qualité des textures",
                      ["Basse", "Moyenne", "Haute"], "Haute"),
        SettingOption(350, 340, 200, 40, "Effets visuels",
                      ["Désactivés", "Basiques", "Complets"], "Complets"),
        SettingOption(350, 400, 200, 40, "Anti-aliasing",
                      ["Désactivé", "x2", "x4", "x8"], "x4"),
        SettingOption(350, 460, 200, 40, "Ombres",
                      ["Désactivées", "Basses", "Moyennes", "Hautes"], "Hautes")
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
                # Gestion des clics sur les options
                for setting in settings:
                    if setting.rect.collidepoint(mouse_pos):
                        current_index = setting.options.index(setting.current_value)
                        if event.button == 1:  # Clic gauche
                            current_index = (current_index + 1) % len(setting.options)
                        elif event.button == 3:  # Clic droit
                            current_index = (current_index - 1) % len(setting.options)
                        setting.current_value = setting.options[current_index]

                # Bouton Retour
                if pygame.Rect(50, 520, 200, 50).collidepoint(mouse_pos):
                    return

        # Mise à jour
        preview.update()

        # Dessin
        screen.fill(BACKGROUND_COLOR)

        # Titre avec effet de lueur
        title_font = pygame.font.Font(None, 64)
        title = "Options Graphiques"
        title_glow = title_font.render(title, True, ACCENT_COLOR)
        title_glow.set_alpha(int(128 + math.sin(time * 0.01) * 64))
        title_rect = title_glow.get_rect(center=(SCREEN_WIDTH // 2, 100))
        screen.blit(title_glow, title_rect.move(2, 2))

        title_main = title_font.render(title, True, TEXT_COLOR)
        screen.blit(title_main, title_rect)

        # Fenêtre de prévisualisation
        preview.draw(screen, time)
        preview_title = pygame.font.Font(None, 32).render("Prévisualisation", True, TEXT_COLOR)
        screen.blit(preview_title, (preview.rect.centerx - preview_title.get_width()//2,
                                    preview.rect.top - 30))

        # Options
        for setting in settings:
            setting.draw(screen, time)

        # Bouton Retour avec effet de survol
        back_rect = pygame.Rect(50, 520, 200, 50)
        mouse_over_back = back_rect.collidepoint(pygame.mouse.get_pos())

        if mouse_over_back:
            back_color = ACCENT_COLOR
        else:
            back_color = ACCENT_COLOR_2

        pygame.draw.rect(screen, back_color, back_rect, border_radius=10)
        pygame.draw.rect(screen, ACCENT_COLOR, back_rect, 2, border_radius=10)

        back_text = pygame.font.Font(None, 32).render("Retour", True, TEXT_COLOR)
        back_rect = back_text.get_rect(center=(150, 545))
        screen.blit(back_text, back_rect)

        # Bouton Appliquer
        apply_rect = pygame.Rect(SCREEN_WIDTH - 250, 520, 200, 50)
        pygame.draw.rect(screen, ACCENT_COLOR_2, apply_rect, border_radius=10)
        pygame.draw.rect(screen, ACCENT_COLOR, apply_rect, 2, border_radius=10)

        apply_text = pygame.font.Font(None, 32).render("Appliquer", True, TEXT_COLOR)
        apply_rect = apply_text.get_rect(center=(SCREEN_WIDTH - 150, 545))
        screen.blit(apply_text, apply_rect)

        pygame.display.flip()
        clock.tick(60)

import pygame
import math
import sys
from pygame import gfxdraw

# Constantes
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (20, 24, 32)
TEXT_COLOR = (255, 255, 255)
SLIDER_BG_COLOR = (45, 50, 60)
SLIDER_ACTIVE_COLOR = (92, 184, 92)
SLIDER_HANDLE_COLOR = (220, 220, 220)
ACCENT_COLOR = (178, 34, 34)

class VolumeSlider:
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
        # Fond du slider avec effet de lueur
        glow_radius = 5 + math.sin(time * 0.005) * 2 * self.hover
        for i in range(int(glow_radius)):
            alpha = int(50 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*SLIDER_BG_COLOR, alpha), glow_rect, border_radius=8)

        # Fond principal
        pygame.draw.rect(surface, SLIDER_BG_COLOR, self.rect, border_radius=8)

        # Partie active
        active_width = int(self.rect.width * self.value)
        active_rect = pygame.Rect(self.rect.x, self.rect.y, active_width, self.rect.height)

        # Dégradé pour la partie active
        for i in range(active_width):
            progress = i / self.rect.width
            color = (
                int(SLIDER_ACTIVE_COLOR[0] * (1 - progress) + ACCENT_COLOR[0] * progress),
                int(SLIDER_ACTIVE_COLOR[1] * (1 - progress) + ACCENT_COLOR[1] * progress),
                int(SLIDER_ACTIVE_COLOR[2] * (1 - progress) + ACCENT_COLOR[2] * progress)
            )
            line_rect = pygame.Rect(self.rect.x + i, self.rect.y, 1, self.rect.height)
            pygame.draw.rect(surface, color, line_rect)

        # Poignée du slider
        handle_pos = (self.rect.x + active_width, self.rect.centery)
        handle_radius = 12 + self.hover * 2

        # Effet de lueur sur la poignée
        for i in range(5):
            alpha = 150 - i * 30
            pygame.draw.circle(surface, (*SLIDER_HANDLE_COLOR, alpha),
                               handle_pos, handle_radius + i)

        pygame.draw.circle(surface, SLIDER_HANDLE_COLOR, handle_pos, handle_radius)

        # Pourcentage
        font = pygame.font.Font(None, 24)
        percentage = f"{int(self.value * 100)}%"
        text_surf = font.render(percentage, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(midleft=(self.rect.right + 20, self.rect.centery))
        surface.blit(text_surf, text_rect)

class BackButton:
    def __init__(self, x, y, width, height):
        self.rect = pygame.Rect(x, y, width, height)
        self.hover = 0

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)

        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)

        # Effet de lueur
        glow_radius = 10 + math.sin(time * 0.005) * 2
        for i in range(int(glow_radius)):
            alpha = int(50 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*ACCENT_COLOR, alpha), glow_rect, border_radius=10)

        # Bouton principal
        color = (
            int(SLIDER_BG_COLOR[0] + (ACCENT_COLOR[0] - SLIDER_BG_COLOR[0]) * self.hover),
            int(SLIDER_BG_COLOR[1] + (ACCENT_COLOR[1] - SLIDER_BG_COLOR[1]) * self.hover),
            int(SLIDER_BG_COLOR[2] + (ACCENT_COLOR[2] - SLIDER_BG_COLOR[2]) * self.hover)
        )
        pygame.draw.rect(surface, color, self.rect, border_radius=10)

        # Texte
        font = pygame.font.Font(None, 36)
        text_surf = font.render("Retour", True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

def draw_title(surface, time):
    title = "Options Sonores"
    font = pygame.font.Font(None, 72)

    # Animation du titre
    wave_height = 5
    wave_length = 0.1
    wave_speed = 0.005
    glow_intensity = int(128 + math.sin(time * 0.01) * 64)

    # Calcul de la largeur totale
    total_width = sum(font.size(char)[0] for char in title)
    start_x = SCREEN_WIDTH // 2 - total_width // 2

    current_x = start_x
    for i, char in enumerate(title):
        offset = math.sin(time * wave_speed + i * wave_length) * wave_height
        char_surf = font.render(char, True, TEXT_COLOR)
        char_width = font.size(char)[0]

        # Effet de lueur
        glow_surf = font.render(char, True, ACCENT_COLOR)
        glow_surf.set_alpha(glow_intensity)
        surface.blit(glow_surf, (current_x + 2, 100 + offset + 2))

        # Caractère principal
        surface.blit(char_surf, (current_x, 100 + offset))
        current_x += char_width

def sound_options_screen():
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

        # Mise à jour des sliders
        for slider in sliders.values():
            slider.update(events)

        # Dessin
        screen.fill(BACKGROUND_COLOR)

        # Titre
        draw_title(screen, time)

        # Labels et sliders
        y_position = 180
        for label, slider in sliders.items():
            # Label avec effet de lueur
            font = pygame.font.Font(None, 36)
            label_surf = font.render(label, True, TEXT_COLOR)
            label_rect = label_surf.get_rect(midright=(320, y_position + 10))

            # Effet de lueur sur le texte
            glow_surf = font.render(label, True, ACCENT_COLOR)
            glow_surf.set_alpha(50)
            screen.blit(glow_surf, (label_rect.x + 2, label_rect.y + 2))

            screen.blit(label_surf, label_rect)
            slider.draw(screen, time)
            y_position += 80

        # Bouton retour
        back_button.draw(screen, time)

        pygame.display.flip()
        clock.tick(60)

import pygame
import math
import colorsys
from pygame import gfxdraw

# Constantes
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (20, 24, 32)
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (60, 66, 77)
BUTTON_HOVER_COLOR = (75, 83, 96)
ACCENT_COLOR = (92, 184, 92)
SLIDER_BG = (45, 50, 60)
SLIDER_FILL = (92, 184, 92)

class Slider:
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
        # Effet de lueur
        glow_radius = 5 + math.sin(time * 0.003) * 2 * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*SLIDER_FILL, alpha), glow_rect, border_radius=5)

        # Fond du slider
        pygame.draw.rect(surface, SLIDER_BG, self.rect, border_radius=5)

        # Partie remplie
        fill_rect = pygame.Rect(self.rect.x, self.rect.y,
                                self.get_current_pos() - self.rect.x, self.rect.height)
        pygame.draw.rect(surface, SLIDER_FILL, fill_rect, border_radius=5)

        # Poignée
        handle_pos = (self.get_current_pos(), self.rect.centery)
        handle_radius = 10 + math.sin(time * 0.003) * 2 * self.hover
        pygame.draw.circle(surface, TEXT_COLOR, handle_pos, handle_radius)

class ToggleButton:
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
        # Couleurs interpolées
        off_color = BUTTON_COLOR
        on_color = ACCENT_COLOR
        current_color = tuple(int(c1 + (c2 - c1) * self.animation)
                              for c1, c2 in zip(off_color, on_color))

        # Effet de lueur
        glow_radius = 5 + math.sin(time * 0.003) * 2 * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*current_color, alpha), glow_rect, border_radius=10)

        # Bouton principal
        pygame.draw.rect(surface, current_color, self.rect, border_radius=10)

        # Cercle de toggle
        circle_x = self.rect.x + 5 + (self.rect.width - 25) * self.animation
        circle_y = self.rect.centery
        pygame.draw.circle(surface, TEXT_COLOR, (circle_x, circle_y), 10)

class DifficultySelector:
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

        # Effet de lueur
        glow_radius = 5 + math.sin(time * 0.003) * 2 * self.hover
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*BUTTON_COLOR, alpha), glow_rect, border_radius=10)

        # Bouton principal
        pygame.draw.rect(surface, BUTTON_COLOR, self.rect, border_radius=10)

        # Texte
        font = pygame.font.Font(None, 36)
        text_surf = font.render(current_diff, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

def draw_background_pattern(surface, time):
    # Motif hexagonal subtil
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
    clock = pygame.time.Clock()

    # Création des contrôles
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

        # Mise à jour des contrôles
        difficulty_selector.update(events)
        game_speed_slider.update(events)
        tutorial_toggle.update(events)
        notifications_toggle.update(events)

        # Dessin
        screen.fill(BACKGROUND_COLOR)
        draw_background_pattern(screen, time)

        # Titre avec effet de lueur
        title = "Options de Jouabilité"
        font_title = pygame.font.Font(None, 64)
        title_color = tuple(int(c * (0.8 + math.sin(time * 0.003) * 0.2))
                            for c in (255, 255, 255))
        title_surf = font_title.render(title, True, title_color)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 100))
        screen.blit(title_surf, title_rect)

        # Labels
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

        # Contrôles
        difficulty_selector.draw(screen, time)
        game_speed_slider.draw(screen, time)
        tutorial_toggle.draw(screen, time)
        notifications_toggle.draw(screen, time)

        # Bouton Retour
        back_rect = pygame.Rect(50, 520, 200, 50)
        pygame.draw.rect(screen, BUTTON_COLOR, back_rect, border_radius=10)
        back_text = font.render("Retour", True, TEXT_COLOR)
        back_text_rect = back_text.get_rect(center=back_rect.center)
        screen.blit(back_text, back_text_rect)

        pygame.display.flip()
        clock.tick(60)

import pygame
import math
import colorsys
from pygame import gfxdraw

# Constantes
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (20, 24, 32)
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (45, 50, 60)
BUTTON_HOVER_COLOR = (65, 70, 85)
ACCENT_COLOR = (92, 184, 92)
GRID_COLOR = (40, 44, 52)

class KeyBindButton:
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

        # Animation de survol
        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)

        # Animation de pulsation
        self.pulse = (math.sin(time * 0.005) + 1) * 0.5 if self.listening else 0

        # Couleurs
        base_color = [int(c1 + (c2 - c1) * self.hover)
                      for c1, c2 in zip(BUTTON_COLOR, BUTTON_HOVER_COLOR)]

        # Effet de lueur
        glow_radius = 10 if self.listening else 5
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_color = (*ACCENT_COLOR, alpha) if self.listening else (*base_color, alpha)
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, glow_color, glow_rect, border_radius=10)

        # Bouton principal
        pygame.draw.rect(surface, base_color, self.rect, border_radius=10)
        border_color = ACCENT_COLOR if self.listening else (169, 169, 169)
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=10)

        # Texte
        font = pygame.font.Font(None, 32)
        text = "..." if self.listening else (self.key if self.key else "Non assigné")
        text_color = ACCENT_COLOR if self.listening else TEXT_COLOR
        text_surf = font.render(text, True, text_color)
        text_rect = text_surf.get_rect(center=self.rect.center)

        if self.listening:
            text_rect.y += math.sin(time * 0.01) * 3

        surface.blit(text_surf, text_rect)

def draw_background_grid(surface, time):
    cell_size = 50
    offset = (time * 0.5) % cell_size

    # Lignes horizontales
    for y in range(0, SCREEN_HEIGHT + cell_size, cell_size):
        alpha = int(20 + math.sin(y * 0.01 + time * 0.001) * 10)
        pygame.draw.line(surface, (*GRID_COLOR, alpha),
                         (0, y + offset), (SCREEN_WIDTH, y + offset))

    # Lignes verticales
    for x in range(0, SCREEN_WIDTH + cell_size, cell_size):
        alpha = int(20 + math.sin(x * 0.01 + time * 0.001) * 10)
        pygame.draw.line(surface, (*GRID_COLOR, alpha),
                         (x + offset, 0), (x + offset, SCREEN_HEIGHT))

def draw_section_header(surface, text, x, y, width):
    font = pygame.font.Font(None, 36)
    text_surf = font.render(text, True, TEXT_COLOR)
    text_rect = text_surf.get_rect(centerx=x + width//2, centery=y)

    # Ligne décorative
    line_y = y + text_rect.height//2
    pygame.draw.line(surface, ACCENT_COLOR, (x, line_y), (x + width, line_y), 2)

    # Fond du texte
    padding = 10
    bg_rect = text_rect.inflate(padding * 2, padding)
    bg_rect.centerx = x + width//2
    pygame.draw.rect(surface, BACKGROUND_COLOR, bg_rect)

    surface.blit(text_surf, text_rect)

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


import pygame
import math
import random
from pygame import gfxdraw
from datetime import datetime

# Constantes
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (15, 18, 25)
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (45, 50, 60)
BUTTON_HOVER_COLOR = (65, 70, 85)

# Couleurs pour chaque type de catastrophe
CATASTROPHE_COLORS = {
    "Eau": (64, 164, 223),
    "Feu": (235, 83, 83),
    "Air": (188, 231, 253),
    "Terre": (141, 110, 99),
    "Vie": (92, 184, 92)
}

class SaveSlot:
    def __init__(self, x, y, width, height, save_data):
        self.rect = pygame.Rect(x, y, width, height)
        self.save_data = save_data
        self.hover = 0
        self.selected = False
        self.animation = 0

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)

        # Animation de survol
        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)

        # Couleur de base selon la catastrophe
        base_color = CATASTROPHE_COLORS.get(self.save_data['catastrophe'], BUTTON_COLOR)

        # Effet de lueur
        glow_radius = 10 + math.sin(time * 0.003) * 2
        for i in range(int(glow_radius)):
            alpha = int(60 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            pygame.draw.rect(surface, (*base_color, alpha), glow_rect, border_radius=15)

        # Fond du slot
        color = [int(c1 + (c2 - c1) * self.hover) for c1, c2 in zip(BUTTON_COLOR, BUTTON_HOVER_COLOR)]
        pygame.draw.rect(surface, color, self.rect, border_radius=15)

        # Bordure
        border_color = (*base_color, 255) if self.selected else (*base_color, 150)
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=15)

        # Informations de la sauvegarde
        font = pygame.font.Font(None, 36)
        small_font = pygame.font.Font(None, 24)

        # Titre de la sauvegarde
        title = f"Sauvegarde {self.save_data['id']}"
        title_surf = font.render(title, True, TEXT_COLOR)
        surface.blit(title_surf, (self.rect.x + 20, self.rect.y + 10))

        # Icône de catastrophe
        icon_size = 30
        icon_rect = pygame.Rect(self.rect.x + 20, self.rect.y + 45, icon_size, icon_size)
        pygame.draw.rect(surface, base_color, icon_rect, border_radius=5)

        # Informations détaillées
        info_x = self.rect.x + 60
        info_y = self.rect.y + 45

        # Type de catastrophe
        catastrophe_text = f"Catastrophe : {self.save_data['catastrophe']}"
        catastrophe_surf = small_font.render(catastrophe_text, True, base_color)
        surface.blit(catastrophe_surf, (info_x, info_y))

        # Tour
        tour_text = f"Tour : {self.save_data['tour']}"
        tour_surf = small_font.render(tour_text, True, TEXT_COLOR)
        surface.blit(tour_surf, (info_x + 250, info_y))

        # Date de sauvegarde
        date_text = f"Dernière sauvegarde : {self.save_data['date']}"
        date_surf = small_font.render(date_text, True, TEXT_COLOR)
        surface.blit(date_surf, (info_x + 400, info_y))

class Button:
    def __init__(self, x, y, width, height, text):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.hover = 0

    def draw(self, surface, time):
        mouse_pos = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse_pos)

        self.hover = min(1, self.hover + 0.1) if hover else max(0, self.hover - 0.1)

        # Effet de lueur
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

def draw_background_grid(surface, time):
    cell_size = 50
    alpha = 20

    for x in range(0, SCREEN_WIDTH, cell_size):
        for y in range(0, SCREEN_HEIGHT, cell_size):
            intensity = int(10 + math.sin(time * 0.002 + x * 0.01 + y * 0.01) * 5)
            pygame.draw.rect(surface, (intensity, intensity, intensity, alpha),
                             (x, y, cell_size - 1, cell_size - 1), 1)

def load_game_screen():
    clock = pygame.time.Clock()

    # Données de sauvegarde simulées
    saves = [
        {
            'id': 1,
            'catastrophe': 'Eau',
            'tour': 25,
            'date': '23/12/2024 15:30'
        },
        {
            'id': 2,
            'catastrophe': 'Feu',
            'tour': 12,
            'date': '23/12/2024 14:45'
        },
        {
            'id': 3,
            'catastrophe': 'Air',
            'tour': 48,
            'date': '22/12/2024 20:15'
        }
    ]

    save_slots = [
        SaveSlot(150, 180 + i * 100, 900, 80, save)
        for i, save in enumerate(saves)
    ]

    load_button = Button(SCREEN_WIDTH//2 - 100, 520, 200, 50, "Charger")
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

        # Dessin
        screen.fill(BACKGROUND_COLOR)
        draw_background_grid(screen, time)

        # Titre avec effet de lueur
        font_title = pygame.font.Font(None, 64)
        title_text = "Charger une Partie"
        title_shadow = font_title.render(title_text, True, (30, 30, 30))
        title = font_title.render(title_text, True, TEXT_COLOR)

        shadow_offset = abs(math.sin(time * 0.002)) * 3 + 2
        screen.blit(title_shadow, (SCREEN_WIDTH//2 - title.get_width()//2 + shadow_offset,
                                   100 + shadow_offset))
        screen.blit(title, (SCREEN_WIDTH//2 - title.get_width()//2, 100))

        # Slots de sauvegarde
        for slot in save_slots:
            slot.draw(screen, time)

        # Boutons
        load_button.draw(screen, time)
        back_button.draw(screen, time)

        pygame.display.flip()
        clock.tick(60)

import pygame
import math
import time
from pygame import gfxdraw

# Constantes améliorées
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (20, 24, 32)
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (60, 66, 77)
BUTTON_HOVER_COLOR = (75, 83, 96)
ACCENT_COLOR = (92, 184, 92)  # Vert pour les sauvegardes
INPUT_BG_COLOR = (30, 34, 42)
PLACEHOLDER_COLOR = (128, 128, 128)

class TextInput:
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
        self.key_cooldown = 50  # ms

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
            if self.active:
                self.animation = 0.0  # Réinitialiser l'animation lors du focus

        if self.active and event.type == pygame.KEYDOWN:
            current_time = time.time() * 1000
            if current_time - self.last_key_time > self.key_cooldown:
                if event.key == pygame.K_BACKSPACE:
                    self.text = self.text[:-1]
                    self.shake_offset = [-3, 0]  # Petit effet de secousse
                elif event.key == pygame.K_RETURN:
                    self.active = False
                elif len(self.text) < 30:  # Limite de caractères
                    self.text += event.unicode
                    self.animation = 0.0  # Réinitialiser l'animation
                self.last_key_time = current_time

    def update(self, current_time):
        # Animation du curseur
        if current_time % 1000 < 500:
            self.cursor_visible = True
        else:
            self.cursor_visible = False

        # Animation de focus
        if self.active:
            self.animation = min(1.0, self.animation + 0.1)
        else:
            self.animation = max(0.0, self.animation - 0.1)

        # Atténuation de l'effet de secousse
        self.shake_offset[0] *= 0.8
        self.shake_offset[1] *= 0.8

    def draw(self, surface, current_time):
        # Effet de lueur
        glow_rect = self.rect.inflate(4, 4)
        glow_color = (*ACCENT_COLOR, int(128 * self.animation))
        pygame.draw.rect(surface, glow_color, glow_rect, border_radius=10)

        # Fond du champ de texte
        pygame.draw.rect(surface, INPUT_BG_COLOR, self.rect, border_radius=8)

        # Bordure animée
        border_color = [int(c1 + (c2 - c1) * self.animation)
                        for c1, c2 in zip(BUTTON_COLOR, ACCENT_COLOR)]
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=8)

        # Texte ou placeholder
        font = pygame.font.Font(None, 36)
        if self.text:
            text_surface = font.render(self.text, True, TEXT_COLOR)
        else:
            text_surface = font.render(self.placeholder, True, PLACEHOLDER_COLOR)

        # Position du texte avec effet de secousse
        text_pos = (self.rect.x + 10 + self.shake_offset[0],
                    self.rect.centery - text_surface.get_height() // 2 + self.shake_offset[1])
        surface.blit(text_surface, text_pos)

        # Curseur clignotant
        if self.active and self.cursor_visible:
            cursor_x = self.rect.x + 10 + font.size(self.text)[0]
            cursor_color = (*TEXT_COLOR, int(255 * (0.5 + math.sin(current_time * 0.01) * 0.5)))
            pygame.draw.line(surface, cursor_color,
                             (cursor_x, self.rect.y + 10),
                             (cursor_x, self.rect.bottom - 10), 2)

class SaveSlot:
    def __init__(self, x, y, width, height, save_data=None):
        self.rect = pygame.Rect(x, y, width, height)
        self.save_data = save_data
        self.hover = 0.0
        self.selected = False

    def draw(self, surface, current_time):
        hover_color = (*BUTTON_HOVER_COLOR, int(255 * self.hover))

        # Fond avec effet de survol
        pygame.draw.rect(surface, BUTTON_COLOR, self.rect, border_radius=10)
        pygame.draw.rect(surface, hover_color, self.rect, border_radius=10)

        if self.selected:
            # Bordure animée pour la sélection
            border_color = (ACCENT_COLOR[0],
                            ACCENT_COLOR[1],
                            ACCENT_COLOR[2],
                            int(128 + math.sin(current_time * 0.01) * 64))
            pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=10)

        # Affichage des informations de sauvegarde
        if self.save_data:
            font = pygame.font.Font(None, 32)
            name_text = font.render(self.save_data["name"], True, TEXT_COLOR)
            date_text = font.render(self.save_data["date"], True, (*TEXT_COLOR, 180))

            surface.blit(name_text, (self.rect.x + 20, self.rect.y + 15))
            surface.blit(date_text, (self.rect.x + 20, self.rect.y + 45))

def save_game_screen():
    clock = pygame.time.Clock()
    text_input = TextInput(150, 230, 500, 50)

    # Exemples de sauvegardes existantes
    save_slots = [
        SaveSlot(150, 320 + i * 80, 500, 70, {
            "name": f"Sauvegarde {i+1}",
            "date": f"2024/12/{20+i} 14:30"
        }) for i in range(3)
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

                # Gestion des slots de sauvegarde
                for slot in save_slots:
                    if slot.rect.collidepoint(mouse_pos):
                        text_input.text = slot.save_data["name"]
                        slot.selected = True
                        for other_slot in save_slots:
                            if other_slot != slot:
                                other_slot.selected = False

                # Bouton Annuler
                if 50 <= mouse_pos[0] <= 250 and 520 <= mouse_pos[1] <= 570:
                    return "pause_menu"

        # Mise à jour
        text_input.update(current_time)

        # Mise à jour des effets de survol des slots
        mouse_pos = pygame.mouse.get_pos()
        for slot in save_slots:
            if slot.rect.collidepoint(mouse_pos):
                slot.hover = min(1.0, slot.hover + 0.1)
            else:
                slot.hover = max(0.0, slot.hover - 0.1)

        # Dessin
        screen.fill(BACKGROUND_COLOR)

        # Titre avec effet de lueur
        title = "Sauvegarder la Partie"
        title_font = pygame.font.Font(None, 64)
        for offset in range(3):
            alpha = 255 - offset * 50
            title_surf = title_font.render(title, True, (*ACCENT_COLOR, alpha))
            screen.blit(title_surf, (SCREEN_WIDTH//2 - title_surf.get_width()//2 + offset,
                                     100 + offset))
        title_surf = title_font.render(title, True, TEXT_COLOR)
        screen.blit(title_surf, (SCREEN_WIDTH//2 - title_surf.get_width()//2, 100))

        # Label du champ de saisie
        font = pygame.font.Font(None, 36)
        label = font.render("Nom de la sauvegarde :", True, TEXT_COLOR)
        screen.blit(label, (150, 200))

        # Champ de saisie
        text_input.draw(screen, current_time)

        # Slots de sauvegarde
        for slot in save_slots:
            slot.draw(screen, current_time)

        # Boutons avec effet de survol
        mouse_pos = pygame.mouse.get_pos()
        save_hover = 300 <= mouse_pos[0] <= 500 and 620 <= mouse_pos[1] <= 670
        cancel_hover = 50 <= mouse_pos[0] <= 250 and 520 <= mouse_pos[1] <= 570

        for button_data in [
            ((300, 620, 200, 50), "Sauvegarder", save_hover),
            ((50, 520, 200, 50), "Annuler", cancel_hover)
        ]:
            rect, text, hovering = button_data

            # Effet de lueur au survol
            if hovering:
                glow_rect = pygame.Rect(*rect).inflate(8, 8)
                pygame.draw.rect(screen, (*ACCENT_COLOR, 100), glow_rect, border_radius=10)

            color = BUTTON_HOVER_COLOR if hovering else BUTTON_COLOR
            pygame.draw.rect(screen, color, rect, border_radius=8)
            pygame.draw.rect(screen, ACCENT_COLOR, rect, 2, border_radius=8)

            text_surf = font.render(text, True, TEXT_COLOR)
            text_rect = text_surf.get_rect(center=(rect[0] + rect[2]//2, rect[1] + rect[3]//2))
            screen.blit(text_surf, text_rect)

        pygame.display.flip()
        clock.tick(60)

import pygame
import math
import random
from pygame import gfxdraw
import colorsys

# Constantes
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (15, 18, 25)
TEXT_COLOR = (255, 255, 255)
VICTORY_RED = (220, 20, 20)
DARK_RED = (120, 20, 20)

class Particle:
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
        gfxdraw.filled_circle(surface, int(self.x), int(self.y),
                              int(self.size), (*self.color, alpha))

class VictoryScreen:
    def __init__(self):
        self.particles = []
        self.time = 0
        self.stats = {
            'turns': 58,
            'population': 0,
            'destruction': 100,
            'time_elapsed': "2:15:30"
        }

    def create_particles(self):
        if random.random() < 0.3:
            x = random.randint(0, SCREEN_WIDTH)
            y = random.randint(0, SCREEN_HEIGHT)
            self.particles.append(Particle(x, y))

    def draw_victory_text(self, surface, time):
        # Effet de texte dramatique pour "VICTOIRE"
        title = "VICTOIRE"
        title_font = pygame.font.Font(None, 120)

        # Animation d'échelle et rotation pour chaque lettre
        current_x = SCREEN_WIDTH // 2 - title_font.size(title)[0] // 2
        for i, char in enumerate(title):
            scale = 1 + math.sin(time * 0.005 + i * 0.5) * 0.2
            angle = math.sin(time * 0.003 + i * 0.4) * 5

            char_surf = title_font.render(char, True, VICTORY_RED)
            scaled_size = (int(char_surf.get_width() * scale),
                           int(char_surf.get_height() * scale))
            char_surf = pygame.transform.scale(char_surf, scaled_size)
            char_surf = pygame.transform.rotate(char_surf, angle)

            # Effet de lueur
            glow_surf = title_font.render(char, True, DARK_RED)
            glow_surf = pygame.transform.scale(glow_surf, scaled_size)
            glow_surf = pygame.transform.rotate(glow_surf, angle)

            char_rect = char_surf.get_rect(center=(current_x + title_font.size(char)[0]//2,
                                                   200 + math.sin(time * 0.004 + i) * 10))

            # Multiple layers of glow
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

        # Statistiques avec animation de compteur
        stats_text = [
            f"Nombre de tours : {self.stats['turns']}",
            f"Population restante : {self.stats['population']}",
            f"Destruction totale : {self.stats['destruction']}%",
            f"Temps écoulé : {self.stats['time_elapsed']}"
        ]

        for i, text in enumerate(stats_text):
            alpha = min(255, time * 2 - i * 100)  # Apparition progressive
            offset = math.sin(time * 0.005 + i * 0.5) * 5

            # Ombre du texte
            shadow_surf = stats_font.render(text, True, (0, 0, 0))
            shadow_surf.set_alpha(alpha // 2)
            surface.blit(shadow_surf, (SCREEN_WIDTH//2 - shadow_surf.get_width()//2 + 2,
                                       y_pos + i * 40 + 2))

            # Texte principal
            text_surf = stats_font.render(text, True, TEXT_COLOR)
            text_surf.set_alpha(alpha)
            surface.blit(text_surf, (SCREEN_WIDTH//2 - text_surf.get_width()//2 + offset,
                                     y_pos + i * 40))

    def draw_background_effect(self, surface, time):
        # Effet de grille en perspective
        for i in range(20):
            progress = (time * 0.5 + i) % 20 / 20
            y = SCREEN_HEIGHT * progress
            alpha = int(255 * (1 - progress))

            pygame.draw.line(surface, (*DARK_RED, alpha // 4),
                             (0, y), (SCREEN_WIDTH, y))

            for x in range(0, SCREEN_WIDTH, 100):
                end_y = SCREEN_HEIGHT//2 + (y - SCREEN_HEIGHT//2) * 1.2
                pygame.draw.line(surface, (*DARK_RED, alpha // 4),
                                 (x, y), (x, end_y))

    def run(self):
        clock = pygame.time.Clock()
        buttons = {
            'replay': pygame.Rect(450, 550, 300, 50),
            'menu': pygame.Rect(450, 620, 300, 50)
        }

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

            # Update
            self.create_particles()
            self.particles = [p for p in self.particles if p.update()]

            # Draw
            screen.fill(BACKGROUND_COLOR)

            # Background effects
            self.draw_background_effect(screen, self.time)

            # Particles
            for particle in self.particles:
                particle.draw(screen)

            # Main content
            self.draw_victory_text(screen, self.time)

            # Subtitle avec effet de fondu
            subtitle = "La Catastrophe a Triomphé"
            alpha = int(128 + math.sin(self.time * 0.05) * 64)
            subtitle_surf = subtitle_font.render(subtitle, True, VICTORY_RED)
            subtitle_surf.set_alpha(alpha)
            subtitle_rect = subtitle_surf.get_rect(center=(SCREEN_WIDTH//2, 300))
            screen.blit(subtitle_surf, subtitle_rect)

            # Stats
            self.draw_stats(screen, self.time)

            # Buttons with effects
            mouse_pos = pygame.mouse.get_pos()
            for text, button in zip(['Rejouer', 'Menu Principal'], buttons.values()):
                hover = button.collidepoint(mouse_pos)

                # Button glow effect
                glow_color = VICTORY_RED if hover else DARK_RED
                for i in range(5):
                    glow_rect = button.inflate(i*2, i*2)
                    pygame.draw.rect(screen, (*glow_color, 50-i*10), glow_rect, border_radius=10)

                # Main button
                pygame.draw.rect(screen, BACKGROUND_COLOR, button, border_radius=8)
                pygame.draw.rect(screen, VICTORY_RED, button, 2, border_radius=8)

                # Button text with shadow
                text_surf = button_font.render(text, True, TEXT_COLOR)
                text_rect = text_surf.get_rect(center=button.center)
                if hover:
                    text_rect.y += math.sin(self.time * 0.1) * 2
                screen.blit(text_surf, text_rect)

            pygame.display.flip()
            clock.tick(60)

def catastrophe_victory_screen():
    victory_screen = VictoryScreen()
    return victory_screen.run()

import pygame
import math
import random
from pygame import gfxdraw

# Constantes
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (15, 18, 25)
TEXT_COLOR = (255, 255, 255)
VICTORY_COLOR = (64, 209, 124)
GOLDEN_COLOR = (255, 215, 0)

class VictoryParticle:
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
        gfxdraw.filled_circle(surface, int(self.x), int(self.y),
                              int(self.size), (*self.color, self.alpha))

class AnimatedText:
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
            # Effet de lueur
            glow_color = VICTORY_COLOR
            glow_alpha = int(128 + math.sin(time * 0.01) * 64)

            for offset in range(3):
                glow_surf = self.font.render(char['char'], True, glow_color)
                glow_surf.set_alpha(glow_alpha // (offset + 1))
                for dx, dy in [(offset,0), (-offset,0), (0,offset), (0,-offset)]:
                    surface.blit(glow_surf, (char['x'] + dx, char['y'] + dy))

            # Texte principal
            text_surf = self.font.render(char['char'], True, TEXT_COLOR)
            surface.blit(text_surf, (char['x'], char['y']))

class VictoryButton:
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

        # Effet de lueur
        glow_radius = 10 + self.pulse
        for i in range(int(glow_radius)):
            alpha = int(100 * (1 - i / glow_radius))
            glow_rect = self.rect.inflate(i * 2, i * 2)
            glow_color = VICTORY_COLOR if hover else (100, 100, 100)
            pygame.draw.rect(surface, (*glow_color, alpha), glow_rect, border_radius=15)

        # Bouton principal
        color = (80, 180, 100) if hover else (60, 66, 77)
        pygame.draw.rect(surface, color, self.rect, border_radius=15)
        pygame.draw.rect(surface, VICTORY_COLOR, self.rect, 2, border_radius=15)

        # Texte
        font = pygame.font.Font(None, 36)
        if hover:
            # Effet de lueur sur le texte
            for offset in [-1, 1]:
                text_glow = font.render(self.text, True, VICTORY_COLOR)
                text_rect = text_glow.get_rect(center=(self.rect.centerx + offset,
                                                       self.rect.centery + offset))
                surface.blit(text_glow, text_rect)

        text_surf = font.render(self.text, True, TEXT_COLOR)
        text_rect = text_surf.get_rect(center=self.rect.center)
        surface.blit(text_surf, text_rect)

def draw_earth(surface, time):
    # Dessine une Terre stylisée
    center_x, center_y = SCREEN_WIDTH // 2, 120
    radius = 60

    # Aura de la Terre
    for i in range(20):
        alpha = int(100 * (1 - i / 20))
        glow_radius = radius + i * 2
        glow_color = (*VICTORY_COLOR, alpha)
        pygame.draw.circle(surface, glow_color, (center_x, center_y), glow_radius)

    # Terre
    pygame.draw.circle(surface, (100, 200, 255), (center_x, center_y), radius)

    # Continents animés
    for i in range(5):
        angle = time * 0.001 + i * math.pi / 2.5
        x = center_x + math.cos(angle) * radius * 0.7
        y = center_y + math.sin(angle) * radius * 0.7
        size = random.randint(10, 20)
        pygame.draw.circle(surface, (64, 209, 124), (int(x), int(y)), size)

def humanity_victory_screen():
    clock = pygame.time.Clock()
    particles = [VictoryParticle() for _ in range(100)]

    # Textes animés
    title = AnimatedText("VICTOIRE DE L'HUMANITÉ", pygame.font.Font(None, 72), 200)
    subtitle = AnimatedText("L'équilibre écologique est atteint!", pygame.font.Font(None, 48), 300)

    # Boutons
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
                elif menu_button.rect.collidepoint(mouse_pos):
                    print("Menu Principal")

        # Mise à jour
        for particle in particles:
            particle.update(time)
        title.update(time)
        subtitle.update(time)

        # Dessin
        screen.fill(BACKGROUND_COLOR)

        # Particules
        for particle in particles:
            particle.draw(screen)

        # Terre animée
        draw_earth(screen, time)

        # Textes animés
        title.draw(screen, time)
        subtitle.draw(screen, time)

        # Stats avec fondu
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

        # Boutons
        retry_button.draw(screen, time)
        menu_button.draw(screen, time)

        pygame.display.flip()
        clock.tick(60)

if __name__ == "__main__":
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Gaia Ultimatum - Victoire")
    # humanity_victory_screen()
    # screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    # pygame.display.set_caption("Gaia Ultimatum - Victoire")
    # catastrophe_victory_screen()
    # screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    # pygame.display.set_caption("Gaia Ultimatum - Sauvegarde")
    # save_game_screen()
    # screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    # pygame.display.set_caption("Gaia Ultimatum - Charger une Partie")
    # load_game_screen()
    # screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    # pygame.display.set_caption("Gaia Ultimatum - Options")
    # controls_options_screen()
    # screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    # pygame.display.set_caption("Options de Jouabilité")
    # playability_options_screen()
    # screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    # pygame.display.set_caption("Options Sonores")
    # sound_options_screen()
    # screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    # pygame.display.set_caption("Options Graphiques")
    # graphics_options_screen()
    # options_screen()
    # country_info_window()
    # screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    # pygame.display.set_caption("Gaia Ultimatum - Améliorations")
    # catastrophe_upgrades_screen()
    # world_map_screen()
    # new_game_menu()
    # main_menu()