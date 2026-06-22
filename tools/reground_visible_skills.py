"""Reground visible skills across both JSONs with realistic / educational metrics.

Targeted refinements — only the *visible* (first 3 per tier) skills, since
the renderer's ``tier.skills[:3]`` cap is what the player sees. Hidden
ranks are left untouched to avoid scope creep.

Fixes by file:

  ``skills.json`` (GAIA side):
    1. Feu / Intensité / Fondations / **Étincelle Primale** — was
       500/1000/1500 °C at the *spark / Fondations* tier. A spark is a
       sub-second event in the 600-800 °C range; sustained kilo-celsius
       belongs to crown-fire territory. Walked back to 350/550/750 °C.
    2. Feu / Intensité / Transformation / **Feu Symbiotique** — was
       1000/2000/3000 °C. 3000 °C is plasma / arc-welder. Crown fire
       physics caps near 1100 °C. Walked back to 900/1000/1100 °C.
    3. Feu / Intensité / Transformation / **Métamorphose Ardente** —
       was 1500/2500/3500 °C. 3500 °C is oxyacetylene torch flame.
       Same cap, plus added a "Surface affectée" scale that grows with
       tier instead of one immobile metric.
    4. Eau wave skills — **Vague Initiale**, **Marée Destructrice**,
       **Tsunami Composite** — had "Force d'impact" in Newtons
       (500-4000 N). 500 N is a person's body weight, not a wave's
       impact. Real wave hydrodynamic pressure is measured in kPa
       (10s to 100s of kPa for storm surge, > 1 MPa for tsunami run-up).
       Replaced with "Pression dynamique" in kPa at realistic values.
    5. Eau / Intensité / Transformation / **Réseau Hydrodynamique** —
       "Force des courants" 2000-4000 N → "Pression dynamique" in kPa.
    6. Terre / Intensité / Transformation / **Subduction Dynamique** —
       Niveau 3 magnitude was 10.0. Moment magnitude tops out near 9.5
       (Chile 1960, the all-time record); a magnitude 10 would need a
       fault rupture longer than any tectonic plate. Capped at 9.5.

  ``skills_humanite.json`` (HUMANITÉ side):
    7. Eau / Intensité / Fondations — all three skills (**Digues
       primaires**, **Pluviales urbaines**, **Bassins de rétention**)
       had *identical* {"Hauteur de digue", "Population protégée"}
       blocks. That's structurally wrong: each skill represents a
       distinct adaptive mechanism (sea defence, urban runoff
       management, retention storage), so their metrics should be
       distinct too. Replaced each with the metric that actually
       characterises its mechanism.

Run from repo root::

    python tools/reground_visible_skills.py
"""

from __future__ import annotations

import json
from pathlib import Path

SKILLS = Path("gaia_ultimatum/data/skills.json")
HUMANITE = Path("gaia_ultimatum/data/skills_humanite.json")


# ---- GAIA side ------------------------------------------------------

