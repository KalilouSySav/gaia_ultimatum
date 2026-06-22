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
from gaia_ultimatum.models.game import (
    CLUSTER_CASCADE_PRESSURE_BY_COUNT,
    GAIA_INDICATOR_DAMAGE_PER_SKILL,
    INDICATOR_BOOST_PER_SKILL,
    MILESTONES,
    Phase,
    _SYNERGY_BONUS_BY_TIER,
)

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
    # Population set to 10 M — the centre of the spawn-loop's log-scaled
    # ``pop_bias`` curve (pop_bias = 1.0 at 10 M, clamped to [0.5, 2.0]).
    # The earlier ``population=1000`` triggered the 0.5 floor and halved
    # the effective spawn probability, breaking the deterministic-spawn
    # invariant this test relies on.
    world.countries["A"] = Country.new_random("A", "A", [SQUARE_POLYGON], 10_000_000, random.Random(1))
    rng = random.Random(42)
    # High intensity makes spawns reliable for the test — base spawn prob
    # has been tightened across production tuning (0.005 → 0.0035 →
    # 0.0020 → 0.0010), so the headroom needs to grow each time. 5000.0
    # keeps 0.0010 × 5000 = 5.0 effective spawn probability — well past
    # the 1.0 ceiling so the first country roll is guaranteed regardless
    # of seed, and the test stays robust to one more spawn-rate halving.
    catastrophe.intensity = 5000.0
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


def test_game_defeat_by_critical_share(tmp_path: Path) -> None:
    """Secondary defeat path: when ≥75 % of *population* (not country
    count) lives in critical-state regions (state ≥ 0.5), defeat fires
    even with no recorded deaths. Lock-in for the population-weighted
    threshold so a future swap back to the old country-count metric
    can't silently regress the secondary defeat path.
    """
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    # All countries tipped critical, zero recorded deaths — the primary
    # mortality threshold (0.65) can't fire, so any defeat must come
    # from the secondary critical-share path.
    for country in game.world.countries.values():
        country.state = 0.6
        country.dead = 0
    game._check_outcome()
    assert game.outcome is GameOutcome.DEFEAT


def test_world_missing_file_raises(tmp_path: Path) -> None:
    from gaia_ultimatum.models.world import GeoJsonLoadError

    with pytest.raises(GeoJsonLoadError):
        World().load_countries(tmp_path / "does-not-exist.geojson")


# ---------------------------------------------------------------------------
# Touch-mode (Android / pygbag) tap-target sizing
# ---------------------------------------------------------------------------


def test_touch_mode_grows_small_ui_rects_to_min_target() -> None:
    """Every UI rect that was sub-48 on its shortest axis must reach the
    MIN_TOUCH_TARGET when ``display.touch_mode`` is on.

    Pinned because the Play Store build (and any future Android port)
    depends on these — a regression that quietly shrinks any of these
    rects back below 48 would re-create the "finger taps miss the
    audio toggle" UX bug.
    """
    from dataclasses import replace
    from gaia_ultimatum.config import DEFAULT_CONFIG, MIN_TOUCH_TARGET
    from gaia_ultimatum.view.renderer import (
        audio_toggle_rect,
        close_button_rect,
        help_button_rect,
        settings_close_rect,
        settings_toggle_rects,
        skill_tree_close_button_rect,
        tutorial_button_rect,
    )

    touch_config = replace(
        DEFAULT_CONFIG,
        display=replace(DEFAULT_CONFIG.display, touch_mode=True),
    )
    desktop_config = DEFAULT_CONFIG

    # Single-rect helpers — assert shortest-axis growth.
    single_rect_fns = [
        audio_toggle_rect,
        help_button_rect,
        tutorial_button_rect,
        settings_close_rect,
        close_button_rect,
        skill_tree_close_button_rect,
    ]
    for fn in single_rect_fns:
        touch = fn(touch_config)
        desktop = fn(desktop_config)
        assert min(touch.width, touch.height) >= MIN_TOUCH_TARGET, (
            f"{fn.__name__} short axis = {min(touch.width, touch.height)} "
            f"< {MIN_TOUCH_TARGET} in touch_mode"
        )
        # Sanity — desktop should stay at its original (smaller) size.
        assert min(desktop.width, desktop.height) < MIN_TOUCH_TARGET or (
            fn is audio_toggle_rect  # audio uses 56 wide on both
        ), f"{fn.__name__} unexpectedly already ≥ {MIN_TOUCH_TARGET} on desktop"

    # Dict-returning helpers — every value rect must meet the bound.
    for key, rect in settings_toggle_rects(touch_config).items():
        assert min(rect.width, rect.height) >= MIN_TOUCH_TARGET, (
            f"settings_toggle_rects[{key!r}] short axis = "
            f"{min(rect.width, rect.height)} < {MIN_TOUCH_TARGET}"
        )


