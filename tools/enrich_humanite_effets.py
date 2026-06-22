"""Rewrite the ``Effet`` block of every human skill with concrete units.

Background
==========
``data/skills.json`` (Gaia) carries each skill level with physically
grounded values — ``"Rayon d'action": "10 km"``, ``"Force d'impact":
"500 N"``, ``"Vitesse de propagation": "15 km/h"``. The aperçu tab in the
skill tree reads these straight from the JSON so the player sees
educational, real-world magnitudes.

``data/skills_humanite.json`` shipped with placeholder values that gave
no information back to the player::

    "Effet": {
      "Couverture": "+10 %",
      "Coût opération": "faible"
    }

Every one of the 540 ``Effet`` blocks in the file was a permutation of
the same three percentages and three intensity words. The aperçu tab
ended up looking generic on the Humanité side.

What this script does
=====================
For each ``(Catastrophe, Type)`` pair (20 combos), it defines a template
with two real-world educational fields. Per ``(Tier, Niveau)`` it picks
the right magnitude from a scale and writes it back into the JSON. The
result: every skill level shows the player a credible engineering /
public-health number tied to the actual mechanism (digue height +
people protected, magnitude resisted + buildings reinforced, vaccine
efficacy + doses produced, etc.).

Run with::

    python tools/enrich_humanite_effets.py

The script is idempotent — re-running produces the same JSON.
"""

from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills_humanite.json"

TIERS = ("Fondations", "Amplification", "Transformation")
NIVEAUX = ("Niveau 1", "Niveau 2", "Niveau 3")

