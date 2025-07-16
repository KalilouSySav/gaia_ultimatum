import pygame
import math

class GraphicsEngine:

    def __init__(self, screen_width=1200, screen_height=800):
        self.screen_width = screen_width
        self.screen_height = screen_height

    def render_map(self, screen, map_path="data/world_map.png"):
        """Affiche la carte du monde sur l'écran.

        Args:
            screen: La surface Pygame sur laquelle dessiner.
            map_path: Le chemin d'accès au fichier image de la carte.
        """

        try:
            map_image = pygame.image.load(map_path)
            map_image = pygame.transform.scale(map_image, (self.screen_width, self.screen_height))  # Ajuster à la taille de l'écran

            screen.blit(map_image, (0, 0))

        except FileNotFoundError:
            print(f"Erreur: Fichier de carte non trouvé: {map_path}")
            # Gérer l'erreur, par exemple afficher un message à l'écran ou utiliser une carte par défaut.
            pygame.draw.rect(screen, (0, 0, 0), (0, 0, self.screen_width, self.screen_height)) # Affiche un rectangle noir en cas d'erreur

        except Exception as e:  # Gérer d'autres erreurs potentielles
            print(f"Erreur lors du chargement de la carte: {e}")
            pygame.draw.rect(screen, (0, 0, 0), (0, 0, self.screen_width, self.screen_height)) # Affiche un rectangle noir en cas d'erreur

    def draw_zones(self, screen, zones_data, impact_data):
        """Dessine les zones critiques avec des couleurs dynamiques.

        Args:
            screen: La surface Pygame sur laquelle dessiner.
            zones_data:  Données GeoJSON ou dictionnaires des zones et de leurs polygones.
            impact_data: Dictionnaire contenant l'impact pour chaque zone.
        """
        for zone_name, polygon in zones_data.items():  # Itérer sur les zones
            try:
                impact = impact_data[zone_name]
                # Déterminer la couleur en fonction de l'impact
                if impact < 0.3:
                    color = (255, 255, 0, 128)  # Jaune transparent (alerte)
                elif impact < 0.7:
                    color = (255, 165, 0, 128)  # Orange transparent (dégâts modérés)
                else:
                    color = (255, 0, 0, 128)  # Rouge transparent (crise sévère)

                # Dessiner le polygone rempli avec la couleur
                points = [(int(x), int(y)) for x, y in polygon]  # Convertir les coordonnées en entiers
                pygame.draw.polygon(screen, color, points)


            except KeyError:
                print(f"Avertissement : Données d'impact manquantes pour la zone : {zone_name}")
                # Vous pouvez choisir d'ignorer la zone ou d'utiliser une couleur par défaut.

    def animate_hurricane(self, screen, position, radius, color=(255, 255, 255), angle=0, speed=1):
        """Anime un ouragan comme un cercle en rotation.

        Args:
            screen: La surface Pygame sur laquelle dessiner.
            position: Le centre de l'ouragan (tuple x, y).
            radius: Le rayon de l'ouragan.
            color: La couleur de l'ouragan (tuple RVB).
            angle: L'angle initial de rotation.
            speed: La vitesse de rotation.
        """

        x = position[0] + radius * math.cos(math.radians(angle))
        y = position[1] + radius * math.sin(math.radians(angle))
        pygame.draw.circle(screen, color, (int(x), int(y)), 5) # Dessiner un petit cercle pour simuler le mouvement de rotation.


        return angle + speed  # Retourner l'angle mis à jour

    def animate_earthquake(self, screen, position, max_length=50, color=(255, 0, 0), lines=[]):
        """Anime une fissure sismique.

        Args:
            screen: La surface Pygame sur laquelle dessiner.
            position:  Point de départ de la fissure (tuple x, y).
            max_length: Longueur maximale de la fissure.
            color: Couleur de la fissure (tuple RVB).
            lines: Liste des segments de ligne existants.
        """
        if len(lines) < max_length: # limiter la taille de la fissure
            new_x = position[0] + random.randint(-2, 2) # léger décalage aléatoire
            new_y = position[1] + random.randint(-2, 2)

            if len(lines)>0: # à partir du 2eme segment
                last_pos=lines[-1] # prendre la derniere position
                pygame.draw.line(screen, color, last_pos,(new_x, new_y),2)
            else: # premier segment, partir de la position initiale
                pygame.draw.line(screen, color, position,(new_x, new_y),2)
            lines.append((new_x, new_y))



        else: # fissure à sa taille max, la faire disparaitre progressivement
            if len(lines) > 0:
                lines.pop(0) # supprimer les anciens segments

        for i in range(len(lines)-1):
            pygame.draw.line(screen, color, lines[i], lines[i+1], 2)





        return lines # Retourne les segments pour l'animation suivante

    def animate_fire(self, screen, position, size=20, color=(255, 69, 0), intensity=1.0):
        """Anime un feu à une position donnée.

        Args:
            screen: La surface Pygame sur laquelle dessiner.
            position: La position du feu (tuple x, y).
            size: La taille de base du feu.
            color: La couleur du feu.
            intensity: Un facteur pour ajuster la taille et la fluctuation du feu.
        """
        flicker = random.uniform(0.5 * intensity, 1.5 * intensity) # Fluctuation aléatoire de la taille
        fire_size = int(size * flicker)
        # Créer une surface pour le feu avec transparence (optionnel, pour un effet plus lisse)
        fire_surface = pygame.Surface((fire_size * 2, fire_size * 2), pygame.SRCALPHA)
        pygame.draw.circle(fire_surface, color + (int(150 * intensity),), (fire_size, fire_size), fire_size)
        screen.blit(fire_surface, (position[0] - fire_size, position[1]- fire_size ))

    def zoom_map(self, screen, map_path, zoom_level, zoom_center):

        """Zoom sur la carte.

        Args:
            screen: La surface Pygame sur laquelle dessiner.
            map_path:  Chemin vers l'image de la carte.
            zoom_level:  Niveau de zoom (1.0 = zoom normal, >1.0 = zoom avant, <1.0 = zoom arrière).
            zoom_center: Centre du zoom (tuple x, y).
        """
        try:
            map_image = pygame.image.load(map_path)

            width = int(map_image.get_width() * zoom_level)
            height = int(map_image.get_height() * zoom_level)
            zoomed_map = pygame.transform.scale(map_image,(width,height))

            # Calculer l'offset pour centrer le zoom
            offset_x = zoom_center[0] - zoomed_map.get_width() // 2
            offset_y = zoom_center[1] - zoomed_map.get_height() // 2



            screen.blit(zoomed_map, (offset_x, offset_y))

        except FileNotFoundError:
            print(f"Erreur : Fichier de carte non trouvé : {map_path}")
            # Gérer l'erreur...
        except Exception as e:
            print(f"Erreur lors du chargement ou du zoom de la carte : {e}")