def test_touch_mode_env_override_propagates_to_config() -> None:
    """``GAIA_TOUCH_MODE=1`` env var flips ``display.touch_mode`` so the
    Play Store / pygbag wrappers can force-enable touch UI from outside
    Python without editing config.json."""
    import os
    from gaia_ultimatum.config import load_config

    saved = os.environ.get("GAIA_TOUCH_MODE")
    try:
        os.environ["GAIA_TOUCH_MODE"] = "1"
        assert load_config().display.touch_mode is True
        os.environ["GAIA_TOUCH_MODE"] = "0"
        assert load_config().display.touch_mode is False
    finally:
        if saved is None:
            os.environ.pop("GAIA_TOUCH_MODE", None)
        else:
            os.environ["GAIA_TOUCH_MODE"] = saved


# ---------------------------------------------------------------------------
# Milestone player-side severity translation
# ---------------------------------------------------------------------------


def _arm_only_milestone(game: Game, ident: str) -> None:
    """Lock every milestone except ``ident`` so a single ``_check_milestones``
    call exercises one predicate in isolation."""
    for entry in MILESTONES:
        if entry[0] != ident:
            game.unlocked_milestones.add(entry[0])


def _trigger_milestone(game: Game, ident: str) -> str | None:
    """Run ``_check_milestones`` with only ``ident`` armed and return the
    severity of the milestone banner the predicate produced.

    ``speed = 0`` suppresses the auto-pause path on intrinsic-critical
    events, which otherwise stacks a second "critical" banner from
    ``push_event_card`` onto the deque and would mask the milestone's
    own (potentially translated) severity.
    """
    game.speed = 0
    game.milestone_banners.clear()
    _arm_only_milestone(game, ident)
    game._check_milestones()
    if not game.milestone_banners:
        return None
    return game.milestone_banners[0].severity


def test_milestone_favors_gaia_critical_flips_to_trophy_for_gaia_player(
    tmp_path: Path,
) -> None:
    """A defeat-approach milestone (``favors='gaia'``, base ``critical``) shows
    as ``trophy`` to the GAIA player — their attack is landing — while the
    HUMANITÉ player sees it as ``critical`` — their fight is failing."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    for country in game.world.countries.values():
        country.dead = int(country.population * 0.15)  # well past 10 %
    game.player_side = "gaia"
    assert _trigger_milestone(game, "ten_pct_dead") == "trophy"

    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    for country in game.world.countries.values():
        country.dead = int(country.population * 0.15)
    game.player_side = "humanite"
    assert _trigger_milestone(game, "ten_pct_dead") == "critical"


def test_milestone_favors_humanite_trophy_flips_to_warning_for_gaia_player(
    tmp_path: Path,
) -> None:
    """``victory_imminent`` is ``favors='humanite'``, base ``trophy``. The
    HUMANITÉ player sees the trophy; the GAIA player sees a ``warning``
    (their grip is slipping)."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    game.humans.global_progress = 0.72
    game.player_side = "humanite"
    assert _trigger_milestone(game, "victory_imminent") == "trophy"

    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    game.humans.global_progress = 0.72
    game.player_side = "gaia"
    assert _trigger_milestone(game, "victory_imminent") == "warning"


def test_milestone_favors_neutral_keeps_base_severity(tmp_path: Path) -> None:
    """``first_evolution`` is ``favors='neutral'``: both sides see the same
    trophy register because the marker means the same thing to both."""
    for side in ("gaia", "humanite"):
        game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
        game.purchased_skills["any:Intensite:Fondations:X"] = 1
        game.player_side = side
        assert _trigger_milestone(game, "first_evolution") == "trophy"


