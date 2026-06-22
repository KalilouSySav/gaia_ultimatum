"""Post-uniformization Eau CATASTROPHE rework — fix chain visibility.

After the catastrophe trees were trimmed to 3+3+3, several Trans skills
were left pointing cross-chain rather than to the Ampl in the same
position-index. Because the renderer paints chains by position, this
made the visible chain layout disagree with the actual prereq graph —
the opposite of "evident".

This pass:
  * Repoints 5 Trans prereqs so each position-N chain's Trans-N
    requires the Ampl-N at the same position. Concretely:
      - Eau/Intensité Trans[1] ``Crues en Cascade`` ← Sape des
        Fondations (was Surcote Marine)
      - Eau/Portée Trans[1] ``Tsunami Transocéanique`` ← Submersion
        Marine (was Inondation Régionale)
      - Eau/Portée Trans[2] ``Cycle Mondial de l'Eau`` ← Inondation
        Régionale (was Submersion Marine)
      - Eau/Durée: swap Trans[1] (Submersion Récurrente) and Trans[2]
        (Polluants Persistants) so positions match their existing
        prereqs (Polluants ← Érosion Chronique sits at index 1 / chain
        2, Submersion ← Débit Soutenu sits at index 2 / chain 3)
  * Renames ``Crues Synchrones`` → ``Inondations Mondiales`` — more
    visceral for a player. The Portée Trans[0] target.

Run from repo root::

    python tools/rework_eau_catastrophe_v2.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"


def find(comp_list, name):
    for i, sk in enumerate(comp_list):
        if sk["Nom"] == name:
            return i
    raise KeyError(name)


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    eau = next(c for c in data["catastrophes"] if c["Catastrophe"] == "Eau")

    # === Intensité — Trans[1] Crues en Cascade aligns with chain 2 ===
    int_trans = eau["Types"]["Intensite"]["Niveaux"]["Transformation"]["Competences"]
    for sk in int_trans:
        if sk["Nom"] == "Crues en Cascade":
            sk["Prerequis"] = "Sape des Fondations (Niveau 3)"

    # === Portée — Trans[1] swaps with Trans[2]'s prereq ===
    por_trans = eau["Types"]["Portee"]["Niveaux"]["Transformation"]["Competences"]
    for sk in por_trans:
        if sk["Nom"] == "Tsunami Transocéanique":
            sk["Prerequis"] = "Submersion Marine (Niveau 2)"
        elif sk["Nom"] == "Cycle Mondial de l'Eau":
            sk["Prerequis"] = "Inondation Régionale (Niveau 2)"

    # === Durée — two swaps to fully position-align all three chains ===
    # Pre-rework state in Durée after the uniformization-only pass:
    #   Fond[0]=Infiltration Lente,    Fond[1]=Crue Persistante,    Fond[2]=Humidité Résiduelle
    #   Ampl[0]=Engorgement des Sols (← Crue Persistante = chain-2 Fond)  ← misaligned
    #   Ampl[1]=Érosion Chronique    (← Infiltration Lente = chain-1 Fond) ← misaligned
    #   Ampl[2]=Débit Soutenu        (← Humidité Résiduelle = chain-3 Fond)  ✓
    #
    # Swap Ampl[0]↔Ampl[1] to align each Ampl with its same-position
    # Fond. Then mirror the swap at Trans[0]↔Trans[1] so each Trans
    # follows its position-aligned Ampl through its prereq:
    #   chain 1: Infiltration → Érosion Chronique → Polluants Persistants
    #   chain 2: Crue Persistante → Engorgement des Sols → Vagues en Résonance
    #   chain 3: Humidité Résiduelle → Débit Soutenu → Submersion Récurrente
    duree = eau["Types"]["Duree"]["Niveaux"]
    duree_ampl = duree["Amplification"]["Competences"]
    duree_trans = duree["Transformation"]["Competences"]
    i_engorgement = find(duree_ampl, "Engorgement des Sols")
    i_erosion = find(duree_ampl, "Érosion Chronique")
    duree_ampl[i_engorgement], duree_ampl[i_erosion] = (
        duree_ampl[i_erosion],
        duree_ampl[i_engorgement],
    )
    i_vagues = find(duree_trans, "Vagues en Résonance")
    i_pollu = find(duree_trans, "Polluants Persistants")
    duree_trans[i_vagues], duree_trans[i_pollu] = (
        duree_trans[i_pollu],
        duree_trans[i_vagues],
    )

    # === Rename Crues Synchrones → Inondations Mondiales ===
    # Portée Trans[0]. No other prereq references it (this is a top-tier
    # leaf), so no referrer update needed.
    for sk in por_trans:
        if sk["Nom"] == "Crues Synchrones":
            sk["Nom"] = "Inondations Mondiales"

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # === Validate + display ===
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    eau = next(c for c in reloaded["catastrophes"] if c["Catastrophe"] == "Eau")
    sys.stdout.reconfigure(encoding="utf-8")

    print("=== Final Eau catastrophe chains (position = chain) ===")
    for ax_name, ax in eau["Types"].items():
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


if __name__ == "__main__":
    main()
