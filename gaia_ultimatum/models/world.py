"""World domain model: a collection of countries loaded from GeoJSON."""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from gaia_ultimatum.models.country import Country, Polygon

logger = logging.getLogger(__name__)


class GeoJsonLoadError(RuntimeError):
    """Raised when the GeoJSON map data cannot be loaded."""


class World:
    """Map of countries plus camera state (scale + pan offset)."""

    def __init__(self) -> None:
        self.countries: dict[str, Country] = {}
        self.scale: float = 1.0
        self.offset_x: float = 0.0
        self.offset_y: float = 0.0
        self.selected_country: str | None = None

    def load_countries(self, geojson_path: Path, rng: random.Random | None = None) -> None:
        """Load countries from a Natural Earth-style GeoJSON file.

        Expected properties per feature: ``ISO_A3`` (id), ``ADMIN`` (name),
        ``pop_est`` (population). Missing values fall back to safe defaults.
        """
        rng = rng or random.Random()
        try:
            payload = json.loads(Path(geojson_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise GeoJsonLoadError(f"Failed to load GeoJSON at {geojson_path}: {exc}") from exc

        for feature in payload.get("features", []):
            country = self._parse_feature(feature, rng)
            if country is not None:
                self.countries[country.id] = country

        logger.info("Loaded %d countries from %s", len(self.countries), geojson_path)

    @staticmethod
    def _parse_feature(feature: dict, rng: random.Random) -> Country | None:
        properties = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        country_id = properties.get("ISO_A3") or properties.get("iso_a3")
        name = properties.get("ADMIN") or properties.get("name")
        if not country_id or not name:
            return None
        population = int(properties.get("pop_est") or 1_000_000)
        polygons = _extract_polygons(geometry)
        if not polygons:
            return None
        return Country.new_random(country_id, name, polygons, population, rng=rng)

    def transform_point(self, point: tuple[float, float], screen_size: tuple[int, int]) -> tuple[float, float]:
        width, height = screen_size
        x = point[0] * self.scale + self.offset_x + width / 2
        y = -point[1] * self.scale + self.offset_y + height / 2
        return (x, y)

    def inverse_transform(
        self, screen_point: tuple[float, float], screen_size: tuple[int, int]
    ) -> tuple[float, float]:
        width, height = screen_size
        map_x = (screen_point[0] - width / 2 - self.offset_x) / self.scale
        map_y = -(screen_point[1] - height / 2 - self.offset_y) / self.scale
        return (map_x, map_y)

    def country_at(self, map_point: tuple[float, float]) -> str | None:
        for country_id, country in self.countries.items():
            if country.contains(map_point):
                return country_id
        return None


def _extract_polygons(geometry: dict) -> list[Polygon]:
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    polygons: list[Polygon] = []
    if geom_type == "Polygon":
        if coordinates:
            polygons.append([(c[0], c[1]) for c in coordinates[0]])
    elif geom_type == "MultiPolygon":
        for part in coordinates:
            if part:
                polygons.append([(c[0], c[1]) for c in part[0]])
    return polygons
