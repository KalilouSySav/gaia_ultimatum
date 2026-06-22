"""One-shot Eau CATASTROPHE rename rework for lambda-user clarity.

The catastrophe (Gaïa) side has wider trees than HUMANITÉ — Eau alone
ships 50 skills (3+5+5 per tier × 4 axes) with branching/converging
prereqs and a per-tier cost scale ((5,10,15) → (10,15,20) → (20,25,30))
so cross-tier moves would break balance. The rework therefore stays
**rename-only**, plus a small set of prereq tweaks where the existing
"X emerges from Y" relationship reads as arbitrary to a lambda player.

Prereq format note: catastrophe prereqs use the parenthesised form
``Name (Niveau N)`` rather than HUMANITÉ's bare ``Name Niveau N``. The
referrer-update logic handles both.

Run from repo root::

    python tools/rework_eau_catastrophe.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"

# Renames grouped by axis (informational only — the rewrite scans the
# whole catastrophe block).
RENAMES = {
    # Intensité — drop hydraulics jargon
    "Érosion Régressive": "Érosion Profonde",
    "Affouillement": "Coups de Bélier",
    "Charge Hydrostatique": "Pression de l'Eau",
    "Charriage Torrentiel": "Torrent de Débris",
    "Onde de Crue Couplée": "Crues en Cascade",
    "Inversion Hydrologique": "Territoire Submergé",
    # Portée — drop oceanography / hydrology jargon
    "Cycle Hydrologique Global": "Cycle Mondial de l'Eau",
    "Eutrophisation Côtière": "Asphyxie Côtière",
    "Circulation Thermohaline": "Courants Océaniques",
    # Durée — drop technical period-terms
    "Onde de Seiche": "Vagues en Résonance",
    "Aléa Latent": "Menace Cachée",
    "Régime Inondé Permanent": "Inondation Permanente",
    # Impact Écologique — drop biology jargon
    "Désynchronisation Phénologique": "Saisons Déréglées",
    "Capture Fluviale": "Détournement de Rivière",
}


def rewrite_prereq(pre: str, renames: dict) -> str:
    """Update a ``Name (Niveau N)`` or ``Name Niveau N`` prereq if its
    target skill got renamed. Preserves the surrounding format."""
    if not pre or pre == "Aucun":
        return pre
    # Catastrophe format: "Name (Niveau N)"
    m = re.match(r"^(.+?) \(Niveau (\d+)\)$", pre)
    if m:
        nm, lvl = m.group(1), m.group(2)
        if nm in renames:
            return f"{renames[nm]} (Niveau {lvl})"
        return pre
    # Fall-through: bare-format prereqs (none expected in catastrophe
    # skills but defensive).
    m = re.match(r"^(.+?) Niveau (\d+)$", pre)
    if m:
        nm, lvl = m.group(1), m.group(2)
        if nm in renames:
            return f"{renames[nm]} Niveau {lvl}"
    return pre


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    eau = next(c for c in data["catastrophes"] if c["Catastrophe"] == "Eau")

    n_nom = n_prereq = 0
    for ax in eau["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                if sk["Nom"] in RENAMES:
                    sk["Nom"] = RENAMES[sk["Nom"]]
                    n_nom += 1
                new_pre = rewrite_prereq(sk.get("Prerequis", ""), RENAMES)
                if new_pre != sk.get("Prerequis", ""):
                    sk["Prerequis"] = new_pre
                    n_prereq += 1

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    # Validate
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    eau = next(c for c in reloaded["catastrophes"] if c["Catastrophe"] == "Eau")
    all_names = set()
    for ax in eau["Types"].values():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                all_names.add(sk["Nom"])
    broken = []
    for ax_name, ax in eau["Types"].items():
        for tier in ax["Niveaux"].values():
            for sk in tier["Competences"]:
                pre = sk.get("Prerequis", "")
                if pre == "Aucun":
                    continue
                m = re.match(r"^(.+?) \(Niveau \d+\)$", pre) or re.match(
                    r"^(.+?) Niveau \d+$", pre
                )
                if m and m.group(1) not in all_names:
                    broken.append((ax_name, sk["Nom"], pre))

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Renamed Nom entries: {n_nom}")
    print(f"Updated Prerequis references: {n_prereq}")

    print("\n=== Final Eau catastrophe trees ===")
    for ax_name, ax in eau["Types"].items():
        print(f"\n  [{ax_name}]")
        for tier_name, tier in ax["Niveaux"].items():
            print(f"    {tier_name}:")
            for sk in tier["Competences"]:
                pre = sk.get("Prerequis", "")
                print(f"      - {sk['Nom']:32s} ← {pre}")

    if broken:
        print("\nBROKEN PREREQS:")
        for b in broken:
            print(f"  {b}")
    else:
        print("\nAll Eau catastrophe prereqs resolve.")


if __name__ == "__main__":
    main()
