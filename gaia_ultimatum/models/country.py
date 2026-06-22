"""Country domain model."""

from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

from gaia_ultimatum.models.country_profiles import CountryProfile, profile_for

Point = tuple[float, float]
Polygon = list[Point]

STATE_HISTORY_LEN = 6

# Per-element decay distribution for the four equilibrium indicators.
# Each tuple is ``(resilience, stability, regeneration, adaptation)``
# scaled relative to the ``decay`` base. Total per-row stays ≈ 4.0 so
# the *magnitude* of indicator damage from one tick is the same as the
# old uniform (1.10, 1.20, 0.90, 0.80) distribution — only the *shape*
# changes, which gives each catastrophe its own educational signature:
#
#   * **Eau** (floods / tsunamis): infrastructure + displacement
#     dominate. Wetland renewal and soil enrichment limit regeneration
#     loss, so its decay coefficient is the lowest of the five.
#   * **Feu** (wildfires): ecosystem-driven. Regeneration takes the
#     hardest hit; adaptation barely changes because the response
#     pattern is established.
#   * **Terre** (earthquakes): infrastructure shock. Resilience drops
#     hardest, adaptation least (a quake reveals preparedness but
#     doesn't re-teach it on a single tick).
#   * **Air** (storms / hurricanes): mid-range across the board with
#     a slight tilt toward resilience (structural damage) and stability
#     (evacuation churn).
#   * **Vie** (pandemics): social cohesion bears the largest hit; the
#     remaining decay spreads roughly even across the others.
#
# Catastrophes outside this map (or ``element=None``) fall back to
# ``_DEFAULT_DECAY_PROFILE``, which is the historical uniform tuning.
_ELEMENT_DECAY_PROFILES: dict[str, tuple[float, float, float, float]] = {
    "Eau":   (1.15, 1.25, 0.70, 0.90),
    "Feu":   (1.00, 1.05, 1.40, 0.55),
    "Terre": (1.50, 1.20, 0.80, 0.50),
    "Air":   (1.20, 1.15, 0.95, 0.70),
    "Vie":   (0.90, 1.50, 0.80, 0.80),
}
_DEFAULT_DECAY_PROFILE: tuple[float, float, float, float] = (1.10, 1.20, 0.90, 0.80)


# Per-turn auto-recovery window for the four equilibrium indicators.
# Was a binary cutoff at state ≥ 0.25 — a country at state 0.249 healed
# at the full rate (~24 turns to regain 1 full indicator point), while
# one at state 0.251 healed at zero. That 0.002-state cliff produced a
# perceived "stuck" feeling when a borderline country drifted just over
# the line.
#
# New shape: full rate up to ``RECOVERY_FULL_BELOW``, then a quadratic
# ease-out down to zero at ``RECOVERY_CUTOFF`` — moderately-stressed
# countries get a small but nonzero lifeline (matches reality: even a
# half-affected region partly recovers between disaster waves), while
# the deep critical zone still locks recovery out so HUMANITÉ skills
# remain the only way back from a serious tip.
#
# Tuning rationale: 0.20 → 0.40 is roughly the "stressed but not
# critical" band. State ≥ 0.5 is the "zone critique" threshold the
# rest of the UI uses, so ``RECOVERY_CUTOFF = 0.40`` stays clear of
# it — a country in genuine critical state never auto-heals.
RECOVERY_FULL_BELOW = 0.20
RECOVERY_CUTOFF = 0.40

# Floor that ``regenerate()`` recovers indicators *up to* — countries
# with low archetype baselines (arid_sahelian resilience 0.30, etc.)
# drift here, not to their natural baseline. This is the central
# winning-strategy tuning value: it sits deliberately below the
# 0.75 victory threshold (``GameplayConfig.victory_threshold``) so
# passive recovery alone can never carry HUMANITÉ to victory —
# defense = avg of 4 indicators is capped at 0.7 in the passive
# limit, and the gap to 0.75 must be closed by skill purchases.
# Was a local literal inside ``regenerate``; hoisted to sit
# alongside the other two recovery constants so the three values
# that shape the recovery dynamics are discoverable together.
RECOVERY_FLOOR = 0.70


