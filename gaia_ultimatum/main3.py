import pygame
import pygame.gfxdraw
import sys
import json
import random
import math
from enum import Enum
import colorsys

# Initialisation de Pygame
pygame.init()

# Constantes
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 800
BACKGROUND_COLOR = (5, 20, 30)
COUNTRY_OUTLINE_COLOR = (100, 100, 100)
SELECTED_COUNTRY_OUTLINE_COLOR = (255, 255, 255)
POINT_RED_COLOR = (255, 50, 50)
UI_BACKGROUND_COLOR = (30, 30, 40, 200)
TEXT_COLOR = (255, 255, 255)
UI_HIGHLIGHT_COLOR = (70, 120, 200)
HEALTHY_COLOR = (50, 100, 255)  # Bleu
AFFECTED_COLOR = (255, 50, 50)  # Rouge
DEAD_COLOR = (10, 10, 10)       # Noir

# Configuration de l'écran
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Gaïa Ultimatum")
clock = pygame.time.Clock()

# Polices
font_small = pygame.font.SysFont("Arial", 14)
font_medium = pygame.font.SysFont("Arial", 18)
font_large = pygame.font.SysFont("Arial", 24)
font_title = pygame.font.SysFont("Arial", 30, bold=True)

# Classes du jeu
class Catastrophe:
    def __init__(self, name, icon, base_impact):
        self.name = name
        self.icon = icon  # Nom du fichier icône
        self.base_impact = base_impact
        self.active_points = []  # Points rouges actuellement actifs
        self.intensity = 1.0     # Multiplicateur d'intensité

    def update(self, world):
        # Mettre à jour les points existants (réduire leur durée de vie)
        for point in self.active_points[:]:
            point["lifetime"] -= 1
            if point["lifetime"] <= 0:
                self.active_points.remove(point)

        # Générer de nouveaux points en fonction de l'intensité
        self.generate_new_points(world)

    def generate_new_points(self, world):
        # Probabilité de base d'apparition de points
        base_probability = 0.05 * self.intensity

        # Pour chaque pays, calculer la probabilité d'apparition d'un point
        for country_id, country in world.countries.items():
            # Plus un pays est affecté, plus il a de chances d'avoir des points
            probability = base_probability * (1 + country.state / 2)

            if random.random() < probability:
                # Générer un point à une position aléatoire dans le pays
                centroid = country.centroid
                # Ajouter un décalage aléatoire
                pos_x = centroid[0] + random.uniform(-20, 20)
                pos_y = centroid[1] + random.uniform(-20, 20)

                # Calculer une durée de vie (en nombre de frames)
                lifetime = random.randint(60, 180)  # 1-3 secondes à 60 FPS

                # Calculer la valeur du point (points d'évolution)
                value = int(5 * self.intensity * (1 + country.state / 2))

                # Ajouter le point à la liste des points actifs
                self.active_points.append({
                    "position": (pos_x, pos_y),
                    "lifetime": lifetime,
                    "max_lifetime": lifetime,
                    "value": value,
                    "size": random.uniform(4, 10),
                    "country_id": country_id
                })

