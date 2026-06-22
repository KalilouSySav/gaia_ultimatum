"""Feu CATASTROPHE name + prereq rework for lambda-user clarity.

Two passes:

1. **Renames** — retire combustion/atmosphere jargon (Pyrolyse Totale,
   Couplage Feu-Atmosphère, Préchauffage Radiatif, Aérosols de
   Combustion, the three ``Régime de Feu …`` variants, ``Rétroaction
   Feu-Climat``, ``Sol Hydrophobe``, etc.) for concrete everyday
   French.

2. **Prereq position-alignment** — Feu's chains carry several
   cross-chain and cross-axis prereqs (e.g. Pyrocumulonimbus pointed
   at Tempête de Feu which is the chain-1 Ampl, but Pyrocumulonimbus
   sits at chain-3 Trans). Also simplify multi-target prereqs
   (``A + B``) by dropping cross-axis branches so each Trans has one
   evident precursor.

Run from repo root::

    python tools/rework_feu_catastrophe.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"


RENAMES = {
    # Intensité — combustion-physics jargon → concrete
    "Pyrolyse Totale": "Fournaise Totale",
    "Couplage Feu-Atmosphère": "Feu et Vent Alliés",
    # Portée — radiative-physics jargon → concrete
    "Préchauffage Radiatif": "Chaleur Anticipée",
    "Aérosols de Combustion": "Fumées Mondiales",
    "Régime de Méga-Feux": "Méga-Feux Permanents",
    # Durée — "Régime de …" / "Rétroaction" jargon → concrete
    "Combustion Couvante": "Feu qui Couve",
    "Régime de Feu Récurrent": "Feux Saisonniers",
    "Régime de Feu Altéré": "Cycle de Feu Dégradé",
    "Rétroaction Feu-Climat": "Cercle Vicieux Feu-Climat",
    # Impact Écologique — soil-chemistry jargon → concrete
    "Sol Hydrophobe": "Sols Imperméables",
    "Érosion de la Biodiversité": "Biodiversité Effondrée",
}

# Per-axis prereq rewrites. Each (axis, skill_name) → new prereq string.
# Goal: each Ampl[i] requires Fond[i] (position-aligned), each Trans[i]
# requires Ampl[i] (position-aligned). Cross-axis '+' branches simplified
# to single-target.
PREREQ_REWRITES = {
    # === Intensité ===
    ("Intensite", "Tempête de Feu"): "Départ de Feu (Niveau 2)",          # was Rayonnement Thermique
    ("Intensite", "Feu de Cime"): "Combustion Vive (Niveau 1)",            # was Tempête de Feu
    ("Intensite", "Fournaise Totale"): "Rayonnement Thermique (Niveau 1)", # was Combustion Vive (renamed Pyrolyse)
    ("Intensite", "Pyrocumulonimbus"): "Fournaise Totale (Niveau 2)",      # was Tempête de Feu — chain 3
    # === Portée ===
    ("Portee", "Méga-Feu"): "Foyer Localisé (Niveau 2)",                   # was Sautes de Feu
    ("Portee", "Tourbillon de Feu"): "Sautes de Feu (Niveau 1)",           # was Foyer Localisé
    ("Portee", "Fumées Mondiales"): "Tourbillon de Feu (Niveau 2)",        # was Feu de Cime cross-axis
    ("Portee", "Méga-Feux Permanents"): "Vague de Chaleur (Niveau 2)",     # was Feux Continentaux cross-chain
    # === Durée ===
    ("Duree", "Incendie Prolongé"): "Reprise de Feu (Niveau 1)",           # was Combustion Couvante
    ("Duree", "Cycle de Feu Dégradé"): "Incendie Prolongé (Niveau 2)",     # drop +Tempête de Feu cross-axis
    ("Duree", "Cercle Vicieux Feu-Climat"): "Feux Saisonniers (Niveau 2)", # was Incendie Prolongé — chain 2
    ("Duree", "Feu Endémique"): "Feu de Tourbe (Niveau 2)",                # was Cycle de Feu Dégradé chain 1
    # === Impact Écologique ===
    ("Impact Ecologique", "Propagation aux Massifs"): "Déforestation (Niveau 1)",                     # drop +Mortalité
    ("Impact Ecologique", "Sols Imperméables"): "Particules Fines (Niveau 1)",                        # unchanged target, just renamed referrer
    ("Impact Ecologique", "Désertification"): "Propagation aux Massifs (Niveau 2)",                   # was Sol Hydrophobe — chain 1
    ("Impact Ecologique", "Altération du Microclimat"): "Sols Imperméables (Niveau 2)",               # was Dérèglement
    ("Impact Ecologique", "Dérèglement du Cycle de l'Eau"): "Mortalité de la Faune (Niveau 1)",       # was Propagation aux Massifs
    ("Impact Ecologique", "Biodiversité Effondrée"): "Dérèglement du Cycle de l'Eau (Niveau 2)",      # was Propagation+Mortalité
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    feu = next(c for c in data["catastrophes"] if c["Catastrophe"] == "Feu")

    # Pass 1: renames + auto-update of any prereq line that references a renamed skill.
    n_nom = 0
    n_pre_auto = 0
    for ax in feu["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                if sk["Nom"] in RENAMES:
                    sk["Nom"] = RENAMES[sk["Nom"]]
                    n_nom += 1
                pre = sk.get("Prerequis", "")
                if not pre or pre == "Aucun":
                    continue
                new = pre
                for old, replacement in RENAMES.items():
                    new = re.sub(
                        rf"\b{re.escape(old)}\b", replacement, new,
                    )
                if new != pre:
                    sk["Prerequis"] = new
                    n_pre_auto += 1

    # Pass 2: explicit prereq position-alignment rewrites.
    n_pre = 0
    for ax_name, ax in feu["Types"].items():
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

    # Validate + display
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    feu = next(c for c in reloaded["catastrophes"] if c["Catastrophe"] == "Feu")
    kept = set()
    for ax in feu["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                kept.add(sk["Nom"])
    broken = []
    for ax_name, ax in feu["Types"].items():
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
    print(f"Auto-updated prereqs (renamed targets): {n_pre_auto}")
    print(f"Explicit prereq rewrites: {n_pre}")

    print("\n=== Final Feu catastrophe chains ===")
    for ax_name, ax in feu["Types"].items():
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
        print("\nAll Feu catastrophe prereqs resolve.")


if __name__ == "__main__":
    main()
