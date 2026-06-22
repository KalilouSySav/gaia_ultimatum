"""Trim redundant words from catastrophe skill names.

Most qualifiers in catastrophe names are load-bearing (they
distinguish across tiers and axes — e.g. "Régionale" vs "Mondiale"
mark Portée scale levels). The audit identified three names where a
qualifier adds no information:

1. **Terre Intensité "Onde Sismique Primaire/Secondaire"** — every
   skill in Terre is sismic by definition, so the "Sismique" inner
   word is pure noise. Rename to just **Onde Primaire** / **Onde
   Secondaire** (the existing **Onde de Surface** already follows
   this shorter pattern).

2. **Air Portée "Vent Local Violent"** — "Violent" is implicit at
   this tier (every Air catastrophe skill describes violent wind).
   Rename to **Vent Local**, matching the sibling **Vent Régional**.

3. **Air Portée "Cyclone de Grande Taille"** — five-word noun phrase
   for what other names get done in one or two words. Rename to
   **Cyclone Géant** — same meaning, half the length, and matches
   the existing **Orages Géants Mondiaux** / **Orage Géant Cyclique**
   "géant" vocabulary already used elsewhere.

Run from repo root::

    python tools/trim_catastrophe_names.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = REPO_ROOT / "gaia_ultimatum" / "data" / "skills.json"


# (catastrophe, old_name) → new_name. Scoping by catastrophe avoids
# accidentally touching same-named skills in unrelated catastrophes.
RENAMES = {
    ("Terre", "Onde Sismique Primaire"): "Onde Primaire",
    ("Terre", "Onde Sismique Secondaire"): "Onde Secondaire",
    ("Air", "Vent Local Violent"): "Vent Local",
    ("Air", "Cyclone de Grande Taille"): "Cyclone Géant",
}


def main() -> None:
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))

    n_nom = n_pre = 0
    for cat in data["catastrophes"]:
        cat_name = cat["Catastrophe"]
        for ax in cat["Types"].values():
            for tier in ax["Niveaux"].values():
                for sk in tier["Competences"]:
                    key = (cat_name, sk["Nom"])
                    if key in RENAMES:
                        sk["Nom"] = RENAMES[key]
                        n_nom += 1
                    pre = sk.get("Prerequis", "")
                    if not pre or pre == "Aucun":
                        continue
                    new = pre
                    # Only rewrite if the prereq is in this catastrophe
                    # (catastrophe prereqs don't cross catastrophes, so
                    # in-scope renames stay scoped correctly).
                    for (rc, old), repl in RENAMES.items():
                        if rc != cat_name:
                            continue
                        new = re.sub(rf"\b{re.escape(old)}\b", repl, new)
                    if new != pre:
                        sk["Prerequis"] = new
                        n_pre += 1

    JSON_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    sys.stdout.reconfigure(encoding="utf-8")
    print(f"Names renamed: {n_nom}")
    print(f"Prereq references updated: {n_pre}")

    # Sanity verify
    reloaded = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    for cat in reloaded["catastrophes"]:
        cat_name = cat["Catastrophe"]
        kept = set()
        for ax in cat["Types"].values():
            for tier in ax["Niveaux"].values():
                for sk in tier["Competences"]:
                    kept.add(sk["Nom"])
        broken = []
        for ax_name, ax in cat["Types"].items():
            for tier in ax["Niveaux"].values():
                for sk in tier["Competences"]:
                    pre = sk.get("Prerequis", "")
                    if pre == "Aucun":
                        continue
                    for token in re.split(r"\s*\+\s*", pre):
                        m = re.match(r"^(.+?) \(Niveau \d+\)$", token.strip())
                        if not m:
                            continue
                        if m.group(1) not in kept:
                            broken.append((cat_name, ax_name, sk["Nom"], token))
        if broken:
            print(f"\nBROKEN PREREQS in {cat_name}:")
            for b in broken:
                print(f"  {b}")

    # Show affected chains
    print("\n=== Affected chains after trim ===")
    for cat in reloaded["catastrophes"]:
        if cat["Catastrophe"] not in ("Terre", "Air"):
            continue
        for ax_name in ("Intensite", "Portee"):
            if ax_name not in cat["Types"]:
                continue
            print(f"\n  {cat['Catastrophe']}/{ax_name}:")
            for tier_name, tier in cat["Types"][ax_name]["Niveaux"].items():
                for sk in tier["Competences"]:
                    pre = sk.get("Prerequis", "Aucun")
                    print(f"    {tier_name[:4]}: {sk['Nom']:25s} ← {pre}")


if __name__ == "__main__":
    main()
