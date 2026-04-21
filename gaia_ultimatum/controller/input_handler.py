"""Translate pygame events into game-state mutations."""

from __future__ import annotations

import math
from dataclasses import dataclass

import pygame

from gaia_ultimatum.config import Config
from gaia_ultimatum.models import Game
from gaia_ultimatum.models.catastrophe import CatastrophePoint
from gaia_ultimatum.view.renderer import close_button_rect


@dataclass
class _DragState:
    start: tuple[int, int]
    initial_offset: tuple[float, float]


class InputHandler:
    def __init__(self, config: Config) -> None:
        self.config = config
        self._drag: _DragState | None = None

    def handle(self, event: pygame.event.Event, game: Game) -> bool:
        """Return False to signal the main loop to exit."""
        if event.type == pygame.QUIT:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN:
            self._on_mouse_down(event, game)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._drag = None
        elif event.type == pygame.MOUSEMOTION and self._drag is not None:
            self._on_drag(event, game)
        elif event.type == pygame.KEYDOWN:
            self._on_key_down(event, game)
        return True

    def _on_mouse_down(self, event: pygame.event.Event, game: Game) -> None:
        if event.button == 1:
            self._on_left_click(event, game)
        elif event.button == 4:
            game.world.scale = min(
                game.world.scale * self.config.gameplay.zoom_step,
                self.config.gameplay.max_zoom,
            )
        elif event.button == 5:
            game.world.scale = max(
                game.world.scale / self.config.gameplay.zoom_step,
                self.config.gameplay.min_zoom,
            )

    def _on_left_click(self, event: pygame.event.Event, game: Game) -> None:
        mouse_pos = event.pos
        if game.info_panel_visible and close_button_rect(self.config).collidepoint(mouse_pos):
            game.close_info_panel()
            return

        clicked_point = self._point_at(mouse_pos, game)
        if clicked_point is not None:
            game.humans.collect_point(clicked_point)
            game.gaia.active.remove_point(clicked_point)
            return

        map_point = game.world.inverse_transform(
            mouse_pos, (self.config.display.width, self.config.display.height)
        )
        country_id = game.world.country_at(map_point)
        if country_id is not None:
            game.select_country(country_id)
        else:
            self._drag = _DragState(
                start=mouse_pos,
                initial_offset=(game.world.offset_x, game.world.offset_y),
            )

    def _point_at(self, mouse_pos: tuple[int, int], game: Game) -> CatastrophePoint | None:
        screen = (self.config.display.width, self.config.display.height)
        for point in game.gaia.active.active_points:
            px, py = game.world.transform_point(point.position, screen)
            if math.hypot(mouse_pos[0] - px, mouse_pos[1] - py) < point.size * 1.5:
                return point
        return None

    def _on_drag(self, event: pygame.event.Event, game: Game) -> None:
        assert self._drag is not None
        dx = event.pos[0] - self._drag.start[0]
        dy = event.pos[1] - self._drag.start[1]
        game.world.offset_x = self._drag.initial_offset[0] + dx
        game.world.offset_y = self._drag.initial_offset[1] + dy

    @staticmethod
    def _on_key_down(event: pygame.event.Event, game: Game) -> None:
        if event.key == pygame.K_SPACE:
            game.next_turn()
        elif event.key == pygame.K_c:
            game.cycle_catastrophe()
        elif event.key == pygame.K_ESCAPE:
            game.close_info_panel()
