"""Differentiate HUMANITÉ / Air / Intensité + Impact Écologique.

Same pattern as the Eau / Feu / Terre differentiation scripts —
completes two axes of HUMANITÉ Air (Intensité = direct wind /
pressure mitigation, Impact Écologique = atmospheric and climate
restoration) = 18 skills.

Real-world anchors used:
  * IBC / Eurocode 1 EN 1991-1-4: residential roofs are designed for
    ~110-180 km/h wind speeds; Miami-Dade NOA standards push to
    ~250 km/h.
  * Hedge/windbreak research (UN-FAO, INRA): a properly-shaped
    windbreak cuts downwind speed by 50-75 % over 10× its height.
  * Modern building aerodynamics (CFD-shaped towers, Burj Khalifa
    setbacks): cuts vortex-shedding force by 25-40 %.
  * 2015 Paris Agreement / IPCC SR15 references global atmospheric
    targets — CO₂ at 350-420 ppm, PM2.5 OMS guidelines at 5 µg/m³.
  * Stratospheric aerosol injection (SAI) studies: targeted 1-2 W/m²
    radiative offset at full scale (Smith & Wagner, 2018).

Run from repo root::

    python tools/differentiate_humanite_air.py
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path("gaia_ultimatum/data/skills_humanite.json")


FIXES = {
    "Air": {
        # -------------------------------------------------------- Intensité
        "Intensite": {
            "Fondations": {
                # Toitures renforcées: reinforced roofing. Modern codes
                # specify uplift resistance + min wind speed rating.
                "Toitures renforcées": [
                    {"Résistance au vent": "180 km/h", "Toitures certifiées": "30 %"},
                    {"Résistance au vent": "220 km/h", "Toitures certifiées": "65 %"},
                    {"Résistance au vent": "300 km/h", "Toitures certifiées": "95 %"},
                ],
                # Brise-vents: living + engineered windbreaks. Height +
                # cumulative km of installed barriers.
                "Brise-vents": [
                    {"Hauteur des brise-vents": "8 m", "Linéaire installé": "5 000 km"},
                    {"Hauteur des brise-vents": "15 m", "Linéaire installé": "60 000 km"},
                    {"Hauteur des brise-vents": "30 m", "Linéaire installé": "500 000 km"},
                ],
                # Maillages anti-vent: lattice / netting structures on
                # urban facades + temporary deployment during alerts.
                "Maillages anti-vent": [
                    {"Réduction de pression au sol": "20 %", "Surface équipée": "100 km²"},
                    {"Réduction de pression au sol": "45 %", "Surface équipée": "2 000 km²"},
                    {"Réduction de pression au sol": "75 %", "Surface équipée": "30 000 km²"},
                ],
            },
            "Amplification": {
                # Brise-vents étendus: regional windbreak networks
                # spanning multiple watersheds.
                "Brise-vents étendus": [
                    {"Linéaire connecté": "100 000 km", "Régions protégées": "20"},
                    {"Linéaire connecté": "1 M km", "Régions protégées": "200"},
                    {"Linéaire connecté": "5 M km", "Régions protégées": "1 500"},
                ],
                # Filets urbains: deployable urban storm netting +
                # debris-capture systems on critical districts.
                "Filets urbains": [
                    {"Vitesse de déploiement": "30 min", "Districts protégés": "200"},
                    {"Vitesse de déploiement": "10 min", "Districts protégés": "3 000"},
                    {"Vitesse de déploiement": "1 min", "Districts protégés": "25 000"},
                ],
                # Architecture aéro-dynamique: CFD-shaped towers that
                # cut vortex shedding force.
                "Architecture aéro-dynamique": [
                    {"Réduction de force aérodynamique": "25 %", "Tours optimisées": "500"},
                    {"Réduction de force aérodynamique": "40 %", "Tours optimisées": "8 000"},
                    {"Réduction de force aérodynamique": "60 %", "Tours optimisées": "100 000"},
                ],
            },
            "Transformation": {
                # Mailles atmosphériques: continent-spanning sensor +
                # actuator grids reading and tempering local turbulence.
                "Mailles atmosphériques": [
                    {"Surface couverte": "5 M km²", "Stations actives": "10 000"},
                    {"Surface couverte": "50 M km²", "Stations actives": "300 000"},
                    {"Surface couverte": "150 M km²", "Stations actives": "5 M"},
                ],
                # Régulation urbaine: city-wide microclimate control
                # via heat/wind cancellation arrays.
                "Régulation urbaine": [
                    {"Métropoles régulées": "15", "Réduction de pic de vent": "30 %"},
                    {"Métropoles régulées": "200", "Réduction de pic de vent": "55 %"},
                    {"Métropoles régulées": "1 500", "Réduction de pic de vent": "80 %"},
                ],
                # Cités carénées: cities engineered with a continuous
                # outer aerodynamic shell.
                "Cités carénées": [
                    {"Cités carénées": "5", "Population concernée": "50 M"},
                    {"Cités carénées": "80", "Population concernée": "1 Md"},
                    {"Cités carénées": "500", "Population concernée": "6 Mds"},
                ],
            },
        },
        # ------------------------------------------------ Impact Écologique
        "Impact Ecologique": {
            "Fondations": {
                # Reboisement coupe-vent: woodlands planted as barriers
                # to dominant wind. FAO Sahel Great Green Wall scale.
                "Reboisement coupe-vent": [
                    {"Surface reboisée": "5 000 ha", "Réduction du vent au sol": "40 %"},
                    {"Surface reboisée": "200 000 ha", "Réduction du vent au sol": "60 %"},
                    {"Surface reboisée": "8 M ha", "Réduction du vent au sol": "75 %"},
                ],
                # Haies bocagères: hedgerow networks. Real bocage
                # density: 100-200 m/ha; restoration target 250 m/ha.
                "Haies bocagères": [
                    {"Linéaire de haies": "100 000 km", "Densité": "50 m/ha"},
                    {"Linéaire de haies": "1 M km", "Densité": "150 m/ha"},
                    {"Linéaire de haies": "10 M km", "Densité": "300 m/ha"},
                ],
                # Couvert permanent: permanent ground cover (cover crops,
                # perennial pastures) reducing soil erosion + dust.
                "Couvert permanent": [
                    {"Surface en couvert permanent": "20 M ha", "Réduction des poussières": "30 %"},
                    {"Surface en couvert permanent": "300 M ha", "Réduction des poussières": "60 %"},
                    {"Surface en couvert permanent": "2 Gha", "Réduction des poussières": "85 %"},
                ],
            },
            "Amplification": {
                # Restauration des sols (Air-flavoured): organic-carbon
                # restoration that anchors particulates.
                "Restauration des sols": [
                    {"Carbone organique du sol": "2 % MO", "Surface restaurée": "30 M ha"},
                    {"Carbone organique du sol": "4 % MO", "Surface restaurée": "400 M ha"},
                    {"Carbone organique du sol": "7 % MO", "Surface restaurée": "3 Gha"},
                ],
                # Agroécologie: regenerative agriculture practices
                # eliminating wind-erosion and reducing GHG emissions.
                "Agroécologie": [
                    {"Surface en agroécologie": "50 M ha", "Réduction des émissions": "15 %"},
                    {"Surface en agroécologie": "500 M ha", "Réduction des émissions": "40 %"},
                    {"Surface en agroécologie": "3 Gha", "Réduction des émissions": "70 %"},
                ],
                # Carbone profond: deep / soil carbon sequestration.
                "Carbone profond": [
                    {"Capture annuelle": "1 Gt CO₂", "Profondeur de stockage": "1 m"},
                    {"Capture annuelle": "8 Gt CO₂", "Profondeur de stockage": "3 m"},
                    {"Capture annuelle": "20 Gt CO₂", "Profondeur de stockage": "10 m"},
                ],
            },
            "Transformation": {
                # Atmosphère stabilisée: integrated atmospheric chemistry
                # management — CO₂ + PM levels + ozone restoration.
                "Atmosphère stabilisée": [
                    {"CO₂ atmosphérique": "420 ppm", "PM2.5 moyen": "15 µg/m³"},
                    {"CO₂ atmosphérique": "380 ppm", "PM2.5 moyen": "8 µg/m³"},
                    {"CO₂ atmosphérique": "350 ppm", "PM2.5 moyen": "5 µg/m³"},
                ],
                # Géo-ingénierie douce: targeted, low-amplitude climate
                # interventions (marine cloud brightening, biochar at
                # scale, stratospheric albedo trims).
                "Géo-ingénierie douce": [
                    {"Forçage radiatif compensé": "0,2 W/m²", "Programmes actifs": "5"},
                    {"Forçage radiatif compensé": "0,8 W/m²", "Programmes actifs": "60"},
                    {"Forçage radiatif compensé": "1,5 W/m²", "Programmes actifs": "300"},
                ],
                # Climat dans les limites: end-state — climate within
                # Holocene-era bounds.
                "Climat dans les limites": [
                    {"Réchauffement global": "+1,8 °C", "Limites planétaires respectées": "5 / 9"},
                    {"Réchauffement global": "+1,4 °C", "Limites planétaires respectées": "7 / 9"},
                    {"Réchauffement global": "+1,0 °C", "Limites planétaires respectées": "9 / 9"},
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

    print(f"Differentiated {touched} HUMANITÉ Air skills "
          "(Intensité × 3 tiers + Impact Écologique × 3 tiers).")

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"Wrote {DATA}")


if __name__ == "__main__":
    main()
