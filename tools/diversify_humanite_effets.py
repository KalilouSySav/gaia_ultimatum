"""Differentiate placeholder Effet values across all remaining HUMANITÉ axes.

After the Vie/Intensité and Vie/Impact Écologique passes, nine axes
still share three tier-level Effet templates across all 3 skills per
tier. This pass gives each skill its own metric pair so the player
sees what's distinct about each option instead of identical numbers.

Tier scale is preserved per axis (Fond modest, Ampl ~10–50×, Trans
~5–20× over Ampl) so balance is unchanged.

Run from repo root::

    python tools/diversify_humanite_effets.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills_humanite.json"


# (catastrophe, axis, skill_name) → list of 3 Effet dicts (L1, L2, L3)
NEW_EFFETS = {
    # =========================================================================
    # Eau/Intensité — three flood-defense Ampl/Trans (Fond already done)
    # =========================================================================
    ("Eau", "Intensite", "Polders"): [
        {"Surface inondable contrôlée": "1 000 ha", "Population protégée": "500 000"},
        {"Surface inondable contrôlée": "20 000 ha", "Population protégée": "3 M"},
        {"Surface inondable contrôlée": "500 000 ha", "Population protégée": "20 M"},
    ],
    ("Eau", "Intensite", "Bâti Surélevé"): [
        {"Bâtiments surélevés": "5 000", "Hauteur de surélévation": "1,5 m"},
        {"Bâtiments surélevés": "500 000", "Hauteur de surélévation": "3 m"},
        {"Bâtiments surélevés": "50 M", "Hauteur de surélévation": "6 m"},
    ],
    ("Eau", "Intensite", "Réseau de Drainage"): [
        {"Linéaire de canaux": "200 km", "Débit évacué": "100 m³/s"},
        {"Linéaire de canaux": "10 000 km", "Débit évacué": "2 000 m³/s"},
        {"Linéaire de canaux": "500 000 km", "Débit évacué": "50 000 m³/s"},
    ],
    ("Eau", "Intensite", "Quartiers Flottants"): [
        {"Quartiers flottants": "5", "Habitants": "10 000"},
        {"Quartiers flottants": "200", "Habitants": "1 M"},
        {"Quartiers flottants": "10 000", "Habitants": "100 M"},
    ],
    ("Eau", "Intensite", "Maisons Amphibies"): [
        {"Maisons amphibies": "10 000", "Niveau d'eau accepté": "2 m"},
        {"Maisons amphibies": "5 M", "Niveau d'eau accepté": "4 m"},
        {"Maisons amphibies": "500 M", "Niveau d'eau accepté": "10 m"},
    ],
    ("Eau", "Intensite", "Ville-Éponge"): [
        {"Villes-éponges": "10", "Eau absorbée": "70 %"},
        {"Villes-éponges": "500", "Eau absorbée": "90 %"},
        {"Villes-éponges": "10 000", "Eau absorbée": "99 %"},
    ],

    # =========================================================================
    # Vie/Impact Écologique — re-apply (earlier pass was overwritten)
    # =========================================================================
    ("Vie", "Impact Ecologique", "Espèces Protégées"): [
        {"Espèces sauvegardées": "100", "Aires sanctuarisées": "500 km²"},
        {"Espèces sauvegardées": "3 000", "Aires sanctuarisées": "50 000 km²"},
        {"Espèces sauvegardées": "30 000", "Aires sanctuarisées": "5 M km²"},
    ],
    ("Vie", "Impact Ecologique", "Banques de Semences"): [
        {"Variétés conservées": "10 000", "Durée de viabilité": "100 ans"},
        {"Variétés conservées": "500 000", "Durée de viabilité": "1 000 ans"},
        {"Variétés conservées": "10 M", "Durée de viabilité": "indéfinie"},
    ],
    ("Vie", "Impact Ecologique", "Aires Protégées"): [
        {"Surface protégée": "1 M ha", "Habitats préservés": "30"},
        {"Surface protégée": "50 M ha", "Habitats préservés": "200"},
        {"Surface protégée": "2 Gha", "Habitats préservés": "1 000"},
    ],
    ("Vie", "Impact Ecologique", "Restauration de la Biodiversité"): [
        {"Hectares restaurés": "100 000", "Espèces revenues": "50"},
        {"Hectares restaurés": "10 M", "Espèces revenues": "500"},
        {"Hectares restaurés": "500 M", "Espèces revenues": "5 000"},
    ],
    ("Vie", "Impact Ecologique", "Corridors Écologiques"): [
        {"Linéaire de corridors": "500 km", "Populations reconnectées": "20"},
        {"Linéaire de corridors": "50 000 km", "Populations reconnectées": "1 000"},
        {"Linéaire de corridors": "2 M km", "Populations reconnectées": "50 000"},
    ],
    ("Vie", "Impact Ecologique", "Réintroduction d'Espèces Clés"): [
        {"Espèces réintroduites": "10", "Populations établies": "5"},
        {"Espèces réintroduites": "500", "Populations établies": "200"},
        {"Espèces réintroduites": "10 000", "Populations établies": "5 000"},
    ],
    ("Vie", "Impact Ecologique", "Résilience des Écosystèmes"): [
        {"Écosystèmes consolidés": "100", "Capacité de rebond": "+30 %"},
        {"Écosystèmes consolidés": "5 000", "Capacité de rebond": "+70 %"},
        {"Écosystèmes consolidés": "100 000", "Capacité de rebond": "+95 %"},
    ],
    ("Vie", "Impact Ecologique", "Renaturation Planétaire"): [
        {"Surface renaturée": "100 M ha", "Couverture planétaire": "5 %"},
        {"Surface renaturée": "1 Gha", "Couverture planétaire": "30 %"},
        {"Surface renaturée": "5 Gha", "Couverture planétaire": "70 %"},
    ],
    ("Vie", "Impact Ecologique", "Biomimétisme"): [
        {"Innovations bio-inspirées": "100", "Industries transformées": "5"},
        {"Innovations bio-inspirées": "5 000", "Industries transformées": "30"},
        {"Innovations bio-inspirées": "200 000", "Industries transformées": "toutes"},
    ],

    # =========================================================================
    # Eau/Impact Écologique — three ecosystem-restoration axes
    # =========================================================================
    ("Eau", "Impact Ecologique", "Végétalisation des Berges"): [
        {"Linéaire de berges": "50 km", "Biodiversité riveraine": "+15 %"},
        {"Linéaire de berges": "1 000 km", "Biodiversité riveraine": "+40 %"},
        {"Linéaire de berges": "50 000 km", "Biodiversité riveraine": "+85 %"},
    ],
    ("Eau", "Impact Ecologique", "Rivières Renaturées"): [
        {"Linéaire renaturé": "100 km", "Méandres rouverts": "12"},
        {"Linéaire renaturé": "5 000 km", "Méandres rouverts": "300"},
        {"Linéaire renaturé": "200 000 km", "Méandres rouverts": "8 000"},
    ],
    ("Eau", "Impact Ecologique", "Bandes Végétales"): [
        {"Linéaire installé": "200 km", "Polluants filtrés": "30 %"},
        {"Linéaire installé": "20 000 km", "Polluants filtrés": "65 %"},
        {"Linéaire installé": "1 M km", "Polluants filtrés": "90 %"},
    ],
    ("Eau", "Impact Ecologique", "Restauration des Mangroves"): [
        {"Surface restaurée": "5 000 ha", "Carbone stocké": "10 Mt"},
        {"Surface restaurée": "200 000 ha", "Carbone stocké": "400 Mt"},
        {"Surface restaurée": "5 M ha", "Carbone stocké": "10 Gt"},
    ],
    ("Eau", "Impact Ecologique", "Récifs Artificiels"): [
        {"Structures immergées": "100", "Espèces accueillies": "30"},
        {"Structures immergées": "5 000", "Espèces accueillies": "200"},
        {"Structures immergées": "200 000", "Espèces accueillies": "1 500"},
    ],
    ("Eau", "Impact Ecologique", "Restauration des Tourbières"): [
        {"Surface restaurée": "10 000 ha", "Carbone retenu": "20 Mt"},
        {"Surface restaurée": "500 000 ha", "Carbone retenu": "1 Gt"},
        {"Surface restaurée": "20 M ha", "Carbone retenu": "40 Gt"},
    ],
    ("Eau", "Impact Ecologique", "Restauration du Littoral"): [
        {"Linéaire de côte": "200 km", "Atténuation des vagues": "1,5 m"},
        {"Linéaire de côte": "10 000 km", "Atténuation des vagues": "3 m"},
        {"Linéaire de côte": "500 000 km", "Atténuation des vagues": "6 m"},
    ],
    ("Eau", "Impact Ecologique", "Restauration des Zones Humides"): [
        {"Surface restaurée": "50 000 ha", "Capacité de stockage": "100 Mm³"},
        {"Surface restaurée": "2 M ha", "Capacité de stockage": "5 Gm³"},
        {"Surface restaurée": "100 M ha", "Capacité de stockage": "200 Gm³"},
    ],
    ("Eau", "Impact Ecologique", "Cycle de l'Eau Restauré"): [
        {"Bassins versants restaurés": "20", "Glaciers préservés": "+5 %"},
        {"Bassins versants restaurés": "500", "Glaciers préservés": "+30 %"},
        {"Bassins versants restaurés": "10 000", "Glaciers préservés": "+90 %"},
    ],

    # =========================================================================
    # Feu/Portée — protection range
    # =========================================================================
    ("Feu", "Portee", "Zones Tampons"): [
        {"Surface aménagée": "5 000 ha", "Combustible retiré": "30 %"},
        {"Surface aménagée": "200 000 ha", "Combustible retiré": "60 %"},
        {"Surface aménagée": "5 M ha", "Combustible retiré": "85 %"},
    ],
    ("Feu", "Portee", "Voies d'Accès"): [
        {"Linéaire de voies": "500 km", "Délai d'intervention": "30 min"},
        {"Linéaire de voies": "20 000 km", "Délai d'intervention": "10 min"},
        {"Linéaire de voies": "500 000 km", "Délai d'intervention": "3 min"},
    ],
    ("Feu", "Portee", "Bornes Incendie"): [
        {"Bornes installées": "2 000", "Débit par borne": "60 m³/h"},
        {"Bornes installées": "100 000", "Débit par borne": "300 m³/h"},
        {"Bornes installées": "5 M", "Débit par borne": "1 200 m³/h"},
    ],
    ("Feu", "Portee", "Évacuation Préventive"): [
        {"Population évacuée": "10 000", "Préavis": "6 h"},
        {"Population évacuée": "1 M", "Préavis": "24 h"},
        {"Population évacuée": "100 M", "Préavis": "5 j"},
    ],
    ("Feu", "Portee", "Système d'Alerte"): [
        {"Personnes alertées": "100 000", "Délai de diffusion": "5 min"},
        {"Personnes alertées": "20 M", "Délai de diffusion": "30 s"},
        {"Personnes alertées": "1 Md", "Délai de diffusion": "5 s"},
    ],
    ("Feu", "Portee", "Abris Anti-Fumée"): [
        {"Abris déployés": "200", "Capacité par abri": "300"},
        {"Abris déployés": "10 000", "Capacité par abri": "2 000"},
        {"Abris déployés": "500 000", "Capacité par abri": "10 000"},
    ],
    ("Feu", "Portee", "Itinéraires d'Évacuation"): [
        {"Linéaire d'itinéraires": "1 000 km", "Débit horaire": "5 000"},
        {"Linéaire d'itinéraires": "50 000 km", "Débit horaire": "200 000"},
        {"Linéaire d'itinéraires": "2 M km", "Débit horaire": "10 M"},
    ],
    ("Feu", "Portee", "Cartographie en Temps Réel"): [
        {"Surface cartographiée": "100 000 km²", "Latence de mise à jour": "5 min"},
        {"Surface cartographiée": "5 M km²", "Latence de mise à jour": "30 s"},
        {"Surface cartographiée": "150 M km²", "Latence de mise à jour": "3 s"},
    ],
    ("Feu", "Portee", "Coopération Internationale"): [
        {"Pays partenaires": "10", "Moyens mutualisés": "50 appareils"},
        {"Pays partenaires": "60", "Moyens mutualisés": "500 appareils"},
        {"Pays partenaires": "190", "Moyens mutualisés": "5 000 appareils"},
    ],

    # =========================================================================
    # Feu/Durée — long-term protection
    # =========================================================================
    ("Feu", "Duree", "Protection Respiratoire"): [
        {"Masques distribués": "100 000", "Filtration des particules": "85 %"},
        {"Masques distribués": "20 M", "Filtration des particules": "95 %"},
        {"Masques distribués": "1 Md", "Filtration des particules": "99 %"},
    ],
    ("Feu", "Duree", "Éducation au Risque"): [
        {"Personnes formées": "50 000", "Bons réflexes acquis": "60 %"},
        {"Personnes formées": "5 M", "Bons réflexes acquis": "80 %"},
        {"Personnes formées": "500 M", "Bons réflexes acquis": "95 %"},
    ],
    ("Feu", "Duree", "Conservation des Semences"): [
        {"Variétés conservées": "5 000", "Durée de viabilité": "20 ans"},
        {"Variétés conservées": "100 000", "Durée de viabilité": "100 ans"},
        {"Variétés conservées": "2 M", "Durée de viabilité": "1 000 ans"},
    ],
    ("Feu", "Duree", "Purification de l'Air"): [
        {"Volume d'air traité": "10 000 m³/h", "Particules retirées": "70 %"},
        {"Volume d'air traité": "1 M m³/h", "Particules retirées": "90 %"},
        {"Volume d'air traité": "100 M m³/h", "Particules retirées": "99 %"},
    ],
    ("Feu", "Duree", "Construction Ignifuge"): [
        {"Bâtiments traités": "1 000", "Résistance au feu": "1 h"},
        {"Bâtiments traités": "100 000", "Résistance au feu": "4 h"},
        {"Bâtiments traités": "10 M", "Résistance au feu": "12 h"},
    ],
    ("Feu", "Duree", "Centres de Rafraîchissement"): [
        {"Centres ouverts": "50", "Personnes accueillies": "5 000"},
        {"Centres ouverts": "2 000", "Personnes accueillies": "300 000"},
        {"Centres ouverts": "100 000", "Personnes accueillies": "20 M"},
    ],
    ("Feu", "Duree", "Qualité de l'Air Mondiale"): [
        {"Villes en conformité": "50", "Réduction des particules": "30 %"},
        {"Villes en conformité": "1 000", "Réduction des particules": "60 %"},
        {"Villes en conformité": "10 000", "Réduction des particules": "90 %"},
    ],
    ("Feu", "Duree", "Stockage du Carbone"): [
        {"Carbone capté par an": "2 Gt CO₂", "Surface plantée": "300 M ha"},
        {"Carbone capté par an": "10 Gt CO₂", "Surface plantée": "1,5 Gha"},
        {"Carbone capté par an": "25 Gt CO₂", "Surface plantée": "4 Gha"},
    ],
    ("Feu", "Duree", "Équilibre Eau-Chaleur"): [
        {"Écosystèmes rééquilibrés": "100", "Rafraîchissement local": "1 °C"},
        {"Écosystèmes rééquilibrés": "5 000", "Rafraîchissement local": "2 °C"},
        {"Écosystèmes rééquilibrés": "100 000", "Rafraîchissement local": "4 °C"},
    ],

    # =========================================================================
    # Terre/Portée — coordination range
    # =========================================================================
    ("Terre", "Portee", "Zones de Rassemblement"): [
        {"Points identifiés": "200", "Capacité par point": "500"},
        {"Points identifiés": "10 000", "Capacité par point": "3 000"},
        {"Points identifiés": "500 000", "Capacité par point": "15 000"},
    ],
    ("Terre", "Portee", "Alerte Précoce"): [
        {"Préavis sismique": "5 s", "Personnes alertées": "100 000"},
        {"Préavis sismique": "30 s", "Personnes alertées": "20 M"},
        {"Préavis sismique": "5 min", "Personnes alertées": "1 Md"},
    ],
    ("Terre", "Portee", "Signalétique de Sécurité"): [
        {"Panneaux installés": "5 000", "Surface couverte": "100 km²"},
        {"Panneaux installés": "300 000", "Surface couverte": "10 000 km²"},
        {"Panneaux installés": "20 M", "Surface couverte": "500 000 km²"},
    ],
    ("Terre", "Portee", "Diffusion d'Alerte"): [
        {"Personnes alertées": "1 M", "Délai de diffusion": "10 s"},
        {"Personnes alertées": "200 M", "Délai de diffusion": "3 s"},
        {"Personnes alertées": "5 Md", "Délai de diffusion": "1 s"},
    ],
    ("Terre", "Portee", "Capteurs Sismiques"): [
        {"Capteurs déployés": "500", "Magnitude minimale détectée": "2,5"},
        {"Capteurs déployés": "20 000", "Magnitude minimale détectée": "1,5"},
        {"Capteurs déployés": "500 000", "Magnitude minimale détectée": "0,5"},
    ],
    ("Terre", "Portee", "Cellule de Crise"): [
        {"Cellules opérationnelles": "20", "Délai de coordination": "30 min"},
        {"Cellules opérationnelles": "500", "Délai de coordination": "5 min"},
        {"Cellules opérationnelles": "10 000", "Délai de coordination": "30 s"},
    ],
    ("Terre", "Portee", "Veille Sismique Mondiale"): [
        {"Pays connectés": "30", "Délai de réponse mondial": "1 h"},
        {"Pays connectés": "120", "Délai de réponse mondial": "10 min"},
        {"Pays connectés": "190", "Délai de réponse mondial": "1 min"},
    ],
    ("Terre", "Portee", "Simulations Sismiques"): [
        {"Scénarios modélisés": "100", "Précision spatiale": "5 km"},
        {"Scénarios modélisés": "5 000", "Précision spatiale": "500 m"},
        {"Scénarios modélisés": "200 000", "Précision spatiale": "50 m"},
    ],
    ("Terre", "Portee", "Coordination Mondiale"): [
        {"Nations engagées": "20", "Aide mobilisable": "1 Md €"},
        {"Nations engagées": "100", "Aide mobilisable": "50 Md €"},
        {"Nations engagées": "190", "Aide mobilisable": "500 Md €"},
    ],

    # =========================================================================
    # Terre/Durée — resilience over time
    # =========================================================================
    ("Terre", "Duree", "Abris de Protection"): [
        {"Abris construits": "500", "Capacité par abri": "200"},
        {"Abris construits": "20 000", "Capacité par abri": "1 000"},
        {"Abris construits": "1 M", "Capacité par abri": "5 000"},
    ],
    ("Terre", "Duree", "Réserves de Survie"): [
        {"Kits stockés": "10 000", "Autonomie par kit": "3 j"},
        {"Kits stockés": "1 M", "Autonomie par kit": "14 j"},
        {"Kits stockés": "100 M", "Autonomie par kit": "60 j"},
    ],
    ("Terre", "Duree", "Secourisme"): [
        {"Secouristes formés": "20 000", "Délai d'intervention": "15 min"},
        {"Secouristes formés": "2 M", "Délai d'intervention": "5 min"},
        {"Secouristes formés": "100 M", "Délai d'intervention": "1 min"},
    ],
    ("Terre", "Duree", "Réserves Stratégiques"): [
        {"Entrepôts régionaux": "50", "Tonnage stocké": "10 000 t"},
        {"Entrepôts régionaux": "1 000", "Tonnage stocké": "500 000 t"},
        {"Entrepôts régionaux": "50 000", "Tonnage stocké": "20 M t"},
    ],
    ("Terre", "Duree", "Logistique Humanitaire"): [
        {"Routes opérationnelles": "100 km", "Tonnage acheminé par jour": "500 t"},
        {"Routes opérationnelles": "10 000 km", "Tonnage acheminé par jour": "30 000 t"},
        {"Routes opérationnelles": "1 M km", "Tonnage acheminé par jour": "2 M t"},
    ],
    ("Terre", "Duree", "Unités Médicales Mobiles"): [
        {"Unités déployables": "100", "Patients par unité par jour": "50"},
        {"Unités déployables": "5 000", "Patients par unité par jour": "200"},
        {"Unités déployables": "200 000", "Patients par unité par jour": "1 000"},
    ],
    ("Terre", "Duree", "Reconstruction Rapide"): [
        {"Logements rebâtis par mois": "1 000", "Délai de retour": "6 mois"},
        {"Logements rebâtis par mois": "100 000", "Délai de retour": "1 mois"},
        {"Logements rebâtis par mois": "10 M", "Délai de retour": "1 semaine"},
    ],
    ("Terre", "Duree", "Reconstruction Durable"): [
        {"Bâtiments certifiés": "5 000", "Durée de vie utile": "50 ans"},
        {"Bâtiments certifiés": "500 000", "Durée de vie utile": "100 ans"},
        {"Bâtiments certifiés": "50 M", "Durée de vie utile": "200 ans"},
    ],
    ("Terre", "Duree", "Communautés Résilientes"): [
        {"Communautés accompagnées": "200", "Délai de rétablissement": "1 an"},
        {"Communautés accompagnées": "10 000", "Délai de rétablissement": "3 mois"},
        {"Communautés accompagnées": "500 000", "Délai de rétablissement": "2 semaines"},
    ],

    # =========================================================================
    # Air/Portée — meteorological reach
    # =========================================================================
    ("Air", "Portee", "Réseau Météorologique"): [
        {"Stations actives": "200", "Couverture par station": "500 km²"},
        {"Stations actives": "10 000", "Couverture par station": "50 km²"},
        {"Stations actives": "500 000", "Couverture par station": "5 km²"},
    ],
    ("Air", "Portee", "Capteurs Locaux"): [
        {"Capteurs installés": "5 000", "Précision spatiale": "1 km"},
        {"Capteurs installés": "500 000", "Précision spatiale": "100 m"},
        {"Capteurs installés": "50 M", "Précision spatiale": "10 m"},
    ],
    ("Air", "Portee", "Capteurs Urbains"): [
        {"Points de mesure par ville": "100", "Fréquence d'échantillonnage": "1/min"},
        {"Points de mesure par ville": "5 000", "Fréquence d'échantillonnage": "10/s"},
        {"Points de mesure par ville": "200 000", "Fréquence d'échantillonnage": "100/s"},
    ],
    ("Air", "Portee", "Alertes Ciblées"): [
        {"Personnes touchées par message": "100 000", "Pertinence": "70 %"},
        {"Personnes touchées par message": "20 M", "Pertinence": "90 %"},
        {"Personnes touchées par message": "2 Md", "Pertinence": "99 %"},
    ],
    ("Air", "Portee", "Alerte Multicanale"): [
        {"Canaux utilisés": "5", "Taux de réception": "80 %"},
        {"Canaux utilisés": "15", "Taux de réception": "95 %"},
        {"Canaux utilisés": "30", "Taux de réception": "99,9 %"},
    ],
    ("Air", "Portee", "Communication de Crise"): [
        {"Personnes informées": "500 000", "Clarté du message": "70 %"},
        {"Personnes informées": "100 M", "Clarté du message": "90 %"},
        {"Personnes informées": "5 Md", "Clarté du message": "99 %"},
    ],
    ("Air", "Portee", "Vigilance Météo Mondiale"): [
        {"Préavis météo": "48 h", "Pays connectés": "100"},
        {"Préavis météo": "7 j", "Pays connectés": "150"},
        {"Préavis météo": "30 j", "Pays connectés": "190"},
    ],
    ("Air", "Portee", "Météo Ouverte à Tous"): [
        {"Jeux de données ouverts": "50", "Utilisateurs": "1 M"},
        {"Jeux de données ouverts": "1 000", "Utilisateurs": "100 M"},
        {"Jeux de données ouverts": "20 000", "Utilisateurs": "5 Md"},
    ],
    ("Air", "Portee", "Gouvernance Climatique"): [
        {"Nations signataires": "30", "Engagements contraignants": "5"},
        {"Nations signataires": "120", "Engagements contraignants": "20"},
        {"Nations signataires": "190", "Engagements contraignants": "50"},
    ],

    # =========================================================================
    # Air/Durée — long-term storm resilience
    # =========================================================================
    ("Air", "Duree", "Abris Anti-Tempête"): [
        {"Abris ouverts": "100", "Capacité totale": "10 000"},
        {"Abris ouverts": "5 000", "Capacité totale": "500 000"},
        {"Abris ouverts": "200 000", "Capacité totale": "20 M"},
    ],
    ("Air", "Duree", "Abris Souterrains"): [
        {"Abris souterrains": "50", "Autonomie": "3 j"},
        {"Abris souterrains": "2 000", "Autonomie": "14 j"},
        {"Abris souterrains": "100 000", "Autonomie": "60 j"},
    ],
    ("Air", "Duree", "Abris Communautaires"): [
        {"Abris partagés": "500", "Personnes par abri": "200"},
        {"Abris partagés": "20 000", "Personnes par abri": "1 000"},
        {"Abris partagés": "1 M", "Personnes par abri": "5 000"},
    ],
    ("Air", "Duree", "Refuges Autonomes"): [
        {"Refuges autonomes": "100", "Autonomie": "30 j"},
        {"Refuges autonomes": "5 000", "Autonomie": "1 an"},
        {"Refuges autonomes": "300 000", "Autonomie": "indéfinie"},
    ],
    ("Air", "Duree", "Énergie Décentralisée"): [
        {"Foyers équipés": "10 000", "Puissance par foyer": "3 kW"},
        {"Foyers équipés": "2 M", "Puissance par foyer": "10 kW"},
        {"Foyers équipés": "500 M", "Puissance par foyer": "30 kW"},
    ],
    ("Air", "Duree", "Logistique d'Urgence"): [
        {"Tonnage stocké": "10 000 t", "Délai d'acheminement": "48 h"},
        {"Tonnage stocké": "500 000 t", "Délai d'acheminement": "12 h"},
        {"Tonnage stocké": "20 M t", "Délai d'acheminement": "2 h"},
    ],
    ("Air", "Duree", "Ville Résiliente"): [
        {"Quartiers résilients": "10", "Délai de retour à la normale": "2 semaines"},
        {"Quartiers résilients": "500", "Délai de retour à la normale": "3 jours"},
        {"Quartiers résilients": "50 000", "Délai de retour à la normale": "24 h"},
    ],
    ("Air", "Duree", "Réduction des Émissions"): [
        {"Réduction des émissions": "20 %", "Villes en transition": "50"},
        {"Réduction des émissions": "50 %", "Villes en transition": "1 000"},
        {"Réduction des émissions": "90 %", "Villes en transition": "10 000"},
    ],
    ("Air", "Duree", "Continuité des Services"): [
        {"Services maintenus": "60 %", "Temps de coupure": "24 h"},
        {"Services maintenus": "90 %", "Temps de coupure": "2 h"},
        {"Services maintenus": "99 %", "Temps de coupure": "10 min"},
    ],

    # =========================================================================
    # Vie/Portée — epidemic containment scope
    # =========================================================================
    ("Vie", "Portee", "Quarantaine"): [
        {"Personnes isolées": "5 000", "Durée d'isolement": "10 j"},
        {"Personnes isolées": "500 000", "Durée d'isolement": "14 j"},
        {"Personnes isolées": "50 M", "Durée d'isolement": "21 j"},
    ],
    ("Vie", "Portee", "Solidarité Locale"): [
        {"Bénévoles mobilisés": "5 000", "Quartiers couverts": "100"},
        {"Bénévoles mobilisés": "500 000", "Quartiers couverts": "10 000"},
        {"Bénévoles mobilisés": "50 M", "Quartiers couverts": "1 M"},
    ],
    ("Vie", "Portee", "Confinement Ciblé"): [
        {"Foyers confinés": "100", "Réduction du R0": "0,3"},
        {"Foyers confinés": "10 000", "Réduction du R0": "1,0"},
        {"Foyers confinés": "1 M", "Réduction du R0": "2,5"},
    ],
    ("Vie", "Portee", "Traçage des Contacts"): [
        {"Contacts retrouvés par jour": "1 000", "Délai d'identification": "48 h"},
        {"Contacts retrouvés par jour": "100 000", "Délai d'identification": "6 h"},
        {"Contacts retrouvés par jour": "10 M", "Délai d'identification": "15 min"},
    ],
    ("Vie", "Portee", "Données de Santé"): [
        {"Données partagées": "1 M", "Anonymisation": "renforcée"},
        {"Données partagées": "500 M", "Anonymisation": "préservée"},
        {"Données partagées": "10 Md", "Anonymisation": "garantie"},
    ],
    ("Vie", "Portee", "Cordon Sanitaire"): [
        {"Frontières sécurisées": "10", "Personnes filtrées par jour": "100 000"},
        {"Frontières sécurisées": "100", "Personnes filtrées par jour": "10 M"},
        {"Frontières sécurisées": "1 000", "Personnes filtrées par jour": "1 Md"},
    ],
    ("Vie", "Portee", "Coordination Sanitaire"): [
        {"Pays coordonnés": "20", "Délai de décision commune": "1 semaine"},
        {"Pays coordonnés": "100", "Délai de décision commune": "48 h"},
        {"Pays coordonnés": "190", "Délai de décision commune": "6 h"},
    ],
    ("Vie", "Portee", "Veille Sanitaire"): [
        {"Pathogènes suivis": "100", "Préavis épidémique": "1 semaine"},
        {"Pathogènes suivis": "5 000", "Préavis épidémique": "1 mois"},
        {"Pathogènes suivis": "100 000", "Préavis épidémique": "6 mois"},
    ],
    ("Vie", "Portee", "Préparation aux Pandémies"): [
        {"Exercices par an": "10", "Niveau de préparation": "60 %"},
        {"Exercices par an": "200", "Niveau de préparation": "85 %"},
        {"Exercices par an": "5 000", "Niveau de préparation": "99 %"},
    ],

    # =========================================================================
    # Vie/Durée — long-term healthcare resilience
    # =========================================================================
    ("Vie", "Duree", "Stock Stratégique"): [
        {"Tonnage stocké": "5 000 t", "Mois de réserve": "3"},
        {"Tonnage stocké": "200 000 t", "Mois de réserve": "12"},
        {"Tonnage stocké": "10 M t", "Mois de réserve": "36"},
    ],
    ("Vie", "Duree", "Chaîne du Froid"): [
        {"Volume réfrigéré": "10 000 m³", "Durée de conservation": "6 mois"},
        {"Volume réfrigéré": "1 M m³", "Durée de conservation": "5 ans"},
        {"Volume réfrigéré": "100 M m³", "Durée de conservation": "30 ans"},
    ],
    ("Vie", "Duree", "Chaîne Logistique Médicale"): [
        {"Points de distribution": "1 000", "Délai de livraison": "24 h"},
        {"Points de distribution": "100 000", "Délai de livraison": "2 h"},
        {"Points de distribution": "10 M", "Délai de livraison": "15 min"},
    ],
    ("Vie", "Duree", "Production Pharmaceutique Continue"): [
        {"Doses produites par mois": "50 M", "Diversité de produits": "100"},
        {"Doses produites par mois": "5 Md", "Diversité de produits": "1 000"},
        {"Doses produites par mois": "500 Md", "Diversité de produits": "10 000"},
    ],
    ("Vie", "Duree", "Bioproduction Décentralisée"): [
        {"Laboratoires locaux": "500", "Autonomie nationale": "30 %"},
        {"Laboratoires locaux": "20 000", "Autonomie nationale": "70 %"},
        {"Laboratoires locaux": "1 M", "Autonomie nationale": "100 %"},
    ],
    ("Vie", "Duree", "Production Médicale Résiliente"): [
        {"Capacité de secours": "20 %", "Temps de remise en route": "1 mois"},
        {"Capacité de secours": "50 %", "Temps de remise en route": "1 semaine"},
        {"Capacité de secours": "100 %", "Temps de remise en route": "24 h"},
    ],
    ("Vie", "Duree", "Couverture Sanitaire Universelle"): [
        {"Population couverte": "60 %", "Coût par habitant": "500 €/an"},
        {"Population couverte": "85 %", "Coût par habitant": "1 500 €/an"},
        {"Population couverte": "100 %", "Coût par habitant": "3 000 €/an"},
    ],
    ("Vie", "Duree", "Télémédecine"): [
        {"Consultations par mois": "1 M", "Zones désertifiées couvertes": "30 %"},
        {"Consultations par mois": "100 M", "Zones désertifiées couvertes": "70 %"},
        {"Consultations par mois": "5 Md", "Zones désertifiées couvertes": "100 %"},
    ],
    ("Vie", "Duree", "Soins de Proximité"): [
        {"Centres de santé": "5 000", "Distance moyenne": "10 km"},
        {"Centres de santé": "200 000", "Distance moyenne": "3 km"},
        {"Centres de santé": "10 M", "Distance moyenne": "500 m"},
    ],
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    n_skills = 0
    not_found = []
    for cat in data["humanite_catastrophes"]:
        cat_name = cat["Catastrophe"]
        for ax_name, ax in cat["Types"].items():
            for tier in ax["Niveaux"].values():
                for sk in tier["Competences"]:
                    key = (cat_name, ax_name, sk["Nom"])
                    if key not in NEW_EFFETS:
                        continue
                    levels_data = NEW_EFFETS[key]
                    for lvl_idx, (lvl_name, lvl) in enumerate(sk["Niveaux"].items()):
                        if not isinstance(lvl, dict) or lvl_idx >= len(levels_data):
                            continue
                        lvl["Effet"] = levels_data[lvl_idx]
                    n_skills += 1

    # Check for keys in NEW_EFFETS not found in data
    seen_keys = set()
    for cat in data["humanite_catastrophes"]:
        cat_name = cat["Catastrophe"]
        for ax_name, ax in cat["Types"].items():
            for tier in ax["Niveaux"].values():
                for sk in tier["Competences"]:
                    seen_keys.add((cat_name, ax_name, sk["Nom"]))
    for key in NEW_EFFETS:
        if key not in seen_keys:
            not_found.append(key)

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Skills rewritten: {n_skills}")
    print(f"Expected: {len(NEW_EFFETS)}")
    if not_found:
        print(f"\nUnmatched entries in NEW_EFFETS (typo?):")
        for k in not_found:
            print(f"  {k}")


if __name__ == "__main__":
    main()
