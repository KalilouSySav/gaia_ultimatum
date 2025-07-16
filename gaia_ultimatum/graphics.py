import colorsys
from pygame import gfxdraw
from utils import *
from config import *
from game import main_menu_game_loop, new_game_menu_loop, dashboard_menu_loop
from collections import deque

class Button:
    def __init__(self, rect, text, action, mouse_pos):
        self.rect = rect
        self.text = text
        self.action = action
        self.mouse_pos = mouse_pos
        self.hover = 0
        self.animation = 0
        self.shake_offset = [0, 0]

    def update_shake(self, time):
        if self.hover > 0.5:
            self.shake_offset = calculate_shake_offset(time, DEFAULT_SHAKE_INTENSITY)
        else:
            self.shake_offset = [0, 0]

    def draw(self, surface, time, mouse_pos):
        hover = self.rect.collidepoint(mouse_pos)
        self.hover = calculate_hover(self.hover, DEFAULT_HOVER_SPEED) if hover else max(0, self.hover - DEFAULT_HOVER_SPEED)
        self.update_shake(time)

        # Appliquer l'effet de tremblement
        rect = self.rect.copy()
        rect.x += self.shake_offset[0]
        rect.y += self.shake_offset[1]

        # Effet de pulsation
        pulse = calculate_pulse(time, DEFAULT_PULSE_AMPLITUDE, DEFAULT_PULSE_FREQ_COEFFICIENT)

        # Couleur dynamique pour l'effet de survol
        dynamic_color = calculate_dynamic_color(time, DEFAULT_HUE_OFFSET, DEFAULT_HUE_SPEED, DEFAULT_SATURATION, DEFAULT_VALUE)

        # Effet de lueur
        self.draw_glow(surface, rect, dynamic_color, pulse, hover)

        # Bouton principal avec couleur de survol
        color = [int(c1 + (c2 - c1) * self.hover) for c1, c2 in zip(BUTTON_COLOR, BUTTON_HOVER_COLOR)]
        draw_button_with_hover_effect(surface, color, rect, DEFAULT_BUTTON_BORDER_RADIUS)

        # Bordure animée
        border_color = dynamic_color if hover else ACCENT_COLOR
        draw_button_with_border(surface, border_color, rect, DEFAULT_BORDER_THICKNESS, DEFAULT_BUTTON_BORDER_RADIUS)

        # Texte avec effets d'ombre et de lueur
        self.draw_text(surface, rect, self.text, dynamic_color, hover, time)

    def draw_glow(self, surface, rect, dynamic_color, pulse=DEFAULT_GLOW_PULSE, hover=False):

        # Calcul du rayon de lueur
        glow_radius = min(calculate_glow_radius(pulse, hover, DEFAULT_GLOW_RADIUS), DEFAULT_MAX_GLOW_RADIUS)

        # Boucle pour dessiner la lueur
        for i in range(int(glow_radius)):
            alpha = int(DEFAULT_GLOW_ALPHA * (1 - i / glow_radius))
            glow_rect = rect.inflate(i * 2, i * 2)
            glow_color = (*dynamic_color, alpha) if hover else (*DEFAULT_BUTTON_COLOR, alpha)
            draw_glow_rect(surface, glow_color, glow_rect, border_radius=DEFAULT_BUTTON_BORDER_RADIUS)
    def draw_text(self, surface, rect, text, dynamic_color, hover=False, time=0):
        # Crée et dessine l'ombre
        shadow_surf, shadow_rect = create_text_surface(text, rect, color=DEFAULT_SHADOW_COLOR, font_size=DEFAULT_BUTTON_FONT_SIZE)
        shadow_rect.center = rect.center
        shadow_rect.x += DEFAULT_SHADOW_OFFSET
        shadow_rect.y += DEFAULT_SHADOW_OFFSET

        surface.blit(shadow_surf, shadow_rect)

        # Si hover est actif, ajoute la lueur dynamique
        if hover:
            draw_glow_text(surface, rect, text, dynamic_color, time, glow_radius=DEFAULT_GLOW_RADIUS, font_size=DEFAULT_BUTTON_FONT_SIZE, glow_intensity=DEFAULT_GLOW_INTENSITY, glow_alpha_step=DEFAULT_GLOW_ALPHA_STEP)

        # Dessine le texte principal
        text_surf, text_rect = create_text_surface(text, rect, color=DEFAULT_BUTTON_COLOR, font_size=DEFAULT_BUTTON_FONT_SIZE)
        surface.blit(text_surf, text_rect)

    def update(self, time):
        self.update_shake(time)

    def handle_event(self, event):
        # if event.type == pygame.MOUSEBUTTONDOWN:
        #     if self.rect.collidepoint(event.pos):
        #         self.action()
        pass

