"""Country domain model."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

Point = tuple[float, float]
Polygon = list[Point]


@dataclass
class Country:
    id: str
    name: str
    polygons: list[Polygon]
    population: int
    state: float = 0.0
    affected: int = 0
    dead: int = 0
    resilience: float = 0.5
    stability: float = 0.5
    regeneration: float = 0.5
    adaptation: float = 0.5
    centroid: Point = field(default=(0.0, 0.0))

    @classmethod
    def new_random(
        cls,
        id: str,
        name: str,
        polygons: list[Polygon],
        population: int,
        rng: random.Random | None = None,
    ) -> Country:
        rng = rng or random.Random()
        country = cls(
            id=id,
            name=name,
            polygons=polygons,
            population=population,
            resilience=rng.uniform(0.3, 0.7),
            stability=rng.uniform(0.3, 0.7),
            regeneration=rng.uniform(0.3, 0.7),
            adaptation=rng.uniform(0.3, 0.7),
        )
        country.centroid = country._centroid()
        return country

    def _centroid(self) -> Point:
        if not self.polygons or not self.polygons[0]:
            return (0.0, 0.0)
        polygon = self.polygons[0]
        count = len(polygon)
        sum_x = sum(p[0] for p in polygon)
        sum_y = sum(p[1] for p in polygon)
        return (sum_x / count, sum_y / count)

    @property
    def defense(self) -> float:
        return (self.resilience + self.stability + self.regeneration + self.adaptation) / 4.0

    def apply_catastrophe(self, catastrophe_impact: float) -> None:
        effective_impact = catastrophe_impact * (1.0 - self.defense * 0.8)
        self.state = min(1.0, self.state + effective_impact)
        self.affected = int(self.population * self.state * 0.8)
        self.dead = int(self.population * self.state * 0.2)

    def contains(self, point: Point) -> bool:
        return any(_point_in_polygon(point, polygon) for polygon in self.polygons)


def _point_in_polygon(point: Point, polygon: Polygon) -> bool:
    """Ray-casting algorithm."""
    if not polygon:
        return False
    x, y = point
    n = len(polygon)
    inside = False
    p1x, p1y = polygon[0]
    xinters = 0.0
    for i in range(n + 1):
        p2x, p2y = polygon[i % n]
        if min(p1y, p2y) < y <= max(p1y, p2y) and x <= max(p1x, p2x):
            if p1y != p2y:
                xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
            if p1x == p2x or x <= xinters:
                inside = not inside
        p1x, p1y = p2x, p2y
    return inside
