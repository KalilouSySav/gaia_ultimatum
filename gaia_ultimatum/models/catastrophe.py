"""Catastrophe domain model."""

from __future__ import annotations

import contextlib
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from gaia_ultimatum.config import GameplayConfig

if TYPE_CHECKING:
    from gaia_ultimatum.models.world import World


@dataclass
class CatastrophePoint:
    position: tuple[float, float]
    lifetime: int
    max_lifetime: int
    value: int
    size: float
    country_id: str


@dataclass
class Catastrophe:
    name: str
    icon: str
    base_impact: float
    intensity: float = 1.0
    active_points: list[CatastrophePoint] = field(default_factory=list)

    def update(self, world: World, gameplay: GameplayConfig, rng: random.Random) -> None:
        """Age existing points and spawn new ones."""
        self._age_points()
        self._spawn_points(world, gameplay, rng)

    def _age_points(self) -> None:
        self.active_points = [p for p in self.active_points if self._tick(p)]

    @staticmethod
    def _tick(point: CatastrophePoint) -> bool:
        point.lifetime -= 1
        return point.lifetime > 0

    def _spawn_points(self, world: World, gameplay: GameplayConfig, rng: random.Random) -> None:
        base_probability = gameplay.point_spawn_probability * self.intensity
        lifetime_min, lifetime_max = gameplay.point_lifetime_range
        size_min, size_max = gameplay.point_size_range

        for country_id, country in world.countries.items():
            probability = base_probability * (1 + country.state / 2)
            if rng.random() >= probability:
                continue
            centroid_x, centroid_y = country.centroid
            lifetime = rng.randint(lifetime_min, lifetime_max)
            point = CatastrophePoint(
                position=(centroid_x + rng.uniform(-20, 20), centroid_y + rng.uniform(-20, 20)),
                lifetime=lifetime,
                max_lifetime=lifetime,
                value=int(5 * self.intensity * (1 + country.state / 2)),
                size=rng.uniform(size_min, size_max),
                country_id=country_id,
            )
            self.active_points.append(point)

    def remove_point(self, point: CatastrophePoint) -> None:
        with contextlib.suppress(ValueError):
            self.active_points.remove(point)
