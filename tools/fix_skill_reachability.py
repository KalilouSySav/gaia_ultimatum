"""One-shot script: bring skills.json into a reachable state.

Two surgical changes:

1. Add 3 new Amplification skills to Feu (Intensité / Durée / Portée),
   each previously sat at 2 skills while every other axis-tier in the
   file ships 3 — so the renderer's third "card slot" stayed empty for
   Feu only. Each new skill follows the existing 3-level structure +
   indicator-impact schema of its tier neighbours.

2. Repair prereqs that the renderer's ``tier.skills[:3]`` cap left
   pointing to hidden 4th/5th skills. The renderer shows only the first
   3 skills per tier; any visible (kept) skill whose ``Prerequis`` named
   a hidden skill was unreachable through the UI. For each:
     - compound "A (Niveau N) + B (Niveau M)" where exactly one part is
       hidden → drop the hidden part
     - both parts hidden, or a single-prereq pointing to a hidden skill
       → redirect to the first visible Amplification skill of the same
       axis (preserving the original level requirement)

Run from repo root:
    python tools/fix_skill_reachability.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path("gaia_ultimatum/data/skills.json")


def _impact_block(base_dampening: int) -> dict:
    """Standard 4-indicator impact block sized off a base dampening level."""
    return {
        "Resilience Technologique": {
            "Valeur_de_Base": base_dampening,
            "Facteur_Affinite": 0.8,
            "Description": "Réduit l'efficacité des systèmes de suppression des incendies.",
        },
        "Stabilite Societale": {
            "Valeur_de_Base": max(1, base_dampening - 1),
            "Facteur_Affinite": 0.9,
            "Description": "Augmente les déplacements de population.",
        },
        "Regeneration Ecologique": {
            "Valeur_de_Base": base_dampening + 2,
            "Facteur_Affinite": 1.2,
            "Description": "Ralentit la repousse des plantes locales.",
        },
        "Adaptation Evolutive": {
            "Valeur_de_Base": max(1, base_dampening - 2),
            "Facteur_Affinite": 0.7,
            "Description": "Réduit la diversité génétique des espèces locales.",
        },
    }


FEU_NEW_SKILLS = {
    "Intensite": {
        "Nom": "Combustion Intensive",
        "Description": (
            "Concentre l'énergie de combustion pour porter la température au cœur "
            "du foyer à des niveaux exceptionnels."
        ),
        "Niveaux": {
            "Niveau 1": {
                "Effet": {"Température maximale": "800 °C", "Force d'impact": "2000 N"},
                "Impact sur les indicateurs": _impact_block(6),
                "Cout": 5,
            },
            "Niveau 2": {
                "Effet": {"Température maximale": "1200 °C", "Force d'impact": "4000 N"},
                "Impact sur les indicateurs": _impact_block(12),
                "Cout": 10,
            },
            "Niveau 3": {
                "Effet": {"Température maximale": "1600 °C", "Force d'impact": "6000 N"},
                "Impact sur les indicateurs": _impact_block(18),
                "Cout": 15,
            },
        },
        "Prerequis": "Combustion Initiale (Niveau 1)",
    },
    "Duree": {
        "Nom": "Combustion Latente Accrue",
        "Description": (
            "Maintient des braises actives bien au-delà de l'extinction visible, "
            "permettant des reprises spontanées du foyer."
        ),
        "Niveaux": {
            "Niveau 1": {
                "Effet": {"Durée de braise": "4 heures"},
                "Impact sur les indicateurs": _impact_block(6),
                "Cout": 5,
            },
            "Niveau 2": {
                "Effet": {"Durée de braise": "8 heures"},
                "Impact sur les indicateurs": _impact_block(12),
                "Cout": 10,
            },
            "Niveau 3": {
                "Effet": {"Durée de braise": "12 heures"},
                "Impact sur les indicateurs": _impact_block(18),
                "Cout": 15,
            },
        },
        "Prerequis": "Braise Résiliente (Niveau 1)",
    },
    "Portee": {
        "Nom": "Vague Thermique",
        "Description": (
            "Diffuse un front de chaleur intense au-devant des flammes, "
            "préchauffant les matériaux et accélérant l'embrasement."
        ),
        "Niveaux": {
            "Niveau 1": {
                "Effet": {"Rayon thermique": "1,5 km", "Température au sol": "90 °C"},
                "Impact sur les indicateurs": _impact_block(6),
                "Cout": 5,
            },
            "Niveau 2": {
                "Effet": {"Rayon thermique": "3 km", "Température au sol": "130 °C"},
                "Impact sur les indicateurs": _impact_block(12),
                "Cout": 10,
            },
            "Niveau 3": {
                "Effet": {"Rayon thermique": "4,5 km", "Température au sol": "170 °C"},
                "Impact sur les indicateurs": _impact_block(18),
                "Cout": 15,
            },
        },
        "Prerequis": "Extension Thermique (Niveau 1)",
    },
}


def main() -> None:
    with open(DATA, "r", encoding="utf-8") as f:
        d = json.load(f)

    # ---- 1. Add 3 new Feu Amplification skills.
    feu = next(c for c in d["catastrophes"] if c["Catastrophe"] == "Feu")
    for axis_name, new_skill in FEU_NEW_SKILLS.items():
        comp = feu["Types"][axis_name]["Niveaux"]["Amplification"]["Competences"]
        existing_names = {s["Nom"] for s in comp}
        if new_skill["Nom"] in existing_names:
            continue
        comp.append(new_skill)

    # ---- 2. Repair broken prereqs.
    # Build visible set per catastrophe (first 3 of each tier — what the
    # renderer actually exposes).
    def visible(cat: dict) -> set[str]:
        out: set[str] = set()
        for axis in cat["Types"].values():
            for tier in axis["Niveaux"].values():
                for s in tier["Competences"][:3]:
                    out.add(s["Nom"])
        return out

    def first_visible_amplification(cat: dict, axis_name: str) -> tuple[str, int] | None:
        """First visible Amplification skill name in this axis + a sensible level."""
        comp = cat["Types"][axis_name]["Niveaux"]["Amplification"]["Competences"]
        if not comp:
            return None
        # Use level 2 as default — a Transformation tier prereq should
        # ask for a meaningful investment, matching the original schema's
        # "(Niveau 2)" defaults.
        return comp[0]["Nom"], 2

    PART_RE = re.compile(r"^(.*?)\s*\(Niveau\s*(\d+)\)\s*$")

    def parse_part(part: str) -> tuple[str, str]:
        """Return (name, '(Niveau N)' or '') for one prereq fragment."""
        part = part.strip()
        m = PART_RE.match(part)
        if m:
            return m.group(1).strip(), f"(Niveau {m.group(2)})"
        # 'Name Niveau N' (humanité-style) — not present in skills.json,
        # but handle defensively.
        if " Niveau " in part:
            head, tail = part.rsplit(" Niveau ", 1)
            return head.strip(), f"Niveau {tail.strip()}"
        return part, ""

    repairs = 0
    for cat in d["catastrophes"]:
        vis = visible(cat)
        for axis_name, axis in cat["Types"].items():
            for tier_name, tier in axis["Niveaux"].items():
                for skill in tier["Competences"][:3]:
                    raw = skill.get("Prerequis")
                    if not raw or raw == "Aucun":
                        continue
                    parts = [p.strip() for p in raw.split("+")]
                    parsed = [parse_part(p) for p in parts]
                    visible_parts = [
                        (name, lvl) for (name, lvl) in parsed if name in vis
                    ]
                    if len(visible_parts) == len(parsed):
                        continue  # nothing broken
                    if visible_parts:
                        # Compound case: at least one part still visible
                        # — keep only the visible part(s).
                        new_req = " + ".join(
                            f"{name} {lvl}".strip()
                            for name, lvl in visible_parts
                        )
                    else:
                        # All parts hidden — redirect to the first
                        # visible Amplification skill of this axis,
                        # preserving the lowest level that was asked for.
                        fallback = first_visible_amplification(cat, axis_name)
                        if fallback is None:
                            continue
                        name, _ = fallback
                        # Use the lowest level required in the original
                        # prereq, defaulting to 2 if we can't recover it.
                        levels = []
                        for _, lvl in parsed:
                            m = re.search(r"\d+", lvl)
                            if m:
                                levels.append(int(m.group()))
                        level = min(levels) if levels else 2
                        new_req = f"{name} (Niveau {level})"
                    skill["Prerequis"] = new_req
                    repairs += 1

    print(f"Repaired {repairs} broken prereqs.")
    # Re-audit.
    re_broken = 0
    for cat in d["catastrophes"]:
        vis = visible(cat)
        for axis_name, axis in cat["Types"].items():
            for tier_name, tier in axis["Niveaux"].items():
                for skill in tier["Competences"][:3]:
                    raw = skill.get("Prerequis")
                    if not raw or raw == "Aucun":
                        continue
                    for part in raw.split("+"):
                        name, _ = parse_part(part.strip())
                        if name and name not in vis:
                            re_broken += 1
                            print(
                                f"  STILL BROKEN: {cat['Catastrophe']} / {axis_name}"
                                f" / {tier_name} / {skill['Nom']} -> {raw} (missing: {name})"
                            )
    print(f"Re-audit broken: {re_broken}")

    # Write back.
    with open(DATA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    print(f"Wrote {DATA}")


if __name__ == "__main__":
    main()
