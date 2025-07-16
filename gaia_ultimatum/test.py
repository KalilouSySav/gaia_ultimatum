import pygame
import requests
import json
import random
import math
from pygame import gfxdraw

# Initialisation de Pygame
pygame.init()
pygame.font.init()
pygame.mixer.init()

# Constantes
WINDOW_WIDTH = 1024
WINDOW_HEIGHT = 768
FPS = 60

# Couleurs
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE = (0, 123, 255)
GREEN = (40, 167, 69)
RED = (220, 53, 69)
GRAY = (128, 128, 128)
DARK_GRAY = (50, 50, 50)

# Sons
BUTTON_CLICK_SOUND = pygame.mixer.Sound("sounds/button-click.mp3")
CORRECT_SOUND = pygame.mixer.Sound("sounds/button-click.mp3")
INCORRECT_SOUND = pygame.mixer.Sound("sounds/button-click.mp3")

# Configuration de la fenêtre
screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Quiz Trivia")
clock = pygame.time.Clock()

# Chargement de la police
font_path = "path/to/your/font.ttf"  # Remplacez par le chemin de votre police
font = pygame.font.Font(font_path, 32)

# Fonction pour un dégradé dynamique
def dynamic_gradient(rect, start_color, end_color, t):
    for y in range(rect.top, rect.bottom):
        progress = (y - rect.top) / rect.height
        color = [
            int(start_color[i] + (end_color[i] - start_color[i]) * (0.5 + 0.5 * math.sin(t + progress)))
            for i in range(3)
        ]
        pygame.draw.line(screen, color, (rect.left, y), (rect.right, y))

# Effet de texte arc-en-ciel animé
def rainbow_text(surface, text, font, x, y, speed=0.05):
    text_surface = font.render(text, True, BLACK)
    text_rect = text_surface.get_rect(topleft=(x, y))

    for i, char in enumerate(text):
        angle = pygame.time.get_ticks() * speed + i * 0.5
        r = int(127 + 127 * math.sin(angle))
        g = int(127 + 127 * math.sin(angle + 2))
        b = int(127 + 127 * math.sin(angle + 4))
        color = (r, g, b)
        char_surface = font.render(char, True, color)
        char_rect = char_surface.get_rect(topleft=(x, y))
        char_rect.x += sum(font.size(text[:i])[0] for i in range(i))

        # Ombre
        shadow_surface = font.render(char, True, DARK_GRAY)
        shadow_rect = shadow_surface.get_rect(topleft=(char_rect.x + 2, char_rect.y + 2))
        surface.blit(shadow_surface, shadow_rect)

        surface.blit(char_surface, char_rect)

