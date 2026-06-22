"""Differentiate HUMANITÉ / Eau / Portée + Durée skills.

The audit at the start of this session found that 59 of 60 HUMANITÉ
tier-groups have all three visible skills printing *identical* Effets
— in every tier, the three skills are conceptually different
mechanisms but the JSON gives them the same numeric label set, so
the player learns nothing distinct from each. The Eau Intensité
Fondations tier was de-homogenised last turn; this script continues
that work by completing **two full Eau axes**: Portée (all 3 tiers)
and Durée (all 3 tiers) — 18 skills.

Each skill now gets metric labels grounded in *its own* mechanism:
where "Canaux de dérivation" is naturally measured in canal-km +
diverted m³/s, "Levées vives" in linear km of vegetated levee +
levee width (m), and "Ouvrages partagés" in signatory countries +
regulated cross-border flow. Educational mode of the same tier
becomes "three different adaptation strategies the world has used",
not "three reskins of a digue".

Run from repo root::

    python tools/differentiate_humanite_eau.py
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path("gaia_ultimatum/data/skills_humanite.json")


# Three-level effet spec per skill. Levels scale realistically — built
# from real-world infrastructure references where possible:
#   * Pump capacities: London's Thames Barrier control = ~370 m³/s,
#     Tokyo G-Cans = ~200 m³/s, Mekong delta total = ~2000 m³/s.
#   * Polder depths: Beemster -3.4 m, Haarlemmermeer -4.5 m,
#     Wieringermeer -6 m.
#   * Mobile desalination: a containerised unit produces ~2000 m³/day
#     (Singapore's TUAS units, Doosan modules).
#   * Wetland buffer nitrate removal: scientific consensus 30-60 %
#     reduction with proper width (USEPA, INRAE).
FIXES = {
    "Eau": {
        # -------------------------------------------------------- Portée
        "Portee": {
            "Fondations": {
                "Canaux de dérivation": [
                    {"Linéaire de canal": "20 km", "Débit dérivé": "100 m³/s"},
                    {"Linéaire de canal": "60 km", "Débit dérivé": "300 m³/s"},
                    {"Linéaire de canal": "180 km", "Débit dérivé": "800 m³/s"},
                ],
                "Levées vives": [
                    {"Linéaire de levée": "15 km", "Largeur boisée": "30 m"},
                    {"Linéaire de levée": "50 km", "Largeur boisée": "60 m"},
                    {"Linéaire de levée": "180 km", "Largeur boisée": "120 m"},
                ],
                "Ouvrages partagés": [
                    {"Pays signataires": "2", "Débit transfrontalier régulé": "150 m³/s"},
                    {"Pays signataires": "5", "Débit transfrontalier régulé": "600 m³/s"},
                    {"Pays signataires": "12", "Débit transfrontalier régulé": "2 500 m³/s"},
                ],
            },
            "Amplification": {
                "Réseau de pompage": [
                    {"Stations de pompage": "12", "Débit cumulé": "500 m³/s"},
                    {"Stations de pompage": "60", "Débit cumulé": "2 500 m³/s"},
                    {"Stations de pompage": "200", "Débit cumulé": "8 000 m³/s"},
                ],
                "Réservoirs intelligents": [
                    {"Volume stocké": "5 M m³", "Anticipation crue": "12 h"},
                    {"Volume stocké": "30 M m³", "Anticipation crue": "48 h"},
                    {"Volume stocké": "150 M m³", "Anticipation crue": "1 semaine"},
                ],
                "Voies d'évacuation rapides": [
                    {"Linéaire d'axes prioritaires": "80 km", "Débit piéton + véhicule": "20 000 pers/h"},
                    {"Linéaire d'axes prioritaires": "250 km", "Débit piéton + véhicule": "80 000 pers/h"},
                    {"Linéaire d'axes prioritaires": "800 km", "Débit piéton + véhicule": "300 000 pers/h"},
                ],
            },
            "Transformation": {
                "Régulation mondiale": [
                    {"Pays adhérents": "15", "Débit régulé annuel": "200 km³/an"},
                    {"Pays adhérents": "60", "Débit régulé annuel": "1 200 km³/an"},
                    {"Pays adhérents": "150", "Débit régulé annuel": "5 000 km³/an"},
                ],
                "Modélisation prédictive": [
                    {"Horizon de prévision": "5 jours", "Précision spatiale": "10 km"},
                    {"Horizon de prévision": "14 jours", "Précision spatiale": "1 km"},
                    {"Horizon de prévision": "30 jours", "Précision spatiale": "100 m"},
                ],
                "Pacte de l'eau": [
                    {"Pays signataires": "30", "Quota garanti par habitant": "20 L/jour"},
                    {"Pays signataires": "100", "Quota garanti par habitant": "50 L/jour"},
                    {"Pays signataires": "180", "Quota garanti par habitant": "100 L/jour"},
                ],
            },
        },
        # -------------------------------------------------------- Durée
        "Duree": {
            "Fondations": {
                "Stocks d'eau potable": [
                    {"Réserve par habitant": "5 L/jour", "Autonomie": "10 jours"},
                    {"Réserve par habitant": "10 L/jour", "Autonomie": "30 jours"},
                    {"Réserve par habitant": "15 L/jour", "Autonomie": "90 jours"},
                ],
                "Citernes mobiles": [
                    {"Citernes déployables": "20", "Capacité totale": "200 m³"},
                    {"Citernes déployables": "120", "Capacité totale": "2 000 m³"},
                    {"Citernes déployables": "600", "Capacité totale": "15 000 m³"},
                ],
                "Filtration domestique": [
                    {"Foyers équipés": "8 %", "Débit par foyer": "5 L/h"},
                    {"Foyers équipés": "30 %", "Débit par foyer": "15 L/h"},
                    {"Foyers équipés": "70 %", "Débit par foyer": "30 L/h"},
                ],
            },
            "Amplification": {
                "Désalinisation mobile": [
                    {"Unités containerisées": "10", "Production par unité": "2 000 m³/jour"},
                    {"Unités containerisées": "60", "Production par unité": "5 000 m³/jour"},
                    {"Unités containerisées": "300", "Production par unité": "10 000 m³/jour"},
                ],
                "Pompage profond": [
                    {"Profondeur de puits": "150 m", "Débit durable par puits": "30 m³/h"},
                    {"Profondeur de puits": "400 m", "Débit durable par puits": "80 m³/h"},
                    {"Profondeur de puits": "800 m", "Débit durable par puits": "200 m³/h"},
                ],
                "Traitement modulaire": [
                    {"Modules déployés": "25", "Capacité par module": "500 m³/jour"},
                    {"Modules déployés": "150", "Capacité par module": "2 000 m³/jour"},
                    {"Modules déployés": "800", "Capacité par module": "8 000 m³/jour"},
                ],
            },
            "Transformation": {
                "Récupération à grande échelle": [
                    {"Taux de réutilisation": "20 %", "Volume retraité": "1 km³/an"},
                    {"Taux de réutilisation": "50 %", "Volume retraité": "8 km³/an"},
                    {"Taux de réutilisation": "85 %", "Volume retraité": "40 km³/an"},
                ],
                "Cycle urbain fermé": [
                    {"Villes certifiées": "5", "Réduction d'apport externe": "30 %"},
                    {"Villes certifiées": "40", "Réduction d'apport externe": "60 %"},
                    {"Villes certifiées": "200", "Réduction d'apport externe": "90 %"},
                ],
                "Eau atmosphérique": [
                    {"Production par m² installé": "2 L/jour", "Surface installée": "100 000 m²"},
                    {"Production par m² installé": "5 L/jour", "Surface installée": "2 M m²"},
                    {"Production par m² installé": "10 L/jour", "Surface installée": "50 M m²"},
                ],
            },
        },
    },
}


def main() -> None:
    with open(DATA, "r", encoding="utf-8") as f:
        d = json.load(f)

    touched = 0
    for cat in d["humanite_catastrophes"]:
        cat_spec = FIXES.get(cat["Catastrophe"])
        if not cat_spec:
            continue
        for axis_name, axis_spec in cat_spec.items():
            axis = cat["Types"].get(axis_name)
            if not axis:
                continue
            for tier_name, tier_spec in axis_spec.items():
                tier = axis["Niveaux"].get(tier_name)
                if not tier:
                    continue
                for skill in tier["Competences"]:
                    levels = tier_spec.get(skill["Nom"])
                    if not levels:
                        continue
                    for i, effet in enumerate(levels, start=1):
                        skill["Niveaux"][f"Niveau {i}"]["Effet"] = effet
                    touched += 1

    print(f"Differentiated {touched} HUMANITÉ Eau skills "
          "(across Portée × 3 tiers + Durée × 3 tiers).")

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"Wrote {DATA}")


if __name__ == "__main__":
    main()
