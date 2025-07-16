import pygame
import json
import pyproj

# Initialiser Pygame
pygame.init()

# Dimensions de la fenêtre
largeur, hauteur = 1200, 600
fenetre = pygame.display.set_mode((largeur, hauteur))
pygame.display.set_caption("Carte du monde avec Pyproj")

# Couleurs
BLANC = (255, 255, 255)
NOIR = (0, 0, 0)
VERT = (0, 255, 0)
BLEU = (173, 216, 230)
ROUGE = (255, 0, 0)

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

# Boucle principale
en_cours = True
info_contextuelle = None  # Pour afficher l'info contextuelle
while en_cours:
    for evenement in pygame.event.get():
        if evenement.type == pygame.QUIT:
            en_cours = False
        elif evenement.type == pygame.MOUSEBUTTONDOWN:
            souris_x, souris_y = pygame.mouse.get_pos()

            if info_contextuelle:
                if est_dans_bouton_fermeture((souris_x, souris_y)):
                    info_contextuelle = None  # Fermer la fenêtre contextuelle en cliquant sur "X"
                elif not pygame.Rect(50, 50, 400, 250).collidepoint(souris_x, souris_y):
                    info_contextuelle = None  # Fermer la fenêtre contextuelle si clic en dehors de la fenêtre

            # Vérifier quel pays a été cliqué
            for pays, info in pays_polygones.items():
                polygones = info.get("polygones", [info.get("polygone")])
                for polygone in polygones:
                    if est_dans_polygone((souris_x, souris_y), polygone):
                        info_contextuelle = info  # Afficher l'info contextuelle du pays cliqué

    fenetre.fill(BLANC)

    # Dessiner chaque polygone projeté
    for pays, info in pays_polygones.items():
        polygones = info.get("polygones", [info.get("polygone")])
        for polygone in polygones:
            pygame.draw.polygon(fenetre, BLEU, polygone)
            pygame.draw.polygon(fenetre, NOIR, polygone, 2)

    # Si une fenêtre contextuelle est ouverte, afficher les informations
    if info_contextuelle:
        pygame.draw.rect(fenetre, BLEU, (50, 50, 400, 250))  # Zone info
        pygame.draw.rect(fenetre, NOIR, (50, 50, 400, 250), 2)  # Bordure de la fenêtre contextuelle
        pygame.draw.rect(fenetre, ROUGE, (450, 55, 25, 25))  # Bouton X

        font = pygame.font.Font(None, 24)
        y_offset = 60
        # Afficher uniquement le nom et la population avec les 4 indicateurs supplémentaires
        for key, value in info_contextuelle.items():
            if key != "polygones" and key != "polygone":
                texte = font.render(formater_texte(key, value), True, NOIR)
                fenetre.blit(texte, (60, y_offset))
                y_offset += 30

    pygame.display.flip()

pygame.quit()
