"""Rewrite skill descriptions that still reference renamed concepts.

After a chain of renames in skills.json (catastrophe side), a handful
of descriptions kept using the old terminology — most notably
'hydrophobe' (now 'Sols Imperméables'), 'dérécho' (now 'Tempête
Linéaire'), 'supercellule' (now 'Orages Géants Mondiaux'), and
'régime' phrasing (now 'Bourrasques Continues'). Rewrite those
sentences to match the new names so the description and the title
no longer disagree.

One stale-reference case is left untouched on purpose:
``Eau/Coups de Bélier`` still says "par à-coups, l'eau frappe avec
la violence d'un bélier" — that wordplay between "à-coups" and the
"bélier" metaphor is what justified the rename in the first place;
removing it would erase the link between the old phrasing players
might recognise and the new name.

Run from repo root::

    python tools/fix_stale_descriptions.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"


# (catastrophe, skill_name) → new description.
DESC_REWRITES = {
    ("Eau", "Saisons Déréglées"): (
        "Les rythmes du vivant se dérèglent. Migrations, reproductions "
        "et floraisons, calés depuis toujours sur l'eau et les saisons, "
        "se désaccordent et brisent des équilibres millénaires."
    ),
    ("Feu", "Sols Imperméables"): (
        "Sous la chaleur extrême, le sol devient imperméable et stérile. "
        "La pluie suivante, au lieu de nourrir, ruisselle et emporte "
        "tout : le feu prépare l'inondation et l'érosion."
    ),
    ("Air", "Tempête Linéaire"): (
        "Un front de vents en ligne droite parcourt des centaines de "
        "kilomètres. Cette tempête linéaire dévaste sur sa route comme "
        "une tornade allongée, laissant un sillage rectiligne de "
        "destruction."
    ),
    ("Air", "Orages Géants Mondiaux"): (
        "Des orages géants se forment partout dans le monde avec une "
        "fréquence inédite. L'orage géant devient un phénomène "
        "planétaire, témoin d'une énergie atmosphérique en hausse."
    ),
    ("Air", "Tempête Linéaire Continentale"): (
        "Des fronts de vents rectilignes balaient les continents. À "
        "l'échelle mondiale, la tempête linéaire devient un fléau "
        "récurrent traçant ses sillons sur toute la planète."
    ),
    ("Air", "Bourrasques Continues"): (
        "Les bourrasques se succèdent sans interruption. Cet "
        "enchaînement de vent soutenu et prolongé transforme un épisode "
        "passager en condition durable, multipliant les dégâts cumulés."
    ),
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    n = 0
    for cat in data["catastrophes"]:
        cat_name = cat["Catastrophe"]
        for ax in cat["Types"].values():
            for tier in ax["Niveaux"].values():
                for sk in tier["Competences"]:
                    key = (cat_name, sk["Nom"])
                    if key in DESC_REWRITES:
                        sk["Description"] = DESC_REWRITES[key]
                        n += 1

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Descriptions rewritten: {n}")
    print(f"Expected: {len(DESC_REWRITES)}")


if __name__ == "__main__":
    main()
