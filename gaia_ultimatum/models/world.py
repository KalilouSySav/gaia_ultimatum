"""World domain model: a collection of countries loaded from GeoJSON."""

from __future__ import annotations

import json
import logging
import random
from pathlib import Path

from gaia_ultimatum.assets import DATA_DIR
from gaia_ultimatum.models.country import Country, Polygon

logger = logging.getLogger(__name__)

# ISO_A3 → {name_fr, population} overrides loaded from data/country_overrides.json.
# Keeps the GeoJSON itself (Natural-Earth-style) untouched while giving every
# major country a realistic 2023/2024 population estimate and a proper French
# display name. Countries missing from the overrides keep their English ADMIN
# name and a 1 M fallback population.
_OVERRIDES_PATH = DATA_DIR / "country_overrides.json"
_COUNTRY_OVERRIDES: dict[str, dict] = {}


def _load_overrides() -> dict[str, dict]:
    global _COUNTRY_OVERRIDES
    if _COUNTRY_OVERRIDES:
        return _COUNTRY_OVERRIDES
    try:
        payload = json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "country_overrides.json unavailable (%s); using GeoJSON defaults",
            exc,
        )
        return {}
    _COUNTRY_OVERRIDES = {
        iso: entry for iso, entry in payload.items()
        if isinstance(entry, dict) and "name_fr" in entry
    }
    logger.info(
        "Loaded %d country overrides (FR name + population)",
        len(_COUNTRY_OVERRIDES),
    )
    return _COUNTRY_OVERRIDES


class GeoJsonLoadError(RuntimeError):
    """Raised when the GeoJSON map data cannot be loaded."""


