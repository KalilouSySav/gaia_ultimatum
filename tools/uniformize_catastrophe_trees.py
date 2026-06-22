"""Uniformize CATASTROPHE skill trees to 3+3+3 per axis.

Pre-rework state was non-uniform:

  * Feu        — already 3+3+3 (Int/Por/Dur), 3+4+4 (Impact Eco)
  * Eau/Terre/Vie — 3+5+5 (Int/Por/Dur), 3+4+4 (Impact Eco)
  * Air        — 3+5+5 (Int/Por/Dur), 3+4+5 (Impact Eco)

After rework: every axis across every catastrophe has exactly 3 Fond +
3 Ampl + 3 Trans = 9 skills, matching HUMANITÉ's structure. 59 skills
removed total.

Selection rule — **keep the first 3 skills in each Ampl/Trans tier
list** (the canonical / primary picks in the original ordering) and
drop the trailing ones. This is verified by inspection to leave every
remaining skill's prereq pointing to a kept skill — no rewiring needed.
Cross-axis prereqs to dropped skills are also handled (only one such
edge existed, ``Effondrement de la Régulation Climatique`` in Air's
Impact Eco pointed at Hypercane in Air's Intensité — both dropped).

Fond tiers are untouched (already 3 skills each, and the catastrophe
side intentionally chains Fond skills as an escalation arc, which is
preserved).

Run from repo root::

    python tools/uniformize_catastrophe_trees.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    target_size = {"Amplification": 3, "Transformation": 3}
    dropped: list[tuple[str, str, str, str]] = []
    for cat in data["catastrophes"]:
        for ax_name, ax in cat["Types"].items():
            for tier_name, tier in ax["Niveaux"].items():
                if tier_name not in target_size:
                    continue
                comp = tier["Competences"]
                limit = target_size[tier_name]
                if len(comp) <= limit:
                    continue
                for sk in comp[limit:]:
                    dropped.append(
                        (cat["Catastrophe"], ax_name, tier_name, sk["Nom"])
                    )
                tier["Competences"] = comp[:limit]

    # Validate no remaining prereq references a dropped skill. Prereqs
    # can be cross-axis within the same catastrophe (e.g. Feu/Portee's
    # ``Aérosols de Combustion`` requires ``Feu de Cime`` from
    # Feu/Intensité), so the kept-set is scoped per catastrophe, not per
    # axis.
    kept_per_cat: dict[str, set[str]] = {}
    for cat in data["catastrophes"]:
        names: set[str] = set()
        for ax in cat["Types"].values():
            for tier in ax["Niveaux"].values():
                for sk in tier["Competences"]:
                    names.add(sk["Nom"])
        kept_per_cat[cat["Catastrophe"]] = names

    broken: list[tuple[str, str, str, str]] = []
    for cat in data["catastrophes"]:
        kept = kept_per_cat[cat["Catastrophe"]]
        for ax_name, ax in cat["Types"].items():
            for tier in ax["Niveaux"].values():
                for sk in tier["Competences"]:
                    pre = sk.get("Prerequis", "")
                    if pre == "Aucun":
                        continue
                    # Catastrophe prereqs can carry multiple targets joined by '+'
                    for token in re.split(r"\s*\+\s*", pre):
                        m = re.match(r"^(.+?) \(Niveau \d+\)$", token.strip())
                        if not m:
                            continue
                        target = m.group(1)
                        if target not in kept:
                            broken.append(
                                (cat["Catastrophe"], ax_name, sk["Nom"], token)
                            )

    if broken:
        sys.stdout.reconfigure(encoding="utf-8")
        print("ABORT — dropping would leave broken prereqs:")
        for b in broken:
            print(f"  {b}")
        return

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Skills dropped: {len(dropped)}")
    print("\nDropped breakdown:")
    by_cat: dict[str, int] = {}
    for cat_name, _, _, _ in dropped:
        by_cat[cat_name] = by_cat.get(cat_name, 0) + 1
    for cat_name, count in by_cat.items():
        print(f"  {cat_name}: {count}")

    # Show resulting sizes
    print("\n=== Resulting tree sizes ===")
    for cat in data["catastrophes"]:
        sizes_per_axis = []
        for ax_name, ax in cat["Types"].items():
            sizes = [len(t["Competences"]) for t in ax["Niveaux"].values()]
            sizes_per_axis.append(f"{ax_name}={tuple(sizes)}")
        print(f"  {cat['Catastrophe']}: {', '.join(sizes_per_axis)}")


if __name__ == "__main__":
    main()
