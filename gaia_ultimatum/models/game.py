"""Top-level game state + turn logic (no rendering or input)."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from gaia_ultimatum.assets import ZONES_GEOJSON
from gaia_ultimatum.config import DEFAULT_CONFIG, Config
from gaia_ultimatum.models.catastrophe import CatastrophePoint
from gaia_ultimatum.models.gaia import Gaia
from gaia_ultimatum.models.humans import Humans
from gaia_ultimatum.models.world import World

logger = logging.getLogger(__name__)


class GameOutcome(Enum):
    IN_PROGRESS = "in_progress"
    VICTORY = "victory"
    DEFEAT = "defeat"


@dataclass
class Game:
    config: Config = DEFAULT_CONFIG
    world: World = None  # type: ignore[assignment]
    humans: Humans = None  # type: ignore[assignment]
    gaia: Gaia = None  # type: ignore[assignment]
    turn: int = 0
    outcome: GameOutcome = GameOutcome.IN_PROGRESS
    info_panel_country: str | None = None
    info_panel_visible: bool = False
    selected_point: CatastrophePoint | None = None
    rng: random.Random = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.world = self.world or World()
        self.humans = self.humans or Humans()
        self.gaia = self.gaia or Gaia()
        self.rng = self.rng or random.Random()

    @classmethod
    def create(
        cls,
        config: Config = DEFAULT_CONFIG,
        geojson_path: Path = ZONES_GEOJSON,
        seed: int | None = None,
    ) -> Game:
        rng = random.Random(seed)
        game = cls(config=config, rng=rng)
        game.world.load_countries(geojson_path, rng=rng)
        return game

    @property
    def game_over(self) -> bool:
        return self.outcome is not GameOutcome.IN_PROGRESS

    def next_turn(self) -> None:
        self.turn += 1
        catastrophe = self.gaia.active
        catastrophe.update(self.world, self.config.gameplay, self.rng)

        human_impact = 1.0 - self.humans.global_progress
        self.gaia.update(human_impact)

        impact = catastrophe.base_impact * catastrophe.intensity
        for country in self.world.countries.values():
            country.apply_catastrophe(impact)

        self.humans.update(self.world)
        self._check_outcome()

    def _check_outcome(self) -> None:
        if self.humans.global_progress >= self.config.gameplay.victory_threshold:
            self.outcome = GameOutcome.VICTORY
            logger.info("Victory: humanity reached balance with Gaia.")
            return
        total_population = sum(c.population for c in self.world.countries.values())
        total_dead = sum(c.dead for c in self.world.countries.values())
        if total_population > 0 and total_dead / total_population >= self.config.gameplay.defeat_mortality_ratio:
            self.outcome = GameOutcome.DEFEAT
            logger.info("Defeat: humanity has been decimated.")

    def cycle_catastrophe(self) -> None:
        self.gaia.next_catastrophe()

    def select_country(self, country_id: str | None) -> None:
        self.world.selected_country = country_id
        self.info_panel_country = country_id
        self.info_panel_visible = country_id is not None

    def close_info_panel(self) -> None:
        self.info_panel_visible = False
