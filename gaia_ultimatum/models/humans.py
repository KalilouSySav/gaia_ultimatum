"""Humanity's global balance state."""

from __future__ import annotations

from dataclasses import dataclass

from gaia_ultimatum.models.catastrophe import CatastrophePoint
from gaia_ultimatum.models.world import World


@dataclass
class Humans:
    global_progress: float = 0.0
    evolution_points: int = 0

    def update(self, world: World) -> None:
        """Recompute global progress as a population-weighted average of balance indicators."""
        total_weight = 0
        weighted_progress = 0.0
        for country in world.countries.values():
            weight = country.population
            total_weight += weight
            indicator = (
                country.resilience
                + country.stability
                + country.regeneration
                + country.adaptation
            ) / 4.0
            weighted_progress += indicator * weight
        if total_weight > 0:
            self.global_progress = weighted_progress / total_weight

    def collect_point(self, point: CatastrophePoint) -> int:
        self.evolution_points += point.value
        return point.value
