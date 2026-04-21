"""Unit tests for the pure-state domain models."""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from gaia_ultimatum.config import DEFAULT_CONFIG
from gaia_ultimatum.models import (
    Catastrophe,
    Country,
    Gaia,
    Game,
    GameOutcome,
    Humans,
    World,
)
from gaia_ultimatum.models.country import _point_in_polygon

SQUARE_POLYGON = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]


def _minimal_geojson(tmp_path: Path) -> Path:
    payload = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"ISO_A3": "AAA", "ADMIN": "Alphaland", "pop_est": 1000},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]],
                },
            },
            {
                "type": "Feature",
                "properties": {"ISO_A3": "BBB", "ADMIN": "Betaland", "pop_est": 2000},
                "geometry": {
                    "type": "MultiPolygon",
                    "coordinates": [
                        [[[20, 0], [30, 0], [30, 10], [20, 10], [20, 0]]],
                    ],
                },
            },
        ],
    }
    path = tmp_path / "zones.geojson"
    path.write_text(json.dumps(payload))
    return path


def test_point_in_polygon_inside_and_outside() -> None:
    assert _point_in_polygon((5.0, 5.0), SQUARE_POLYGON) is True
    assert _point_in_polygon((20.0, 20.0), SQUARE_POLYGON) is False


def test_country_apply_catastrophe_monotonic() -> None:
    country = Country.new_random("X", "Xland", [SQUARE_POLYGON], 1000, rng=random.Random(1))
    assert country.state == 0.0
    country.apply_catastrophe(0.5)
    assert country.state > 0.0
    before = country.state
    country.apply_catastrophe(1.0)
    assert country.state >= before
    assert country.state <= 1.0


def test_country_defense_in_range() -> None:
    country = Country.new_random("X", "Xland", [SQUARE_POLYGON], 10, rng=random.Random(0))
    assert 0.0 <= country.defense <= 1.0


def test_world_loads_geojson(tmp_path: Path) -> None:
    world = World()
    world.load_countries(_minimal_geojson(tmp_path), rng=random.Random(0))
    assert set(world.countries) == {"AAA", "BBB"}
    assert world.countries["AAA"].name == "Alphaland"


def test_world_country_at_round_trips(tmp_path: Path) -> None:
    world = World()
    world.load_countries(_minimal_geojson(tmp_path), rng=random.Random(0))
    assert world.country_at((5.0, 5.0)) == "AAA"
    assert world.country_at((25.0, 5.0)) == "BBB"
    assert world.country_at((100.0, 100.0)) is None


def test_humans_update_weighted_average() -> None:
    world = World()
    world.countries["A"] = Country.new_random("A", "A", [SQUARE_POLYGON], 1000, random.Random(1))
    world.countries["B"] = Country.new_random("B", "B", [SQUARE_POLYGON], 3000, random.Random(2))
    humans = Humans()
    humans.update(world)
    assert 0.0 <= humans.global_progress <= 1.0


def test_gaia_cycles_catastrophes() -> None:
    gaia = Gaia()
    first = gaia.active
    gaia.next_catastrophe()
    assert gaia.active is not first


def test_catastrophe_spawns_and_ages_points() -> None:
    gaia = Gaia()
    catastrophe: Catastrophe = gaia.active
    world = World()
    world.countries["A"] = Country.new_random("A", "A", [SQUARE_POLYGON], 1000, random.Random(1))
    rng = random.Random(42)
    # High intensity makes spawns reliable for the test.
    catastrophe.intensity = 50.0
    catastrophe.update(world, DEFAULT_CONFIG.gameplay, rng)
    assert catastrophe.active_points, "expected at least one point to spawn"
    initial = len(catastrophe.active_points)
    for _ in range(DEFAULT_CONFIG.gameplay.point_lifetime_range[1] + 1):
        for point in catastrophe.active_points:
            point.lifetime = 0
        catastrophe.update(world, DEFAULT_CONFIG.gameplay, random.Random(0))
    assert len(catastrophe.active_points) <= initial + 1


def test_game_next_turn_progresses(tmp_path: Path) -> None:
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=123)
    assert game.turn == 0
    game.next_turn()
    assert game.turn == 1
    assert game.outcome is GameOutcome.IN_PROGRESS


def test_game_defeat_condition(tmp_path: Path) -> None:
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    for country in game.world.countries.values():
        country.dead = country.population
    game._check_outcome()
    assert game.outcome is GameOutcome.DEFEAT


def test_game_victory_condition(tmp_path: Path) -> None:
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    game.humans.global_progress = 0.99
    game._check_outcome()
    assert game.outcome is GameOutcome.VICTORY


def test_world_missing_file_raises(tmp_path: Path) -> None:
    from gaia_ultimatum.models.world import GeoJsonLoadError

    with pytest.raises(GeoJsonLoadError):
        World().load_countries(tmp_path / "does-not-exist.geojson")
