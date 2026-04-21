"""Gaia — planetary antagonist that orchestrates catastrophes."""

from __future__ import annotations

from dataclasses import dataclass, field

from gaia_ultimatum.models.catastrophe import Catastrophe


def _default_catastrophes() -> list[Catastrophe]:
    return [
        Catastrophe(name="Réchauffement Climatique", icon="climate.png", base_impact=0.01),
        Catastrophe(name="Pandémie", icon="pandemic.png", base_impact=0.015),
        Catastrophe(name="Tsunami", icon="tsunami.png", base_impact=0.02),
    ]


@dataclass
class Gaia:
    catastrophes: list[Catastrophe] = field(default_factory=_default_catastrophes)
    active_index: int = 0

    @property
    def active(self) -> Catastrophe:
        return self.catastrophes[self.active_index]

    def next_catastrophe(self) -> Catastrophe:
        self.active_index = (self.active_index + 1) % len(self.catastrophes)
        return self.active

    def update(self, human_impact: float) -> None:
        intensity = 1.0 + human_impact * 2.0
        for catastrophe in self.catastrophes:
            catastrophe.intensity = intensity
