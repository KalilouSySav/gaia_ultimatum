"""Humanity's global balance state."""

from __future__ import annotations

from dataclasses import dataclass

from gaia_ultimatum.models.world import World


@dataclass
class Humans:
    global_progress: float = 0.0
    evolution_points: int = 0

    def update(self, world: World) -> None:
        """Recompute global progress as a **living-population**-weighted
        average of balance indicators.

        Previously the weight was ``country.population`` — the
        *original* pre-catastrophe population. That meant a fully
        collapsed Bangladesh (70 % dead, indicators at 0) kept its
        full ~170 M weight indefinitely, permanently sinking
        ``global_progress`` no matter what the HUMANITÉ side achieved
        elsewhere. The bar effectively had a "memory" of vanished
        population, which contradicted the educational frame: a
        decimated region's surviving people *do* belong in the
        global average, but the deceased do not.

        Now ``weight = max(1, population - dead)`` — the surviving
        population only. A country with 90 % mortality still
        contributes its surviving 10 %, but its weight no longer
        outvotes 5 fully-healthy mid-sized countries. The HUMANITÉ
        objective (raise the bar via skills + preventing collapses)
        becomes mathematically reachable instead of asymptotically
        capped by historical losses.

        The ``max(1, …)`` floor avoids a degenerate divide-by-zero
        and keeps a fully-extinct country still contributing a
        tiny weight (so the global doesn't ignore a 0 % indicator
        on a hypothetical wiped-out region).
        """
        total_weight = 0
        weighted_progress = 0.0
        for country in world.countries.values():
            # Survivors only — historical deaths no longer count
            # toward the global indicator weight.
            weight = max(1, country.population - country.dead)
            total_weight += weight
            # ``country.defense`` is the four-indicator average; reuse
            # it instead of recomputing in-place so the two paths stay
            # in lockstep. The inline form drifted from ``defense`` once
            # already when the indicator mix was being tuned, producing
            # a global bar that disagreed with the per-country
            # "défense moyenne" the info panel shows.
            weighted_progress += country.defense * weight
        if total_weight > 0:
            self.global_progress = weighted_progress / total_weight
