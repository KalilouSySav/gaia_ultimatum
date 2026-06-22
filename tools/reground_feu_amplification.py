"""Reground the 3 Feu Amplification fillers with realistic physical values.

The earlier ``fix_skill_reachability.py`` added one skill per Feu axis
to bring Intensité / Durée / Portée up to 3 visible competences (the
renderer's ``tier.skills[:3]`` cap). The placeholder physical values
were dimensionally awkward:

  - **Combustion Intensive**: ``Force d'impact`` in Newtons is not a
    fire-physics quantity (fires don't have impact force in the way
    tsunamis or quakes do). Temperatures peaked at 1 600 °C — that
    belongs to gasoline pools / aluminium melt, not wildfire. Real
    crown-fire temperatures top out around 1 100 °C.
  - **Combustion Latente Accrue**: 4 / 8 / 12 h reads as a normal
    flame, not the *latent* (smouldering ember / peat) regime it
    claims to be. Smouldering combustion of duff / peat sustains
    over days to weeks, not hours — the unit needs to climb.
  - **Vague Thermique**: ``Température au sol`` of 90-170 °C
    sustained over a 1-4 km radius is unphysical. Radiative
    preheat at that range raises ambient temperature by tens of
    degrees, not above water-boil. The metric should be
    ``Élévation thermique`` (rise above ambient) — the real
    pyrology measure that explains why fuels desiccate ahead of
    the flame front.

This script replaces the 3 skills' ``Niveaux[*].Effet`` blocks with
values grounded in actual wildfire science, keeping the existing
3-level structure and educational tone.
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path("gaia_ultimatum/data/skills.json")

REPLACEMENTS = {
    "Combustion Intensive": {
        "Description": (
            "Concentre la chaleur de combustion au cœur du foyer. La "
            "température au front de flamme grimpe et le flux radiatif "
            "augmente, ce qui rend l'incendie capable d'enflammer les "
            "matériaux structurels à distance."
        ),
        "Effets": {
            # Realistic wildfire flame-front temperatures: surface fires
            # average 600-800 °C, crown fires reach ~1 100 °C, sustained
            # peaks at 1 200 °C in extreme convection columns. Flux
            # radiatif: > 12 kW/m² is lethal to exposed skin, > 25 kW/m²
            # ignites wood at distance — these are the canonical NFPA /
            # ISO 13943 thresholds.
            "Niveau 1": {
                "Température au front": "600 °C",
                "Flux radiatif": "20 kW/m²",
            },
            "Niveau 2": {
                "Température au front": "900 °C",
                "Flux radiatif": "50 kW/m²",
            },
            "Niveau 3": {
                "Température au front": "1 100 °C",
                "Flux radiatif": "80 kW/m²",
            },
        },
    },
    "Combustion Latente Accrue": {
        "Description": (
            "Entretient une combustion sans flamme dans la litière, la "
            "tourbe et le bois mort. Les braises sub-superficielles "
            "couvent à 300-500 °C, parfois pendant des jours, et "
            "rallument le foyer à la moindre reprise de vent."
        ),
        "Effets": {
            # Real smouldering combustion of peat / duff sustains for
            # days to weeks at 300-500 °C below the surface. The famous
            # Indonesian peat fires of 1997 burned for ~6 months. Unit
            # shift from hours to days/weeks is intentional — it marks
            # this as the *latent* regime, distinct from the
            # active-flame "Brasier Prolongé" skill above.
            "Niveau 1": {
                "Durée de couvaison": "1 jour",
                "Profondeur de braise": "5 cm",
            },
            "Niveau 2": {
                "Durée de couvaison": "5 jours",
                "Profondeur de braise": "15 cm",
            },
            "Niveau 3": {
                "Durée de couvaison": "2 semaines",
                "Profondeur de braise": "30 cm",
            },
        },
    },
    "Vague Thermique": {
        "Description": (
            "Diffuse un front de chaleur radiative en avant des "
            "flammes. L'air et les combustibles se dessèchent par "
            "préchauffage, ce qui accélère l'embrasement quand le "
            "front atteint la zone."
        ),
        "Effets": {
            # Radiative preheat of a fire front: a megafire's
            # convection column raises ambient temperature by tens of
            # degrees up to several kilometres downwind (documented
            # during the 2017 Pacific NW and 2019-20 Australian
            # megafires). 1.5-4.5 km radius matches Brasier Régional's
            # scale; "Élévation thermique" (rise above ambient) is the
            # accurate metric — fuels with moisture below ~20 % ignite
            # readily, so a +50 °C lift over ambient brings most
            # vegetation into the ignitable range.
            "Niveau 1": {
                "Rayon de préchauffage": "1,5 km",
                "Élévation thermique": "+20 °C",
            },
            "Niveau 2": {
                "Rayon de préchauffage": "3 km",
                "Élévation thermique": "+35 °C",
            },
            "Niveau 3": {
                "Rayon de préchauffage": "4,5 km",
                "Élévation thermique": "+50 °C",
            },
        },
    },
}


def main() -> None:
    with open(DATA, "r", encoding="utf-8") as f:
        d = json.load(f)

    feu = next(c for c in d["catastrophes"] if c["Catastrophe"] == "Feu")
    touched = 0
    for axis in feu["Types"].values():
        for skill in axis["Niveaux"]["Amplification"]["Competences"]:
            spec = REPLACEMENTS.get(skill["Nom"])
            if spec is None:
                continue
            skill["Description"] = spec["Description"]
            for lvl_key, effet in spec["Effets"].items():
                skill["Niveaux"][lvl_key]["Effet"] = effet
            touched += 1

    print(f"Regrounded {touched}/3 Feu Amplification skills.")

    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"Wrote {DATA}")


if __name__ == "__main__":
    main()
