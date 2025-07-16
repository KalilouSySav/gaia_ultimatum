from config import *
from ui import main_menu_handle_events, new_game_handle_events, dashboard_handle_events
from utils import *
import pygame


def main_menu_game_loop(screen, clock, particle_system, buttons, draw_background_effect, new_game_menu, catastrophes):
    """Gère la boucle principale du menu."""
    time = 0
    while True:
        time += 1

        # Gestion des événements
        main_menu_handle_events(screen, clock, buttons, new_game_menu, catastrophes)

        # Mise à jour des particules
        particle_system.update(time)

        # Dessin des éléments du menu
        screen.fill(BACKGROUND_COLOR)
        draw_background_effect(screen, time)
        particle_system.draw(screen)
        draw_animated_text(
            surface=screen,
            text="GAIA ULTIMATUM",
            font_path=DEFAULT_FONT_PATH,
            font_size=DEFAULT_FONT_SIZE,
            color=TEXT_COLOR,
            wave_height=DEFAULT_WAVE_HEIGHT,
            wave_length=DEFAULT_WAVE_LENGTH,
            wave_speed=DEFAULT_WAVE_SPEED,
            glow_color=DEFAULT_GLOW_COLOR,
            glow_intensity=DEFAULT_GLOW_INTENSITY,
            glow_steps=DEFAULT_GLOW_STEPS,
            x=SCREEN_WIDTH // 2,
            y=TITLE_Y_POSITION,
            time=time,
            center=True
        )

        # Texte secondaire animé
        font_small = pygame.font.Font(None, 28)
        subtitle = "L'avenir de la Terre est entre vos mains"
        alpha = int(128 + math.sin(time * TITLE_SUBTITLE_ALPHA_SPEED) * 64)
        subtitle_surf = font_small.render(subtitle, True, TEXT_COLOR)
        subtitle_surf.set_alpha(alpha)
        subtitle_rect = subtitle_surf.get_rect(center=(SCREEN_WIDTH // 2, TITLE_Y_POSITION + 100))
        screen.blit(subtitle_surf, subtitle_rect)
        # get mouse position
        mouse_pos = pygame.mouse.get_pos()
        # Dessin des boutons
        for button in buttons:
            button.draw(screen, time, mouse_pos)

        # Version du jeu
        version_text = "v1.0.0"
        version_alpha = int(128 + math.sin(time * TITLE_VERSION_ALPHA_SPEED) * 64)
        version_surf = font_small.render(version_text, True, ACCENT_COLOR)
        version_surf.set_alpha(version_alpha)
        screen.blit(version_surf, (20, SCREEN_HEIGHT - 30))

        # Mise à jour de l'écran
        pygame.display.flip()
        clock.tick(FPS)

def new_game_menu_loop(screen, clock, back_button, element_buttons, new_game_menu_particles, main_menu, dashboard_menu, catastrophes):
    time = 0

    while True:
        time += 1
        mouse_pos = pygame.mouse.get_pos()
        # Event handling
        new_game_handle_events(back_button, element_buttons, main_menu, dashboard_menu, screen, clock, catastrophes)


        # Drawing elements
        screen.fill(BACKGROUND_COLOR)
        new_game_menu_particles.draw_background(screen, time)
        draw_animated_text(
            surface=screen,
            text="Choisissez une Catastrophe",
            font_path=DEFAULT_SUBTITLE_FONT_PATH,
            font_size=DEFAULT_SUBTITLE_FONT_SIZE,
            color=DEFAULT_SUBTITLE_COLOR,
            wave_height=DEFAULT_SUBTITLE_WAVE_HEIGHT,
            wave_length=DEFAULT_SUBTITLE_WAVE_LENGTH,
            wave_speed=DEFAULT_SUBTITLE_WAVE_SPEED,
            glow_color=DEFAULT_SUBTITLE_GLOW_COLOR,
            glow_intensity=DEFAULT_GLOW_INTENSITY,
            glow_steps=DEFAULT_SUBTITLE_GLOW_STEPS,
            x=DEFAULT_SUBTITLE_START_X,
            y=DEFAULT_SUBTITLE_START_Y,
            time=time
        )
        for button in element_buttons:
            button.draw(screen, time, mouse_pos)

        back_button.draw(screen, time, mouse_pos)

        # Update screen
        pygame.display.flip()
        clock.tick(FPS)

def dashboard_menu_loop(screen, humanity_progress, evolution_points, world_map_image, world_map_rect, choix_catastrophe,
                        progress_bar, pause_button, view_map_button, upgrade_skills_button, panel,
                        particles
                        ):
    clock = pygame.time.Clock()
    time = 0
    while True:
        time+=1
        mouse_pos = get_mouse_positon()
        screen.fill(BACKGROUND_COLOR)

        particles.update(time)
        particles.draw(screen)
        # Titre
        title_font = create_font(TITLE_FONT)
        draw_text(screen, "Tableau de Bord", title_font, TEXT_COLOR, SCREEN_WIDTH // 3, 50)

        # Afficher l'image de la carte du monde
        screen.blit(world_map_image, world_map_rect)

        # Barre de progression de l'humanité
        small_font = create_font(SMALL_FONT)
        progress_bar.draw(screen, 22)
        draw_text(screen, "Progrès de l'Humanité", small_font, TEXT_COLOR, 1000, 80)

        # Points d'évolution
        new_font = create_font(FONT)
        draw_text(screen, f"Points d'Évolution : {evolution_points}", new_font, TEXT_COLOR, 900, 180)

        # Panel de notifications
        panel.draw(screen, 800, 220, 350, 250)

        # Bouton Menu Pause
        pause_button.draw(screen, time, mouse_pos)

        # Bouton "Voir la carte"
        view_map_button.draw(screen, time, mouse_pos)

        # Bouton "Améliorer compétence"
        upgrade_skills_button.draw(screen, time, mouse_pos)

        dashboard_handle_events(pause_button, world_map_rect, upgrade_skills_button, choix_catastrophe)

        pygame.display.flip()
        clock.tick(FPS)

def pause_menu_loop():
    time=0
    while True:
        time+=1
        screen.blit(overlay, (0, 0))
        draw_text(screen, "Pause", TITLE_FONT, TEXT_COLOR, SCREEN_WIDTH // 2, 80)

        button_rects = []
        for text, y in buttons:
            button_rect = pygame.Rect(SCREEN_WIDTH // 2 - 100, y, 200, 40)
            draw_button_world_map(button_rect.x, button_rect.y, button_rect.width, button_rect.height, BUTTON_COLOR, BUTTON_BORDER_COLOR, text, FONT, TEXT_COLOR, screen, hover=True)
            button_rects.append((button_rect, text))

        pygame.display.flip()

