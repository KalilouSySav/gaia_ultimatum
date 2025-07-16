import json
import math
import random
import os
import time
from typing import List, Dict, Any, Tuple
import random
import colorsys
import pyproj
import typing

from pygame import gfxdraw, draw, font, image, mixer, rect, Surface, transform, display, mouse



# Fonctions de Gestion de Fichiers et de Données

def load_json(filepath: str) -> Dict[str, Any]:
    """
    Charge un fichier JSON et retourne les données sous forme de dictionnaire.

    Args:
        filepath (str): Le chemin vers le fichier JSON.

    Returns:
        Dict[str, Any]: Les données chargées sous forme de dictionnaire.
    """
    with open(filepath, 'r') as file:
        return json.load(file)

def save_json(filepath: str, data: Dict[str, Any]) -> None:
    """
    Sauvegarde les données sous forme de fichier JSON.

    Args:
        filepath (str): Le chemin vers le fichier JSON.
        data (Dict[str, Any]): Les données à sauvegarder.
    """
    with open(filepath, 'w') as file:
        json.dump(data, file, indent=4)

def load_image(filepath: str) -> Surface:
    """
    Charge une image à partir d'un fichier et retourne une surface Pygame.

    Args:
        filepath (str): Le chemin vers le fichier image.

    Returns:
        pygame.Surface: La surface chargée.
    """
    return image.load(filepath)

def load_sound(filepath: str) -> mixer.Sound:
    """
    Charge un son à partir d'un fichier et retourne un objet son Pygame.

    Args:
        filepath (str): Le chemin vers le fichier son.

    Returns:
        pygame.mixer.Sound: L'objet son chargé.
    """
    return mixer.Sound(filepath)

def load_config(filepath: str) -> Dict[str, Any]:
    """
    Charge un fichier de configuration JSON et retourne les données sous forme de dictionnaire.

    Args:
        filepath (str): Le chemin vers le fichier de configuration JSON.

    Returns:
        Dict[str, Any]: Les données de configuration chargées.
    """
    return load_json(filepath)

def save_config(filepath: str, config: Dict[str, Any]) -> None:
    """
    Sauvegarde les données de configuration sous forme de fichier JSON.

    Args:
        filepath (str): Le chemin vers le fichier de configuration JSON.
        config (Dict[str, Any]): Les données de configuration à sauvegarder.
    """
    save_json(filepath, config)

def load_game_data() -> Dict[str, Any]:
    """
    Charge les données du jeu à partir de plusieurs fichiers de configuration et retourne un dictionnaire consolidé.

    Returns:
        Dict[str, Any]: Les données du jeu consolidées.
    """
    config_data = load_config('config/game_config.json')
    map_data = load_json('data/map_data.json')
    zones_data = load_json('data/zones_data.json')
    return {**config_data, **map_data, **zones_data}

# Fonctions Mathématiques et de Calcul

def normalize(value: float, min_value: float, max_value: float) -> float:
    """
    Normalise une valeur dans l'intervalle [0, 1].

    Args:
        value (float): La valeur à normaliser.
        min_value (float): La valeur minimale de l'intervalle.
        max_value (float): La valeur maximale de l'intervalle.

    Returns:
        float: La valeur normalisée.
    """
    return (value - min_value) / (max_value - min_value)

def lerp(start: float, end: float, t: float) -> float:
    """
    Interpolation linéaire entre deux valeurs.

    Args:
        start (float): La valeur de départ.
        end (float): La valeur de fin.
        t (float): Le facteur d'interpolation (0 à 1).

    Returns:
        float: La valeur interpolée.
    """
    return start + (end - start) * t

def clamp(value: float, min_value: float, max_value: float) -> float:
    """
    Limite une valeur entre un minimum et un maximum.

    Args:
        value (float): La valeur à limiter.
        min_value (float): La valeur minimale.
        max_value (float): La valeur maximale.

    Returns:
        float: La valeur limitée.
    """
    return max(min_value, min(value, max_value))

