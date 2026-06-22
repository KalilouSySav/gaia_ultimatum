"""Air CATASTROPHE name + prereq rework for lambda-user clarity.

Air's chains were the most-tangled: Intensité, Portée, and Durée all
have repeating fond-themes (windstorm / cyclone / tornado-shear)
across tiers, but the original prereqs criss-crossed those themes
instead of staying on a single chain. Impact Écologique pulled prereqs
from other axes entirely (cross-axis ``Vent Local Violent`` etc.).

This rework:
  * Retires meteorology jargon — "Cisaillement", "Synoptique",
    "Dérécho", "Cyclogenèse", "Anémochorie", and the long
    "Supercellules Généralisées" / "Régime de Bourrasques" labels —
    for everyday French.
  * Position-aligns every Ampl[i]/Trans[i] so each three-chain reads
    as one mono-thematic escalation arc (windstorm / cyclone /
    tornado-shear).
  * Eliminates cross-axis prereqs in Impact Écologique (each Ampl
    now requires the Impact Eco Fond at its own position).

Run from repo root::

    python tools/rework_air_catastrophe.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"


RENAMES = {
    # Intensité
    "Cisaillement du Vent": "Vents Tournants",
    "Tempête Synoptique": "Grosse Tempête",
    "Dérécho": "Tempête Linéaire",
    # Portée
    "Cisaillement Régional": "Vents Tournants Régionaux",
    "Cyclogenèse Mondiale": "Tempêtes Mondiales",
    "Supercellules Généralisées": "Orages Géants Mondiaux",
    "Dérécho Continental": "Tempête Linéaire Continentale",
    # Durée
    "Régime de Bourrasques": "Bourrasques Continues",
    "Cisaillement Persistant": "Vents Tournants Continus",
    "Cyclogenèse Persistante": "Tempêtes Sans Fin",
    "Supercellule Régénérative": "Orage Géant Cyclique",
    "Dérécho Prolongé": "Tempête Linéaire Persistante",
    # Impact Écologique
    "Anémochorie": "Graines Emportées",
    "Habitats Pionniers": "Nouveaux Milieux",
}

PREREQ_REWRITES = {
    # === Intensité ===
    ("Intensite", "Grosse Tempête"): "Rafale de Vent (Niveau 1)",
    ("Intensite", "Cyclone Tropical"): "Grain Orageux (Niveau 1)",
    ("Intensite", "Tornade"): "Vents Tournants (Niveau 1)",
    ("Intensite", "Cyclone Explosif"): "Grosse Tempête (Niveau 2)",
    ("Intensite", "Supercellule"): "Cyclone Tropical (Niveau 2)",
    ("Intensite", "Tempête Linéaire"): "Tornade (Niveau 2)",
    # === Portée ===
    ("Portee", "Système Dépressionnaire"): "Vent Local Violent (Niveau 1)",
    ("Portee", "Cyclone de Grande Taille"): "Vent Régional (Niveau 1)",
    ("Portee", "Tornade Majeure"): "Vents Tournants Régionaux (Niveau 1)",
    ("Portee", "Tempêtes Mondiales"): "Système Dépressionnaire (Niveau 2)",
    ("Portee", "Orages Géants Mondiaux"): "Cyclone de Grande Taille (Niveau 2)",
    ("Portee", "Tempête Linéaire Continentale"): "Tornade Majeure (Niveau 2)",
    # === Durée ===
    ("Duree", "Tempête Stationnaire"): "Vent Soutenu (Niveau 1)",
    ("Duree", "Cyclone Stationnaire"): "Bourrasques Continues (Niveau 1)",
    ("Duree", "Tornade de Longue Trace"): "Vents Tournants Continus (Niveau 1)",
    ("Duree", "Tempêtes Sans Fin"): "Tempête Stationnaire (Niveau 2)",
    ("Duree", "Orage Géant Cyclique"): "Cyclone Stationnaire (Niveau 2)",
    ("Duree", "Tempête Linéaire Persistante"): "Tornade de Longue Trace (Niveau 2)",
    # === Impact Écologique ===
    ("Impact Ecologique", "Tempête de Sable"): "Chablis (Niveau 1)",
    ("Impact Ecologique", "Tempête de Poussière"): "Érosion Éolienne (Niveau 1)",
    ("Impact Ecologique", "Projection de Débris"): "Graines Emportées (Niveau 1)",
    ("Impact Ecologique", "Altération du Littoral"): "Tempête de Sable (Niveau 2)",
    ("Impact Ecologique", "Nouveaux Milieux"): "Tempête de Poussière (Niveau 2)",
    ("Impact Ecologique", "Dérèglement Climatique"): "Projection de Débris (Niveau 2)",
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    air = next(c for c in data["catastrophes"] if c["Catastrophe"] == "Air")

    n_nom = n_pre_auto = 0
    for ax in air["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                if sk["Nom"] in RENAMES:
                    sk["Nom"] = RENAMES[sk["Nom"]]
                    n_nom += 1
                pre = sk.get("Prerequis", "")
                if not pre or pre == "Aucun":
                    continue
                new = pre
                # Apply longest-first to avoid prefix collisions
                # ("Cisaillement Régional" contains "Cisaillement")
                for old in sorted(RENAMES, key=len, reverse=True):
                    new = re.sub(rf"\b{re.escape(old)}\b", RENAMES[old], new)
                if new != pre:
                    sk["Prerequis"] = new
                    n_pre_auto += 1

    n_pre = 0
    for ax_name, ax in air["Types"].items():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                key = (ax_name, sk["Nom"])
                if key in PREREQ_REWRITES:
                    sk["Prerequis"] = PREREQ_REWRITES[key]
                    n_pre += 1

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    air = next(c for c in reloaded["catastrophes"] if c["Catastrophe"] == "Air")
    kept = set()
    for ax in air["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                kept.add(sk["Nom"])
    broken = []
    for ax_name, ax in air["Types"].items():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                pre = sk.get("Prerequis", "")
                if pre == "Aucun":
                    continue
                for token in re.split(r"\s*\+\s*", pre):
                    m = re.match(r"^(.+?) \(Niveau \d+\)$", token.strip())
                    if not m:
                        continue
                    if m.group(1) not in kept:
                        broken.append((ax_name, sk["Nom"], token))

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Renamed Nom entries: {n_nom}")
    print(f"Auto-updated prereqs: {n_pre_auto}")
    print(f"Explicit prereq rewrites: {n_pre}")

    print("\n=== Final Air catastrophe chains ===")
    for ax_name, ax in air["Types"].items():
        print(f"\n  [{ax_name}]")
        tiers = list(ax["Niveaux"].items())
        for chain_i in range(3):
            chain = []
            prereqs = []
            for _, tier in tiers:
                if chain_i < len(tier["Competences"]):
                    sk = tier["Competences"][chain_i]
                    chain.append(sk["Nom"])
                    pre = sk.get("Prerequis", "")
                    prereqs.append(pre if pre != "Aucun" else "—")
            print(f"    Chain {chain_i+1}: {' -> '.join(chain)}")
            print(f"             prereqs: {' | '.join(prereqs)}")

    if broken:
        print("\nBROKEN PREREQS:")
        for b in broken:
            print(f"  {b}")
    else:
        print("\nAll Air prereqs resolve.")


if __name__ == "__main__":
    main()