class Particle:
    def __init__(self, x, y, color, shape='circle', gravity=False, rotation=False, trail=False):
        self.x = x
        self.y = y
        self.size = random.randint(5, 10)
        self.color = color
        self.shape = shape
        self.gravity = gravity
        self.rotation = rotation
        self.trail = trail
        self.angle = random.uniform(0, 2 * math.pi)
        self.speed = random.uniform(1, 4)
        self.dx = math.cos(self.angle) * self.speed
        self.dy = math.sin(self.angle) * self.speed
        self.life = 1.0
        self.rotation_angle = 0
        self.rotation_speed = random.uniform(-0.1, 0.1)
        self.trail_positions = []

    def update(self):
        self.x += self.dx
        self.y += self.dy
        self.life -= 0.02

        if self.gravity:
            self.dy += 0.1  # Simule la gravité

        if self.rotation:
            self.rotation_angle += self.rotation_speed

        if self.trail:
            self.trail_positions.append((self.x, self.y))
            if len(self.trail_positions) > 10:
                self.trail_positions.pop(0)

    def draw(self, screen):
        alpha = int(255 * self.life)
        color = (*self.color, alpha)

        if self.trail:
            for i, pos in enumerate(self.trail_positions):
                trail_alpha = int(255 * (i / len(self.trail_positions)) * self.life)
                trail_color = (*self.color, trail_alpha)
                pygame.draw.circle(screen, trail_color, (int(pos[0]), int(pos[1])), 2)

        if self.shape == 'circle':
            pos = (int(self.x), int(self.y))
            pygame.draw.circle(screen, color, pos, self.size)
        elif self.shape == 'square':
            rect = pygame.Rect(self.x - self.size // 2, self.y - self.size // 2, self.size, self.size)
            if self.rotation:
                rotated_surface = pygame.Surface((self.size, self.size), pygame.SRCALPHA)
                pygame.draw.rect(rotated_surface, color, (0, 0, self.size, self.size))
                rotated_surface = pygame.transform.rotate(rotated_surface, math.degrees(self.rotation_angle))
                rotated_rect = rotated_surface.get_rect(center=rect.center)
                screen.blit(rotated_surface, rotated_rect)
            else:
                pygame.draw.rect(screen, color, rect)
        elif self.shape == 'star':
            points = self.calculate_star_points(self.x, self.y, self.size)
            if self.rotation:
                rotated_points = []
                for p in points:
                    rotated_x = (p[0] - self.x) * math.cos(self.rotation_angle) - (p[1] - self.y) * math.sin(self.rotation_angle) + self.x
                    rotated_y = (p[0] - self.x) * math.sin(self.rotation_angle) + (p[1] - self.y) * math.cos(self.rotation_angle) + self.y
                    rotated_points.append((rotated_x, rotated_y))
                pygame.draw.polygon(screen, color, rotated_points)
            else:
                pygame.draw.polygon(screen, color, points)

    def calculate_star_points(self, x, y, size):
        points = []
        for i in range(5):
            angle = i * 2 * math.pi / 5
            outer_radius = size
            inner_radius = size // 2
            px = x + outer_radius * math.cos(angle)
            py = y - outer_radius * math.sin(angle)
            points.append((px, py))

            angle += math.pi / 5
            px = x + inner_radius * math.cos(angle)
            py = y - inner_radius * math.sin(angle)
            points.append((px, py))
        return points

class ParticleEffect:
    def __init__(self, x, y, colors, shapes=['circle'], gravity=False, rotation=False, trail=False):
        self.particles = []
        self.x = x
        self.y = y
        self.colors = colors
        self.shapes = shapes
        self.gravity = gravity
        self.rotation = rotation
        self.trail = trail

        for _ in range(50):
            color = random.choice(self.colors)
            shape = random.choice(self.shapes)
            self.particles.append(Particle(x, y, color, shape, self.gravity, self.rotation, self.trail))

    def update(self):
        for particle in self.particles[:]:
            particle.update()
            if particle.life <= 0:
                self.particles.remove(particle)

    def draw(self, screen):
        for particle in self.particles:
            particle.draw(screen)

    def add_particles(self, n, x=None, y=None):
        x = x if x is not None else self.x
        y = y if y is not None else self.y
        for _ in range(n):
            color = random.choice(self.colors)
            shape = random.choice(self.shapes)
            self.particles.append(Particle(x, y, color, shape, self.gravity, self.rotation, self.trail))

    def is_alive(self):
        return bool(self.particles)

class Button:
    def __init__(self, x, y, width, height, text, color, text_color=WHITE, font_size=20, action=None, outline_color=None, gradient=None, shadow=True):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = text
        self.color = color
        self.text_color = text_color
        self.font = pygame.font.Font(font_path, font_size)
        self.action = action
        self.hovered = False
        self.outline_color = outline_color
        self.gradient = gradient
        self.shadow = shadow
        self.wave_y = 0
        self.wave_speed = 0.1
        self.wave_amplitude = 5
        self.glow_radius = 0
        self.glow_speed = 0.05

    def draw(self, screen):
        # Ombre dynamique
        if self.shadow:
            shadow_offset = 4
            shadow_rect = self.rect.move(shadow_offset, shadow_offset)
            pygame.draw.rect(screen, DARK_GRAY, shadow_rect, border_radius=10)

        # Effet de vague animé
        if self.hovered:
            self.wave_y += self.wave_speed
            if self.wave_y > self.wave_amplitude or self.wave_y < -self.wave_amplitude:
                self.wave_speed *= -1
            wave_offset = int(self.wave_y)
            wave_rect = self.rect.move(0, wave_offset)
        else:
            wave_rect = self.rect

        # Dégradé
        if self.gradient:
            gradient_rect = pygame.Rect(wave_rect.left, wave_rect.top, wave_rect.width, wave_rect.height)
            for i in range(gradient_rect.height):
                t = i / gradient_rect.height
                color = (
                    int(self.gradient[0][0] * (1 - t) + self.gradient[1][0] * t),
                    int(self.gradient[0][1] * (1 - t) + self.gradient[1][1] * t),
                    int(self.gradient[0][2] * (1 - t) + self.gradient[1][2] * t),
                )
                pygame.draw.line(screen, color, (gradient_rect.left, gradient_rect.top + i),
                                 (gradient_rect.right, gradient_rect.top + i))
        else:
            pygame.draw.rect(screen, self.color, wave_rect, border_radius=10)

        # Contour
        if self.outline_color:
            pygame.draw.rect(screen, self.outline_color, wave_rect, 2, border_radius=10)

        # Effet de lueur dynamique au survol
        if self.hovered:
            self.glow_radius = min(self.glow_radius + self.glow_speed, 10)
        else:
            self.glow_radius = max(self.glow_radius - self.glow_speed, 0)

        if self.glow_radius > 0:
            glow_surface = pygame.Surface((self.rect.width + 2 * self.glow_radius, self.rect.height + 2 * self.glow_radius), pygame.SRCALPHA)
            glow_color = (*self.color, 100)
            pygame.draw.rect(glow_surface, glow_color, (self.glow_radius, self.glow_radius, self.rect.width, self.rect.height), border_radius=10)
            screen.blit(glow_surface, (self.rect.x - self.glow_radius, self.rect.y - self.glow_radius), special_flags=pygame.BLEND_RGBA_ADD)

        # Texte
        text_surface = self.font.render(self.text, True, self.text_color)
        text_rect = text_surface.get_rect(center=wave_rect.center)
        screen.blit(text_surface, text_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.hovered = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.hovered:
                BUTTON_CLICK_SOUND.play()
                if self.action:
                    self.action()
                return True
        return False

class Card:
    def __init__(self, x, y, width, height, title, content, color, title_color=WHITE, content_color=WHITE, font_size=20):
        self.rect = pygame.Rect(x, y, width, height)
        self.title = title
        self.content = content
        self.color = color
        self.title_color = title_color
        self.content_color = content_color
        self.font = pygame.font.Font(font_path, font_size)
        self.title_font = pygame.font.Font(font_path, font_size + 8)
        self.shadow_offset = 4

    def draw(self, screen):
        # Ombre
        shadow_rect = self.rect.move(self.shadow_offset, self.shadow_offset)
        pygame.draw.rect(screen, DARK_GRAY, shadow_rect, border_radius=10)

        # Corps de la carte
        pygame.draw.rect(screen, self.color, self.rect, border_radius=10)

        # Titre
        title_surface = self.title_font.render(self.title, True, self.title_color)
        title_rect = title_surface.get_rect(topleft=(self.rect.x + 10, self.rect.y + 10))
        screen.blit(title_surface, title_rect)

        # Contenu
        content_lines = self.content.split('\n')
        y_offset = title_rect.bottom + 10
        for line in content_lines:
            content_surface = self.font.render(line, True, self.content_color)
            content_rect = content_surface.get_rect(topleft=(self.rect.x + 10, y_offset))
            screen.blit(content_surface, content_rect)
            y_offset += self.font.get_height() + 5

    def handle_event(self, event):
        # Vous pouvez ajouter des interactions ici si nécessaire
        pass

class TriviaGame:
    def __init__(self):
        self.font_title = pygame.font.Font(font_path, 56)
        self.font_question = pygame.font.Font(font_path, 32)
        self.current_screen = "menu"
        self.difficulty = "medium"
        self.score = 0
        self.high_scores = self.load_high_scores()
        self.questions = []
        self.current_question = 0
        self.buttons = []
        self.difficulty_buttons = []
        self.menu_buttons = []
        self.high_score_buttons = []
        self.game_over_buttons = []

        self.background_start_color = (174, 214, 241)
        self.background_end_color = (93, 173, 226)
        self.time = 0

        self.particle_effects = []

        self.setup_menu_buttons()
        self.setup_difficulty_buttons()
        self.setup_high_score_buttons()
        self.setup_game_over_buttons()

    def setup_menu_buttons(self):
        button_width = 200
        button_height = 50
        spacing = 20
        x = WINDOW_WIDTH // 2 - button_width // 2
        y = WINDOW_HEIGHT // 2 - (button_height + spacing)

        play_button = Button(x, y, button_width, button_height, "Jouer", BLUE, WHITE, 30, action=self.start_game, gradient=((52, 152, 219), (41, 128, 185)))
        difficulty_button = Button(x, y + button_height + spacing, button_width, button_height, "Difficulté", GREEN, WHITE, 30, action=self.show_difficulty_screen, gradient=((40, 167, 69), (30, 125, 52)))
        high_score_button = Button(x, y + 2*(button_height + spacing), button_width, button_height, "High Scores", RED, WHITE, 30, action=self.show_high_score_screen, gradient=((220, 53, 69), (165, 40, 52)))

        self.menu_buttons = [play_button, difficulty_button, high_score_button]

    def setup_difficulty_buttons(self):
        button_width = 200
        button_height = 50
        spacing = 20
        x = WINDOW_WIDTH // 2 - button_width // 2
        y = WINDOW_HEIGHT // 2 - (button_height + spacing)

        easy_button = Button(x, y, button_width, button_height, "Facile", GREEN, WHITE, 30, action=lambda: self.set_difficulty("easy"), gradient=((40, 167, 69), (30, 125, 52)))
        medium_button = Button(x, y + button_height + spacing, button_width, button_height, "Moyen", BLUE, WHITE, 30, action=lambda: self.set_difficulty("medium"), gradient=((52, 152, 219), (41, 128, 185)))
        hard_button = Button(x, y + 2*(button_height + spacing), button_width, button_height, "Difficile", RED, WHITE, 30, action=lambda: self.set_difficulty("hard"), gradient=((220, 53, 69), (165, 40, 52)))
        back_button = Button(x, y + 3*(button_height + spacing), button_width, button_height, "Retour", GRAY, WHITE, 30, action=self.show_menu_screen, gradient=((128, 128, 128), (100, 100, 100)))

        self.difficulty_buttons = [easy_button, medium_button, hard_button, back_button]

    def setup_high_score_buttons(self):
        button_width = 200
        button_height = 50
        spacing = 20
        x = WINDOW_WIDTH // 2 - button_width // 2
        y = WINDOW_HEIGHT - button_height - spacing - 50

        back_button = Button(x, y, button_width, button_height, "Retour", GRAY, WHITE, 30, action=self.show_menu_screen, gradient=((128, 128, 128), (100, 100, 100)))
        self.high_score_buttons = [back_button]

    def setup_game_over_buttons(self):
        menu_button = Button(WINDOW_WIDTH // 2 - 100, 520, 200, 50, "Menu", BLUE, WHITE, 30, action=self.show_menu_screen, gradient=((52, 152, 219), (41, 128, 185)))
        play_again_button = Button(WINDOW_WIDTH // 2 - 100, 450, 200, 50, "Rejouer", GREEN, WHITE, 30, action=self.start_game, gradient=((40, 167, 69), (30, 125, 52)))
        self.game_over_buttons = [menu_button, play_again_button]

    def set_difficulty(self, difficulty):
        self.difficulty = difficulty
        self.show_menu_screen()

    def fetch_questions(self):
        try:
            url = f"https://opentdb.com/api.php?amount=10&difficulty={self.difficulty}&type=multiple"
            response = requests.get(url)
            data = response.json()
            self.questions = data['results']
            self.current_question = 0
            self.score = 0
            self.setup_buttons()
        except Exception as e:
            print(f"Erreur lors de la récupération des questions : {e}")
            self.questions = []
            self.current_question = 0
            self.score = 0

    def setup_buttons(self):
        self.buttons = []
        if 0 <= self.current_question < len(self.questions):
            answers = self.get_current_answers()
            y_start = 384
            button_width = 400
            button_height = 60
            spacing = 20
            x = WINDOW_WIDTH // 2 - button_width // 2

            for i, answer in enumerate(answers):
                btn = Button(x, y_start + i * (button_height + spacing), button_width, button_height, answer, BLUE, WHITE, 24, gradient=((52, 152, 219), (41, 128, 185)))
                self.buttons.append(btn)

    def get_current_answers(self):
        if not (0 <= self.current_question < len(self.questions)):
            return []
        question = self.questions[self.current_question]
        answers = question['incorrect_answers'] + [question['correct_answer']]
        random.shuffle(answers)
        return answers

    def handle_answer(self, selected_answer):
        correct_answer = self.questions[self.current_question]['correct_answer']
        if selected_answer == correct_answer:
            self.score += 1
            if CORRECT_SOUND:
                CORRECT_SOUND.play()
            self.particle_effects.append(ParticleEffect(WINDOW_WIDTH//2, WINDOW_HEIGHT//2, [(0, 255, 0)], ['circle', 'square', 'star'], gravity=True, rotation=True, trail=True))
        else:
            if INCORRECT_SOUND:
                INCORRECT_SOUND.play()
            self.particle_effects.append(ParticleEffect(WINDOW_WIDTH//2, WINDOW_HEIGHT//2, [(255, 0, 0)], ['circle', 'square', 'star'], gravity=True, rotation=True, trail=True))
        self.current_question += 1
        if self.current_question < len(self.questions):
            self.setup_buttons()
        else:
            self.show_game_over_screen()
            self.add_high_score(self.score)

    def show_menu_screen(self):
        self.current_screen = "menu"

    def start_game(self):
        self.fetch_questions()
        self.current_screen = "game"

    def show_difficulty_screen(self):
        self.current_screen = "difficulty"

    def show_high_score_screen(self):
        self.current_screen = "high_score"

    def show_game_over_screen(self):
        self.current_screen = "game_over"

    def load_high_scores(self):
        try:
            with open('high_scores.json', 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save_high_scores(self):
        with open('high_scores.json', 'w') as file:
            json.dump(self.high_scores, file)

    def add_high_score(self, score):
        name = "Joueur"  # Vous pourriez demander le nom du joueur ici
        if self.difficulty not in self.high_scores:
            self.high_scores[self.difficulty] = []
        self.high_scores[self.difficulty].append((name, score))
        self.high_scores[self.difficulty].sort(key=lambda x: x[1], reverse=True)
        self.high_scores[self.difficulty] = self.high_scores[self.difficulty][:10]
        self.save_high_scores()

    def draw_menu(self, screen):
        rainbow_text(screen, "Quiz Trivia", self.font_title, WINDOW_WIDTH // 2 - self.font_title.size("Quiz Trivia")[0] // 2, 150)

        for button in self.menu_buttons:
            button.draw(screen)

    def draw_game(self, screen):
        if 0 <= self.current_question < len(self.questions):
            question_text = self.questions[self.current_question]['question']
            question_surface = self.font_question.render(question_text, True, BLACK)
            question_rect = question_surface.get_rect(center=(WINDOW_WIDTH // 2, 200))

            # Ombre pour le texte de la question
            shadow_surface = self.font_question.render(question_text, True, DARK_GRAY)
            shadow_rect = shadow_surface.get_rect(center=(WINDOW_WIDTH // 2 + 2, 200 + 2))
            screen.blit(shadow_surface, shadow_rect)
            screen.blit(question_surface, question_rect)

            for button in self.buttons:
                button.draw(screen)

            # Afficher le score actuel
            score_text = f"Score: {self.score}"
            score_surface = self.font_question.render(score_text, True, BLACK)
            score_rect = score_surface.get_rect(topright=(WINDOW_WIDTH - 20, 20))
            screen.blit(score_surface, score_rect)
        else:
            self.show_game_over_screen()

    def draw_difficulty(self, screen):
        title = self.font_title.render("Difficulté", True, BLACK)
        screen.blit(title, (WINDOW_WIDTH // 2 - title.get_width() // 2, 100))
        for button in self.difficulty_buttons:
            button.draw(screen)

    def draw_high_score(self, screen):
        title = self.font_title.render("High Scores", True, BLACK)
        screen.blit(title, (WINDOW_WIDTH // 2 - title.get_width() // 2, 50))

        y_offset = 150
        for difficulty, scores in self.high_scores.items():
            diff_title = self.font_question.render(f"{difficulty.capitalize()}:", True, BLACK)
            screen.blit(diff_title, (WINDOW_WIDTH // 2 - diff_title.get_width() // 2, y_offset))
            y_offset += 40
            for name, score in scores:
                score_text = f"{name}: {score}"
                score_surface = self.font_question.render(score_text, True, BLACK)
                screen.blit(score_surface, (WINDOW_WIDTH // 2 - score_surface.get_width() // 2, y_offset))
                y_offset += 30
            y_offset += 20

        for button in self.high_score_buttons:
            button.draw(screen)

    def draw_game_over(self, screen):
        game_over_text = "Jeu terminé!"
        game_over_surface = self.font_title.render(game_over_text, True, BLACK)
        game_over_rect = game_over_surface.get_rect(center=(WINDOW_WIDTH // 2, 250))
        screen.blit(game_over_surface, game_over_rect)

        final_score_text = f"Score final: {self.score}/{len(self.questions)}"
        final_score_surface = self.font_question.render(final_score_text, True, BLACK)
        final_score_rect = final_score_surface.get_rect(center=(WINDOW_WIDTH // 2, 350))
        screen.blit(final_score_surface, final_score_rect)

        for button in self.game_over_buttons:
            button.draw(screen)

    def draw(self, screen):
        self.time += 1 / FPS
        background_rect = screen.get_rect()
        dynamic_gradient(background_rect, self.background_start_color, self.background_end_color, self.time)

        for effect in self.particle_effects:
            effect.update()
            effect.draw(screen)

        if self.current_screen == "menu":
            self.draw_menu(screen)
        elif self.current_screen == "game":
            self.draw_game(screen)
        elif self.current_screen == "difficulty":
            self.draw_difficulty(screen)
        elif self.current_screen == "high_score":
            self.draw_high_score(screen)
        elif self.current_screen == "game_over":
            self.draw_game_over(screen)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if self.current_screen == "menu":
                for button in self.menu_buttons:
                    if button.handle_event(event):
                        break
            elif self.current_screen == "game":
                if self.buttons:
                    for button in self.buttons:
                        if button.handle_event(event):
                            self.handle_answer(button.text)
                            break
            elif self.current_screen == "difficulty":
                for button in self.difficulty_buttons:
                    if button.handle_event(event):
                        break
            elif self.current_screen == "high_score":
                for button in self.high_score_buttons:
                    if button.handle_event(event):
                        break
            elif self.current_screen == "game_over":
                for button in self.game_over_buttons:
                    if button.handle_event(event):
                        break

        return True

def main():
    game = TriviaGame()
    running = True

    while running:
        running = game.handle_events()
        game.draw(screen)
        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()

if __name__ == '__main__':
    main()
