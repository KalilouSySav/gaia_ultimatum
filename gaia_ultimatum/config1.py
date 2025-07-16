import os
import json
from typing import Dict, Any, List, Tuple
import pygame
from utils import load_json, save_json

# Chemins d'accès aux ressources
DOSSIER_DATA = "data"
DOSSIER_IMAGES = os.path.join(DOSSIER_DATA, "images")
DOSSIER_SONS = os.path.join(DOSSIER_DATA, "sounds")
DOSSIER_MUSIQUES = os.path.join(DOSSIER_DATA, "music")
DOSSIER_FONTS = os.path.join(DOSSIER_DATA, "fonts")
DOSSIER_SAUVEGARDES = os.path.join(DOSSIER_DATA, "saves")
FICHIER_CARTE = os.path.join(DOSSIER_DATA, "map.json")
FICHIER_ZONES_GEOJSON = os.path.join(DOSSIER_DATA, "zones.geojson")
FICHIER_COMPETENCES_EAU = os.path.join(DOSSIER_DATA, "competences_eau.json")
FICHIER_COMPETENCES_FEU = os.path.join(DOSSIER_DATA, "competences_feu.json")
FICHIER_COMPETENCES_AIR = os.path.join(DOSSIER_DATA, "competences_air.json")
FICHIER_COMPETENCES_TERRE = os.path.join(DOSSIER_DATA, "competences_terre.json")
FICHIER_COMPETENCES_VIE = os.path.join(DOSSIER_DATA, "competences_vie.json")
FICHIER_DONNEES_PAYS = os.path.join(DOSSIER_DATA, "pays_data.json")

# Paramètres Généraux du Jeu
class GameConfig:
    NOM_JEU = "Gaia Ultimatum"
    VERSION = "1.0.0"
    AUTEUR = "Votre Nom"
    LARGEUR_FENETRE = 1200
    HAUTEUR_FENETRE = 800
    FPS = 60
    MODE_FENETRE = "fenêtré"  # Options: "plein écran", "fenêtré"
    ECHELLE_INTERFACE = 1.0

# Options Graphiques
class GraphicsConfig:
    AFFICHAGE_FPS = True
    ANTI_ALIASING = True
    QUALITE_TEXTURES = "haute"  # Options: "basse", "moyenne", "haute"
    NIVEAU_DETAILS_CARTE = "moyen"  # Options: "bas", "moyen", "élevé"
    AFFICHER_OMBRES = True
    AFFICHER_REFLETS = True
    AFFICHER_ANIMATIONS = True

# Options Sonores
class AudioConfig:
    VOLUME_GENERAL = 0.8
    VOLUME_MUSIQUE = 0.7
    VOLUME_EFFETS_SONORES = 0.8
    VOLUME_AMBIANCE = 0.6
    MUTED = False

# Options de Jouabilité
class PlayabilityConfig:
    DIFFICULTE = "normale"  # Options: "facile", "normale", "difficile"
    VITESSE_JEU = 1.0
    ACTIVER_DIDACTICIEL = True
    ACTIVER_NOTIFICATIONS = True

# Configuration des Commandes
class ControlsConfig:
    TOUCHE_PAUSE = pygame.K_ESCAPE
    TOUCHE_AMELIORATIONS = pygame.K_a
    TOUCHE_INFO_PAYS = pygame.K_i
    TOUCHE_MENU_PRINCIPAL = pygame.K_m
    TOUCHE_ANNULER = pygame.K_BACKSPACE
    TOUCHE_SELECTIONNER = pygame.K_RETURN
    TOUCHE_HAUT = pygame.K_UP
    TOUCHE_BAS = pygame.K_DOWN
    TOUCHE_GAUCHE = pygame.K_LEFT
    TOUCHE_DROITE = pygame.K_RIGHT
    TOUCHE_PLEIN_ECRAN = pygame.K_F11

# Paramètres de la Catastrophe
class CatastropheConfig:
    COEFFICIENT_DUREE = 1.0
    COEFFICIENT_PORTEE = 1.0
    COEFFICIENT_INTENSITE = 1.0
    COEFFICIENT_IMPACT_ECOLOGIQUE = 1.0
    DUREE_BASE_POINT_ROUGE = 10.0
    FACTEUR_IMPREVISIBLE = 0.1
    FACTEUR_MUTATION = 0.05

# Paramètres des Pays
class PaysConfig:
    FACTEUR_AFFECTION = 0.5
    FACTEUR_MORTALITE = 0.1
    COEFFICIENT_CONTRE_ATTAQUE = 0.8

# Paramètres d'Affichage des Points Rouges
class PointsRougesConfig:
    TAILLE_POINT_ROUGE = 10
    COULEUR_POINT_ROUGE = (255, 0, 0)
    DUREE_FONDU_ENTREE = 1.0
    DUREE_FONDU_SORTIE = 1.0
    FACTEUR_PROXIMITE_APPARITION = 0.5

# Paramètres d'Interface Utilisateur
class UIConfig:
    COULEUR_FOND_FENETRE = (240, 240, 240)
    COULEUR_BORDURE_FENETRE = (169, 169, 169)
    COULEUR_TEXTE = (0, 0, 0)
    POLICE_TEXTE = os.path.join(DOSSIER_FONTS, "Arial.ttf")
    TAILLE_POLICE_TITRE = 48
    TAILLE_POLICE_TEXTE = 24
    COULEUR_BOUTON = (211, 211, 211)
    COULEUR_BOUTON_SURVOL = (192, 192, 192)
    COULEUR_BOUTON_SELECTIONNE = (169, 169, 169)
    COULEUR_BOUTON_DESACTIVE = (128, 128, 128)

# Paramètres de la Barre de Progression
class ProgressBarConfig:
    COULEUR_FOND_BARRE = (200, 200, 200)
    COULEUR_REMPLISSAGE_BARRE = (0, 255, 0)
    LARGEUR_BARRE = 20
    HAUTEUR_BARRE = 10
    MARGE_BARRE = 5

# Paramètres de Sauvegarde
class SaveConfig:
    NOM_DOSSIER_SAUVEGARDES = DOSSIER_SAUVEGARDES
    NOM_FICHIER_SAUVEGARDE_AUTOMATIQUE = "autosave.json"

# Paramètres pour la Génération des Notifications
class NotificationConfig:
    TYPES_NOTIFICATIONS = ["info", "avertissement", "urgent"]
    DUREE_AFFICHAGE_NOTIFICATION = 5.0
    CAPACITE_FILE_ATTENTE_NOTIFICATIONS = 10
    COEFFICIENT_NOTIFICATION_URGENTE = 2.0

# Paramètres pour la Gestion des Tours
class TourConfig:
    NB_TOURS_PERIODE_GRACE = 10
    NB_TOURS_LIMITE_VICTOIRE = 100
    SEUIL_PROGRESSION_VICTOIRE = 0.75

# Fonctions pour charger et sauvegarder la configuration
def load_config() -> Dict[str, Any]:
    """
    Charge la configuration à partir d'un fichier JSON.

    Returns:
        Dict[str, Any]: La configuration chargée.
    """
    return load_json(os.path.join(DOSSIER_DATA, "config.json"))

def save_config(config: Dict[str, Any]) -> None:
    """
    Sauvegarde la configuration dans un fichier JSON.

    Args:
        config (Dict[str, Any]): La configuration à sauvegarder.
    """
    save_json(os.path.join(DOSSIER_DATA, "config.json"), config)

# Chargement initial de la configuration
CONFIG = load_config()
