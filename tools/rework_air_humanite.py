"""One-shot Air HUMANITÉ rework for lambda-user clarity.

Air's chains were mostly OK but Intensité had three Fond skills neatly
themed (Buildings / Vegetation / Aerodynamic) while their Ampl and Trans
were paired with mismatched themes — buildings (Toitures) flowed into a
vegetation Ampl (Ceintures Boisées). Two within-tier swaps realign all
three chains thematically.

Portée gets three meteorology-jargon renames (Microclimats /
Modélisation / Prévision d'Ensemble). Durée and Impact Écologique are
left as-is — their chain themes already hold and the names are clear.

Run from repo root::

    python tools/rework_air_humanite.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills_humanite.json"


def find(tier_list, name):
    for i, sk in enumerate(tier_list):
        if sk["Nom"] == name:
            return i, sk
    raise KeyError(name)


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    air = next(c for c in data["humanite_catastrophes"] if c["Catastrophe"] == "Air")

    # === Air/Intensité — realign chains by Ampl + Trans swaps ===
    # Themes (rooted at Fond):
    #   Chain 1: Buildings  — Toitures Ancrées (Fond[0])
    #   Chain 2: Vegetation — Brise-Vent (Fond[1])
    #   Chain 3: Aerodynamic — Filets Pare-Débris (Fond[2])
    # Need Ampl[0]=Aménagement Anti-Vent, Ampl[1]=Ceintures Boisées
    # and Trans[0]=Urbanisme Bioclimatique, Trans[1]=Atténuation des Vents.
    intensite = air["Types"]["Intensite"]["Niveaux"]
    ampl_list = intensite["Amplification"]["Competences"]
    trans_list = intensite["Transformation"]["Competences"]

    i_ceintures = find(ampl_list, "Ceintures Boisées")[0]
    i_amenag = find(ampl_list, "Aménagement Anti-Vent")[0]
    ampl_list[i_ceintures], ampl_list[i_amenag] = (
        ampl_list[i_amenag],
        ampl_list[i_ceintures],
    )

    i_attenuation = find(trans_list, "Atténuation des Vents")[0]
    i_urbanisme = find(trans_list, "Urbanisme Bioclimatique")[0]
    trans_list[i_attenuation], trans_list[i_urbanisme] = (
        trans_list[i_urbanisme],
        trans_list[i_attenuation],
    )

    # After Ampl swap, the Ampl prereqs are now cross-index (pointing to
    # the *other* chain's Fond). Realign them to the matching Fond:
    #   Aménagement Anti-Vent at Ampl[0] needs Fond[0] = Toitures Ancrées
    #   Ceintures Boisées at Ampl[1] needs Fond[1] = Brise-Vent
    for sk in ampl_list:
        if sk["Nom"] == "Aménagement Anti-Vent":
            sk["Prerequis"] = "Toitures Ancrées Niveau 1"
        elif sk["Nom"] == "Ceintures Boisées":
            sk["Prerequis"] = "Brise-Vent Niveau 1"
    # Trans prereqs auto-aligned (Urbanisme Bioclimatique's original prereq
    # was "Aménagement Anti-Vent Niveau 1" which now sits at Ampl[0]; same
    # for Atténuation des Vents ← Ceintures Boisées Niveau 1).

    # === Air/Portée — three meteo-jargon renames ===
    PORTEE_RENAMES = {
        "Microclimats Urbains": "Capteurs Urbains",
        "Prévision d'Ensemble": "Vigilance Météo Mondiale",
        "Modélisation Météo Ouverte": "Météo Ouverte à Tous",
    }
    portee = air["Types"]["Portee"]["Niveaux"]
    for tier in portee.values():
        for sk in tier["Competences"]:
            if sk["Nom"] in PORTEE_RENAMES:
                sk["Nom"] = PORTEE_RENAMES[sk["Nom"]]
            pre = sk.get("Prerequis", "")
            for old, new in PORTEE_RENAMES.items():
                if pre == f"{old} Niveau 1":
                    sk["Prerequis"] = f"{new} Niveau 1"
                    break

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Validate
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    air = next(c for c in reloaded["humanite_catastrophes"] if c["Catastrophe"] == "Air")
    all_names = set()
    for ax in air["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                all_names.add(sk["Nom"])
    broken = []
    for ax_name, ax in air["Types"].items():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                pre = sk.get("Prerequis", "")
                if pre == "Aucun":
                    continue
                nm = pre.rsplit(" Niveau ", 1)[0] if " Niveau " in pre else pre
                if nm not in all_names:
                    broken.append((ax_name, sk["Nom"], pre))

    sys.stdout.reconfigure(encoding="utf-8")
    print("=== Final Air chains ===")
    for ax_name, ax in air["Types"].items():
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
        print("\nAll Air prereqs resolve.")


if __name__ == "__main__":
    main()
