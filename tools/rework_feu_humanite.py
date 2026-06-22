"""One-shot Feu HUMANITÉ name/prereq rework for lambda-user clarity.

Run from repo root::

    python tools/rework_feu_humanite.py

Restructures all 4 Feu axes — within-tier swaps for Portée / Durée /
Impact Écologique and 3 cross-tier moves in Intensité (Cout structure
is uniform across tiers, so moves are safe). Renames jargon-heavy
skill names to concrete everyday equivalents.
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
    feu = next(c for c in data["humanite_catastrophes"] if c["Catastrophe"] == "Feu")

    # === Feu/Intensité — 3-way data rotation + renames ===
    intensite = feu["Types"]["Intensite"]["Niveaux"]
    ampl_list = intensite["Amplification"]["Competences"]
    trans_list = intensite["Transformation"]["Competences"]

    ai_robot = find(ampl_list, "Robotique d'Intervention")[0]
    ti_telede = find(trans_list, "Télédétection Satellitaire")[0]
    ti_coord = find(trans_list, "Coordination Continentale")[0]

    # Snapshot data dicts
    telede_dict = trans_list[ti_telede]
    coord_dict = trans_list[ti_coord]
    robot_dict = ampl_list[ai_robot]

    # Apply renames before placement
    telede_dict["Nom"] = "Détection Satellite"
    robot_dict["Nom"] = "Robots Pompiers"

    # Place: Ampl[robot_slot] ← Télédétection (renamed),
    #        Trans[telede_slot] ← Coordination,
    #        Trans[coord_slot] ← Robotique (renamed)
    ampl_list[ai_robot] = telede_dict
    trans_list[ti_telede] = coord_dict
    trans_list[ti_coord] = robot_dict

    # In-place renames (no position change):
    for sk in ampl_list:
        if sk["Nom"] == "Points d'Eau Aériens":
            sk["Nom"] = "Points d'Eau Stratégiques"
    for sk in trans_list:
        if sk["Nom"] == "Modélisation Prédictive du Risque":
            sk["Nom"] = "Prévision des Incendies"

    # Rewrite Intensité prereqs to reflect new chain structure.
    new_prereqs = {
        "Lutte Aérienne": "Pare-Feu Niveau 1",
        "Détection Satellite": "Détection Précoce Niveau 1",
        "Points d'Eau Stratégiques": "Débroussaillement Niveau 1",
        "Coordination Continentale": "Lutte Aérienne Niveau 1",
        "Prévision des Incendies": "Détection Satellite Niveau 1",
        "Robots Pompiers": "Points d'Eau Stratégiques Niveau 1",
    }
    for tier in (ampl_list, trans_list):
        for sk in tier:
            if sk["Nom"] in new_prereqs:
                sk["Prerequis"] = new_prereqs[sk["Nom"]]

    # === Feu/Portée — swap Trans[0] <-> Trans[2] ===
    portee_trans = feu["Types"]["Portee"]["Niveaux"]["Transformation"]["Competences"]
    i_coop = find(portee_trans, "Coopération Internationale")[0]
    i_itin = find(portee_trans, "Itinéraires d'Évacuation")[0]
    portee_trans[i_coop], portee_trans[i_itin] = (
        portee_trans[i_itin],
        portee_trans[i_coop],
    )
    for sk in portee_trans:
        if sk["Nom"] == "Itinéraires d'Évacuation":
            sk["Prerequis"] = "Évacuation Préventive Niveau 1"
        elif sk["Nom"] == "Coopération Internationale":
            sk["Prerequis"] = "Abris Anti-Fumée Niveau 1"

    # === Feu/Durée — swap Fond[1]<->Fond[2], Ampl[1]<->Ampl[2] + renames ===
    duree = feu["Types"]["Duree"]["Niveaux"]
    fond_list = duree["Fondations"]["Competences"]
    ampl_list = duree["Amplification"]["Competences"]
    trans_list = duree["Transformation"]["Competences"]

    i_cons = find(fond_list, "Conservation des Semences")[0]
    i_edu = find(fond_list, "Éducation au Risque")[0]
    fond_list[i_cons], fond_list[i_edu] = fond_list[i_edu], fond_list[i_cons]

    i_centre = find(ampl_list, "Centres de Rafraîchissement")[0]
    i_ignif = find(ampl_list, "Construction Ignifuge")[0]
    ampl_list[i_centre], ampl_list[i_ignif] = (
        ampl_list[i_ignif],
        ampl_list[i_centre],
    )

    for sk in trans_list:
        if sk["Nom"] == "Séquestration du Carbone":
            sk["Nom"] = "Stockage du Carbone"
            sk["Prerequis"] = "Construction Ignifuge Niveau 1"
        elif sk["Nom"] == "Régulation Hydro-Thermique":
            sk["Nom"] = "Équilibre Eau-Chaleur"
            sk["Prerequis"] = "Centres de Rafraîchissement Niveau 1"

    # === Feu/Impact Écologique — rename Sylviculture + fix referrers ===
    impact = feu["Types"]["Impact Ecologique"]["Niveaux"]
    for tier_name in ("Amplification", "Transformation"):
        for sk in impact[tier_name]["Competences"]:
            if sk["Nom"] == "Sylviculture Diversifiée":
                sk["Nom"] = "Forêts Mixtes"
            if sk.get("Prerequis") == "Sylviculture Diversifiée Niveau 1":
                sk["Prerequis"] = "Forêts Mixtes Niveau 1"

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Validation
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    feu = next(c for c in reloaded["humanite_catastrophes"] if c["Catastrophe"] == "Feu")

    sys.stdout.reconfigure(encoding="utf-8")
    print("=== Final Feu chains ===")
    for ax_name, ax in feu["Types"].items():
        print(f"\n  [{ax_name}]")
        tiers = list(ax["Niveaux"].items())
        for chain_i in range(3):
            chain = []
            for _, tier in tiers:
                if chain_i < len(tier["Competences"]):
                    chain.append(tier["Competences"][chain_i]["Nom"])
            print(f"    Chain {chain_i+1}: {' -> '.join(chain)}")

    all_names = set()
    for ax in feu["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                all_names.add(sk["Nom"])
    broken = []
    for ax_name, ax in feu["Types"].items():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                pre = sk.get("Prerequis", "")
                if pre == "Aucun":
                    continue
                nm = pre.rsplit(" Niveau ", 1)[0] if " Niveau " in pre else pre
                if nm not in all_names:
                    broken.append((ax_name, sk["Nom"], pre))
    if broken:
        print("\nBROKEN PREREQS:")
        for b in broken:
            print(f"  {b}")
    else:
        print("\nAll Feu prereqs resolve.")


if __name__ == "__main__":
    main()