def test_milestone_favors_news_prefix_tracks_effective_severity(
    tmp_path: Path,
) -> None:
    """News ticker prefix follows ``effective_severity``, not base. A GAIA
    player on a ``critical`` defeat-approach event reads "Jalon" (trophy
    register), not "Bascule" (critical register)."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    for country in game.world.countries.values():
        country.dead = int(country.population * 0.15)
    game.player_side = "gaia"
    game.speed = 0  # suppress auto-pause news noise
    _arm_only_milestone(game, "ten_pct_dead")
    game._check_milestones()
    assert any(n.startswith("Jalon") for n in game.news)
    assert not any(n.startswith("Bascule") for n in game.news)


def test_milestone_no_duplicate_banner_when_auto_pausing(
    tmp_path: Path,
) -> None:
    """A critical milestone that auto-pauses must push exactly ONE banner.

    Regression for the player-visible bug where two near-identical
    banners appeared simultaneously: the milestone banner (bare title)
    plus the auto-pause banner (title + "— Espace pour reprendre.").
    The fix combines the suffix into the milestone banner upfront and
    calls ``_auto_pause(..., with_banner=False)`` so the pause-side
    push_event_card no longer duplicates the milestone banner.
    """
    for side in ("gaia", "humanite"):
        game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
        for country in game.world.countries.values():
            country.dead = int(country.population * 0.15)
        game.player_side = side
        game.phase = Phase.PLAYING
        game.speed = 3  # > 0 so auto-pause path engages
        _arm_only_milestone(game, "ten_pct_dead")
        game._check_milestones()
        assert game.speed == 0, "auto-pause must still fire"
        assert len(game.milestone_banners) == 1, (
            f"expected exactly 1 banner for {side}, "
            f"got {len(game.milestone_banners)}: "
            f"{[(b.title, b.severity) for b in game.milestone_banners]}"
        )
        only_banner = game.milestone_banners[0]
        assert "Espace pour reprendre" in only_banner.title, (
            "the single banner must carry the resume hint"
        )


def test_milestone_auto_pause_keys_on_base_severity_not_effective(
    tmp_path: Path,
) -> None:
    """Auto-pause must trigger on intrinsic ``critical`` events even when
    the player-translated severity is ``trophy`` (a GAIA player still needs
    to pause and read the "10 % dead" beat — that's their celebration
    moment)."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    for country in game.world.countries.values():
        country.dead = int(country.population * 0.15)
    game.player_side = "gaia"
    game.phase = Phase.PLAYING
    game.speed = 3  # > 0 so _auto_pause has something to pause from
    _arm_only_milestone(game, "ten_pct_dead")
    game._check_milestones()
    assert game.speed == 0, "auto-pause should fire on base critical regardless of side"
    assert "ten_pct_dead" in game.auto_paused_classes


# ---------------------------------------------------------------------------
# JSON-driven indicator boost/damage scaling
# ---------------------------------------------------------------------------


def _eau_skill_id(side: str) -> str:
    """Pick the ``Eau:Intensite:Fondations`` opener for the side, which both
    catalogs ship with the canonical 4/8/12 VdB progression on Resilience."""
    return (
        "Eau:Intensite:Fondations:Crue Éclair"
        if side == "gaia"
        else "Eau:Intensite:Fondations:Digues de Protection"
    )


def test_indicator_boost_scales_linearly_with_json_vdb(tmp_path: Path) -> None:
    """L1=4 / L2=8 / L3=12 VdB → 1× / 2× / 3× ``INDICATOR_BOOST_PER_SKILL``,
    so every ÉN spent yields the same indicator gain regardless of level."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    skill_id = _eau_skill_id("humanite")
    # Resilience Technologique is the Intensite axis's matched indicator.
    boosts = [
        game._indicator_boost_for_level(skill_id, level, "resilience")
        for level in (1, 2, 3)
    ]
    assert boosts[0] == pytest.approx(INDICATOR_BOOST_PER_SKILL * 1.0)
    assert boosts[1] == pytest.approx(INDICATOR_BOOST_PER_SKILL * 2.0)
    assert boosts[2] == pytest.approx(INDICATOR_BOOST_PER_SKILL * 3.0)


def test_indicator_damage_folds_facteur_affinite(tmp_path: Path) -> None:
    """GAIA damage formula = ``GAIA_INDICATOR_DAMAGE_PER_SKILL × (vdb/4) × fa``.
    Crue Éclair's Resilience has VdB=4, Fa=0.8 at L1, so L1 damage is
    ``0.02 × 1.0 × 0.8 = 0.016`` — Fa < 1 dampens, Regeneration's Fa=1.2 lifts."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    skill_id = _eau_skill_id("gaia")
    res_l1 = game._indicator_damage_for_level(skill_id, 1, "resilience")
    regen_l1 = game._indicator_damage_for_level(skill_id, 1, "regeneration")
    assert res_l1 == pytest.approx(GAIA_INDICATOR_DAMAGE_PER_SKILL * 1.0 * 0.8)
    # Crue Éclair L1 Regeneration: VdB=6, Fa=1.2.
    assert regen_l1 == pytest.approx(GAIA_INDICATOR_DAMAGE_PER_SKILL * (6 / 4.0) * 1.2)