class MenuButton(Button):
    def __init__(self, rect, text, action, mouse_pos):
        super().__init__(rect, text, action, mouse_pos)

    def draw(self, surface, time, mouse_pos):
        super().draw(surface, time, mouse_pos)

    def update(self, time):
        super().update(time)

    def handle_event(self, event):
        super().handle_event(event)

class ElementButton(Button):
    """Bouton pour la sélection d'un élément, basé sur la classe Button."""
    def __init__(self, rect, text, action, mouse_pos, description, colors, background_image_path):
        super().__init__(rect, text, action, mouse_pos)
        self.description = description
        self.colors = colors  # [default_color, hover_color]
        self.selected = False
        self.animation = 0
        self.color = colors[0]
        self.hover_color = colors[1]
        self.background_image_path = background_image_path

    def draw(self, surface, time, mouse_pos):
        super().draw(surface, time, mouse_pos)
        hover = self.rect.collidepoint(mouse_pos)
        pulse = calculate_pulse(time, DEFAULT_ELEMENT_PULSE_AMPLITUDE, DEFAULT_ELEMENT_PULSE_FREQ_COEFFICIENT)

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
            draw_glow_rect(surface, glow_color, glow_rect, border_radius=15)

        draw_rect(surface, current_color, self.rect, 0, border_radius=15)
        draw_rect(surface, (*current_color, 150), self.rect, 3, border_radius=15)

        # Ajout de l'image translucide en arrière-plan
        background_image = load_image(self.background_image_path)
        if background_image:
            scale_factor_width = self.rect.width / background_image.get_width()
            scale_factor_height = self.rect.height / background_image.get_height()
            image = scale_image(background_image, (scale_factor_width, scale_factor_height))
            image.set_alpha(120)  # Réglage de la transparence
            surface.blit(image, self.rect.topleft)

        element_font = create_font(ELEMENT_FONT_SIZE)
        description_font = create_font(DESCRIPTION_FONT)
        element_surf = element_font.render(self.text, True, TEXT_COLOR)
        element_rect = element_surf.get_rect(center=self.rect.center)
        surface.blit(element_surf, element_rect)
        if hover:
            desc_surf = description_font.render(self.description, True, TEXT_COLOR)
            desc_rect = desc_surf.get_rect(midtop=(self.rect.centerx, self.rect.bottom + 10))
            surface.blit(desc_surf, desc_rect)


    def update(self, time):
        super().update(time)

    def handle_event(self, event):
        super().handle_event(event)


