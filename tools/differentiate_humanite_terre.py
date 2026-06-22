"""Differentiate HUMANITÉ / Terre / Intensité + Impact Écologique.

Same pattern as the Eau and Feu differentiation scripts — completes
two axes of HUMANITÉ Terre (Intensité = direct shock mitigation,
Impact Écologique = post-event geological recovery) = 18 skills.

Real-world anchors used:
  * Modern parasismic codes: Mexico's NTC-DCEC 2017 + Japan's 2000
    Kijun-hō targets cut life-safety failure by ~10× vs. unreinforced
    masonry. PGA tolerance up to ~0.5 g for tier-3 buildings.
  * Base-isolation systems (Friction Pendulum, lead-rubber bearings):
    reduce floor accelerations by 60-85 %, used since the 1985 Mexico
    quake retrofits.
  * Slope-stabilising vetiver grass holds slopes up to 30° at 80 %
    bio-engineering reduction in failure probability (USDA, ICIMOD).
  * Reforestation root depth: vetiver 3 m, indigenous deep-root species
    5-15 m, anchoring landslide-prone slopes.
  * Liquefaction susceptibility halved by deep soil mixing / vibro-
    compaction at 5-15 m depth.
  * IUCN 30×30 target = 30 % of land in protected status by 2030.

Run from repo root::

    python tools/differentiate_humanite_terre.py
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path("gaia_ultimatum/data/skills_humanite.json")


FIXES = {
    "Terre": {
        # -------------------------------------------------------- Intensité
        "Intensite": {
            "Fondations": {
                # Bâti antisismique: parasismic building codes.
                # PGA tolerance + protected building stock %.
                "Bâti antisismique": [
                    {"Accélération tolérée": "0,2 g", "Bâti certifié": "20 %"},
                    {"Accélération tolérée": "0,35 g", "Bâti certifié": "55 %"},
                    {"Accélération tolérée": "0,5 g", "Bâti certifié": "90 %"},
                ],
                # Renforcement public: school / hospital retrofitting
                # campaigns. Measured in renovated buildings + lives
                # protected per quake event.
                "Renforcement public": [
                    {"Établissements rénovés": "500", "Population abritée": "1 M"},
                    {"Établissements rénovés": "8 000", "Population abritée": "30 M"},
                    {"Établissements rénovés": "80 000", "Population abritée": "300 M"},
                ],
                # Aciers absorbants: damped steel frames (BRBs, BRB-V).
                # Real BRB damping cuts inter-story drift by 50-80 %.
                "Aciers absorbants": [
                    {"Réduction d'oscillation": "30 %", "Bâti renforcé": "5 M m²"},
                    {"Réduction d'oscillation": "55 %", "Bâti renforcé": "40 M m²"},
                    {"Réduction d'oscillation": "80 %", "Bâti renforcé": "250 M m²"},
                ],
            },
            "Amplification": {
                # Renforcement structurel: city-scale base isolation
                # retrofits (lead-rubber, friction pendulum).
                # Real systems (Marina Bay, Roppongi Hills) cut floor
                # accelerations 60-85 %.
                "Renforcement structurel": [
                    {"Réduction d'accélération": "60 %", "Tours équipées": "150"},
                    {"Réduction d'accélération": "75 %", "Tours équipées": "2 500"},
                    {"Réduction d'accélération": "85 %", "Tours équipées": "20 000"},
                ],
                # Bouclier urbain: integrated city-wide seismic
                # protection — soil treatment + isolation + dampers.
                "Bouclier urbain": [
                    {"Surface protégée": "50 km²", "Population couverte": "2 M"},
                    {"Surface protégée": "500 km²", "Population couverte": "30 M"},
                    {"Surface protégée": "5 000 km²", "Population couverte": "300 M"},
                ],
                # Réseaux durcis: hardened lifelines (water, gas,
                # electricity) — flexible joints + redundant routing.
                # Restoration time after a major quake is the real KPI.
                "Réseaux durcis": [
                    {"Continuité après séisme": "70 %", "Temps de rétablissement": "48 h"},
                    {"Continuité après séisme": "90 %", "Temps de rétablissement": "12 h"},
                    {"Continuité après séisme": "98 %", "Temps de rétablissement": "2 h"},
                ],
            },
            "Transformation": {
                # Méta-structures: post-2050 megastructures with active
                # damping (TMDs at building scale, ML-driven response).
                "Méta-structures": [
                    {"Magnitude soutenable": "M 7,5", "Mégastructures actives": "10"},
                    {"Magnitude soutenable": "M 8,5", "Mégastructures actives": "200"},
                    {"Magnitude soutenable": "M 9,5", "Mégastructures actives": "2 500"},
                ],
                # Cités-tampons: urban districts on isolated platforms —
                # everything between platform and ground decouples.
                "Cités-tampons": [
                    {"Districts isolés": "20", "Population décrochée du sol": "10 M"},
                    {"Districts isolés": "200", "Population décrochée du sol": "200 M"},
                    {"Districts isolés": "1 500", "Population décrochée du sol": "2 Mds"},
                ],
                # Architecture vivante: bio-inspired self-healing
                # structures using mycelium / bacterial concrete.
                "Architecture vivante": [
                    {"Auto-réparation": "15 %", "Bâti vivant": "50 M m²"},
                    {"Auto-réparation": "50 %", "Bâti vivant": "1 G m²"},
                    {"Auto-réparation": "90 %", "Bâti vivant": "30 G m²"},
                ],
            },
        },
        # ------------------------------------------------ Impact Écologique
        "Impact Ecologique": {
            "Fondations": {
                # Stabilisation des sols: vibro-compaction / dynamic
                # compaction / deep soil mixing — reduces liquefaction
                # depth.
                "Stabilisation des sols": [
                    {"Profondeur traitée": "5 m", "Surface stabilisée": "500 ha"},
                    {"Profondeur traitée": "12 m", "Surface stabilisée": "10 000 ha"},
                    {"Profondeur traitée": "25 m", "Surface stabilisée": "200 000 ha"},
                ],
                # Plantes fixatrices: vetiver / bambou / engineered
                # species holding slopes. Vetiver roots reach 3-5 m.
                "Plantes fixatrices": [
                    {"Profondeur racinaire": "2 m", "Linéaire de pente fixée": "200 km"},
                    {"Profondeur racinaire": "5 m", "Linéaire de pente fixée": "5 000 km"},
                    {"Profondeur racinaire": "10 m", "Linéaire de pente fixée": "100 000 km"},
                ],
                # Renaturation: removing built surfaces, restoring
                # natural hydrology + soil ecology.
                "Renaturation": [
                    {"Surface renaturée": "1 000 ha", "Espèces réintroduites": "30"},
                    {"Surface renaturée": "30 000 ha", "Espèces réintroduites": "200"},
                    {"Surface renaturée": "1 M ha", "Espèces réintroduites": "1 200"},
                ],
            },
            "Amplification": {
                # Reforestation racinaire: deep-root forest restoration
                # targeting slope stability. Root reinforcement boosts
                # slope strength by Si (root cohesion) of 1-10 kPa per
                # well-rooted hectare.
                "Reforestation racinaire": [
                    {"Cohésion racinaire": "2 kPa", "Surface reboisée": "5 M ha"},
                    {"Cohésion racinaire": "6 kPa", "Surface reboisée": "60 M ha"},
                    {"Cohésion racinaire": "12 kPa", "Surface reboisée": "500 M ha"},
                ],
                # Sylviculture des pentes: terraced + contour planting
                # on landslide-prone slopes.
                "Sylviculture des pentes": [
                    {"Pente maximale stabilisée": "20°", "Surface aménagée": "2 M ha"},
                    {"Pente maximale stabilisée": "35°", "Surface aménagée": "40 M ha"},
                    {"Pente maximale stabilisée": "50°", "Surface aménagée": "500 M ha"},
                ],
                # Agro-foresterie: tree-crop integration on agricultural
                # land — reduces erosion, anchors soil. UN-FAO scale.
                "Agro-foresterie": [
                    {"Arbres par hectare": "50", "Surface en agroforesterie": "10 M ha"},
                    {"Arbres par hectare": "200", "Surface en agroforesterie": "200 M ha"},
                    {"Arbres par hectare": "600", "Surface en agroforesterie": "1,5 Gha"},
                ],
            },
            "Transformation": {
                # Régénération géologique: deep-time restoration —
                # active rehabilitation of fault scarps, removal of
                # mining scars.
                "Régénération géologique": [
                    {"Failles réhabilitées": "100 km", "Cicatrisation à 50 ans": "30 %"},
                    {"Failles réhabilitées": "5 000 km", "Cicatrisation à 50 ans": "70 %"},
                    {"Failles réhabilitées": "100 000 km", "Cicatrisation à 50 ans": "95 %"},
                ],
                # Aménagement faillé: building IN fault zones with
                # zoning + adaptive design (analogous to wadi/floodplain
                # planning but for seismic).
                "Aménagement faillé": [
                    {"Zones réglementées": "10 000 km²", "Population sécurisée": "20 M"},
                    {"Zones réglementées": "200 000 km²", "Population sécurisée": "400 M"},
                    {"Zones réglementées": "2 M km²", "Population sécurisée": "4 Mds"},
                ],
                # Civilisation tectonique: full societal alignment with
                # plate dynamics — coastal mobility, vertical farming,
                # post-static urbanism.
                "Civilisation tectonique": [
                    {"Métropoles tectono-adaptées": "5", "Population concernée": "50 M"},
                    {"Métropoles tectono-adaptées": "60", "Population concernée": "800 M"},
                    {"Métropoles tectono-adaptées": "300", "Population concernée": "5 Mds"},
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

    print(f"Differentiated {touched} HUMANITÉ Terre skills "
          "(Intensité × 3 tiers + Impact Écologique × 3 tiers).")

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"Wrote {DATA}")


if __name__ == "__main__":
    main()