def test_indicator_boost_falls_back_to_flat_constant_when_unknown(
    tmp_path: Path,
) -> None:
    """Unknown skill id and unknown attribute both return the flat
    ``INDICATOR_BOOST_PER_SKILL`` baseline — never regress to weaker
    than the pre-refactor behaviour."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    assert game._indicator_boost_for_level("nope:nope:nope:nope", 1, "resilience") == (
        INDICATOR_BOOST_PER_SKILL
    )
    assert game._indicator_boost_for_level(
        _eau_skill_id("humanite"), 1, "nonexistent_attr",
    ) == INDICATOR_BOOST_PER_SKILL


def test_indicator_damage_returns_zero_when_catalog_missing(
    tmp_path: Path,
) -> None:
    """GAIA path returns 0 (no bonus damage) when the JSON lacks data —
    catastrophe-parameter mutation still runs from ``_apply_skill_effect``,
    so the buy never regresses to harmless."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    assert game._indicator_damage_for_level("nope:nope:nope:nope", 1, "resilience") == 0.0


# ---------------------------------------------------------------------------
# Orb expiration damage
# ---------------------------------------------------------------------------


def test_orb_expiration_damages_host_country() -> None:
    """An expired orb applies ``base_impact × intensity × ORB_EXPIRATION_DAMAGE_FRACTION``
    to its host country and is removed from ``active_points``."""
    gaia = Gaia()
    catastrophe = gaia.active
    world = World()
    world.countries["A"] = Country.new_random(
        "A", "A", [SQUARE_POLYGON], 10_000_000, random.Random(1),
    )
    # Bake the orb manually to control lifetime and host id deterministically.
    from gaia_ultimatum.models.catastrophe import CatastrophePoint

    catastrophe.active_points.append(
        CatastrophePoint(
            position=(5.0, 5.0),
            lifetime=1,
            max_lifetime=1,
            value=10,
            size=1.0,
            country_id="A",
        )
    )
    host = world.countries["A"]
    state_before = host.state
    # _age_points decrements to 0 then applies expiration damage.
    catastrophe._age_points(world)
    assert catastrophe.active_points == [], "expired orb must be removed"
    assert host.state > state_before, "host should take expiration damage"


def test_orb_expiration_skipped_when_host_collapsed() -> None:
    """Expired orbs don't damage already-collapsed countries (state ≥ 1.0
    can't go higher — no point inflicting more)."""
    gaia = Gaia()
    catastrophe = gaia.active
    world = World()
    world.countries["A"] = Country.new_random(
        "A", "A", [SQUARE_POLYGON], 10_000_000, random.Random(1),
    )
    world.countries["A"].state = 1.0
    from gaia_ultimatum.models.catastrophe import CatastrophePoint

    catastrophe.active_points.append(
        CatastrophePoint(
            position=(5.0, 5.0),
            lifetime=1,
            max_lifetime=1,
            value=10,
            size=1.0,
            country_id="A",
        )
    )
    state_before = world.countries["A"].state
    catastrophe._age_points(world)
    assert catastrophe.active_points == []
    assert world.countries["A"].state == state_before, "collapsed host should be skipped"


def test_orb_expiration_skipped_when_host_missing() -> None:
    """Orb pointing to a no-longer-present country id is removed cleanly
    without raising."""
    gaia = Gaia()
    catastrophe = gaia.active
    world = World()  # empty world — host lookup returns None.
    from gaia_ultimatum.models.catastrophe import CatastrophePoint

    catastrophe.active_points.append(
        CatastrophePoint(
            position=(0.0, 0.0),
            lifetime=1,
            max_lifetime=1,
            value=10,
            size=1.0,
            country_id="ghost",
        )
    )
    catastrophe._age_points(world)  # must not raise
    assert catastrophe.active_points == []


# ---------------------------------------------------------------------------
# Cluster cascade pressure
# ---------------------------------------------------------------------------


def _square_at(cx: float, cy: float, half: float = 1.0) -> list[tuple[float, float]]:
    return [
        (cx - half, cy - half),
        (cx + half, cy - half),
        (cx + half, cy + half),
        (cx - half, cy + half),
    ]


