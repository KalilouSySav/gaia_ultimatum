"""One-shot Terre HUMANITÉ rename + prereq rework for lambda-user clarity.

The 4 Terre axes already had mostly thematically coherent chains (unlike
Feu, which needed 3-way cross-tier rotation). The rework here is mostly
**renames** — drop jargon-heavy terms like ``Confortement Parasismique``,
``Modélisation Sismique``, ``Zonage Sismique``, ``Génie Végétal`` —
plus the small number of prereq references that point at those names.

Run from repo root::

    python tools/rework_terre_humanite.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills_humanite.json"

# Old → new name map across all 4 Terre axes.
RENAMES = {
    # Intensité — concrete building actions instead of formal/civil-engineering terms
    "Confortement Parasismique": "Renforcement des Bâtiments",
    "Bâti Stratégique": "Bâtiments Prioritaires",
    "Plan de Prévention des Risques": "Plan Anti-Séisme",
    "Zonage Sismique": "Villes Anti-Séisme",
    # Portée — drop "sismomètres" / "modélisation" / "gouvernance" jargon
    "Réseau de Sismomètres": "Capteurs Sismiques",
    "Modélisation Sismique": "Simulations Sismiques",
    "Gouvernance du Risque Sismique": "Coordination Mondiale",
    # Durée — direct verbs and concrete subjects
    "Réhabilitation Post-Sismique": "Reconstruction Rapide",
    "Résilience Communautaire": "Communautés Résilientes",
    # Impact Écologique — drop bioengineering jargon
    "Génie Végétal": "Plantes Stabilisatrices",
    "Réhabilitation des Sols": "Sols Restaurés",
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    terre = next(c for c in data["humanite_catastrophes"] if c["Catastrophe"] == "Terre")

    n_nom = 0
    n_prereq = 0
    for ax in terre["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                if sk["Nom"] in RENAMES:
                    sk["Nom"] = RENAMES[sk["Nom"]]
                    n_nom += 1
                pre = sk.get("Prerequis", "")
                for old, new in RENAMES.items():
                    if pre == f"{old} Niveau 1":
                        sk["Prerequis"] = f"{new} Niveau 1"
                        n_prereq += 1
                        break

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Validate
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    terre = next(c for c in reloaded["humanite_catastrophes"] if c["Catastrophe"] == "Terre")
    all_names = set()
    for ax in terre["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                all_names.add(sk["Nom"])
    broken = []
    for ax_name, ax in terre["Types"].items():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                pre = sk.get("Prerequis", "")
                if pre == "Aucun":
                    continue
                nm = pre.rsplit(" Niveau ", 1)[0] if " Niveau " in pre else pre
                if nm not in all_names:
                    broken.append((ax_name, sk["Nom"], pre))

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Renamed Nom entries: {n_nom}")
    print(f"Updated Prerequis references: {n_prereq}")

    print("\n=== Final Terre chains ===")
    for ax_name, ax in terre["Types"].items():
        print(f"\n  [{ax_name}]")
        tiers = list(ax["Niveaux"].items())
        for chain_i in range(3):
            chain = []
            for _, tier in tiers:
                if chain_i < len(tier["Competences"]):
                    chain.append(tier["Competences"][chain_i]["Nom"])
            print(f"    Chain {chain_i+1}: {' -> '.join(chain)}")

    if broken:
        print("\nBROKEN PREREQS:")
        for b in broken:
            print(f"  {b}")
    else:
        print("\nAll Terre prereqs resolve.")


if __name__ == "__main__":
    main()