class World:
    """Map of countries plus camera state (scale + pan offset)."""

    def __init__(self) -> None:
        self.countries: dict[str, Country] = {}
        # Bumped from 1.0 — at unit scale the world only spans ~360px in
        # the 1200x800 viewport, leaving the map tiny and unreadable. 1.5
        # sits just under the labels-visible threshold (1.6) so we stay in
        # overview mode.
        self.scale: float = 1.5
        self.offset_x: float = 0.0
        self.offset_y: float = 0.0
        # Vertical shift applied on top of (height / 2) when projecting
        # world → screen. Lets the renderer push the world down (or up)
        # so it sits centred inside the *visible* map area rather than
        # the raw canvas centre — different phases reserve different
        # amounts of vertical space (top bar, picker title, news bar,
        # nav buttons), so the visible centre is rarely at height / 2.
        # Click hit-tests via ``inverse_transform`` read the same value,
        # so screen pixel ↔ world point stays consistent.
        self.view_center_y: float = 0.0
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
        name = properties.get("ADMIN") or properties.get("name")

        # ``-99`` is the Natural Earth sentinel for "no real ISO-3166
        # code" — assigned to disputed regions (Kosovo, Northern
        # Cyprus, Somaliland), sovereign base areas (Akrotiri,
        # Dhekelia), uninhabited reefs (Spratly, Scarborough), and a
        # handful of military/space exclaves. Without filtering, all
        # of those collapse onto a single ``world.countries["-99"]``
        # entry (last-write-wins), so 17 distinct features in the
        # bundled GeoJSON used to silently overwrite each other —
        # Kosovo got eaten by Pitcairn's neighbour ID etc. Treat
        # ``-99`` as falsy so the ``or``-chain falls through to the
        # next field, eventually landing on ``name`` and giving each
        # disputed/exclave region a unique country_id keyed on its
        # ADMIN name.
        def _real(value: object) -> str | None:
            v = str(value) if value is not None else ""
            return v if v and v != "-99" else None

        country_id = (
            _real(properties.get("ISO_A3"))
            or _real(properties.get("iso_a3"))
            or _real(properties.get("ADM0_A3"))
            or name
        )
        if not country_id or not name:
            return None
        # Apply French-name + realistic-population override when one exists.
        # Falls back to the GeoJSON's English ADMIN name + a 1 M placeholder
        # for tiny entries not in the overrides file.
        overrides = _load_overrides().get(country_id)
        if overrides is not None:
            name = overrides.get("name_fr") or name
            population = int(
                overrides.get("population")
                or properties.get("pop_est")
                or 1_000_000
            )
        else:
            population = int(properties.get("pop_est") or 1_000_000)
        polygons, holes = _extract_polygons(geometry)
        if not polygons:
            return None
        return Country.new_random(
            country_id, name, polygons, population, rng=rng, holes=holes,
        )

    def transform_point(self, point: tuple[float, float], screen_size: tuple[int, int]) -> tuple[float, float]:
        width, height = screen_size
        x = point[0] * self.scale + self.offset_x + width / 2
        y = -point[1] * self.scale + self.offset_y + height / 2 + self.view_center_y
        return (x, y)

    def inverse_transform(
        self, screen_point: tuple[float, float], screen_size: tuple[int, int]
    ) -> tuple[float, float]:
        width, height = screen_size
        map_x = (screen_point[0] - width / 2 - self.offset_x) / self.scale
        map_y = -(
            screen_point[1] - height / 2 - self.offset_y - self.view_center_y
        ) / self.scale
        return (map_x, map_y)

    def country_at(self, map_point: tuple[float, float]) -> str | None:
        for country_id, country in self.countries.items():
            if country.contains(map_point):
                return country_id
        return None

    def country_at_lenient(
        self, map_point: tuple[float, float],
        hit_radius_px: float = 14.0,
    ) -> str | None:
        """Like ``country_at`` but with a centroid-distance fallback.

        Why: tiny island polygons (Fiji, Marshall Islands, Kiribati,
        Tuvalu, etc.) are only a few pixels wide at default zoom, so
        the strict polygon ray-cast in ``country_at`` requires pixel-
        perfect clicks. Players complained right-edge islands felt
        unreachable.

        Strategy:
          1. Try strict polygon containment first — preserves behaviour
             for mainland clicks (no surprise snapping to a nearby
             country).
          2. If nothing was hit, return the country whose centroid is
             closest to the click and lies within ``hit_radius_px``
             screen pixels of it (converted through ``self.scale``).
             Mainland centroids are typically far from coastlines, so
             they don't false-match clicks that land in the ocean a
             few pixels off an island.

        ``hit_radius_px`` is screen-pixels at the current zoom so the
        forgiveness window stays roughly constant on-screen.
        """
        direct = self.country_at(map_point)
        if direct is not None:
            return direct
        if hit_radius_px <= 0 or self.scale <= 0:
            return None
        tolerance_world = hit_radius_px / self.scale
        best_id: str | None = None
        best_d = tolerance_world
        mx, my = map_point
        for country_id, country in self.countries.items():
            cx, cy = country.centroid
            dx = mx - cx
            dy = my - cy
            d = (dx * dx + dy * dy) ** 0.5
            if d < best_d:
                best_d = d
                best_id = country_id
        return best_id


def _extract_polygons(geometry: dict) -> tuple[list[Polygon], list[Polygon]]:
    """Extract outer rings *and* interior holes from a GeoJSON geometry.

    Returns ``(outer_rings, hole_rings)``. The previous version
    silently dropped interior rings, which broke enclave hit-detection
    (clicks inside Lesotho matched both Lesotho's polygon and South
    Africa's outer polygon, with dict-iteration order picking the
    winner non-deterministically). Now holes are carried through to
    ``Country.holes`` and excluded by ``Country.contains``.

    For MultiPolygon geometries, all parts' holes are pooled into one
    flat ``hole_rings`` list — semantically a "country-wide" exclusion
    set. This is sound for the bundled dataset because no part's hole
    falls inside another part's outer ring (the only country with a
    hole is South Africa, and it's a single Polygon).
    """
    geom_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    polygons: list[Polygon] = []
    holes: list[Polygon] = []
    if geom_type == "Polygon":
        if coordinates:
            polygons.append([(c[0], c[1]) for c in coordinates[0]])
            # coordinates[1:] are interior rings (holes) of this polygon.
            for ring in coordinates[1:]:
                if ring:
                    holes.append([(c[0], c[1]) for c in ring])
    elif geom_type == "MultiPolygon":
        for part in coordinates:
            if part:
                polygons.append([(c[0], c[1]) for c in part[0]])
                for ring in part[1:]:
                    if ring:
                        holes.append([(c[0], c[1]) for c in ring])
    return polygons, holes
