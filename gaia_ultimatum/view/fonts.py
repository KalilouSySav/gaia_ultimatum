"""Font loading."""

from __future__ import annotations

from dataclasses import dataclass

import pygame


@dataclass
class Fonts:
    small: pygame.font.Font
    medium: pygame.font.Font
    large: pygame.font.Font
    title: pygame.font.Font

    @classmethod
    def create(cls) -> Fonts:
        if not pygame.font.get_init():
            pygame.font.init()
        return cls(
            small=pygame.font.SysFont("Arial", 14),
            medium=pygame.font.SysFont("Arial", 18),
            large=pygame.font.SysFont("Arial", 24),
            title=pygame.font.SysFont("Arial", 30, bold=True),
        )
