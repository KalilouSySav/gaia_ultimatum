"""Gaia — planetary antagonist that orchestrates catastrophes."""

from __future__ import annotations

from dataclasses import dataclass, field

from gaia_ultimatum.models.catastrophe import Catastrophe


def _default_catastrophes() -> list[Catastrophe]:
    """Five elemental catastrophes, matching the keys in ``data/skills.json``.

    Names are kept terse (Eau, Feu, Terre, Air, Vie) so that:
      * UI badges render cleanly at small sizes,
      * lookup against the SkillCatalog is a direct case-insensitive match.
    """
    return [
        # Eau — floods and tsunamis: slow but very wide along coasts and rivers.
        Catastrophe(
            name="Eau",
            icon="water.png",
            base_impact=0.011,
            spread_neighbors=4,
            spread_distance_half=35.0,
            jump_chance=0.0,
            point_color=(60, 140, 230),
            arc_color=(60, 140, 230),
        ),
        # Feu — wildfires: fast, mid-range; no oceanic jumps.
        Catastrophe(
            name="Feu",
            icon="fire.png",
            base_impact=0.018,
            spread_neighbors=3,
            spread_distance_half=22.0,
            jump_chance=0.0,
            point_color=(235, 110, 50),
            arc_color=(235, 110, 50),
        ),
        # Terre — earthquakes: short range, devastating local impact.
        Catastrophe(
            name="Terre",
            icon="earth.png",
            base_impact=0.024,
            spread_neighbors=2,
            spread_distance_half=10.0,
            jump_chance=0.0,
            point_color=(200, 145, 80),
            arc_color=(200, 145, 80),
        ),
        # Air — storms / hurricanes: wide range, occasional jumps as fronts move.
        # Colour bumped from (175, 205, 225) — that pale cyan tested too
        # close to the ocean-grid tone + the amber-affected country
        # fills, so Air orbs and spread arcs read as washed-out against
        # the world map. (130, 190, 235) keeps the sky-cyan identity
        # but raises saturation and shifts toward true blue so the
        # element pops against every state colour while still feeling
        # distinct from Eau's deeper (60, 140, 230).
        Catastrophe(
            name="Air",
            icon="air.png",
            base_impact=0.013,
            spread_neighbors=3,
            spread_distance_half=30.0,
            jump_chance=0.04,
            point_color=(130, 190, 235),
            arc_color=(130, 190, 235),
        ),
        # Vie — pandemics: short-range with intercontinental air-travel jumps.
        Catastrophe(
            name="Vie",
            icon="life.png",
            base_impact=0.014,
            spread_neighbors=2,
            spread_distance_half=18.0,
            jump_chance=0.06,
            point_color=(120, 220, 130),
            arc_color=(120, 220, 130),
        ),
    ]


@dataclass
class Gaia:
    catastrophes: list[Catastrophe] = field(default_factory=_default_catastrophes)
    active_index: int = 0

    @property
    def active(self) -> Catastrophe:
        return self.catastrophes[self.active_index]

    def next_catastrophe(self) -> Catastrophe:
        self.active_index = (self.active_index + 1) % len(self.catastrophes)
        return self.active

    def prev_catastrophe(self) -> Catastrophe:
        self.active_index = (self.active_index - 1) % len(self.catastrophes)
        return self.active

    def update(self, human_impact: float) -> None:
        intensity = 1.0 + human_impact * 2.0
        for catastrophe in self.catastrophes:
            catastrophe.intensity = intensity