class Country:
    def __init__(self, id, name, polygons, population):
        self.id = id
        self.name = name
        self.polygons = polygons  # Liste de polygones (pour les pays avec plusieurs parties)
        self.population = population
        self.affected = 0         # Nombre de personnes affectées
        self.dead = 0             # Nombre de personnes mortes
        self.state = 0.0          # État du pays (0.0 = sain, 1.0 = totalement affecté)
        self.resilience = random.uniform(0.3, 0.7)     # Résilience Technologique
        self.stability = random.uniform(0.3, 0.7)      # Stabilité Sociétale
        self.regeneration = random.uniform(0.3, 0.7)   # Régénération Écologique
        self.adaptation = random.uniform(0.3, 0.7)     # Adaptation Évolutive

        # Calculer le centroïde du pays (approximation simple)
        self.centroid = self.calculate_centroid()

    def calculate_centroid(self):
        if not self.polygons or not self.polygons[0]:
            return (0, 0)

        # Prendre le premier polygone (le plus grand généralement)
        polygon = self.polygons[0]

        # Calculer la moyenne des coordonnées x et y
        sum_x = sum(point[0] for point in polygon)
        sum_y = sum(point[1] for point in polygon)
        count = len(polygon)

        return (sum_x / count, sum_y / count)

    def update_state(self, catastrophe_impact):
        # Mettre à jour l'état du pays en fonction de l'impact de la catastrophe
        # et des indicateurs d'équilibre

        # Calculer la défense moyenne du pays
        defense = (self.resilience + self.stability + self.regeneration + self.adaptation) / 4

        # L'impact est réduit par la défense
        effective_impact = catastrophe_impact * (1 - defense * 0.8)

        # Mettre à jour l'état du pays
        self.state = min(1.0, self.state + effective_impact)

        # Calculer les personnes affectées et mortes
        self.affected = int(self.population * self.state * 0.8)
        self.dead = int(self.population * self.state * 0.2)

    def get_color(self):
        # Interpolation linéaire entre bleu (sain), rouge (affecté) et noir (mort)
        if self.state < 0.5:
            # De bleu à rouge
            ratio = self.state * 2  # 0 à 1 pour la moitié de l'échelle
            r = int(HEALTHY_COLOR[0] + (AFFECTED_COLOR[0] - HEALTHY_COLOR[0]) * ratio)
            g = int(HEALTHY_COLOR[1] + (AFFECTED_COLOR[1] - HEALTHY_COLOR[1]) * ratio)
            b = int(HEALTHY_COLOR[2] + (AFFECTED_COLOR[2] - HEALTHY_COLOR[2]) * ratio)
        else:
            # De rouge à noir
            ratio = (self.state - 0.5) * 2  # 0 à 1 pour la seconde moitié
            r = int(AFFECTED_COLOR[0] + (DEAD_COLOR[0] - AFFECTED_COLOR[0]) * ratio)
            g = int(AFFECTED_COLOR[1] + (DEAD_COLOR[1] - AFFECTED_COLOR[1]) * ratio)
            b = int(AFFECTED_COLOR[2] + (DEAD_COLOR[2] - AFFECTED_COLOR[2]) * ratio)

        return (r, g, b)

