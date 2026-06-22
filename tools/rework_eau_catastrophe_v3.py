"""Eau catastrophe Durée alignment fix (v3).

Final pass on Eau catastrophe: the Durée Ampl tier has chain-1 and
chain-2 Ampls swapped relative to their position-aligned Fond. The
Trans tier is already pointing at those Ampls by name, so swapping
the Ampls without also swapping their position-matched Trans would
re-break Trans alignment. This script does both swaps atomically.

Pre-state (after v2):
  Ampl[0]=Engorgement des Sols (← Crue Persistante = chain-2 Fond)
  Ampl[1]=Érosion Chronique    (← Infiltration Lente = chain-1 Fond)
  Trans[0]=Vagues en Résonance  (← Engorgement des Sols)
  Trans[1]=Polluants Persistants(← Érosion Chronique)

Post-state:
  Ampl[0]=Érosion Chronique    (← Infiltration Lente)  — chain 1
  Ampl[1]=Engorgement des Sols (← Crue Persistante)    — chain 2
  Trans[0]=Polluants Persistants(← Érosion Chronique)  — chain 1
  Trans[1]=Vagues en Résonance  (← Engorgement des Sols)— chain 2

Run from repo root::

    python tools/rework_eau_catastrophe_v3.py
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
    duree = eau["Types"]["Duree"]["Niveaux"]

    ampl = duree["Amplification"]["Competences"]
    trans = duree["Transformation"]["Competences"]

    i_e = find(ampl, "Engorgement des Sols")
    i_er = find(ampl, "Érosion Chronique")
    ampl[i_e], ampl[i_er] = ampl[i_er], ampl[i_e]

    i_v = find(trans, "Vagues en Résonance")
    i_p = find(trans, "Polluants Persistants")
    trans[i_v], trans[i_p] = trans[i_p], trans[i_v]

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Display all Eau chains for final verification
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