class ProgressBar:
    def __init__(self, background_progress_bar_rect, progress_bar_rect, progress, max_value,
                 bar_color=PROGRESS_BAR_FILL, bg_color=PROGRESS_BAR_BG,
                 text_color=TEXT_COLOR, font=SMALL_FONT, corner_radius=5, padding=2):
        self.background_progress_bar_rect = background_progress_bar_rect
        self.progress_bar_rect = progress_bar_rect
        self.progress = progress
        self.max_value = max_value
        self.bar_color = bar_color
        self.bg_color = bg_color
        self.text_color = text_color
        self.font = font
        self.corner_radius = corner_radius
        self.padding = padding


    def draw(self, surface, progress):
        """
        Dessine une barre de progression avec un effet arrondi et personnalisable.

        Args:
            surface: Surface pygame où dessiner la barre.
            x, y: Position (en pixels) de la barre.
            width, height: Dimensions (en pixels) de la barre.
            progress: Valeur actuelle du progrès.
            max_value: Valeur maximale correspondant à 100 %.
            bar_color: Couleur de la partie remplie de la barre.
            bg_color: Couleur de l'arrière-plan de la barre.
            text_color: Couleur du texte affichant le pourcentage.
            font: Police utilisée pour afficher le texte.
            corner_radius: Rayon des coins arrondis de la barre.
            padding: Espacement (en pixels) entre le remplissage et les bords.
        """
        # Dessine l'arrière-plan de la barre
        draw_rounded_rect(surface, self.bg_color, self.background_progress_bar_rect, self.corner_radius)

        # Calcul de la largeur de la partie remplie
        (x, y, width, height) = self.background_progress_bar_rect
        progress_width = int((progress / self.max_value) * (width - 2 * self.padding))
        if progress_width > 0:
            draw_rounded_rect(surface, self.bar_color, self.progress_bar_rect, self.corner_radius)

        # Affiche le pourcentage au centre de la barre
        percentage = f"{int(progress / self.max_value * 100)}%"
        new_font = create_font(FONT)
        draw_text(surface, percentage, new_font, self.text_color, x + width // 2, y + height // 2)

class ParticleSystem:
    def __init__(self, screen_width=SCREEN_WIDTH, screen_height=SCREEN_HEIGHT, num_particles=NUM_PARTICLES,emitters=EMITTERS, accent_colors=ACCENT_COLORS, size_range=SIZE_RANGE,speed_range=SPEED_RANGE, alpha_range=ALPHA_RANGE):
        """
        Initialise le système de particules.

        :param screen_width: Largeur de l'écran.
        :param screen_height: Hauteur de l'écran.
        :param num_particles: Nombre de particules à afficher.
        :param emitters: Liste des émetteurs de particules.
        :param accent_colors: Couleurs d'accentuation des particules.
        :param size_range: Plage de tailles de particules.
        :param speed_range: Plage de vitesses de particules.
        :param alpha_range: Plage de valeurs alpha pour les particules.
        """
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.num_particles = num_particles
        self.emitters = emitters
        self.accent_colors = accent_colors
        self.size_range = size_range
        self.speed_range = speed_range
        self.alpha_range = alpha_range
        self.particles = [
            create_particle(
                self.emitters,
                self.screen_height,
                self.accent_colors,
                self.size_range,
                self.speed_range,
                self.alpha_range
            )
            for _ in range(self.num_particles)
        ]

    def update(self, time):
        for particle in self.particles:
            update_particle(particle, time, self.screen_width, self.screen_height, self.emitters)

    def draw(self, surface):
        for particle in self.particles:
            draw_particle(surface, particle)

    def draw_background(self, surface, time):
        """
        Dessine des particules en arrière-plan pour un effet visuel.
        """
        for i in range(DEFAULT_BACKGROUND_PARTICLE_COUNT):
            x, y = calculate_particle_position(time, i, self.screen_width, self.screen_height)
            size, alpha = calculate_particle_size_alpha(time, x, y)
            gfxdraw.filled_circle(surface, int(x), int(y), int(size), (*DEFAULT_BUTTON_COLOR, alpha))

from collections import deque
import pygame
import time
from pygame import gfxdraw
import math

class Notification:
    def __init__(self, message, type="info"):
        self.message = message
        self.type = type
        self.creation_time = time.time()
        self.opacity = 0
        self.y_offset = 50  # Pour l'animation d'entrée

        # Couleurs selon le type de notification
        self.colors = {
            "info": (70, 130, 180),      # Bleu steel
            "success": (92, 184, 92),     # Vert
            "warning": (240, 173, 78),    # Orange
            "error": (217, 83, 79)        # Rouge
        }
        self.color = self.colors.get(type, self.colors["info"])

class NotificationPanel:
    def __init__(self, max_notifications=10):
        """Initialise le panneau de notifications avec animations."""
        self.notifications = deque(maxlen=max_notifications)
        self.font = pygame.font.Font(None, 32)
        self.small_font = pygame.font.Font(None, 24)
        self.title_font = pygame.font.Font(None, 36)
        self.animation_speed = 5
        self.notification_height = 40
        self.padding = 10
        self.icon_size = 20

    def add_notification(self, message, type="info"):
        """Ajoute une notification avec un type spécifique."""
        self.notifications.append(Notification(message, type))

    def clear_notifications(self):
        """Efface toutes les notifications."""
        self.notifications.clear()

    def _draw_notification_icon(self, surface, notification, x, y):
        """Dessine l'icône de la notification selon son type."""
        icon_x = x + self.padding
        icon_y = y + (self.notification_height - self.icon_size) // 2

        if notification.type == "info":
            # Cercle d'information
            pygame.draw.circle(surface, notification.color, (icon_x + self.icon_size//2, icon_y + self.icon_size//2),
                               self.icon_size//2)
            draw_text(surface, "i", self.small_font, (255, 255, 255),
                      icon_x + self.icon_size//2, icon_y + self.icon_size//2)

        elif notification.type == "success":
            # Coche
            points = [
                (icon_x + 5, icon_y + self.icon_size//2),
                (icon_x + self.icon_size//2, icon_y + self.icon_size - 5),
                (icon_x + self.icon_size - 5, icon_y + 5)
            ]
            pygame.draw.lines(surface, notification.color, False, points, 2)

        elif notification.type == "warning":
            # Triangle d'avertissement
            points = [
                (icon_x + self.icon_size//2, icon_y),
                (icon_x + self.icon_size, icon_y + self.icon_size),
                (icon_x, icon_y + self.icon_size)
            ]
            pygame.draw.polygon(surface, notification.color, points)

        elif notification.type == "error":
            # X
            pygame.draw.line(surface, notification.color,
                             (icon_x + 5, icon_y + 5),
                             (icon_x + self.icon_size - 5, icon_y + self.icon_size - 5), 2)
            pygame.draw.line(surface, notification.color,
                             (icon_x + 5, icon_y + self.icon_size - 5),
                             (icon_x + self.icon_size - 5, icon_y + 5), 2)

    def draw(self, surface, x, y, width, height):
        """Dessine le panneau de notifications avec effets visuels."""
        current_time = time.time()

        # Fond du panneau avec effet de dégradé
        for i in range(height):
            alpha = int(150 + (i / height) * 50)
            pygame.draw.line(surface, (*self.notifications[0].colors["info"], alpha) if self.notifications else (70, 130, 180, alpha),
                             (x, y + i), (x + width, y + i))

        # Bordure arrondie
        pygame.draw.rect(surface, (255, 255, 255, 30), (x, y, width, height), 2, border_radius=10)

        # Titre avec effet de lueur
        title = "Notifications"
        title_surf = self.title_font.render(title, True, (255, 255, 255))
        title_rect = title_surf.get_rect(centerx=x + width//2, y=y + 25)

        # Effet de lueur pour le titre
        glow_surf = pygame.Surface((title_rect.width + 20, title_rect.height + 20), pygame.SRCALPHA)
        for i in range(10):
            alpha = 20 - i * 2
            pygame.draw.rect(glow_surf, (255, 255, 255, alpha),
                             (10-i, 10-i, title_rect.width + i*2, title_rect.height + i*2),
                             border_radius=5)
        surface.blit(glow_surf, (title_rect.x - 10, title_rect.y - 10))
        surface.blit(title_surf, title_rect)

        # Ligne de séparation avec animation
        line_pos = y + 50
        line_width = int(width * (0.5 + math.sin(current_time * 2) * 0.1))
        pygame.draw.line(surface, (255, 255, 255, 100),
                         (x + width//2 - line_width//2, line_pos),
                         (x + width//2 + line_width//2, line_pos), 2)

        # Affichage des notifications avec animations
        notification_y = y + 60
        for notification in list(self.notifications)[-3:]:
            age = current_time - notification.creation_time

            # Animation d'entrée
            if notification.opacity < 255:
                notification.opacity = min(255, notification.opacity + self.animation_speed)
            if notification.y_offset > 0:
                notification.y_offset = max(0, notification.y_offset - self.animation_speed)

            # Fond de la notification
            notification_rect = pygame.Rect(x + 5, notification_y + notification.y_offset,
                                            width - 10, self.notification_height)
            pygame.draw.rect(surface, (*notification.color, 40), notification_rect,
                             border_radius=5)

            # Icône
            self._draw_notification_icon(surface, notification,
                                         notification_rect.x, notification_rect.y)

            # Texte de la notification
            message_surface = self.small_font.render(notification.message, True,
                                                     (255, 255, 255, notification.opacity))
            surface.blit(message_surface, (notification_rect.x + self.icon_size + self.padding * 2,
                                           notification_rect.y + (self.notification_height - message_surface.get_height())//2))

            notification_y += self.notification_height + 5

def draw_background_effect(surface, time):
    """Dessine un effet de grille en perspective en arrière-plan."""
    num_lines = 20
    for i in range(num_lines):
        progress = (time * 0.001 + i) % num_lines / num_lines
        y = SCREEN_HEIGHT * progress
        alpha = int(255 * (1 - progress))

        start_pos = (0, y)
        end_pos = (SCREEN_WIDTH, y)
        draw_new_line(surface, (*ACCENT_COLOR, alpha // 4), start_pos, end_pos)

        for x in range(0, SCREEN_WIDTH, 100):
            vanishing_point = SCREEN_HEIGHT // 2
            start_y = y
            end_y = vanishing_point + (y - vanishing_point) * 1.2
            draw_new_line(surface, (*ACCENT_COLOR, alpha // 4), (x, start_y), (x, end_y))


# Les écrans du jeu
def main_menu(screen, clock, mouse_pos, catastrophes):
    """Fonction principale pour afficher le menu principal du jeu."""
    particle_system = ParticleSystem(SCREEN_WIDTH, SCREEN_HEIGHT)

    new_game_rect = create_rect(SCREEN_WIDTH // 2 - MAIN_MENU_BUTTON_WIDTH // 2, MAIN_MENU_START_Y, MAIN_MENU_BUTTON_WIDTH, MAIN_MENU_BUTTON_HEIGHT)
    continue_rect = new_game_rect.copy()
    continue_rect.y += MAIN_MENU_BUTTON_SPACING
    options_rect = continue_rect.copy()
    options_rect.y += MAIN_MENU_BUTTON_SPACING
    quit_rect = options_rect.copy()
    quit_rect.y += MAIN_MENU_BUTTON_SPACING


    # Création des boutons
    buttons = [
        MenuButton(new_game_rect, "Nouvelle Partie", "new_game", mouse_pos),
        MenuButton(continue_rect, "Continuer", "continue", mouse_pos),
        MenuButton(options_rect, "Options", "options", mouse_pos),
        MenuButton(quit_rect, "Quitter", "quit", mouse_pos),
    ]

    # Lancer la boucle de jeu
    main_menu_game_loop(screen, clock, particle_system, buttons, draw_background_effect, new_game_menu, catastrophes)

def new_game_menu(screen, clock, mouse_pos, catastrophes):

    # Création des boutons
    button_positions = calculate_button_positions(len(catastrophes), ELEMENT_BUTTON_WIDTH, ELEMENT_BUTTON_HEIGHT, ELEMENT_BUTTON_SPACING, ELEMENT_MAX_BUTTONS_PER_LINE, SCREEN_WIDTH, ELEMENT_BUTTON_START_Y)
    element_buttons = [
        ElementButton(
            create_rect(x, y, ELEMENT_BUTTON_WIDTH, ELEMENT_BUTTON_HEIGHT),  # Rect calculé
            c["text"],                                      # Texte du bouton
            c["text"],                                      # Action associée
            mouse_pos,                                      # Position de la souris
            c["description"],                               # Description
            [c["color"], c["color"]],                                 # Couleur
            c["icon"]                                        # Chemin de l'icône
        )
        for (x, y), c in zip(button_positions, catastrophes)
    ]

    new_game_menu_particles = ParticleSystem()
    back_button = Button(create_rect(DEFAULT_BACK_BUTTON_START_X, DEFAULT_BACK_BUTTON_START_Y, DEFAULT_BACK_BUTTON_WIDTH, DEFAULT_BACK_BUTTON_HEIGHT), "retour", "back", mouse_pos)
    new_game_menu_loop(screen, clock, back_button, element_buttons, new_game_menu_particles, main_menu, dashboard_menu, catastrophes)

def dashboard_menu(screen, choix_catastrophe):
    """Écran de la carte du monde avec les informations et les actions possibles."""
    notifications = ["Nouvelle technologie découverte!", "Population: 1M habitants", "Ressources: Stables"]
    evolution_points = 10
    humanity_progress = 50

    # Charger l'image de la carte du monde
    world_map_image = load_image("data/images/world_map.png")
    scale_factor_width = 600 / world_map_image.get_width()
    scale_factor_height = 400 / world_map_image.get_height()
    world_map_image = scale_image(world_map_image, (scale_factor_width, scale_factor_height))  # Ajuster la taille si nécessaire
    world_map_rect = world_map_image.get_rect(topleft=(100, 100))

    # Bouton "Voir la carte"
    mouse_pos = get_mouse_positon()
    view_map_rect = create_rect(100, 560, 200, 50)
    view_map_button = Button(view_map_rect, "Voir la carte", "view_map", mouse_pos)

    # Bouton "Améliorer compétence"
    improve_skills_rect = create_rect(400, 560, 250, 50)
    improve_skills_button = Button(improve_skills_rect, "Améliorer compétence", "improve_skills", mouse_pos)

    pause_button_rect = create_rect(900, 560, 150, 50)
    pause_button = Button(pause_button_rect, "Pause", "pause", mouse_pos)

    background_progress_bar_rect = create_rect(850, 100, 300, 30)
    progress_width = int((70 / 100) * (30 - 2 * 2))
    progress_bar_rect = create_rect(850 + 2, 100 + 2, progress_width, 30 - 2 * 2)
    progress_bar = ProgressBar(background_progress_bar_rect, progress_bar_rect, 70, 80)

    particles = ParticleSystem()

    panel = NotificationPanel()
    unit_pop = " milliards"
    unit_death_pop = " milions"
    unit_target_pop = " milions"
    death_pop = 2
    target_pop = 766
    population = 8
    panel.add_notification("Population mondiale: "+str(population)+unit_pop, "info")
    panel.add_notification("Personnes affectées: "+str(target_pop)+unit_target_pop, "info")
    panel.add_notification("Morts: "+str(death_pop)+unit_death_pop, "info")

    dashboard_menu_loop(screen, humanity_progress, evolution_points, world_map_image, world_map_rect, choix_catastrophe, progress_bar, pause_button, view_map_button, improve_skills_button, panel, particles)


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