@dataclass
class Country:
    id: str
    name: str
    polygons: list[Polygon]
    population: int
    # Interior rings (holes) extracted from GeoJSON Polygon coordinates
    # past index 0. Only one country in the bundled dataset has a hole
    # — South Africa's polygon has Lesotho as an interior ring. Without
    # this, ``contains()`` returns True for both ZAF and LSO on a click
    # inside Lesotho, and dict-iteration order chose the winner (a
    # subtle determinism bug for enclave clicks). Listing all holes
    # flat across all the country's outer polygons is correct for the
    # current dataset because no hole of one polygon falls inside the
    # interior of another polygon of the same country.
    holes: list[Polygon] = field(default_factory=list)
    state: float = 0.0
    affected: int = 0
    dead: int = 0
    resilience: float = 0.5
    stability: float = 0.5
    regeneration: float = 0.5
    adaptation: float = 0.5
    # Archetype baselines — set at construction from the country's
    # profile and never mutated. `regenerate()` targets these so a
    # high-baseline country (polar_isolated stability 0.80,
    # tropical_forest regeneration 0.80) recovers to its full
    # archetype value instead of being capped at the global 0.7
    # recovery floor.
    baseline_resilience: float = 0.5
    baseline_stability: float = 0.5
    baseline_regeneration: float = 0.5
    baseline_adaptation: float = 0.5
    # Per-catastrophe vulnerability multiplier — 1.0 is neutral, > 1 = more
    # vulnerable (faster damage), < 1 = more resilient. Sourced from the
    # country's archetype in ``country_profiles.py``.
    vulnerability: dict[str, float] = field(default_factory=dict)
    profile_name: str = "neutral"
    centroid: Point = field(default=(0.0, 0.0))
    state_history: deque[float] = field(
        default_factory=lambda: deque(maxlen=STATE_HISTORY_LEN)
    )

    @classmethod
    def new_random(
        cls,
        id: str,
        name: str,
        polygons: list[Polygon],
        population: int,
        rng: random.Random | None = None,
        *,
        holes: list[Polygon] | None = None,
    ) -> Country:
        """Build a country with archetype-aware baseline indicators.

        The archetype (``country_profiles.profile_for(id)``) sets a
        characteristic baseline for the four indicators and a per-element
        vulnerability dict. A small ±0.05 jitter keeps countries within an
        archetype slightly distinct so two "developed_temperate" neighbours
        don't have identical stats.
        """
        rng = rng or random.Random()
        profile = profile_for(id)
        jitter = 0.05

        def _baseline(value: float) -> float:
            return max(0.05, min(0.95, value + rng.uniform(-jitter, jitter)))

        country = cls(
            id=id,
            name=name,
            polygons=polygons,
            holes=list(holes) if holes else [],
            population=population,
            resilience=_baseline(profile.resilience),
            stability=_baseline(profile.stability),
            regeneration=_baseline(profile.regeneration),
            adaptation=_baseline(profile.adaptation),
            # Baselines (no jitter) — recovery targets that preserve
            # archetype identity after damage.
            baseline_resilience=profile.resilience,
            baseline_stability=profile.stability,
            baseline_regeneration=profile.regeneration,
            baseline_adaptation=profile.adaptation,
            vulnerability=dict(profile.vulnerability),
            profile_name=profile.name,
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

    def apply_catastrophe(
        self,
        catastrophe_impact: float,
        element: str | None = None,
    ) -> None:
        """Apply a single tick of catastrophe damage.

        ``element`` is the catastrophe name (Eau / Feu / Terre / Air / Vie)
        and selects a per-country vulnerability multiplier so countries
        respond realistically — Bangladesh degrades fast under Eau, the
        Sahel under Feu, Japan under Terre, etc. Falls back to the neutral
        multiplier (1.0) when the element isn't provided or known.
        """
        vuln = 1.0
        if element and self.vulnerability:
            vuln = self.vulnerability.get(element, 1.0)
        effective_impact = catastrophe_impact * vuln * (1.0 - self.defense * 0.8)
        self.state = min(1.0, self.state + effective_impact)
        self.recompute_population_impact()
        # Damage degrades the four equilibrium indicators so the global
        # "ÉQUILIBRE PLANÉTAIRE" bar actually responds to gameplay. Without
        # this, indicators stayed at their random init values forever and
        # neither victory nor defeat thresholds moved. The per-element
        # decay profile (see module-level ``_ELEMENT_DECAY_PROFILES``)
        # shifts the distribution to match each catastrophe's real-world
        # damage signature while preserving the same total magnitude per
        # tick, so global balance impact is unchanged.
        decay = effective_impact * 0.55
        mr, ms, mg, ma = _ELEMENT_DECAY_PROFILES.get(
            element or "", _DEFAULT_DECAY_PROFILE,
        )
        self.resilience   = max(0.0, self.resilience   - decay * mr)
        self.stability    = max(0.0, self.stability    - decay * ms)
        self.regeneration = max(0.0, self.regeneration - decay * mg)
        self.adaptation   = max(0.0, self.adaptation   - decay * ma)

    def recompute_population_impact(self) -> None:
        """Recompute ``affected`` / ``dead`` from the current ``state``.

        Single source of truth for the population-impact formula —
        called by ``apply_catastrophe`` *and* by every seed path
        (patient zero, long-distance jump, ``start_with_country``)
        that mutates ``state`` directly without going through the
        normal damage tick.

        - ``affected`` scales linearly with state (people "impacted but
          alive": 85 % of population at full collapse). Recoverable —
          if the future ever drops state, affected drops with it.
        - ``dead`` scales *quadratically* with state, **modulated by
          the country's adaptation indicator**. Bangladesh cut its
          cyclone mortality ~100× from the 1970s baseline by building
          out shelters, training, and warning systems — that's
          precisely the "adaptation" indicator the HUMANITÉ side
          invests in. A maxed-adaptation country (1.0) loses 40 %
          fewer lives at the same state level than a zero-adaptation
          one, which finally makes the HUMANITÉ adaptation skill
          save the lives it's named for.
        - ``dead`` is **monotonic** — only ratchets up, never down.
          Without this, raising adaptation later (via skills /
          regeneration) would un-die already-counted casualties
          when the formula gets recomputed. The ratchet guarantees
          historical deaths stay dead even as mitigation arrives.
        """
        # Adaptation-aware mortality coefficient: 0.70 at adapt=0,
        # 0.42 at adapt=1.0 → 40 % reduction at full preparation.
        mortality_coef = 0.70 * (1.0 - 0.4 * self.adaptation)
        formula_dead = int(self.population * self.state * self.state * mortality_coef)
        # Ratchet — never decreases. ``max()`` over the prior value
        # locks in historical casualties even if adaptation rises
        # later or any future mechanic walks state back down.
        self.dead = max(self.dead, formula_dead)
        # ``affected`` is the *alive* impacted count — was previously
        # set to ``pop * state * 0.85`` which includes the dead, so
        # ``affected + dead`` could exceed ``population`` (at
        # state=1.0, adapt=0.5: 8.5 M + 5.6 M = 14.1 M for a 10 M
        # country). The info-panel BILAN tab displays the two as
        # independent rows summing > 100 %, and the chart plots
        # ``infected_history`` and ``dead_history`` as separate lines
        # under an "Infectés" label that only makes sense if dead is
        # excluded. Compute the broad-impact total first, then
        # subtract the dead and clamp to >= 0 so the two metrics
        # partition the population cleanly.
        total_impacted = int(self.population * self.state * 0.85)
        self.affected = max(0, total_impacted - self.dead)

    def regenerate(self, rate: float = 0.006) -> None:
        """Slow auto-recovery of indicators in countries that aren't suffering.

        When state is low (population is healthy) the country's resilience
        indicators drift back toward their *archetype baseline* at a small
        per-turn rate. Was hard-clamped at 0.7, which meant high-baseline
        archetypes (polar_isolated stability 0.80, tropical_forest
        regeneration 0.80, etc.) lost their identity permanently after
        any damage — they could never recover above 0.7 even when fully
        healed. Now each indicator targets at least 0.7 *or* its archetype
        baseline (whichever is higher), preserving the geographic
        character that the profile system encodes.

        Recovery rate now tapers smoothly from full at low state to zero
        at ``RECOVERY_CUTOFF`` instead of cliff-cutting at state ≥ 0.25.
        See ``RECOVERY_FULL_BELOW`` / ``RECOVERY_CUTOFF`` constants for
        the rationale.
        """
        if self.state >= RECOVERY_CUTOFF:
            return  # deep critical zones still lock recovery — HUMANITÉ
                    # skills remain the only way back at that point.
        if self.state <= RECOVERY_FULL_BELOW:
            scale = 1.0
        else:
            # Quadratic ease-out across the (FULL_BELOW, CUTOFF) band:
            # rate drops slowly at first as state climbs, then faster
            # near the cutoff. Smooth and monotonic — no perceptible
            # "stuck" point.
            band = (self.state - RECOVERY_FULL_BELOW) / (
                RECOVERY_CUTOFF - RECOVERY_FULL_BELOW
            )
            scale = (1.0 - band) ** 2
        # Regeneration indicator now amplifies the recovery rate —
        # high-regeneration countries (tropical forests, healthy
        # ecosystems, well-managed urban green spaces) bounce back
        # measurably faster than degraded ones. Previously every
        # indicator was equally interchangeable inside the ``defense``
        # average and there was nothing distinct about owning a high
        # regeneration value — it just shifted the average. Now
        # Régénération Écologique has its own mechanical identity:
        # *speed of recovery*, the natural counterpart to Adaptation's
        # *survival under stress*. Scaling: regen=0 → 1.0× rate
        # (baseline), regen=1 → 1.5× rate. The 50 % cap keeps the
        # mechanic from runaway-healing a country that's somehow
        # accumulated maxed regen — it tilts the curve, doesn't
        # invert it.
        effective_rate = rate * scale * (1.0 + 0.5 * self.regeneration)
        if effective_rate <= 0.0:
            return
        for attr in ("resilience", "stability", "regeneration", "adaptation"):
            current = getattr(self, attr)
            baseline = getattr(self, f"baseline_{attr}")
            target = max(RECOVERY_FLOOR, baseline)
            if current < target:
                setattr(self, attr, min(target, current + effective_rate))

    def snapshot_state(self) -> None:
        """Append the current state to history; called once per game turn."""
        self.state_history.append(self.state)

    def infection_rate(self) -> float:
        """Average per-turn signed delta over the *recent* history.

        Returns the raw average — *positive* when state is climbing
        (catastrophe deteriorating), *negative* when state is dropping
        (the country is recovering ground after damage). The previous
        version clamped to ``≥ 0``, which made the "Sain (recovery)"
        display branch in the leaderboard and TENDANCE tab impossible
        to reach. With state recovery wired in by future mechanics
        (humanity-side adaptation, indicator-driven heal-back, etc.)
        the signed rate becomes the load-bearing display signal.

        Windowed to the **last 3 deltas** (≈ 3 most recent days of
        motion) rather than the whole 6-tick history. The full-window
        average was laggy: a country hit hard 5 days ago but stable
        since still reported a positive rate, because two old big
        deltas dominated the mean. Players reading the rate column
        expect "what's happening now", not "what happened on average
        this week". Three samples smooth single-day noise while
        staying reactive to genuine direction changes within a
        2-3 day horizon — the same window the sparkline's per-segment
        colour grading already shows visually, so the rate column and
        the chart now describe the same trajectory.

        When history is too short for 3 deltas (the first 2-3 days of
        a run), falls back to whatever deltas exist — a single
        observation is still informative for a country that just got
        hit on the previous turn.
        """
        history = list(self.state_history)
        if len(history) < 2:
            return 0.0
        deltas = [b - a for a, b in zip(history, history[1:])]
        recent = deltas[-3:]
        return sum(recent) / len(recent)

    def turns_to_collapse(self) -> int | None:
        """Estimate turns until state hits 1.0; None if not progressing.

        Two correctness fixes over the prior ``int((1-state)/rate)``:

        1. **Ceil, not truncate.** At rate=0.07 / state=0.5 the
           projection is 7.14 days, but the country *actually*
           collapses on turn 8 (after 7 turns state = 0.99, after 8
           it crosses 1.0). Truncation reported "~7 jours" — under-
           warning by a full day for roughly 70 % of rate/state
           combinations. ``math.ceil`` gives the right semantic:
           "after how many turns will the threshold be crossed?"
        2. **Cap at 30 days.** Just above the ``rate > 1e-4``
           threshold the linear projection can return 10 000+ days,
           which has no information content past a couple of weeks
           (the linear extrapolation is meaningless at that range and
           the chip's colour logic already paints anything > 15
           green). Cap at 30 → ``None`` so the rate column falls back
           to the "stable" / "figé" rendering paths instead of
           emitting absurd numbers.
        """
        if self.state >= 1.0:
            return 0
        rate = self.infection_rate()
        if rate <= 1e-4:
            return None
        days = (1.0 - self.state) / rate
        if days > 30.0:
            return None
        return max(1, math.ceil(days))

    def contains(self, point: Point) -> bool:
        """True iff ``point`` is inside one of the country's outer polygons
        and *not* inside any of its interior holes.

        Hole exclusion fixes the enclave-overlap bug: South Africa's
        polygon used to claim Lesotho's interior as its own (because
        the hole ring was dropped at GeoJSON parse), so a click in
        Lesotho would match both countries and dict-iteration order
        decided which won. Now ZAF correctly rejects the click and
        LSO is the unique match.
        """
        if not any(_point_in_polygon(point, polygon) for polygon in self.polygons):
            return False
        # Exclude points falling inside any interior ring. ``holes`` is
        # empty for all countries except South Africa in the bundled
        # dataset, so this short-circuits cheaply for every click.
        if self.holes and any(_point_in_polygon(point, hole) for hole in self.holes):
            return False
        return True


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