def _make_cluster_world(
    n_critical: int, target_offset: float = 0.0,
) -> tuple[Game, Country]:
    """Build a world where the target sits at the origin and ``n_critical``
    neighbours sit nearby in critical state. Returns the game and the
    target country."""
    # Single country dataset — we only need _apply_spread to walk the
    # cluster loop. Use Game.create's geojson loader with a tmp file
    # would be heavyweight; build directly instead.
    game = Game(rng=random.Random(0))
    # Target at origin, far from any cluster default — no spread will hit it
    # directly because we'll keep its state below SPREAD_INFECTED_THRESHOLD.
    target = Country.new_random("T", "T", [_square_at(0.0, 0.0)], 1_000_000, random.Random(1))
    target.state = target_offset
    game.world.countries["T"] = target
    # n neighbours close enough to land in the 4-nearest set, each above
    # CLUSTER_CRITICAL_NEIGHBOUR_STATE.
    for i in range(n_critical):
        nid = f"N{i}"
        c = Country.new_random(nid, nid, [_square_at(0.5 + i * 0.1, 0.5)], 1_000, random.Random(2))
        c.state = 0.8
        game.world.countries[nid] = c
    return game, target


def test_cluster_cascade_no_pressure_under_three_neighbours() -> None:
    """Fewer than 3 critical neighbours → no cluster pressure applied."""
    game, target = _make_cluster_world(n_critical=2)
    state_before = target.state
    game._apply_spread(game.gaia.active)
    assert target.state == pytest.approx(state_before)


def test_cluster_cascade_three_neighbours_applies_low_pressure() -> None:
    """3 critical neighbours → 0.20 cascade pressure applied to target."""
    game, target = _make_cluster_world(n_critical=3)
    state_before = target.state
    game._apply_spread(game.gaia.active)
    assert target.state > state_before
    assert CLUSTER_CASCADE_PRESSURE_BY_COUNT[3] == pytest.approx(0.20)


def test_cluster_cascade_four_neighbours_applies_more_pressure_than_three() -> None:
    """4 critical neighbours bring the heavier 0.40 multiplier — strictly
    more damage than the 3-neighbour bucket under identical input."""
    game_3, target_3 = _make_cluster_world(n_critical=3)
    game_4, target_4 = _make_cluster_world(n_critical=4)
    # Make both targets identical so the only varying input is the cluster.
    target_3.resilience = target_4.resilience = 0.5
    target_3.stability = target_4.stability = 0.5
    target_3.regeneration = target_4.regeneration = 0.5
    target_3.adaptation = target_4.adaptation = 0.5
    target_3.vulnerability = target_4.vulnerability = {}
    game_3._apply_spread(game_3.gaia.active)
    game_4._apply_spread(game_4.gaia.active)
    assert target_4.state > target_3.state
    assert CLUSTER_CASCADE_PRESSURE_BY_COUNT[4] == pytest.approx(0.40)


# ---------------------------------------------------------------------------
# Synergy bonus per-tier + revoke
# ---------------------------------------------------------------------------


def _humanite_fondations_skill_ids(game: Game, cat: str, axis: str) -> list[str]:
    catalog = game.skill_catalog.for_catastrophe_side(cat, "humanite")
    assert catalog is not None
    axis_obj = catalog.axis(axis)
    assert axis_obj is not None
    for tier in axis_obj.tiers:
        if tier.name == "Fondations":
            return [sk.id for sk in tier.skills]
    raise AssertionError("Fondations tier missing")


