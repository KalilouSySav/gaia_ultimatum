"""Catastrophe domain model."""

from __future__ import annotations

import contextlib
import math
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
    # Spread profile.
    spread_neighbors: int = 3          # candidate neighbors per source per turn
    spread_distance_half: float = 25.0  # degrees where spread chance halves
    jump_chance: float = 0.0            # per-source per-turn long-distance jump probability
    # Visual identity.
    point_color: tuple[int, int, int] = (220, 60, 50)
    arc_color: tuple[int, int, int] = (220, 60, 50)

    # Fraction of catastrophe ``base_impact`` applied to an orb's host
    # country when the orb expires uncollected. Half of normal impact —
    # significant enough that the player notices missed orbs as a
    # mechanical cost, conservative enough that an out-of-reach orb
    # isn't game-ending. Composes with the country's existing
    # ``defense`` reduction (well-defended countries take less
    # expiration damage), so investing in indicators provides a
    # double benefit: easier orb collection AND smaller penalty when
    # an orb does slip away.
    #
    # Before this mechanic, expired orbs silently vanished — no
    # urgency to collect, no consequence to ignore. The orb system
    # was pure upside (collect → ÉN), turning the map into a passive
    # currency-grind layer rather than a strategic decision surface
    # ("which orb to chase next given the regional crisis"). Letting
    # missed orbs deal a small parting blow turns each spawn into a
    # genuine choice the player has to make under time pressure.
    ORB_EXPIRATION_DAMAGE_FRACTION = 0.5

    def update(self, world: World, gameplay: GameplayConfig, rng: random.Random) -> None:
        """Age existing points and spawn new ones."""
        self._age_points(world)
        self._spawn_points(world, gameplay, rng)

    def _age_points(self, world: World) -> None:
        """Tick lifetimes and apply expiration damage to hosts.

        Each orb whose lifetime drops to zero applies a small fraction
        of normal catastrophe impact to its host country before being
        removed. Skipped if the host has already collapsed (state ≥
        1.0) — no benefit to inflicting more damage on a country whose
        defeat is already counted.
        """
        survivors: list[CatastrophePoint] = []
        for point in self.active_points:
            point.lifetime -= 1
            if point.lifetime > 0:
                survivors.append(point)
                continue
            # Orb expired uncollected — consolation damage to host.
            host = world.countries.get(point.country_id)
            if host is None or host.state >= 1.0:
                continue
            host.apply_catastrophe(
                self.base_impact
                * self.intensity
                * self.ORB_EXPIRATION_DAMAGE_FRACTION,
                element=self.name,
            )
        self.active_points = survivors

    # Hard cap on simultaneous points on screen — was uncapped which let
    # spawn rate × country count × turn cadence produce a sea of dots.
    # Tightened progressively: ∞ → 16 → 8 → 5 → 4 → 3 → 2 so the canvas
    # stays focused. Never more than 2 high-value orbs visible at once.
    MAX_ACTIVE_POINTS = 2

    def _spawn_points(self, world: World, gameplay: GameplayConfig, rng: random.Random) -> None:
        remaining = self.MAX_ACTIVE_POINTS - len(self.active_points)
        if remaining <= 0:
            return
        base_probability = gameplay.point_spawn_probability * self.intensity
        lifetime_min, lifetime_max = gameplay.point_lifetime_range
        size_min, size_max = gameplay.point_size_range

        # Iterate countries in shuffled order so we don't always favour the
        # same ones when the cap is tight. Stop as soon as we hit the cap.
        # Two bias multipliers stack on top of base_probability:
        #
        #   * ``state_bias`` (1.0 → 3.0): critical zones get 3× the spawn
        #     rate of a fresh country, so chasing damage feels strategic.
        #   * ``pop_bias`` (0.5 → 2.0, log-scaled, centred at 10 M people):
        #     a 1 B-people country (China / India) gets ~2× base spawn,
        #     a 1 M-people country (Estonia, Botswana) gets ~0.7×, a
        #     50 k-people atoll (Nauru, Tuvalu) gets the 0.5× floor.
        #     Combined with ``MAX_ACTIVE_POINTS=2``, this keeps the 2
        #     active slots landing over countries where collecting an
        #     orb actually shifts the simulation. Previously a 1 B
        #     country and a 50 k atoll competed for the same slot at
        #     equal odds — wasteful given the population-weighted
        #     impact on the global indicator.
        country_items = list(world.countries.items())
        rng.shuffle(country_items)
        spawned = 0
        for country_id, country in country_items:
            if spawned >= remaining:
                break
            # Collapsed countries (state >= 1.0) no longer host new
            # orbs. Three reasons stacked:
            #   1. Value formula peaks at state=1.0 — the orb on a
            #      dead country was a *maximum*-value ÉN gift
            #      (``18 · intensity · (0.7 + 1.0·0.8)`` = the
            #      highest possible single-orb yield).
            #   2. Collecting it doesn't move the simulation: the
            #      country can't degrade further, so the player
            #      gets a free strategic no-op — degenerate optimum.
            #   3. Visual intent — orbs mark "the catastrophe is
            #      *escalating* here". A collapsed country isn't
            #      escalating, the run there is over. Letting orbs
            #      keep popping on dead countries contradicted that
            #      reading and confused players ("why is there an
            #      orb on a 100 % country?").
            # Skip ineligible hosts before the RNG roll so the
            # bounded ``MAX_ACTIVE_POINTS`` budget actually lands on
            # viable countries.
            if country.state >= 1.0:
                continue
            state_bias = 1.0 + country.state * 2.0
            # Log10(pop / 10M) → 0 at 10 M people, +1 at 100 M, +2 at 1 B,
            # −2 at 100 k. Mapped to factor: 1.0 at centre, clamped
            # outside [0.5, 2.0] so the floor protects small countries
            # from never spawning and the ceiling prevents one giant
            # from monopolising every orb.
            pop_log = math.log10(max(1e3, country.population) / 1e7)
            pop_bias = max(0.5, min(2.0, 1.0 + 0.5 * pop_log))
            probability = base_probability * state_bias * pop_bias
            if rng.random() >= probability:
                continue
            centroid_x, centroid_y = country.centroid
            lifetime = rng.randint(lifetime_min, lifetime_max)
            point = CatastrophePoint(
                position=(centroid_x + rng.uniform(-20, 20), centroid_y + rng.uniform(-20, 20)),
                lifetime=lifetime,
                max_lifetime=lifetime,
                # Value also scales by state — high-stress orbs are
                # worth more, so chasing them is strategic, not pure
                # busywork.
                #
                # Base coefficient: 95 → 35 → 18 → 36 across rounds.
                # The 18-coefficient era paired with a 0.0020 spawn rate
                # produced an orb-every-3-turns cadence: too many small
                # collections, the run felt like click-spam over its
                # 30-40 day arc. Spawn rate is now halved (0.0010 in
                # config.py) and value DOUBLED here so the total
                # ÉN-per-minute stays identical but the player clicks
                # half as often — each orb is now a 24-162 ÉN payout
                # (NORMAL × intensity × state), large enough to buy
                # 2-3 median skills in one collect instead of 1-2.
                # Same strategic depth, half the wrist work.
                value=int(36 * self.intensity * (0.7 + country.state * 0.8)),
                size=rng.uniform(size_min, size_max),
                country_id=country_id,
            )
            self.active_points.append(point)
            spawned += 1

    def remove_point(self, point: CatastrophePoint) -> None:
        with contextlib.suppress(ValueError):
            self.active_points.remove(point)
