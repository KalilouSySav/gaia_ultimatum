"""One-shot Vie HUMANITÉ rework for lambda-user clarity.

Vie's chains were almost all coherent already (post-COVID medical
terminology is widely understood). The rework is minimal:

  * 4 renames — replace the more formal medical/biology phrasings
    (``Lutte contre l'Antibiorésistance``, ``Médecine de Premier
    Recours``, ``Conservation in situ``, ``Production Vaccinale
    Rapide``) with concrete everyday equivalents.
  * 1 within-tier swap in Impact Écologique to give chain 2 a clean
    connectivity arc (Banques de Semences → Corridors Écologiques →
    Renaturation Planétaire) and chain 3 a clean active-intervention
    arc (Aires Protégées → Réintroduction d'Espèces Clés →
    Biomimétisme).

Run from repo root::

    python tools/rework_vie_humanite.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills_humanite.json"

RENAMES = {
    # Intensité
    "Production Vaccinale Rapide": "Vaccins Express",
    "Lutte contre l'Antibiorésistance": "Antibiotiques Préservés",
    # Durée
    "Médecine de Premier Recours": "Soins de Proximité",
    # Impact Écologique
    "Conservation in situ": "Espèces Protégées",
}


def find(tier_list, name):
    for i, sk in enumerate(tier_list):
        if sk["Nom"] == name:
            return i, sk
    raise KeyError(name)


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    vie = next(c for c in data["humanite_catastrophes"] if c["Catastrophe"] == "Vie")

    # === Apply renames + update referrers ===
    n_nom = n_prereq = 0
    for ax in vie["Types"].values():
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

    # === Vie/Impact Écologique — swap Trans[1] ↔ Trans[2] ===
    # Goal:
    #   Chain 1 (Restoration): Espèces Protégées → Restauration de la
    #     Biodiversité → Résilience des Écosystèmes (unchanged)
    #   Chain 2 (Connectivity): Banques de Semences → Corridors
    #     Écologiques → Renaturation Planétaire
    #   Chain 3 (Active intervention): Aires Protégées → Réintroduction
    #     d'Espèces Clés → Biomimétisme
    impact_trans = vie["Types"]["Impact Ecologique"]["Niveaux"]["Transformation"]["Competences"]
    i_renat = find(impact_trans, "Renaturation Planétaire")[0]
    i_bio = find(impact_trans, "Biomimétisme")[0]
    impact_trans[i_renat], impact_trans[i_bio] = (
        impact_trans[i_bio],
        impact_trans[i_renat],
    )
    # Realign Trans prereqs to the new chain positions:
    #   Renaturation Planétaire now at Trans[1] requires Ampl[1] = Corridors Écologiques
    #   Biomimétisme now at Trans[2] requires Ampl[2] = Réintroduction d'Espèces Clés
    for sk in impact_trans:
        if sk["Nom"] == "Renaturation Planétaire":
            sk["Prerequis"] = "Corridors Écologiques Niveau 1"
        elif sk["Nom"] == "Biomimétisme":
            sk["Prerequis"] = "Réintroduction d'Espèces Clés Niveau 1"

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Validate
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    vie = next(c for c in reloaded["humanite_catastrophes"] if c["Catastrophe"] == "Vie")
    all_names = set()
    for ax in vie["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                all_names.add(sk["Nom"])
    broken = []
    for ax_name, ax in vie["Types"].items():
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

    print("\n=== Final Vie chains ===")
    for ax_name, ax in vie["Types"].items():
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
        print("\nAll Vie prereqs resolve.")


if __name__ == "__main__":
    main()