GAIA_FIXES = {
    "Feu": {
        "Intensite": {
            "Fondations": {
                # Real spark / arc-source temperatures: 600-800 °C peak,
                # 200-400 °C at the early-ignition radius. The original
                # 500/1000/1500 °C oversold the *Fondations* tier — that
                # should be the seed of a fire, not a furnace.
                "Étincelle Primale": {
                    "Niveau 1": {
                        "Température d'amorçage": "350 °C",
                        "Rayon d'embrasement": "5 m",
                    },
                    "Niveau 2": {
                        "Température d'amorçage": "550 °C",
                        "Rayon d'embrasement": "10 m",
                    },
                    "Niveau 3": {
                        "Température d'amorçage": "750 °C",
                        "Rayon d'embrasement": "15 m",
                    },
                },
            },
            "Transformation": {
                # Crown fire physics ceiling ≈ 1100 °C. Anything above
                # belongs to industrial / acetylene / plasma sources,
                # not wildfire phenomenology.
                "Feu Symbiotique": {
                    "Niveau 1": {
                        "Hauteur des flammes": "20 m",
                        "Température au front": "900 °C",
                    },
                    "Niveau 2": {
                        "Hauteur des flammes": "30 m",
                        "Température au front": "1 000 °C",
                    },
                    "Niveau 3": {
                        "Hauteur des flammes": "40 m",
                        "Température au front": "1 100 °C",
                    },
                },
                "Métamorphose Ardente": {
                    "Niveau 1": {
                        "Température au front": "950 °C",
                        "Surface affectée": "500 m²",
                    },
                    "Niveau 2": {
                        "Température au front": "1 050 °C",
                        "Surface affectée": "1 000 m²",
                    },
                    "Niveau 3": {
                        "Température au front": "1 100 °C",
                        "Surface affectée": "1 500 m²",
                    },
                },
            },
        },
    },
    "Eau": {
        "Intensite": {
            "Fondations": {
                # Vague Initiale — storm surge / coastal wave dynamics.
                # Hydrodynamic pressure from a 3-5 m surge is 30-50 kPa
                # at the wall; published wave-impact tables (USACE
                # CEM, Cuomo et al.) put a 10-15 km/h moderate wave at
                # ≈ 15-25 kPa peak pressure on a vertical face.
                "Vague Initiale": {
                    "Niveau 1": {
                        "Rayon d'action": "10 km",
                        "Vitesse de propagation": "15 km/h",
                        "Pression dynamique": "15 kPa",
                    },
                    "Niveau 2": {
                        "Rayon d'action": "20 km",
                        "Vitesse de propagation": "25 km/h",
                        "Pression dynamique": "35 kPa",
                    },
                    "Niveau 3": {
                        "Rayon d'action": "30 km",
                        "Vitesse de propagation": "35 km/h",
                        "Pression dynamique": "60 kPa",
                    },
                },
            },
            "Amplification": {
                # Marée Destructrice — 5-15 m wave heights line up with
                # storm-surge / tsunami precursor zones. Pressure scales
                # roughly with ρ·g·h plus dynamic head from velocity.
                "Marée Destructrice": {
                    "Niveau 1": {
                        "Hauteur des vagues": "5 m",
                        "Vitesse de propagation": "20 km/h",
                        "Pression dynamique": "50 kPa",
                    },
                    "Niveau 2": {
                        "Hauteur des vagues": "10 m",
                        "Vitesse de propagation": "30 km/h",
                        "Pression dynamique": "120 kPa",
                    },
                    "Niveau 3": {
                        "Hauteur des vagues": "15 m",
                        "Vitesse de propagation": "40 km/h",
                        "Pression dynamique": "200 kPa",
                    },
                },
            },
            "Transformation": {
                # Tsunami Composite — full tsunami impact. Run-up
                # dynamic pressures on a vertical wall regularly hit
                # 200-500 kPa, with peak measurements > 1 MPa during
                # the 2011 Tōhoku event. We stay conservative.
                "Tsunami Composite": {
                    "Niveau 1": {
                        "Hauteur des vagues": "20 m",
                        "Vitesse de propagation": "50 km/h",
                        "Pression dynamique": "350 kPa",
                    },
                    "Niveau 2": {
                        "Hauteur des vagues": "30 m",
                        "Vitesse de propagation": "70 km/h",
                        "Pression dynamique": "600 kPa",
                    },
                    "Niveau 3": {
                        "Hauteur des vagues": "40 m",
                        "Vitesse de propagation": "90 km/h",
                        "Pression dynamique": "900 kPa",
                    },
                },
                "Réseau Hydrodynamique": {
                    "Niveau 1": {
                        "Vitesse des courants": "30 km/h",
                        "Pression dynamique": "40 kPa",
                        "Dégâts structurels": "40 %",
                    },
                    "Niveau 2": {
                        "Vitesse des courants": "50 km/h",
                        "Pression dynamique": "100 kPa",
                        "Dégâts structurels": "60 %",
                    },
                    "Niveau 3": {
                        "Vitesse des courants": "70 km/h",
                        "Pression dynamique": "200 kPa",
                        "Dégâts structurels": "80 %",
                    },
                },
            },
        },
    },
    "Terre": {
        "Intensite": {
            "Transformation": {
                # Moment magnitude ceiling ≈ 9.5 (Chile 1960). Going
                # higher would require a fault rupture longer than any
                # tectonic plate — geophysically impossible. Bumped
                # the Niveau 3 value back into the realistic ceiling.
                "Subduction Dynamique": {
                    "Niveau 1": {
                        "Magnitude": "7.0",
                        "Profondeur de subduction": "10 km",
                    },
                    "Niveau 2": {
                        "Magnitude": "8.2",
                        "Profondeur de subduction": "15 km",
                    },
                    "Niveau 3": {
                        "Magnitude": "9.5",
                        "Profondeur de subduction": "20 km",
                    },
                },
            },
        },
    },
}


