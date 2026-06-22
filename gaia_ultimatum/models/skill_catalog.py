"""Skill catalog: structured view over ``data/skills.json``.

The JSON is laid out as a Gaia-perspective tree::

    catastrophes:                     # 5 elements (Eau / Feu / Terre / Air / Vie)
        Catastrophe: <name>
        Types:                        # 4 axes per catastrophe
            <axis>:
                Niveaux:              # 3 tiers (Fondations / Amplification / Transformation)
                    <tier>:
                        Competences:  # 3 skills per tier
                            - Nom: <skill>
                              Description: <flavour>
                              Niveaux:    # 3 progressive levels per skill
                                  Niveau N:
                                      Effet: {<numeric facts>}
                                      Impact sur les indicateurs:
                                          <Indicator>: {Description, Valeur_de_Base, ...}
                                      Cout: <int>

This module exposes immutable dataclasses + a single ``load_skill_catalog`` entry
point. Consumers (renderer, evolution overlay, news) walk the catalog by name.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillLevel:
    cost: int
    effects: dict[str, str]                # raw "Effet" map: e.g. {"Rayon d'action": "10 km"}
    impact_descriptions: dict[str, str]    # indicator name -> educational description
    # ``indicator_impacts`` carries the JSON's per-indicator
    # (Valeur_de_Base, Facteur_Affinite) pair for this level. The loader
    # populated only ``impact_descriptions`` before — the numeric
    # weighting that drives skill power (4 / 8 / 12 across L1/L2/L3
    # on HUMANITÉ; richer on GAIA) was dropped on the floor, so every
    # purchase yielded the same hardcoded 0.04 indicator boost. With
    # this field, ``_apply_skill_effect`` can scale by level (and side)
    # using the per-skill data the JSON has carried all along.
    # Empty dict when the level had no ``Impact sur les indicateurs``
    # block, so existing call sites stay safe.
    indicator_impacts: dict[str, tuple[float, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    prerequis: str
    levels: tuple[SkillLevel, ...]
    # Globally-unique id "<catastrophe>:<axis>:<tier>:<name>" set at load time.
    id: str = ""


@dataclass(frozen=True)
class Tier:
    name: str    # Fondations / Amplification / Transformation
    skills: tuple[Skill, ...]


@dataclass(frozen=True)
class Axis:
    name: str    # Intensite / Portee / Duree / Impact Ecologique
    tiers: tuple[Tier, ...]


@dataclass(frozen=True)
class CatastropheCatalog:
    name: str    # Eau / Feu / Terre / Air / Vie
    axes: tuple[Axis, ...]

    def axis(self, name: str) -> Axis | None:
        lowered = name.lower()
        for axis in self.axes:
            if axis.name.lower() == lowered:
                return axis
        return None


@dataclass(frozen=True)
class SkillCatalog:
    """Catalog of catastrophe skills.

    ``catastrophes`` is the GAIA-side ladder (loaded from ``skills.json``).
    ``humanite_catastrophes`` mirrors the same structure but holds defensive
    counterparts loaded from ``skills_humanite.json``. The renderer + game
    logic call ``catalog_for_side`` to pick the right side at runtime.

    ``find_skill`` is called from per-frame render code (skill detail
    panel, outro tiles), so the catalog precomputes a flat ``id → Skill``
    index in ``__post_init__`` instead of walking the 5 × 4 × 3 × ~3
    skill tree on every call. The index is built once at construction
    and re-derived if anyone ever rebuilds the catalog.
    """
    catastrophes: tuple[CatastropheCatalog, ...] = field(default_factory=tuple)
    humanite_catastrophes: tuple[CatastropheCatalog, ...] = field(default_factory=tuple)
    # O(1) skill-id lookup. ``compare=False`` keeps equality / hash on
    # the two tuple fields only (so two catalogs with the same content
    # remain equal regardless of dict iteration order), ``init=False``
    # hides the field from the public constructor signature, and
    # ``__post_init__`` populates it from the tuples.
    _skill_index: dict[str, Skill] = field(
        default_factory=dict, repr=False, compare=False, init=False,
    )

    def __post_init__(self) -> None:
        index: dict[str, Skill] = {}
        # GAIA side first, then humanité — second write wins on
        # collision. Preserves the prior ``find_skill`` semantic of
        # walking ``humanite_catastrophes`` first.
        for source in (self.catastrophes, self.humanite_catastrophes):
            for cat in source:
                for axis in cat.axes:
                    for tier in axis.tiers:
                        for skill in tier.skills:
                            if skill.id:
                                index[skill.id] = skill
        # Frozen dataclass — bypass the setattr guard to install the
        # cache exactly once at construction.
        object.__setattr__(self, "_skill_index", index)

    def for_catastrophe(self, name: str) -> CatastropheCatalog | None:
        lowered = name.lower()
        for cat in self.catastrophes:
            if cat.name.lower() == lowered:
                return cat
        return None

    def catastrophes_for_side(self, side: str) -> tuple[CatastropheCatalog, ...]:
        if side == "humanite" and self.humanite_catastrophes:
            return self.humanite_catastrophes
        return self.catastrophes

    def for_catastrophe_side(
        self, name: str, side: str,
    ) -> CatastropheCatalog | None:
        """Like ``for_catastrophe`` but picks the side's catalog first; falls
        back to the GAIA catalog when the humanité version is missing."""
        lowered = name.lower()
        for cat in self.catastrophes_for_side(side):
            if cat.name.lower() == lowered:
                return cat
        return self.for_catastrophe(name)

    def find_skill(self, skill_id: str) -> Skill | None:
        """Look up a skill by its composite id ``cat:axis:tier:name``.

        Returns the humanité version when both sides ship the same id
        (matches the prior tree-walk order). O(1) via the
        ``_skill_index`` cache populated in ``__post_init__``.
        """
        if not skill_id:
            return None
        return self._skill_index.get(skill_id)


def _parse_catastrophe_list(
    payload_list: list[dict[str, Any]] | None,
) -> tuple[CatastropheCatalog, ...]:
    catastrophes: list[CatastropheCatalog] = []
    for cat_data in payload_list or []:
        cat_name = cat_data.get("Catastrophe")
        if not cat_name:
            continue
        axes: list[Axis] = []
        for axis_name, axis_data in (cat_data.get("Types") or {}).items():
            tiers: list[Tier] = []
            for tier_name, tier_data in (axis_data.get("Niveaux") or {}).items():
                skills: list[Skill] = []
                for comp in tier_data.get("Competences") or []:
                    # Pass the composite-id context so ``_parse_skill``
                    # can stamp the id directly. Previously the parser
                    # built a Skill with id="" and threw it away to
                    # build a second one with the real id — wasteful
                    # double allocation per skill across ~150 skills.
                    skills.append(
                        _parse_skill(comp, context=f"{cat_name}:{axis_name}:{tier_name}")
                    )
                tiers.append(Tier(name=tier_name, skills=tuple(skills)))
            axes.append(Axis(name=axis_name, tiers=tuple(tiers)))
        catastrophes.append(CatastropheCatalog(name=cat_name, axes=tuple(axes)))
    return tuple(catastrophes)


def load_skill_catalog(path: Path) -> SkillCatalog:
    """Load and parse the skill catalog from JSON.

    Also looks for ``skills_humanite.json`` next to ``skills.json`` to fill
    the humanité-side defensive ladder. Both files are optional and the game
    remains playable when either is missing.
    """
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Skill catalog unavailable at %s: %s", path, exc)
        return SkillCatalog()
    catastrophes = _parse_catastrophe_list(payload.get("catastrophes"))

    # Side b — humanité countermeasures live in skills_humanite.json by
    # default, sitting alongside skills.json.
    humanite_cats: tuple[CatastropheCatalog, ...] = ()
    h_path = Path(path).with_name("skills_humanite.json")
    if h_path.is_file():
        try:
            h_payload = json.loads(h_path.read_text(encoding="utf-8"))
            humanite_cats = _parse_catastrophe_list(
                h_payload.get("humanite_catastrophes")
            )
            logger.info(
                "Loaded humanité catalog: %d catastrophes from %s",
                len(humanite_cats), h_path,
            )
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Humanité catalog unreadable (%s); skipping", exc)

    logger.info("Loaded skill catalog: %d catastrophes from %s", len(catastrophes), path)
    return SkillCatalog(
        catastrophes=catastrophes,
        humanite_catastrophes=humanite_cats,
    )


def _parse_skill(comp: dict[str, Any], *, context: str = "") -> Skill:
    """Parse one JSON ``Competence`` block into a :class:`Skill`.

    ``context`` is the ``"<cat>:<axis>:<tier>"`` prefix; combined with
    the skill's name it produces the globally-unique ``Skill.id``.
    Passing context here lets the parser stamp the id in a single
    allocation instead of building a half-formed Skill and immediately
    cloning it.
    """
    name = str(comp.get("Nom") or "?")
    levels: list[SkillLevel] = []
    for level_name, level_data in (comp.get("Niveaux") or {}).items():
        # Some skills carry stray scalar siblings next to the Niveau N dicts
        # (e.g. an orphan "Cout: 15" key in skills.json). Skip those silently.
        if not isinstance(level_data, dict):
            logger.debug(
                "Skill %s: skipping non-dict niveau %r (%s)",
                name,
                level_name,
                type(level_data).__name__,
            )
            continue
        effet = level_data.get("Effet")
        effects = (
            {str(k): str(v) for k, v in effet.items()} if isinstance(effet, dict) else {}
        )
        impact_descriptions: dict[str, str] = {}
        indicator_impacts: dict[str, tuple[float, float]] = {}
        impacts = level_data.get("Impact sur les indicateurs")
        if isinstance(impacts, dict):
            for indicator, details in impacts.items():
                if isinstance(details, dict):
                    desc = details.get("Description")
                    if desc:
                        impact_descriptions[str(indicator)] = str(desc)
                    # Capture the (Valeur_de_Base, Facteur_Affinite)
                    # pair so consumers can drive mechanics from the
                    # JSON instead of hardcoding. Both must parse to
                    # numerics for the entry to land in the dict —
                    # malformed values silently skip rather than
                    # raising so a half-edited JSON doesn't blow up
                    # the whole catalog load.
                    vdb = details.get("Valeur_de_Base")
                    fa = details.get("Facteur_Affinite")
                    if isinstance(vdb, (int, float)) and isinstance(
                        fa, (int, float),
                    ):
                        indicator_impacts[str(indicator)] = (
                            float(vdb), float(fa),
                        )
        levels.append(
            SkillLevel(
                cost=int(level_data.get("Cout") or 0),
                effects=effects,
                impact_descriptions=impact_descriptions,
                indicator_impacts=indicator_impacts,
            )
        )
    return Skill(
        name=name,
        description=str(comp.get("Description") or ""),
        prerequis=str(comp.get("Prerequis") or "Aucun"),
        levels=tuple(levels),
        id=f"{context}:{name}" if context else "",
    )
