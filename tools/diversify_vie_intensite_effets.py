"""Differentiate Vie/Intensité (HUMANITÉ) Effet placeholders.

The 9 Vie/Intensité skills currently share three tier-level Effet
templates — every Fond skill shows {Doses produites: 1 M, Efficacité
vaccinale: 55 %}, every Ampl shows {…: 30 M, …: 80 %}, every Trans
shows {…: 1 Md, …: 94 %}. Skill-by-skill the metric is the same
regardless of whether you're looking at Vaccination, Vaccins Express,
or Antibiotiques Préservés — players can't tell what each option
actually delivers.

This pass gives each skill its own pair of metrics that match what
the skill semantically represents. Tier-scale band is roughly
preserved (Fond modest, Ampl ~10–50×, Trans ~5–20× over Ampl) so
balance is unchanged.

Run from repo root::

    python tools/diversify_vie_intensite_effets.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills_humanite.json"


# Per-skill new Effet (L1/L2/L3). Each skill's metrics match its
# semantic identity: Vaccination = doses + efficacy, Antibiotiques
# Préservés = resistance reduction, Santé Publique = population
# served, etc.
NEW_EFFETS = {
    # === Fondations ===
    "Vaccination": [
        {"Doses administrées": "1 M", "Efficacité vaccinale": "55 %"},
        {"Doses administrées": "10 M", "Efficacité vaccinale": "70 %"},
        {"Doses administrées": "100 M", "Efficacité vaccinale": "85 %"},
    ],
    "Vaccins Express": [
        {"Délai de mise au point": "6 mois", "Doses produites par mois": "5 M"},
        {"Délai de mise au point": "3 mois", "Doses produites par mois": "50 M"},
        {"Délai de mise au point": "30 jours", "Doses produites par mois": "500 M"},
    ],
    "Couverture Vaccinale Universelle": [
        {"Population couverte": "30 %", "Pays participants": "50"},
        {"Population couverte": "65 %", "Pays participants": "120"},
        {"Population couverte": "95 %", "Pays participants": "190"},
    ],
    # === Amplification ===
    "Vaccin ARNm": [
        {"Variants couverts": "3", "Adaptation à un nouveau variant": "60 jours"},
        {"Variants couverts": "10", "Adaptation à un nouveau variant": "21 jours"},
        {"Variants couverts": "30", "Adaptation à un nouveau variant": "7 jours"},
    ],
    "Médecine Personnalisée": [
        {"Patients pris en charge": "10 000", "Taux de réponse": "70 %"},
        {"Patients pris en charge": "200 000", "Taux de réponse": "85 %"},
        {"Patients pris en charge": "5 M", "Taux de réponse": "95 %"},
    ],
    "Antibiotiques Préservés": [
        {"Souches résistantes contenues": "15 %", "Nouvelles molécules": "2"},
        {"Souches résistantes contenues": "50 %", "Nouvelles molécules": "8"},
        {"Souches résistantes contenues": "85 %", "Nouvelles molécules": "25"},
    ],
    # === Transformation ===
    "Immunothérapie": [
        {"Taux de réponse durable": "40 %", "Durée de la rémission": "2 ans"},
        {"Taux de réponse durable": "65 %", "Durée de la rémission": "10 ans"},
        {"Taux de réponse durable": "85 %", "Durée de la rémission": "à vie"},
    ],
    "Biotechnologies Médicales": [
        {"Thérapies disponibles": "20", "Maladies couvertes": "50"},
        {"Thérapies disponibles": "200", "Maladies couvertes": "500"},
        {"Thérapies disponibles": "2 000", "Maladies couvertes": "toutes"},
    ],
    "Santé Publique": [
        {"Espérance de vie en bonne santé": "70 ans", "Inégalités d'accès": "réduites de 30 %"},
        {"Espérance de vie en bonne santé": "78 ans", "Inégalités d'accès": "réduites de 60 %"},
        {"Espérance de vie en bonne santé": "85 ans", "Inégalités d'accès": "supprimées"},
    ],
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    vie = next(c for c in data["humanite_catastrophes"] if c["Catastrophe"] == "Vie")
    intensite = vie["Types"]["Intensite"]["Niveaux"]

    n = 0
    for tier in intensite.values():
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

    # Display
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    vie = next(c for c in reloaded["humanite_catastrophes"] if c["Catastrophe"] == "Vie")
    print("\n=== Vie/Intensité after differentiation ===")
    for tier_name, tier in vie["Types"]["Intensite"]["Niveaux"].items():
        print(f"\n  [{tier_name}]")
        for sk in tier["Competences"]:
            print(f"    {sk['Nom']}")
            for lvl_name, lvl in sk["Niveaux"].items():
                if isinstance(lvl, dict):
                    eff_str = ", ".join(f"{k}={v}" for k, v in lvl.get("Effet", {}).items())
                    print(f"      {lvl_name}: {eff_str}")


if __name__ == "__main__":
    main()