def calculate_distance(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """
    Calcule la distance euclidienne entre deux points.

    Args:
        point1 (Tuple[float, float]): Le premier point.
        point2 (Tuple[float, float]): Le deuxième point.

    Returns:
        float: La distance entre les deux points.
    """
    return math.sqrt((point1[0] - point2[0])**2 + (point1[1] - point2[1])**2)

def calculate_angle(point1: Tuple[float, float], point2: Tuple[float, float]) -> float:
    """
    Calcule l'angle entre deux points.

    Args:
        point1 (Tuple[float, float]): Le premier point.
        point2 (Tuple[float, float]): Le deuxième point.

    Returns:
        float: L'angle en radians.
    """
    return math.atan2(point2[1] - point1[1], point2[0] - point1[0])

def weighted_choice(choices: List[Tuple[Any, float]]) -> Any:
    """
    Sélectionne un élément de manière pondérée à partir d'une liste de choix.

    Args:
        choices (List[Tuple[Any, float]]): La liste des choix avec leurs poids.

    Returns:
        Any: L'élément sélectionné.
    """
    total = sum(weight for item, weight in choices)
    r = random.uniform(0, total)
    upto = 0
    for item, weight in choices:
        if upto + weight >= r:
            return item
        upto += weight
    return None

def generate_random_point_in_polygon(polygon: List[Tuple[float, float]]) -> Tuple[float, float]:
    """
    Génère un point aléatoire à l'intérieur d'un polygone.

    Args:
        polygon (List[Tuple[float, float]]): Le polygone.

    Returns:
        Tuple[float, float]: Le point généré.
    """
    min_x = min(point[0] for point in polygon)
    max_x = max(point[0] for point in polygon)
    min_y = min(point[1] for point in polygon)
    max_y = max(point[1] for point in polygon)
    while True:
        point = (random.uniform(min_x, max_x), random.uniform(min_y, max_y))
        if is_point_in_polygon(point, polygon):
            return point

def smoothstep(t: float) -> float:
    """
    Interpolation douce entre 0 et 1.

    Args:
        t (float): Le facteur d'interpolation.

    Returns:
        float: La valeur interpolée.
    """
    return t * t * (3 - 2 * t)

def cosine_interpolate(t: float) -> float:
    """
    Interpolation cosinusoïdale entre 0 et 1.

    Args:
        t (float): Le facteur d'interpolation.

    Returns:
        float: La valeur interpolée.
    """
    return (1 - math.cos(t * math.pi)) / 2

def random_choice(choices: List[Any]) -> Any:
    """
    Sélectionne un élément aléatoire dans une liste.

    Args:
        choices (List[Any]): La liste des choix.

    Returns:
        Any: L'élément sélectionné.
    """
    return random.choice(choices)


# Fonctions de Conversion et de Formatage

def format_number(number: float) -> str:
    """
    Formate un nombre avec des séparateurs de milliers.

    Args:
        number (float): Le nombre à formater.

    Returns:
        str: Le nombre formaté.
    """
    return "{:,}".format(number)

def format_percentage(value: float) -> str:
    """
    Formate un pourcentage.

    Args:
        value (float): La valeur du pourcentage.

    Returns:
        str: Le pourcentage formaté.
    """
    return f"{value * 100:.2f}%"

def rgb_to_hex(r: int, g: int, b: int) -> str:
    """
    Convertit une couleur RGB en format hexadécimal.

    Args:
        r (int): La composante rouge.
        g (int): La composante verte.
        b (int): La composante bleue.

    Returns:
        str: La couleur en format hexadécimal.
    """
    return "#{:02x}{:02x}{:02x}".format(r, g, b)

def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """
    Convertit une couleur hexadécimale en format RGB.

    Args:
        hex_color (str): La couleur en format hexadécimal.

    Returns:
        Tuple[int, int, int]: La couleur en format RGB.
    """
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def project_coordinates(latitude: float, longitude: float, projection_in: str, projection_out: str, width: int, height: int) -> Tuple[int, int]:
    """
    Projette des coordonnées géographiques d'une projection à une autre.

    Args:
        latitude (float): La latitude.
        longitude (float): La longitude.
        projection_in (str): La projection d'entrée.
        projection_out (str): La projection de sortie.
        width (int): La largeur de la carte.
        height (int): La hauteur de la carte.

    Returns:
        Tuple[int, int]: Les coordonnées projetées.
    """
    # Implémentation dépendante de la bibliothèque de projection utilisée
    pass

def convertir_vers_cases(longitude: float, latitude: float) -> Tuple[int, int]:
    """
    Convertit les coordonnées de longitude et latitude en case d'une grille.

    Args:
        longitude (float): La longitude.
        latitude (float): La latitude.

    Returns:
        Tuple[int, int]: Les coordonnées de la case.
    """
    # Implémentation dépendante de la taille et de la résolution de la grille
    pass

# Fonctions de Manipulation de Données Géographiques

def get_neighbors(zone: Dict[str, Any], zones_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Retourne les zones voisines d'une zone donnée.

    Args:
        zone (Dict[str, Any]): La zone dont on veut obtenir les voisins.
        zones_data (List[Dict[str, Any]]): La liste de toutes les zones.

    Returns:
        List[Dict[str, Any]]: La liste des zones voisines.
    """
    neighbors = []
    for other_zone in zones_data:
        if zone != other_zone and any(calculate_distance(point, other_point) < 1 for point in zone['borders'] for other_point in other_zone['borders']):
            neighbors.append(other_zone)
    return neighbors

def is_point_in_polygon(point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
    """
    Vérifie si un point est à l'intérieur d'un polygone.

    Args:
        point (Tuple[float, float]): Le point à vérifier.
        polygon (List[Tuple[float, float]]): Le polygone.

    Returns:
        bool: True si le point est dans le polygone, False sinon.
    """
    x, y = point
    n = len(polygon)
    inside = False
    px, py = polygon[0]
    for i in range(n + 1):
        px_next, py_next = polygon[i % n]
        if y > min(py, py_next):
            if y <= max(py, py_next):
                if x <= max(px, px_next):
                    if py != py_next:
                        xinters = (y - py) * (px_next - px) / (py_next - py) + px
                    if px == px_next or x <= xinters:
                        inside = not inside
        px, py = px_next, py_next
    return inside

def get_country_at_coordinates(x: float, y: float, zones_data: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Retourne le pays à des coordonnées données.

    Args:
        x (float): La coordonnée x.
        y (float): La coordonnée y.
        zones_data (List[Dict[str, Any]]): La liste de toutes les zones.

    Returns:
        Dict[str, Any]: Le pays à ces coordonnées, ou None si aucun pays n'est trouvé.
    """
    for zone in zones_data:
        if is_point_in_polygon((x, y), zone['borders']):
            return zone
    return None

def calculer_population_totale(pays: Dict[str, Any]) -> int:
    """
    Calcule la population totale d'un pays à partir de la population de chaque tuile.

    Args:
        pays (Dict[str, Any]): Le pays dont on veut calculer la population totale.

    Returns:
        int: La population totale du pays.
    """
    return sum(tile['population'] for tile in pays['tiles'])

# Fonctions de Gestion du Temps

def get_current_time() -> float:
    """
    Retourne le temps actuel en secondes.

    Returns:
        float: Le temps actuel en secondes.
    """
    return time.time()

def format_time(seconds: float) -> str:
    """
    Formate un temps en secondes en une chaîne de caractères lisible.

    Args:
        seconds (float): Le temps en secondes.

    Returns:
        str: Le temps formaté.
    """
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{int(hours):02}:{int(minutes):02}:{int(seconds):02}"

class Timer:
    def __init__(self):
        """
        Initialise un nouveau chronomètre.
        """
        self.start_time = None
        self.end_time = None

    def start_timer(self) -> None:
        """
        Démarre le chronomètre.
        """
        self.start_time = get_current_time()
        self.end_time = None

    def stop_timer(self) -> None:
        """
        Arrête le chronomètre.
        """
        self.end_time = get_current_time()

    def get_elapsed_time(self) -> float:
        """
        Retourne le temps écoulé en secondes.

        Returns:
            float: Le temps écoulé en secondes.
        """
        if self.end_time is None:
            return get_current_time() - self.start_time
        return self.end_time - self.start_time

# Fonctions de Gestion des Couleurs

def interpolate_color(color1: Tuple[int, int, int], color2: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    """
    Interpole entre deux couleurs RGB.

    Args:
        color1 (Tuple[int, int, int]): La première couleur.
        color2 (Tuple[int, int, int]): La deuxième couleur.
        factor (float): Le facteur d'interpolation.

    Returns:
        Tuple[int, int, int]: La couleur interpolée.
    """
    return (
        int(color1[0] + (color2[0] - color1[0]) * factor),
        int(color1[1] + (color2[1] - color1[1]) * factor),
        int(color1[2] + (color2[2] - color1[2]) * factor)
    )

def adjust_brightness(color: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    """
    Ajuste la luminosité d'une couleur RGB.

    Args:
        color (Tuple[int, int, int]): La couleur à ajuster.
        factor (float): Le facteur de luminosité.

    Returns:
        Tuple[int, int, int]: La couleur ajustée.
    """
    return tuple(int(clamp(c * factor, 0, 255)) for c in color)

# Fonctions utilisées pour la carte du monde
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

# Fonctions Utilitaires Diverses

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

def draw_glow_rect(surface, glow_color, glow_rect, border_radius):
    """Dessine un rectangle avec un effet de lueur."""
    draw.rect(surface, glow_color, glow_rect, border_radius=border_radius)


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
    draw.rect(surface, color, (x + radius, y, width - 2 * radius, height))
    draw.rect(surface, color, (x, y + radius, width, height - 2 * radius))

def scale_image(image, scale_factors):
    """
    Redimensionne une image en utilisant des facteurs d'échelle distincts pour la largeur et la hauteur.

    Args:
        image (Surface): L'image Pygame à redimensionner.
        scale_factors (tuple): Un tuple contenant (scale_factor_width, scale_factor_height).

    Returns:
        Surface: L'image redimensionnée.
    """
    scale_factor_width, scale_factor_height = scale_factors
    new_width = int(image.get_width() * scale_factor_width)
    new_height = int(image.get_height() * scale_factor_height)
    return transform.scale(image, (new_width, new_height))
def rotate_image(image: Surface, angle: float) -> Surface:
    """
    Fait pivoter une image.

    Args:
        image (pygame.Surface): L'image à faire pivoter.
        angle (float): L'angle de rotation en degrés.

    Returns:
        pygame.Surface: L'image pivotée.
    """
    return transform.rotate(image, angle)

def apply_fade_in(surface: Surface, duration: float) -> None:
    """
    Applique un fondu entrant à une surface Pygame.

    Args:
        surface (pygame.Surface): La surface sur laquelle appliquer le fondu.
        duration (float): La durée du fondu en secondes.
    """
    alpha = 0
    start_time = get_current_time()
    while alpha < 255:
        alpha = int((get_current_time() - start_time) / duration * 255)
        surface.set_alpha(alpha)
        display.flip()

def apply_fade_out(surface: Surface, duration: float) -> None:
    """
    Applique un fondu sortant à une surface Pygame.

    Args:
        surface (pygame.Surface): La surface sur laquelle appliquer le fondu.
        duration (float): La durée du fondu en secondes.
    """
    alpha = 255
    start_time = get_current_time()
    while alpha > 0:
        alpha = int((1 - (get_current_time() - start_time) / duration) * 255)
        surface.set_alpha(alpha)
        display.flip()

def generate_points_on_circle(center_x: int, center_y: int, radius: int, num_points: int) -> List[Tuple[int, int]]:
    """
    Génère des points répartis uniformément sur un cercle.

    Args:
        center_x (int): La coordonnée x du centre du cercle.
        center_y (int): La coordonnée y du centre du cercle.
        radius (int): Le rayon du cercle.
        num_points (int): Le nombre de points à générer.

    Returns:
        List[Tuple[int, int]]: La liste des points générés.
    """
    points = []
    for i in range(num_points):
        angle = 2 * math.pi * i / num_points
        x = center_x + int(radius * math.cos(angle))
        y = center_y + int(radius * math.sin(angle))
        points.append((x, y))
    return points

def load_competence(type):
    try:
        with open("data/skills.json", encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        print("Fichier 'catastrophes.txt' introuvable.")
        return
    except json.JSONDecodeError:
        print("Erreur de décodage du fichier JSON.")
        return

    skills = {}
    for catastrophe in data["catastrophes"]:
        if catastrophe["Catastrophe"] == type:
            for type_competence, details in catastrophe["Types"].items():
                for niveau, competences in details["Niveaux"].items():
                    for competence in competences["Competences"]:
                        skill_name = competence["Nom"]
                        skill_description = competence["Description"]
                        skill_cost = competence["Niveaux"]["Niveau 1"]["Cout"]
                        skill_type = type_competence
                        skill_niveau = niveau
                        skills[skill_name] = {
                            "description": skill_description,
                            "cost": skill_cost,
                            "type": skill_type,
                            "levels": competence["Niveaux"],
                            "niveau": skill_niveau,
                            "name": skill_name
                        }

    print(skills)
    return skills

def load_catastrophes():
    try:
        with open("data/skills.json", encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        print("Fichier 'catastrophes.txt' introuvable.")
        return
    except json.JSONDecodeError:
        print("Erreur de décodage du fichier JSON.")
        return

    catastrophes = []
    for catastrophe in data["catastrophes"]:
        catastrophe_text = catastrophe["text"]
        catastrophe_description = catastrophe["description"]
        catastrophe_color = catastrophe["color"]
        catastrophe_icon = catastrophe["icon"]
        catastrophe = {
            "text": catastrophe_text,
            "description": catastrophe_description,
            "color": catastrophe_color,
            "icon": catastrophe_icon
        }
        catastrophes.append(catastrophe)

    #print(catastrophes)
    return catastrophes

# Button
def calculate_shake_offset(time, intensity):
    return [math.sin(time * 0.1) * intensity, math.cos(time * 0.1) * intensity]
def calculate_pulse(time, amplitude, frequency):
    return math.sin(time * frequency) * amplitude
def calculate_glow_radius(pulse, hover, base_radius):
    return base_radius + pulse * hover
def calculate_hover(hover, hover_speed):
    return min(1, hover + hover_speed)
def calculate_dynamic_color(time, hue_offset, hue_speed, saturation, value):
    """
    Calcule une couleur dynamique en fonction du temps.

    :param time: Le temps, généralement la valeur de 'time' dans une boucle d'animation.
    :param hue_offset: Décalage de la teinte pour l'effet (par défaut 0.6).
    :param saturation: Saturation de la couleur (par défaut 0.6).
    :param value: Valeur de la luminosité de la couleur (par défaut 0.8).
    :return: La couleur dynamique sous forme de tuple RGB (entiers entre 0 et 255).
    """
    # Calcul de la teinte dynamique
    hue = (math.sin(time * hue_speed) * 0.05 + hue_offset) % 1.0

    # Conversion de HSV à RGB (les valeurs RGB sont entre 0 et 1, donc multipliées par 255)
    dynamic_color = tuple(int(c * 255) for c in colorsys.hsv_to_rgb(hue, saturation, value))

    return dynamic_color


# Particules
def create_particle(emitters, screen_height, accent_colors, size_range, speed_range, alpha_range):
    """Crée une particule avec des propriétés configurables."""
    emitter = random.choice(emitters)
    return {
        'x': emitter[0] + random.randint(-100, 100),
        'y': random.randint(0, screen_height),
        'size': random.uniform(*size_range),
        'speed': random.uniform(*speed_range),
        'angle': random.uniform(0, math.pi * 2),
        'color': random.choice(accent_colors),
        'alpha': random.randint(*alpha_range)
    }
def update_particle(particle, time, screen_width, screen_height, emitters):
    """Met à jour la position et la transparence d'une particule."""
    particle['y'] += math.sin(time * 0.001 + particle['angle']) * 0.5 + particle['speed']
    particle['x'] += math.cos(time * 0.001 + particle['angle']) * 0.5
    particle['alpha'] = int(100 + math.sin(time * 0.002 + particle['y'] * 0.1) * 50)

    # Réinitialisation si la particule dépasse les limites
    if particle['y'] > screen_height:
        emitter = random.choice(emitters)
        particle['y'] = 0
        particle['x'] = emitter[0] + random.randint(-100, 100)
def draw_particle(surface, particle):
    """Dessine une particule sur la surface."""
    gfxdraw.filled_circle(surface, int(particle['x']), int(particle['y']),
                          int(particle['size']), (*particle['color'], particle['alpha']))
def calculate_particle_position(time, index, screen_width, screen_height):
    """
    Calcule la position d'une particule en fonction du temps et de l'indice.
    """
    x = (time * (index % 5 + 1) * 0.5 + index * 50) % screen_width
    y = (math.sin(time * 0.001 + index) * 50 + index * 20) % screen_height
    return x, y
def calculate_particle_size_alpha(time, x, y):
    """
    Calcule la taille et l'alpha d'une particule en fonction de sa position et du temps.
    """
    size = (math.sin(time * 0.003 + x * 0.1) + 2) * 2
    alpha = int(128 + math.sin(time * 0.002 + y * 0.1) * 64)
    return size, alpha




def calculate_hover_color(button_color, hover_color, hover_intensity):
    """
    Calcule la couleur finale du bouton en fonction de l'intensité de l'effet de survol.

    :param button_color: La couleur normale du bouton.
    :param hover_color: La couleur lorsque le bouton est survolé.
    :param hover_intensity: L'intensité de l'effet de survol (valeur entre 0 et 1).
    :return: La couleur calculée pour l'effet de survol.
    """
    return [
        int(c1 + (c2 - c1) * hover_intensity)
        for c1, c2 in zip(button_color, hover_color)
    ]


# Fonction utilitaire pour calculer les positions des boutons
def calculate_button_positions(num_elements, button_width, button_height, spacing, max_per_line, screen_width, start_y):
    positions = []
    for i in range(num_elements):
        line_index = i // max_per_line
        position_in_line = i % max_per_line

        # Calcul du nombre de boutons dans la ligne actuelle
        if (line_index + 1) * max_per_line > num_elements:
            buttons_in_line = num_elements % max_per_line or max_per_line
        else:
            buttons_in_line = max_per_line

        # Calcul de la largeur totale des boutons dans cette ligne
        total_width_of_buttons = buttons_in_line * button_width + (buttons_in_line - 1) * spacing

        # Calcul du décalage pour centrer les boutons
        x_start = (screen_width - total_width_of_buttons) // 2

        # Position calculée pour chaque bouton
        x = x_start + position_in_line * (button_width + spacing)
        y = start_y + line_index * (button_height + spacing)

        positions.append((x, y))
    return positions

def draw_button_with_border(surface, border_color, rect, border_thickness, border_radius):
    """
    Dessine un bouton avec une bordure qui change de couleur selon le survol et l'animation dynamique.

    :param surface: La surface Pygame où dessiner le bouton.
    :param rect: Le rectangle définissant la position et la taille du bouton.
    :param border_color: La couleur de la bordure.
    :param border_thickness: L'épaisseur de la bordure.
    :param border_radius: Le rayon des coins du bouton.
    """

    # Dessin de la bordure du bouton
    draw.rect(surface, border_color, rect, border_thickness, border_radius)

def draw_button_with_hover_effect(surface, color, rect, border_radius):
    """
    Dessine un bouton avec un effet de survol.

    :param surface: La surface Pygame où dessiner le bouton.
    :param rect: La position et les dimensions du bouton sous forme de (x, y, largeur, hauteur).
    :param color: La couleur du bouton.
    :param border_radius: Le rayon des coins du bouton.
    """

    # Dessin du bouton avec la couleur calculée
    draw.rect(surface, color, rect, border_radius)


def create_shadow(text, rect, time, font_size, shadow_color, shadow_offset):
    """Crée une surface d'ombre pour le texte."""
    new_font = font.Font(None, font_size)
    shadow_surf = new_font.render(text, True, shadow_color)
    shadow_offset = shadow_offset
    shadow_rect = shadow_surf.get_rect(center=(rect.centerx + shadow_offset, rect.centery + shadow_offset))
    return shadow_surf, shadow_rect

def draw_glow_text(surface, rect, text, dynamic_color, time, glow_radius, font_size, glow_intensity, glow_alpha_step):
    """Dessine la lueur animée autour du texte."""
    new_font = font.Font(None, font_size)
    for offset in range(glow_radius):
        glow_surf = new_font.render(text, True, dynamic_color)
        glow_alpha = max(0, glow_intensity - offset * glow_alpha_step)
        glow_surf.set_alpha(glow_alpha)
        glow_x = rect.centerx + math.sin(time * 0.01) * 2
        glow_y = rect.centery + math.cos(time * 0.01) * 2
        glow_rect = glow_surf.get_rect(center=(glow_x, glow_y))
        surface.blit(glow_surf, glow_rect)

def create_text_surface(text, rect, color, font_size):
    """Crée une surface pour le texte principal."""
    new_font = font.Font(None, font_size)
    text_surf = new_font.render(text, True, color)
    text_rect = text_surf.get_rect(center=rect.center)
    return text_surf, text_rect

def draw_animated_text(surface, text, font_path, font_size, color, wave_height, wave_length, wave_speed, glow_color, glow_intensity, glow_steps, x=0, y=0, time=0, center=False):
    """
    Dessine un texte animé avec des effets de vague et de lueur sur la surface.

    Les paramètres par défaut sont définis dans les constantes globales.
    """
    # Charger la police
    new_font = font.Font(font_path, font_size)

    # Calculer la largeur totale si centré
    if center:
        total_width = sum(new_font.size(char)[0] for char in text)
        x -= total_width // 2  # Ajuster pour le centrage

    current_x = x

    for i, char in enumerate(text):
        # Effet de vague
        offset_y = math.sin(time * wave_speed + i * wave_length) * wave_height
        offset_x = math.cos(time * wave_speed * 0.5 + i * wave_length) * 3

        # Rendu du caractère principal
        char_surf = new_font.render(char, True, color)
        char_width = new_font.size(char)[0]
        char_x = current_x + offset_x
        char_y = y + offset_y

        # Effets de lueur
        actual_glow_intensity = int(128 + math.sin(time * 0.01) * glow_intensity)
        for glow_offset in range(glow_steps):
            glow_surf = new_font.render(char, True, glow_color)
            glow_surf.set_alpha(actual_glow_intensity - glow_offset * 40)
            surface.blit(glow_surf, (char_x + glow_offset, char_y + glow_offset))
            surface.blit(glow_surf, (char_x - glow_offset, char_y - glow_offset))

        # Dessiner le texte
        surface.blit(char_surf, (char_x, char_y))
        current_x += char_width

def create_rect(x, y, width, height):
    """Crée un rectangle avec des coordonnées et des dimensions."""
    return rect.Rect(x, y, width, height)

def draw_new_line(surface, color, start_pos, end_pos):
    return draw.line(surface, color, start_pos, end_pos)

def create_font(font_size, font_path=None):
    """Crée une nouvelle police de caractères."""
    return font.Font(font_path, font_size)

def draw_rect(surface, color, rect, width, border_radius=0):
    return draw.rect(surface, color, rect, width, border_radius)

def get_mouse_positon():
    return mouse.get_pos()

if __name__ == "__main__":
    # Exemple d'utilisation des fonctions
    load_catastrophes()