class World:
    def __init__(self):
        self.countries = {}  # Dictionnaire de pays (id -> Country)
        self.scale = 1.0     # Échelle de la carte (zoom)
        self.offset_x = 0    # Décalage horizontal
        self.offset_y = 0    # Décalage vertical
        self.selected_country = None

    def load_countries(self, geojson_path):
        try:
            with open(geojson_path, 'r', encoding='utf-8') as file:
                geojson = json.load(file)

            # Traiter les données GeoJSON
            for feature in geojson['features']:
                # country_id = feature['properties']['sov_a3']
                country_id = feature['properties']['ISO_A3']
                # name = feature['properties']['name']
                name = feature['properties']['ADMIN']
                population = int(feature['properties'].get('pop_est', 1000000))

                polygons = []

                # Extraire les coordonnées des polygones
                if feature['geometry']['type'] == 'Polygon':
                    # Un seul polygone
                    coords = feature['geometry']['coordinates'][0]
                    polygons.append([(coord[0], coord[1]) for coord in coords])
                elif feature['geometry']['type'] == 'MultiPolygon':
                    # Plusieurs polygones
                    for poly in feature['geometry']['coordinates']:
                        coords = poly[0]
                        polygons.append([(coord[0], coord[1]) for coord in coords])


                # Créer le pays
                self.countries[country_id] = Country(country_id, name, polygons, population)

            return True
        except Exception as e:
            print(f"Erreur lors du chargement du GeoJSON: {e}")
            return False

    def transform_point(self, point):
        # Transformer un point en fonction du zoom et du décalage
        x = point[0] * self.scale + self.offset_x + SCREEN_WIDTH / 2
        y = -point[1] * self.scale + self.offset_y + SCREEN_HEIGHT / 2
        return (x, y)

    def draw(self, surface):
        # Dessiner tous les pays
        for country_id, country in self.countries.items():
            color = country.get_color()

            for polygon in country.polygons:
                # Transformer les points du polygone
                transformed_polygon = [self.transform_point(point) for point in polygon]

                # Dessiner le polygone rempli
                pygame.gfxdraw.filled_polygon(surface, transformed_polygon, color)

                # Dessiner le contour
                outline_color = SELECTED_COUNTRY_OUTLINE_COLOR if country_id == self.selected_country else COUNTRY_OUTLINE_COLOR
                pygame.gfxdraw.polygon(surface, transformed_polygon, outline_color)

    def get_country_at_position(self, pos):
        # Transformer la position de l'écran en coordonnées de la carte
        map_x = (pos[0] - SCREEN_WIDTH / 2 - self.offset_x) / self.scale
        map_y = -(pos[1] - SCREEN_HEIGHT / 2 - self.offset_y) / self.scale

        # Vérifier pour chaque pays si le point est à l'intérieur
        for country_id, country in self.countries.items():
            for polygon in country.polygons:
                if self.point_in_polygon((map_x, map_y), polygon):
                    return country_id

        return None

    def point_in_polygon(self, point, polygon):
        # Algorithme du point-in-polygon (PIP) - Ray casting
        x, y = point
        n = len(polygon)
        inside = False

        p1x, p1y = polygon[0]
        for i in range(n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y

        return inside

class Humans:
    def __init__(self):
        self.global_progress = 0.0  # Progression globale vers l'équilibre (0.0 à 1.0)
        self.evolution_points = 0   # Points d'évolution disponibles

    def update(self, catastrophe, world):
        # Calculer la progression globale en fonction de l'état des pays
        total_weight = 0
        weighted_progress = 0

        for country in world.countries.values():
            # Pondérer par la population
            weight = country.population
            total_weight += weight

            # Calculer la contribution du pays à la progression globale
            country_progress = (country.resilience + country.stability +
                                country.regeneration + country.adaptation) / 4
            weighted_progress += country_progress * weight

        if total_weight > 0:
            self.global_progress = weighted_progress / total_weight

    def collect_point(self, point):
        self.evolution_points += point["value"]
        return point["value"]

class Gaia:
    def __init__(self):
        self.catastrophes = []
        self.active_catastrophe_index = 0

        # Ajouter quelques catastrophes de base
        self.catastrophes.append(Catastrophe("Réchauffement Climatique", "climate.png", 0.01))
        self.catastrophes.append(Catastrophe("Pandémie", "pandemic.png", 0.015))
        self.catastrophes.append(Catastrophe("Tsunami", "tsunami.png", 0.02))

    def get_active_catastrophe(self):
        return self.catastrophes[self.active_catastrophe_index]

    def update(self, human_impact):
        # Ajuster l'intensité des catastrophes en fonction de l'impact humain
        for catastrophe in self.catastrophes:
            catastrophe.intensity = 1.0 + human_impact * 2

class Game:
    def __init__(self):
        self.world = World()
        self.humans = Humans()
        self.gaia = Gaia()
        self.turn = 0
        self.game_over = False
        self.dragging = False
        self.drag_start = None
        self.initial_offset = None

        # Interface utilisateur
        self.info_panel_visible = False
        self.info_panel_country = None

        # Chargement des données
        success = self.world.load_countries("data/zones.geojson")
        if not success:
            print("Erreur fatale: Impossible de charger les données des pays.")
            pygame.quit()
            sys.exit()

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False

        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1:  # Clic gauche
                # Vérifier si on clique sur un point rouge
                mouse_pos = pygame.mouse.get_pos()
                point_clicked = self.check_point_click(mouse_pos)

                if point_clicked:
                    value = self.humans.collect_point(point_clicked)
                    catastrophe = self.gaia.get_active_catastrophe()
                    catastrophe.active_points.remove(point_clicked)
                else:
                    # Vérifier si on clique sur un pays
                    country_id = self.world.get_country_at_position(mouse_pos)
                    if country_id:
                        self.world.selected_country = country_id
                        self.info_panel_visible = True
                        self.info_panel_country = country_id
                    else:
                        # Commencer le déplacement (drag)
                        self.dragging = True
                        self.drag_start = mouse_pos
                        self.initial_offset = (self.world.offset_x, self.world.offset_y)

            elif event.button == 4:  # Molette vers le haut
                # Zoomer
                self.world.scale *= 1.1
                self.world.scale = min(self.world.scale, 5.0)  # Limiter le zoom maximal

            elif event.button == 5:  # Molette vers le bas
                # Dézoomer
                self.world.scale /= 1.1
                self.world.scale = max(self.world.scale, 0.2)  # Limiter le zoom minimal

        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1:  # Clic gauche relâché
                self.dragging = False

        elif event.type == pygame.MOUSEMOTION:
            if self.dragging:
                # Mettre à jour le décalage en fonction du déplacement de la souris
                mouse_pos = pygame.mouse.get_pos()
                dx = mouse_pos[0] - self.drag_start[0]
                dy = mouse_pos[1] - self.drag_start[1]
                self.world.offset_x = self.initial_offset[0] + dx
                self.world.offset_y = self.initial_offset[1] + dy

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_SPACE:
                # Passer au tour suivant
                self.next_turn()
            elif event.key == pygame.K_c:
                # Changer de catastrophe active
                self.gaia.active_catastrophe_index = (self.gaia.active_catastrophe_index + 1) % len(self.gaia.catastrophes)

        return True

    def check_point_click(self, mouse_pos):
        # Vérifier si la souris clique sur un point rouge
        catastrophe = self.gaia.get_active_catastrophe()
        for point in catastrophe.active_points:
            # Transformer la position du point
            pos = self.world.transform_point(point["position"])

            # Calculer la distance
            dx = mouse_pos[0] - pos[0]
            dy = mouse_pos[1] - pos[1]
            distance = math.sqrt(dx*dx + dy*dy)

            # Si la distance est inférieure à la taille du point, c'est un clic dessus
            if distance < point["size"] * 1.5:  # Un peu plus grand que le point pour faciliter le clic
                return point

        return None

    def next_turn(self):
        self.turn += 1

        # Mettre à jour la catastrophe
        active_catastrophe = self.gaia.get_active_catastrophe()
        active_catastrophe.update(self.world)

        # Calculer l'impact humain (simplification)
        human_impact = 1.0 - self.humans.global_progress

        # Mettre à jour Gaïa
        self.gaia.update(human_impact)

        # Mettre à jour les pays
        for country in self.world.countries.values():
            country.update_state(active_catastrophe.base_impact * active_catastrophe.intensity)

        # Mettre à jour l'humanité
        self.humans.update(active_catastrophe, self.world)

        # Vérifier les conditions de fin de jeu
        self.check_game_over()

    def check_game_over(self):
        # Vérifier si l'humanité a atteint l'équilibre
        if self.humans.global_progress >= 0.9:
            self.game_over = True
            print("Victoire! L'humanité a atteint l'équilibre avec Gaïa.")

        # Vérifier si l'humanité a été décimée
        total_population = sum(country.population for country in self.world.countries.values())
        total_dead = sum(country.dead for country in self.world.countries.values())

        if total_dead / total_population >= 0.8:
            self.game_over = True
            print("Défaite! L'humanité a été largement décimée.")

    def draw(self, surface):
        # Effacer l'écran
        surface.fill(BACKGROUND_COLOR)

        # Dessiner la carte du monde
        self.world.draw(surface)

        # Dessiner les points rouges
        self.draw_active_points(surface)

        # Dessiner l'interface utilisateur
        self.draw_ui(surface)

        # Dessiner le panneau d'informations si nécessaire
        if self.info_panel_visible:
            self.draw_info_panel(surface)

    def draw_active_points(self, surface):
        catastrophe = self.gaia.get_active_catastrophe()
        for point in catastrophe.active_points:
            # Transformer la position du point
            pos = self.world.transform_point(point["position"])

            # Calculer la taille et l'opacité en fonction de la durée de vie
            lifetime_ratio = point["lifetime"] / point["max_lifetime"]
            size = point["size"] * (0.8 + lifetime_ratio * 0.2)
            alpha = int(255 * lifetime_ratio)

            # Dessiner un cercle rouge avec une opacité variable
            color = (*POINT_RED_COLOR, alpha)
            pygame.gfxdraw.filled_circle(surface, int(pos[0]), int(pos[1]), int(size), color)
            pygame.gfxdraw.aacircle(surface, int(pos[0]), int(pos[1]), int(size), (*POINT_RED_COLOR, min(alpha, 200)))

            # Afficher la valeur du point
            value_text = font_small.render(str(point["value"]), True, TEXT_COLOR)
            text_pos = (pos[0] - value_text.get_width() // 2, pos[1] - value_text.get_height() // 2)
            surface.blit(value_text, text_pos)

    def draw_ui(self, surface):
        # Dessiner la barre de progression
        progress_width = 300
        progress_height = 20
        progress_x = 20
        progress_y = 20

        # Fond de la barre
        pygame.draw.rect(surface, (50, 50, 50), (progress_x, progress_y, progress_width, progress_height))

        # Progression
        progress_fill_width = int(progress_width * self.humans.global_progress)

        # Couleur de progression (vert -> orange -> rouge)
        if self.humans.global_progress < 0.33:
            progress_color = (200, 50, 50)  # Rouge
        elif self.humans.global_progress < 0.66:
            progress_color = (200, 150, 50)  # Orange
        else:
            progress_color = (50, 200, 50)  # Vert

        pygame.draw.rect(surface, progress_color, (progress_x, progress_y, progress_fill_width, progress_height))

        # Contour de la barre
        pygame.draw.rect(surface, (200, 200, 200), (progress_x, progress_y, progress_width, progress_height), 1)

        # Texte de progression
        progress_text = font_medium.render(f"Équilibre: {int(self.humans.global_progress * 100)}%", True, TEXT_COLOR)
        surface.blit(progress_text, (progress_x + progress_width + 10, progress_y))

        # Compteur de tours
        turn_text = font_medium.render(f"Tour: {self.turn}", True, TEXT_COLOR)
        surface.blit(turn_text, (20, 50))

        # Points d'évolution
        points_text = font_medium.render(f"Points d'évolution: {self.humans.evolution_points}", True, TEXT_COLOR)
        surface.blit(points_text, (20, 80))

        # Catastrophe active
        catastrophe = self.gaia.get_active_catastrophe()
        catastrophe_text = font_medium.render(f"Catastrophe: {catastrophe.name}", True, TEXT_COLOR)
        surface.blit(catastrophe_text, (20, 110))

        # Instructions
        instructions = [
            "Clic gauche sur un pays pour voir ses infos",
            "Molette pour zoomer/dézoomer",
            "Clic-glisser pour déplacer la carte",
            "Espace pour passer au tour suivant",
            "C pour changer de catastrophe"
        ]

        for i, instruction in enumerate(instructions):
            instruction_text = font_small.render(instruction, True, TEXT_COLOR)
            surface.blit(instruction_text, (SCREEN_WIDTH - instruction_text.get_width() - 20, 20 + i * 20))

    def draw_info_panel(self, surface):
        if self.info_panel_country not in self.world.countries:
            self.info_panel_visible = False
            return

        country = self.world.countries[self.info_panel_country]

        # Taille et position du panneau
        panel_width = 300
        panel_height = 300
        panel_x = 20
        panel_y = 150

        # Fond du panneau
        s = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        s.fill(UI_BACKGROUND_COLOR)
        surface.blit(s, (panel_x, panel_y))

        # Contour du panneau
        pygame.draw.rect(surface, (200, 200, 200), (panel_x, panel_y, panel_width, panel_height), 1)

        # Titre (nom du pays)
        title_text = font_title.render(country.name, True, TEXT_COLOR)
        surface.blit(title_text, (panel_x + 10, panel_y + 10))

        # Informations
        info_lines = [
            f"Population totale: {country.population:,}",
            f"Personnes affectées: {country.affected:,} ({int(country.affected / country.population * 100)}%)",
            f"Personnes décédées: {country.dead:,} ({int(country.dead / country.population * 100)}%)",
            "",
            "Indicateurs d'équilibre:",
            f"Résilience Technologique: {int(country.resilience * 100)}%",
            f"Stabilité Sociétale: {int(country.stability * 100)}%",
            f"Régénération Écologique: {int(country.regeneration * 100)}%",
            f"Adaptation Évolutive: {int(country.adaptation * 100)}%"
        ]

        for i, line in enumerate(info_lines):
            info_text = font_medium.render(line, True, TEXT_COLOR)
            surface.blit(info_text, (panel_x + 10, panel_y + 50 + i * 25))

        # Bouton de fermeture
        close_text = font_large.render("X", True, TEXT_COLOR)
        close_rect = pygame.Rect(panel_x + panel_width - 30, panel_y + 10, 20, 20)

        # Vérifier si la souris est sur le bouton de fermeture
        mouse_pos = pygame.mouse.get_pos()
        if close_rect.collidepoint(mouse_pos):
            pygame.draw.rect(surface, UI_HIGHLIGHT_COLOR, close_rect)
            if pygame.mouse.get_pressed()[0]:
                self.info_panel_visible = False

        surface.blit(close_text, (panel_x + panel_width - 25, panel_y + 5))

def main():
    game = Game()
    running = True

    while running and not game.game_over:
        # Gestion des événements
        for event in pygame.event.get():
            if not game.handle_event(event):
                running = False
                break

        # Dessiner le jeu
        game.draw(screen)

        # Mise à jour de l'écran
        pygame.display.flip()

        # Limiter à 60 FPS
        clock.tick(60)

    # Attendre un peu avant de quitter si le jeu est terminé
    if game.game_over:
        pygame.time.wait(5000)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()