# Template per (Catastrophe, Type). Each is a dict mapping field labels
# to a 9-slot value list ordered (Fondations-N1, F-N2, F-N3, Dev-N1,
# Dev-N2, Dev-N3, Avancees-N1, A-N2, A-N3). Real-world magnitudes are
# spread over five orders of magnitude so the player sees a credible
# trajectory from "small local works" to "civilisation-scale
# infrastructure".
TEMPLATES: dict[tuple[str, str], dict[str, list[str]]] = {
    # ---------------------------------------------------------------- EAU
    ("Eau", "Intensite"): {
        "Hauteur de digue": [
            "1,5 m", "2,5 m", "4 m",
            "6 m", "9 m", "12 m",
            "18 m", "25 m", "35 m",
        ],
        "Population protégée": [
            "50 000", "120 000", "300 000",
            "800 000", "2 M", "5 M",
            "15 M", "50 M", "200 M",
        ],
    },
    ("Eau", "Portee"): {
        "Portée d'action": [
            "20 km", "40 km", "80 km",
            "150 km", "300 km", "600 km",
            "1 200 km", "2 500 km", "5 000 km",
        ],
        "Débit dérivé": [
            "100 m³/s", "250 m³/s", "600 m³/s",
            "1 500 m³/s", "3 500 m³/s", "8 000 m³/s",
            "20 000 m³/s", "50 000 m³/s", "120 000 m³/s",
        ],
    },
    ("Eau", "Duree"): {
        "Réserve potable": [
            "10 j", "20 j", "40 j",
            "90 j", "180 j", "1 an",
            "2 ans", "5 ans", "10 ans",
        ],
        "Bénéficiaires": [
            "10 000", "30 000", "80 000",
            "200 000", "600 000", "2 M",
            "8 M", "30 M", "100 M",
        ],
    },
    ("Eau", "Impact Ecologique"): {
        "Surface restaurée": [
            "200 ha", "500 ha", "1 200 ha",
            "5 000 ha", "15 000 ha", "50 000 ha",
            "200 000 ha", "1 M ha", "5 M ha",
        ],
        "Horizon": [
            "5 ans", "10 ans", "20 ans",
            "30 ans", "50 ans", "75 ans",
            "1 siècle", "2 siècles", "5 siècles",
        ],
    },
    # ---------------------------------------------------------------- FEU
    ("Feu", "Intensite"): {
        "Périmètre traité": [
            "5 ha/h", "12 ha/h", "30 ha/h",
            "80 ha/h", "200 ha/h", "500 ha/h",
            "1 500 ha/h", "5 000 ha/h", "20 000 ha/h",
        ],
        "Délai d'extinction": [
            "45 min", "25 min", "15 min",
            "8 min", "4 min", "2 min",
            "60 s", "20 s", "5 s",
        ],
    },
    ("Feu", "Portee"): {
        "Couverture": [
            "20 km²", "50 km²", "150 km²",
            "500 km²", "1 500 km²", "5 000 km²",
            "20 000 km²", "100 000 km²", "1 M km²",
        ],
        "Délai de détection": [
            "30 min", "15 min", "8 min",
            "4 min", "2 min", "60 s",
            "20 s", "8 s", "3 s",
        ],
    },
    ("Feu", "Duree"): {
        "Air respirable": [
            "200 m³/h", "500 m³/h", "1 200 m³/h",
            "3 000 m³/h", "8 000 m³/h", "20 000 m³/h",
            "60 000 m³/h", "200 000 m³/h", "1 M m³/h",
        ],
        "Autonomie": [
            "12 h", "24 h", "48 h",
            "5 j", "10 j", "20 j",
            "60 j", "180 j", "1 an",
        ],
    },
    ("Feu", "Impact Ecologique"): {
        "Surface boisée": [
            "100 ha", "250 ha", "600 ha",
            "2 000 ha", "6 000 ha", "20 000 ha",
            "80 000 ha", "500 000 ha", "3 M ha",
        ],
        "Espèces plantées": [
            "5", "10", "20",
            "40", "80", "150",
            "300", "600", "1 200",
        ],
    },
    # -------------------------------------------------------------- TERRE
    ("Terre", "Intensite"): {
        "Magnitude résistée": [
            "5,0", "5,5", "6,0",
            "6,5", "7,0", "7,5",
            "8,0", "8,5", "9,0",
        ],
        "Bâtiments renforcés": [
            "100", "300", "1 000",
            "3 000", "10 000", "30 000",
            "100 000", "300 000", "1 M",
        ],
    },
    ("Terre", "Portee"): {
        "Préavis sismique": [
            "5 s", "10 s", "20 s",
            "45 s", "90 s", "3 min",
            "8 min", "20 min", "1 h",
        ],
        "Capteurs déployés": [
            "50", "120", "300",
            "800", "2 500", "8 000",
            "25 000", "80 000", "250 000",
        ],
    },
    ("Terre", "Duree"): {
        "Capacité d'accueil": [
            "1 000", "2 500", "6 000",
            "15 000", "40 000", "100 000",
            "300 000", "1 M", "3 M",
        ],
        "Autonomie": [
            "72 h", "7 j", "14 j",
            "30 j", "60 j", "120 j",
            "1 an", "3 ans", "10 ans",
        ],
    },
    ("Terre", "Impact Ecologique"): {
        "Surface stabilisée": [
            "100 ha", "300 ha", "800 ha",
            "2 500 ha", "8 000 ha", "25 000 ha",
            "100 000 ha", "500 000 ha", "2 M ha",
        ],
        "Profondeur racinaire": [
            "1,5 m", "2 m", "3 m",
            "4 m", "6 m", "9 m",
            "12 m", "18 m", "25 m",
        ],
    },
    # ----------------------------------------------------------------- AIR
    ("Air", "Intensite"): {
        "Vent résisté": [
            "120 km/h", "150 km/h", "180 km/h",
            "210 km/h", "250 km/h", "300 km/h",
            "350 km/h", "400 km/h", "450 km/h",
        ],
        "Toits protégés": [
            "500", "1 500", "5 000",
            "15 000", "50 000", "150 000",
            "500 000", "1,5 M", "5 M",
        ],
    },
    ("Air", "Portee"): {
        "Préavis météo": [
            "6 h", "12 h", "24 h",
            "48 h", "96 h", "7 j",
            "14 j", "21 j", "30 j",
        ],
        "Couverture": [
            "1 ville", "10 villes", "1 région",
            "1 pays", "1 continent", "2 continents",
            "monde", "monde + océans", "planète intégrale",
        ],
    },
    ("Air", "Duree"): {
        "Refuges": [
            "10", "30", "80",
            "200", "600", "2 000",
            "8 000", "30 000", "120 000",
        ],
        "Autonomie": [
            "24 h", "48 h", "5 j",
            "10 j", "20 j", "45 j",
            "90 j", "180 j", "1 an",
        ],
    },
    ("Air", "Impact Ecologique"): {
        "Haies plantées": [
            "10 km", "30 km", "80 km",
            "200 km", "600 km", "2 000 km",
            "8 000 km", "30 000 km", "120 000 km",
        ],
        "Carbone capturé": [
            "100 t/an", "300 t/an", "1 000 t/an",
            "5 000 t/an", "20 000 t/an", "100 000 t/an",
            "500 000 t/an", "5 Mt/an", "50 Mt/an",
        ],
    },
    # ----------------------------------------------------------------- VIE
    ("Vie", "Intensite"): {
        "Efficacité vaccinale": [
            "55 %", "65 %", "72 %",
            "80 %", "86 %", "90 %",
            "94 %", "97 %", "99 %",
        ],
        "Doses produites": [
            "1 M", "3 M", "10 M",
            "30 M", "100 M", "300 M",
            "1 Md", "3 Md", "8 Md",
        ],
    },
    ("Vie", "Portee"): {
        "R0 réduit de": [
            "0,2", "0,4", "0,7",
            "1,0", "1,4", "1,8",
            "2,2", "2,7", "3,2",
        ],
        "Suivi de contacts": [
            "100/j", "500/j", "2 000/j",
            "10 000/j", "50 000/j", "200 000/j",
            "1 M/j", "5 M/j", "20 M/j",
        ],
    },
    ("Vie", "Duree"): {
        "Stock médical": [
            "1 mois", "3 mois", "6 mois",
            "1 an", "2 ans", "5 ans",
            "10 ans", "25 ans", "50 ans",
        ],
        "Bénéficiaires": [
            "10 000", "50 000", "200 000",
            "1 M", "5 M", "30 M",
            "200 M", "1 Md", "8 Md",
        ],
    },
    ("Vie", "Impact Ecologique"): {
        "Espèces préservées": [
            "10", "30", "100",
            "300", "1 000", "3 000",
            "10 000", "30 000", "100 000",
        ],
        "Aires protégées": [
            "100 km²", "500 km²", "2 000 km²",
            "10 000 km²", "50 000 km²", "200 000 km²",
            "1 M km²", "5 M km²", "20 M km²",
        ],
    },
}


