"""Vie CATASTROPHE name + prereq rework for lambda-user clarity.

Vie's names are mostly already understandable thanks to widespread
post-COVID epidemiology vocabulary (Cas Index, Transmission
Communautaire, Croissance Exponentielle, Variants, etc.). The
rework retires the remaining biology jargon — Adaptation à l'Hôte,
Échappement Immunitaire, Dérive Antigénique, Homogénéisation Biotique
— and position-aligns every chain so each Ampl[i] requires Fond[i]
and each Trans[i] requires Ampl[i].

Run from repo root::

    python tools/rework_vie_catastrophe.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"


RENAMES = {
    # Intensité — replace "host adaptation" / "immune escape" with concrete subjects
    "Adaptation à l'Hôte": "Pathogène Adapté",
    "Échappement Immunitaire": "Résistance aux Vaccins",
    # Durée — drop influenza-vaccine jargon
    "Dérive Antigénique": "Mutations Continues",
    # Impact Écologique — drop ecology jargon
    "Altération des Cycles Biologiques": "Cycles du Vivant Perturbés",
    "Rupture Trophique": "Chaînes Alimentaires Brisées",
    "Effondrement Trophique": "Réseau Alimentaire Effondré",
    "Homogénéisation Biotique": "Vivant Uniformisé",
}

PREREQ_REWRITES = {
    # === Intensité ===
    ("Intensite", "Croissance Exponentielle"): "Cas Index (Niveau 1)",
    ("Intensite", "Réseau de Transmission"): "Transmission Communautaire (Niveau 1)",
    ("Intensite", "Variant Virulent"): "Mutation Virale (Niveau 1)",
    ("Intensite", "Co-Infection"): "Croissance Exponentielle (Niveau 2)",  # drop +Réseau de Transmission
    ("Intensite", "Pathogène Adapté"): "Réseau de Transmission (Niveau 2)",
    ("Intensite", "Résistance aux Vaccins"): "Variant Virulent (Niveau 2)",
    # === Portée ===
    ("Portee", "Épidémie Régionale"): "Foyer Épidémique (Niveau 1)",
    ("Portee", "Épidémie Continentale"): "Diffusion Territoriale (Niveau 1)",
    ("Portee", "Transmission Interhumaine"): "Variants Locaux (Niveau 1)",
    ("Portee", "Variants Mondiaux"): "Épidémie Continentale (Niveau 2)",
    ("Portee", "Diffusion Transcontinentale"): "Transmission Interhumaine (Niveau 2)",
    # === Durée ===
    ("Duree", "Épidémie Prolongée"): "Transmission Asymptomatique (Niveau 1)",
    ("Duree", "Réservoir Pathogène"): "Endémie (Niveau 1)",
    ("Duree", "Saisonnalité Épidémique"): "Vagues Épidémiques (Niveau 2)",
    ("Duree", "Mutations Continues"): "Réservoir Pathogène (Niveau 2)",
    # === Impact Écologique ===
    ("Impact Ecologique", "Chaînes Alimentaires Brisées"): "Cycles du Vivant Perturbés (Niveau 1)",
    ("Impact Ecologique", "Réseau Alimentaire Effondré"): "Épidémie Végétale (Niveau 2)",
    ("Impact Ecologique", "Déplacement des Biomes"): "Effondrement des Rendements (Niveau 2)",
    ("Impact Ecologique", "Vivant Uniformisé"): "Chaînes Alimentaires Brisées (Niveau 2)",
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    vie = next(c for c in data["catastrophes"] if c["Catastrophe"] == "Vie")

    n_nom = n_pre_auto = 0
    for ax in vie["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                if sk["Nom"] in RENAMES:
                    sk["Nom"] = RENAMES[sk["Nom"]]
                    n_nom += 1
                pre = sk.get("Prerequis", "")
                if not pre or pre == "Aucun":
                    continue
                new = pre
                for old in sorted(RENAMES, key=len, reverse=True):
                    new = re.sub(rf"\b{re.escape(old)}\b", RENAMES[old], new)
                if new != pre:
                    sk["Prerequis"] = new
                    n_pre_auto += 1

    n_pre = 0
    for ax_name, ax in vie["Types"].items():
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
    vie = next(c for c in reloaded["catastrophes"] if c["Catastrophe"] == "Vie")
    kept = set()
    for ax in vie["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                kept.add(sk["Nom"])
    broken = []
    for ax_name, ax in vie["Types"].items():
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

    print("\n=== Final Vie catastrophe chains ===")
    for ax_name, ax in vie["Types"].items():
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
        print("\nAll Vie prereqs resolve.")


if __name__ == "__main__":
    main()