# ---- HUMANITÉ side --------------------------------------------------

HUMANITE_FIXES = {
    "Eau": {
        "Intensite": {
            "Fondations": {
                # Digues primaires — sea-wall / river-dyke mechanism.
                # Realistic heights for primary urban dykes: 1.5-4 m
                # (Netherlands secondary dykes). "Hauteur de digue"
                # remains the right metric *for this skill*.
                "Digues primaires": {
                    "Niveau 1": {
                        "Hauteur de digue": "1,5 m",
                        "Population protégée": "50 000",
                    },
                    "Niveau 2": {
                        "Hauteur de digue": "2,5 m",
                        "Population protégée": "120 000",
                    },
                    "Niveau 3": {
                        "Hauteur de digue": "4 m",
                        "Population protégée": "300 000",
                    },
                },
                # Pluviales urbaines — urban storm-water network. Real
                # metric: drainage capacity in mm/h (or L/s/ha). A
                # well-designed system handles 30-50 mm/h ≈ a once-in-
                # 10-year urban storm; tier 3 with 80 mm/h matches a
                # 100-year design (rare but achievable, e.g. Tokyo's
                # G-Cans). Crucially DIFFERENT from "Hauteur de digue".
                "Pluviales urbaines": {
                    "Niveau 1": {
                        "Capacité de drainage": "30 mm/h",
                        "Population protégée": "60 000",
                    },
                    "Niveau 2": {
                        "Capacité de drainage": "55 mm/h",
                        "Population protégée": "150 000",
                    },
                    "Niveau 3": {
                        "Capacité de drainage": "80 mm/h",
                        "Population protégée": "350 000",
                    },
                },
                # Bassins de rétention — buffer storage volume. Real
                # metric: stockage retenu in m³ (or millions). A
                # mid-city retention basin holds ~10 000-50 000 m³;
                # large regional basins reach millions. Distinct
                # mechanism, distinct metric.
                "Bassins de rétention": {
                    "Niveau 1": {
                        "Volume stocké": "20 000 m³",
                        "Population protégée": "40 000",
                    },
                    "Niveau 2": {
                        "Volume stocké": "100 000 m³",
                        "Population protégée": "100 000",
                    },
                    "Niveau 3": {
                        "Volume stocké": "500 000 m³",
                        "Population protégée": "250 000",
                    },
                },
            },
        },
    },
}


def _apply_fixes(catastrophes_key: str, path: Path, fixes: dict) -> int:
    with open(path, "r", encoding="utf-8") as f:
        d = json.load(f)
    touched = 0
    for cat in d[catastrophes_key]:
        cat_fixes = fixes.get(cat["Catastrophe"])
        if not cat_fixes:
            continue
        for axis_name, axis_fixes in cat_fixes.items():
            axis = cat["Types"].get(axis_name)
            if not axis:
                continue
            for tier_name, tier_fixes in axis_fixes.items():
                tier = axis["Niveaux"].get(tier_name)
                if not tier:
                    continue
                for skill in tier["Competences"]:
                    spec = tier_fixes.get(skill["Nom"])
                    if not spec:
                        continue
                    for lvl_key, effet in spec.items():
                        skill["Niveaux"][lvl_key]["Effet"] = effet
                    touched += 1
    with open(path, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    return touched


def main() -> None:
    g = _apply_fixes("catastrophes", SKILLS, GAIA_FIXES)
    h = _apply_fixes("humanite_catastrophes", HUMANITE, HUMANITE_FIXES)
    print(f"GAIA      : regrounded {g} skills.")
    print(f"HUMANITÉ  : regrounded {h} skills.")
    print(f"Wrote     : {SKILLS}")
    print(f"          : {HUMANITE}")


if __name__ == "__main__":
    main()
