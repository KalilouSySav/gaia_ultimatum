"""Differentiate HUMANITÉ / Feu / Intensité + Impact Écologique skills.

Same pattern as ``differentiate_humanite_eau.py`` — completes two
axes of HUMANITÉ Feu (Intensité = direct firefighting, Impact
Écologique = post-event ecological recovery) = 18 skills. The
remaining Feu axes (Portée, Durée) and the other HUMANITÉ
catastrophes (Terre, Air, Vie + remaining Eau tiers) are
future-turn work.

Real-world anchors used:
  * Canadair CL-415 drops ~6 t of water in ~12 s — bracketed by the
    Brigades aériennes scale (1 / 6 / 30 aircraft).
  * Wildfire ROS scales with fuel + wind; firebreaks 5-30 m wide are
    operational; landscape-scale fuel reduction (prescribed burns,
    grazing, thinning) cuts ROS 30-70 %.
  * Satellite thermal detection: Sentinel-3 SLSTR ≈ 1 km/pixel at 1 K
    sensitivity; MODIS ≈ 1 km / 4 K; next-gen GeoXO eyes ≈ 200 m / 2 K.
  * Costa Rica doubled forest cover 1985 → 2020 — anchors the
    "reforestation per year" upper bound.
  * Indigenous "cool burning" (Aborigène, indigenous Californian) cuts
    catastrophic-fire ROS 60-80 %.

Run from repo root::

    python tools/differentiate_humanite_feu.py
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path("gaia_ultimatum/data/skills_humanite.json")


FIXES = {
    "Feu": {
        # -------------------------------------------------------- Intensité
        "Intensite": {
            "Fondations": {
                # Coupe-feux: a mechanical fuel break. Width + linear
                # length is the canonical fire-service spec.
                "Coupe-feux": [
                    {"Largeur de bande": "10 m", "Linéaire traité": "80 km"},
                    {"Largeur de bande": "20 m", "Linéaire traité": "350 km"},
                    {"Largeur de bande": "30 m", "Linéaire traité": "1 200 km"},
                ],
                # Détection précoce: monitoring towers / sensor posts.
                # Real watch-tower spacing varies 5-20 km depending on
                # terrain; "surface couverte par poste" is the standard
                # operational metric.
                "Détection précoce": [
                    {"Délai d'alerte": "30 min", "Surface par poste": "100 km²"},
                    {"Délai d'alerte": "10 min", "Surface par poste": "400 km²"},
                    {"Délai d'alerte": "2 min", "Surface par poste": "1 500 km²"},
                ],
                # Pare-feux paysagers: landscape-scale fuel-reduction —
                # prescribed burns + grazing + mosaic management. Real
                # programs (CALFIRE, ONF) cite 30-70 % ROS reduction.
                "Pare-feux paysagers": [
                    {"Surface aménagée": "5 000 ha", "Réduction du combustible": "30 %"},
                    {"Surface aménagée": "30 000 ha", "Réduction du combustible": "50 %"},
                    {"Surface aménagée": "150 000 ha", "Réduction du combustible": "70 %"},
                ],
            },
            "Amplification": {
                # Brigades aériennes: water-bomber fleet. Canadair CL-415
                # carries ~6 t / sortie; Air Tractor AT-802 ~3 t.
                "Brigades aériennes": [
                    {"Appareils mobilisables": "5", "Capacité par sortie": "6 t d'eau"},
                    {"Appareils mobilisables": "30", "Capacité par sortie": "12 t d'eau"},
                    {"Appareils mobilisables": "150", "Capacité par sortie": "30 t d'eau"},
                ],
                # Robotique anti-feu: ground robots — Thermite RS3 at
                # ~190 m²/min extinguish rate is the published baseline.
                "Robotique anti-feu": [
                    {"Robots déployés": "20", "Cadence d'extinction": "150 m²/min"},
                    {"Robots déployés": "200", "Cadence d'extinction": "400 m²/min"},
                    {"Robots déployés": "1 500", "Cadence d'extinction": "1 200 m²/min"},
                ],
                # Réservoirs aériens: airborne / mountain-top water
                # reservoirs that re-supply aerial brigades.
                "Réservoirs aériens": [
                    {"Volume stocké": "50 000 m³", "Délai de re-largage": "12 min"},
                    {"Volume stocké": "500 000 m³", "Délai de re-largage": "6 min"},
                    {"Volume stocké": "2 M m³", "Délai de re-largage": "2 min"},
                ],
            },
            "Transformation": {
                # Surveillance satellite: thermal imaging from space.
                # Sentinel-3 ≈ 1 km / 1 K; next-gen ≈ 200 m / 0.5 K.
                "Surveillance satellite": [
                    {"Résolution thermique": "1 km / 2 °C", "Latence": "30 min"},
                    {"Résolution thermique": "300 m / 1 °C", "Latence": "5 min"},
                    {"Résolution thermique": "50 m / 0,5 °C", "Latence": "30 s"},
                ],
                # IA prédictive météo-feu: ML-driven fire weather index.
                # ECMWF + CAMS predict fire weather ~5 days out at ~70 %
                # skill; aspirational tier is multi-week + tactical.
                "IA prédictive météo-feu": [
                    {"Horizon de prédiction": "3 jours", "Précision": "70 %"},
                    {"Horizon de prédiction": "10 jours", "Précision": "85 %"},
                    {"Horizon de prédiction": "30 jours", "Précision": "95 %"},
                ],
                # Couverture continentale: integrated stations across
                # continents. Counts are aspirational (one network
                # spanning Europe / Africa / Americas / Asia).
                "Couverture continentale": [
                    {"Surface surveillée": "10 M km²", "Stations interconnectées": "500"},
                    {"Surface surveillée": "60 M km²", "Stations interconnectées": "5 000"},
                    {"Surface surveillée": "150 M km²", "Stations interconnectées": "30 000"},
                ],
            },
        },
        # ------------------------------------------------ Impact Écologique
        "Impact Ecologique": {
            "Fondations": {
                # Reforestation contrôlée: replanting + monitoring.
                # Survival rate is the key real-world metric — many
                # planting programs see 30-60 % first-year survival.
                "Reforestation contrôlée": [
                    {"Surface reboisée par an": "5 000 ha", "Taux de survie à 5 ans": "40 %"},
                    {"Surface reboisée par an": "50 000 ha", "Taux de survie à 5 ans": "65 %"},
                    {"Surface reboisée par an": "500 000 ha", "Taux de survie à 5 ans": "85 %"},
                ],
                # Pépinières communales: distributed nursery production.
                # Real production capacity scales with greenhouse area.
                "Pépinières communales": [
                    {"Plants produits par an": "500 000", "Pépinières actives": "200"},
                    {"Plants produits par an": "10 M", "Pépinières actives": "2 000"},
                    {"Plants produits par an": "200 M", "Pépinières actives": "20 000"},
                ],
                # Brûlages dirigés: prescribed / cool burns. Indigenous
                # cool-burning cuts catastrophic-fire risk 60-80 % at
                # full landscape coverage.
                "Brûlages dirigés": [
                    {"Surface traitée par an": "20 000 ha", "Réduction de l'aléa": "30 %"},
                    {"Surface traitée par an": "200 000 ha", "Réduction de l'aléa": "55 %"},
                    {"Surface traitée par an": "2 M ha", "Réduction de l'aléa": "80 %"},
                ],
            },
            "Amplification": {
                # Espèces résistantes: fire-tolerant species mix.
                # Native sclerophyll forests resist crown fire better
                # than monoculture plantations.
                "Espèces résistantes": [
                    {"Essences résistantes": "15 %", "Surface diversifiée": "1 M ha"},
                    {"Essences résistantes": "40 %", "Surface diversifiée": "20 M ha"},
                    {"Essences résistantes": "75 %", "Surface diversifiée": "200 M ha"},
                ],
                # Sylviculture mixte: mixed-species silviculture.
                # Diversity per hectare is the ecological metric.
                "Sylviculture mixte": [
                    {"Essences par hectare": "3", "Surface aménagée": "2 M ha"},
                    {"Essences par hectare": "8", "Surface aménagée": "40 M ha"},
                    {"Essences par hectare": "15", "Surface aménagée": "400 M ha"},
                ],
                # Restauration des sols: soil carbon recovery. Healthy
                # forest soils carry 80-200 t C/ha; restoration adds
                # ~1-3 t C/ha/an.
                "Restauration des sols": [
                    {"Carbone du sol": "60 t C/ha", "Surface restaurée": "5 M ha"},
                    {"Carbone du sol": "120 t C/ha", "Surface restaurée": "80 M ha"},
                    {"Carbone du sol": "200 t C/ha", "Surface restaurée": "1 Gha"},
                ],
            },
            "Transformation": {
                # Régénération assistée: actively shepherded recovery.
                # Costa Rica scale = ~500 000 ha/an at peak.
                "Régénération assistée": [
                    {"Surface régénérée par an": "1 M ha", "Biodiversité restaurée": "30 %"},
                    {"Surface régénérée par an": "20 M ha", "Biodiversité restaurée": "60 %"},
                    {"Surface régénérée par an": "200 M ha", "Biodiversité restaurée": "90 %"},
                ],
                # Forêts climatiques: planted for carbon + cooling.
                # Global forest carbon sink ≈ 7 Gt CO₂/an today.
                "Forêts climatiques": [
                    {"Capture annuelle": "2 Gt CO₂", "Surface": "300 M ha"},
                    {"Capture annuelle": "10 Gt CO₂", "Surface": "1,5 Gha"},
                    {"Capture annuelle": "25 Gt CO₂", "Surface": "4 Gha"},
                ],
                # Sanctuaires inviolables: strictly-protected reserves.
                # Currently ~6 % of land in strict-protection IUCN
                # categories; aspirational tier is the "30×30" target.
                "Sanctuaires inviolables": [
                    {"Surface intégralement protégée": "100 M ha", "Espèces préservées": "5 000"},
                    {"Surface intégralement protégée": "1 Gha", "Espèces préservées": "50 000"},
                    {"Surface intégralement protégée": "4,5 Gha", "Espèces préservées": "200 000"},
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

    print(f"Differentiated {touched} HUMANITÉ Feu skills "
          "(Intensité × 3 tiers + Impact Écologique × 3 tiers).")

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"Wrote {DATA}")


if __name__ == "__main__":
    main()
