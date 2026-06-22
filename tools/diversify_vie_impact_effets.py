"""Differentiate the placeholder Effet values in Vie/Impact Écologique.

All 9 Vie/Impact Écologique skills currently share the identical Effet
key ``Surface affectée`` with identical numeric scales — clearly a
placeholder that survived earlier passes. Every other catastrophe's
Impact Écologique axis uses skill-specific keys (Eau has *Surface
détruite*, *Nombre d'espèces affectées*, *Longueur des cours d'eau*…).

This pass rewrites each Vie/Impact skill's Effet to match what the
skill semantically represents. Tier scale is preserved (Fond and Ampl
land in the same order-of-magnitude band; Trans escalates ~5×) so
game balance is unchanged — only the descriptor and units shift.

Run from repo root::

    python tools/diversify_vie_impact_effets.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"


# Per-skill new Effet (L1/L2/L3 values). Each picks a metric matching
# the skill's narrative — invading species count their species,
# yield-collapse skills count their % yield drop, food-web skills
# count broken trophic links, etc.
NEW_EFFETS = {
    # === Fondations ===
    "Espèce Invasive": [
        {"Espèces introduites": "5"},
        {"Espèces introduites": "12"},
        {"Espèces introduites": "25"},
    ],
    "Déséquilibre Écologique": [
        {"Écosystèmes perturbés": "3"},
        {"Écosystèmes perturbés": "8"},
        {"Écosystèmes perturbés": "15"},
    ],
    "Cycles du Vivant Perturbés": [
        {"Espèces désaccordées": "20"},
        {"Espèces désaccordées": "100"},
        {"Espèces désaccordées": "500"},
    ],
    # === Amplification ===
    "Épidémie Végétale": [
        {"Surface de cultures atteinte": "10 000 ha"},
        {"Surface de cultures atteinte": "100 000 ha"},
        {"Surface de cultures atteinte": "1 M ha"},
    ],
    "Effondrement des Rendements": [
        {"Baisse des rendements": "15 %"},
        {"Baisse des rendements": "35 %"},
        {"Baisse des rendements": "60 %"},
    ],
    "Chaînes Alimentaires Brisées": [
        {"Liens trophiques rompus": "10"},
        {"Liens trophiques rompus": "50"},
        {"Liens trophiques rompus": "200"},
    ],
    # === Transformation ===
    "Réseau Alimentaire Effondré": [
        {"Part du réseau détruite": "20 %"},
        {"Part du réseau détruite": "45 %"},
        {"Part du réseau détruite": "75 %"},
    ],
    "Déplacement des Biomes": [
        {"Distance de déplacement": "100 km"},
        {"Distance de déplacement": "500 km"},
        {"Distance de déplacement": "2 000 km"},
    ],
    "Vivant Uniformisé": [
        {"Perte de diversité": "15 %"},
        {"Perte de diversité": "40 %"},
        {"Perte de diversité": "70 %"},
    ],
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    vie = next(c for c in data["catastrophes"] if c["Catastrophe"] == "Vie")
    impact = vie["Types"]["Impact Ecologique"]["Niveaux"]

    n = 0
    for tier in impact.values():
        for sk in tier["Competences"]:
            nm = sk["Nom"]
            if nm not in NEW_EFFETS:
                continue
            new_effets = NEW_EFFETS[nm]
            for lvl_idx, (lvl_name, lvl) in enumerate(sk["Niveaux"].items()):
                if not isinstance(lvl, dict) or lvl_idx >= len(new_effets):
                    continue
                lvl["Effet"] = new_effets[lvl_idx]
            n += 1

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Skills with rewritten Effets: {n}")
    print(f"Expected: {len(NEW_EFFETS)}")

    # Display the new state
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    vie = next(c for c in reloaded["catastrophes"] if c["Catastrophe"] == "Vie")
    print("\n=== Vie/Impact Écologique after differentiation ===")
    for tier_name, tier in vie["Types"]["Impact Ecologique"]["Niveaux"].items():
        print(f"\n  [{tier_name}]")
        for sk in tier["Competences"]:
            print(f"    {sk['Nom']}")
            for lvl_name, lvl in sk["Niveaux"].items():
                if isinstance(lvl, dict):
                    eff_str = ", ".join(f"{k}={v}" for k, v in lvl.get("Effet", {}).items())
                    print(f"      {lvl_name}: {eff_str}")


if __name__ == "__main__":
    main()