def _slot_index(tier: str, niveau: str) -> int:
    """Map (tier, niveau) to the 0-8 slot in the value list."""
    tier_offset = TIERS.index(tier) * 3
    niveau_offset = NIVEAUX.index(niveau)
    return tier_offset + niveau_offset


def _build_effet(
    catastrophe: str, type_name: str, tier: str, niveau: str,
) -> "OrderedDict[str, str]":
    key = (catastrophe, type_name)
    template = TEMPLATES.get(key)
    if template is None:
        # Unknown combo — preserve old Effet by returning empty (caller skips).
        return OrderedDict()
    idx = _slot_index(tier, niveau)
    out: OrderedDict[str, str] = OrderedDict()
    for label, values in template.items():
        if idx < len(values):
            out[label] = values[idx]
    return out


def main() -> None:
    text = SKILLS_PATH.read_text(encoding="utf-8")
    data = json.loads(text, object_pairs_hook=OrderedDict)
    touched = 0
    skipped = 0
    for cat in data["humanite_catastrophes"]:
        catastrophe = cat["Catastrophe"]
        for type_name, type_block in cat["Types"].items():
            for tier_name, tier_block in type_block["Niveaux"].items():
                for skill in tier_block["Competences"]:
                    for niveau_name, niveau_block in skill["Niveaux"].items():
                        new_effet = _build_effet(
                            catastrophe, type_name, tier_name, niveau_name,
                        )
                        if not new_effet:
                            skipped += 1
                            continue
                        niveau_block["Effet"] = new_effet
                        touched += 1
    SKILLS_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Rewrote {touched} Effet blocks ({skipped} skipped)")


if __name__ == "__main__":
    main()