def test_synergy_bonus_fires_on_tier_completion(tmp_path: Path) -> None:
    """Completing every skill in a Fondations tier pays the +10 ÉN synergy
    bonus once (and only once)."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    game.player_side = "humanite"
    # The active catastrophe might cycle; pin it to Eau so the JSON lookup
    # in _check_axis_synergy matches the skill id we use.
    while game.gaia.active.name != "Eau":
        game.gaia.next_catastrophe()
    skill_ids = _humanite_fondations_skill_ids(game, "Eau", "Intensite")
    # Mark all three as owned (skip the cost path so the test is focused
    # on the synergy logic, not the wider purchase pipeline).
    for sid in skill_ids:
        game.purchased_skills[sid] = 1
    points_before = game.humans.evolution_points
    game._check_axis_synergy(skill_ids[-1])
    assert game.humans.evolution_points == points_before + _SYNERGY_BONUS_BY_TIER["Fondations"]
    # Idempotent — re-calling does nothing.
    game._check_axis_synergy(skill_ids[-1])
    assert game.humans.evolution_points == points_before + _SYNERGY_BONUS_BY_TIER["Fondations"]


def test_synergy_bonus_revoked_when_tier_broken(tmp_path: Path) -> None:
    """Breaking a previously-completed tier deducts the same bonus back,
    capped at 0 so the player can't end up with negative ÉN."""
    game = Game.create(geojson_path=_minimal_geojson(tmp_path), seed=0)
    game.player_side = "humanite"
    while game.gaia.active.name != "Eau":
        game.gaia.next_catastrophe()
    skill_ids = _humanite_fondations_skill_ids(game, "Eau", "Intensite")
    for sid in skill_ids:
        game.purchased_skills[sid] = 1
    game._check_axis_synergy(skill_ids[-1])
    points_after_bonus = game.humans.evolution_points
    # Drop one skill below the synergy threshold — by deleting the entry
    # _revoke_synergy_if_broken sees it as 0 owned.
    del game.purchased_skills[skill_ids[0]]
    game._revoke_synergy_if_broken(skill_ids[0])
    assert game.humans.evolution_points == max(
        0, points_after_bonus - _SYNERGY_BONUS_BY_TIER["Fondations"],
    )


def test_synergy_bonus_per_tier_magnitude() -> None:
    """The three tier bonuses keep their documented magnitudes — a guard
    so a future tuning change can't drift one tier silently."""
    assert _SYNERGY_BONUS_BY_TIER["Fondations"] == 10
    assert _SYNERGY_BONUS_BY_TIER["Amplification"] == 20
    assert _SYNERGY_BONUS_BY_TIER["Transformation"] == 30


# ---------------------------------------------------------------------------
# Per-indicator strategic roles
# ---------------------------------------------------------------------------


def test_adaptation_reduces_mortality() -> None:
    """``mortality_coef = 0.70 × (1.0 - 0.4 × adaptation)`` — a fully-
    adapted country loses 40 % fewer lives than a zero-adaptation one
    at the same state level."""
    low = Country.new_random("L", "L", [SQUARE_POLYGON], 10_000_000, random.Random(1))
    high = Country.new_random("H", "H", [SQUARE_POLYGON], 10_000_000, random.Random(1))
    low.adaptation = 0.0
    high.adaptation = 1.0
    low.state = high.state = 0.6
    low.recompute_population_impact()
    high.recompute_population_impact()
    assert high.dead < low.dead
    # The high-adaptation country's dead count should be roughly
    # 0.42/0.70 = 60 % of the low-adaptation count (40 % reduction).
    assert high.dead == pytest.approx(low.dead * 0.6, rel=0.01)


def test_regeneration_speeds_recovery() -> None:
    """``regenerate()`` scales the per-turn rate by ``1 + 0.5 × regeneration``
    — a fully-regen country bounces back 1.5× faster than a zero-regen one."""
    low = Country.new_random("L", "L", [SQUARE_POLYGON], 10_000_000, random.Random(1))
    high = Country.new_random("H", "H", [SQUARE_POLYGON], 10_000_000, random.Random(1))
    # Damaged, but inside the recovery window (state < RECOVERY_CUTOFF=0.40).
    low.state = high.state = 0.10
    # Zero out one indicator on each so we can watch it climb without
    # baseline floors interfering with the comparison.
    low.resilience = high.resilience = 0.0
    low.baseline_resilience = high.baseline_resilience = 0.7
    low.regeneration = 0.0
    high.regeneration = 1.0
    low.baseline_regeneration = 0.0
    high.baseline_regeneration = 1.0
    low.regenerate()
    high.regenerate()
    # Both gained on resilience; the high-regen country gained strictly more.
    assert high.resilience > low.resilience > 0.0


def test_adaptation_mortality_is_monotonic_floor() -> None:
    """``dead`` only ratchets up — a later boost in adaptation cannot
    un-die already-counted casualties."""
    c = Country.new_random("X", "X", [SQUARE_POLYGON], 10_000_000, random.Random(1))
    c.adaptation = 0.0
    c.state = 0.7
    c.recompute_population_impact()
    high_water = c.dead
    # Bump adaptation up to its max — recomputing must not lower the count.
    c.adaptation = 1.0
    c.recompute_population_impact()
    assert c.dead >= high_water
