"""Terre CATASTROPHE name + prereq rework for lambda-user clarity.

Terre's names are mostly already accessible (Microséisme, Glissement de
Terrain, Subduction, etc.). The bulk of the rework is **prereq
position-alignment** — most Ampl[i] and Trans[i] pointed at skills in
adjacent chains rather than their own.

Three light renames retire the remaining geological jargon:
  * Orogenèse → Naissance de Montagnes
  * Métamorphisme de Subsurface → Sous-Sol Transformé
  * Perturbation des Aquifères → Nappes Perturbées

Run from repo root::

    python tools/rework_terre_catastrophe.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"


RENAMES = {
    "Orogenèse": "Naissance de Montagnes",
    "Métamorphisme de Subsurface": "Sous-Sol Transformé",
    "Perturbation des Aquifères": "Nappes Perturbées",
}

# (axis, skill_after_rename) → new prereq
PREREQ_REWRITES = {
    # === Intensité ===
    ("Intensite", "Rupture de Faille"): "Microséisme (Niveau 1)",
    ("Intensite", "Onde Sismique Secondaire"): "Onde Sismique Primaire (Niveau 1)",
    ("Intensite", "Métamorphisme"): "Rupture de Faille (Niveau 2)",  # drop +Onde S
    ("Intensite", "Naissance de Montagnes"): "Onde Sismique Secondaire (Niveau 2)",
    # === Portée ===
    ("Portee", "Propagation des Ondes"): "Séisme Local (Niveau 1)",
    ("Portee", "Glissement de Terrain"): "Propagation de Rupture (Niveau 1)",
    ("Portee", "Dérive des Continents"): "Glissement de Terrain (Niveau 2)",
    ("Portee", "Métamorphisme Régional"): "Liquéfaction Étendue (Niveau 2)",
    # === Durée ===
    ("Duree", "Répliques Sismiques"): "Accumulation de Contraintes (Niveau 1)",
    ("Duree", "Liquéfaction Prolongée"): "Trémor Sismique (Niveau 1)",
    ("Duree", "Déformation Périodique"): "Liquéfaction Prolongée (Niveau 2)",
    ("Duree", "Sous-Sol Transformé"): "Cycle Sismique (Niveau 2)",
    # === Impact Écologique ===
    ("Impact Ecologique", "Remodelage du Relief"): "Glissements de Terrain (Niveau 2)",  # drop +Destruction des Habitats
    ("Impact Ecologique", "Destruction des Habitats"): "Nappes Perturbées (Niveau 1)",
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    terre = next(c for c in data["catastrophes"] if c["Catastrophe"] == "Terre")

    # Pass 1: renames + auto-update prereqs that reference renamed skills
    n_nom = n_pre_auto = 0
    for ax in terre["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                if sk["Nom"] in RENAMES:
                    sk["Nom"] = RENAMES[sk["Nom"]]
                    n_nom += 1
                pre = sk.get("Prerequis", "")
                if not pre or pre == "Aucun":
                    continue
                new = pre
                for old, repl in RENAMES.items():
                    new = re.sub(rf"\b{re.escape(old)}\b", repl, new)
                if new != pre:
                    sk["Prerequis"] = new
                    n_pre_auto += 1

    # Pass 2: explicit prereq position-alignment rewrites
    n_pre = 0
    for ax_name, ax in terre["Types"].items():
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
    terre = next(c for c in reloaded["catastrophes"] if c["Catastrophe"] == "Terre")
    kept = set()
    for ax in terre["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                kept.add(sk["Nom"])
    broken = []
    for ax_name, ax in terre["Types"].items():
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

    print("\n=== Final Terre catastrophe chains ===")
    for ax_name, ax in terre["Types"].items():
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
        print("\nAll Terre catastrophe prereqs resolve.")


if __name__ == "__main__":
    main()
