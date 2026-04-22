"""Rendering: the only layer allowed to touch ``pygame.Surface``."""

from __future__ import annotations

import pygame
import pygame.gfxdraw

from gaia_ultimatum.config import Config, Palette
from gaia_ultimatum.models import Country, Game, World
from gaia_ultimatum.models.catastrophe import Catastrophe
from gaia_ultimatum.view.fonts import Fonts

INSTRUCTIONS = (
    "Clic gauche sur un pays pour voir ses infos",
    "Molette pour zoomer/dézoomer",
    "Clic-glisser pour déplacer la carte",
    "Espace pour passer au tour suivant",
    "C pour changer de catastrophe",
)


class Renderer:
    def __init__(self, config: Config, fonts: Fonts) -> None:
        self.config = config
        self.palette: Palette = config.palette
        self.fonts = fonts

    @property
    def screen_size(self) -> tuple[int, int]:
        return (self.config.display.width, self.config.display.height)

    def draw(self, surface: pygame.Surface, game: Game) -> None:
        surface.fill(self.palette.background)
        self._draw_world(surface, game.world)
        self._draw_points(surface, game.world, game.gaia.active)
        self._draw_hud(surface, game)
        if game.info_panel_visible and game.info_panel_country:
            country = game.world.countries.get(game.info_panel_country)
            if country:
                self._draw_info_panel(surface, country)
            else:
                game.info_panel_visible = False

    def _draw_world(self, surface: pygame.Surface, world: World) -> None:
        for country_id, country in world.countries.items():
            color = _country_color(country, self.palette)
            outline = (
                self.palette.selected_outline
                if country_id == world.selected_country
                else self.palette.country_outline
            )
            for polygon in country.polygons:
                transformed = [world.transform_point(p, self.screen_size) for p in polygon]
                if len(transformed) < 3:
                    continue
                pygame.gfxdraw.filled_polygon(surface, transformed, color)
                pygame.gfxdraw.polygon(surface, transformed, outline)

    def _draw_points(self, surface: pygame.Surface, world: World, catastrophe: Catastrophe) -> None:
        for point in catastrophe.active_points:
            pos = world.transform_point(point.position, self.screen_size)
            lifetime_ratio = point.lifetime / point.max_lifetime if point.max_lifetime else 0.0
            size = max(1, int(point.size * (0.8 + lifetime_ratio * 0.2)))
            alpha = int(255 * lifetime_ratio)
            red = (*self.palette.point_red, alpha)
            pygame.gfxdraw.filled_circle(surface, int(pos[0]), int(pos[1]), size, red)
            pygame.gfxdraw.aacircle(
                surface,
                int(pos[0]),
                int(pos[1]),
                size,
                (*self.palette.point_red, min(alpha, 200)),
            )
            value_text = self.fonts.small.render(str(point.value), True, self.palette.text)
            surface.blit(
                value_text,
                (pos[0] - value_text.get_width() // 2, pos[1] - value_text.get_height() // 2),
            )

    def _draw_hud(self, surface: pygame.Surface, game: Game) -> None:
        width = self.config.display.width
        bar_x, bar_y, bar_w, bar_h = 20, 20, 300, 20
        pygame.draw.rect(surface, (50, 50, 50), (bar_x, bar_y, bar_w, bar_h))
        fill_w = int(bar_w * game.humans.global_progress)
        fill_color = _progress_color(game.humans.global_progress)
        pygame.draw.rect(surface, fill_color, (bar_x, bar_y, fill_w, bar_h))
        pygame.draw.rect(surface, (200, 200, 200), (bar_x, bar_y, bar_w, bar_h), 1)

        progress_text = self.fonts.medium.render(
            f"Équilibre: {int(game.humans.global_progress * 100)}%", True, self.palette.text
        )
        surface.blit(progress_text, (bar_x + bar_w + 10, bar_y))

        for i, (label, value) in enumerate(
            (
                ("Tour", game.turn),
                ("Points d'évolution", game.humans.evolution_points),
                ("Catastrophe", game.gaia.active.name),
            )
        ):
            text = self.fonts.medium.render(f"{label}: {value}", True, self.palette.text)
            surface.blit(text, (20, 50 + i * 30))

        for i, instruction in enumerate(INSTRUCTIONS):
            text = self.fonts.small.render(instruction, True, self.palette.text)
            surface.blit(text, (width - text.get_width() - 20, 20 + i * 20))

    def _draw_info_panel(self, surface: pygame.Surface, country: Country) -> None:
        panel_w, panel_h, panel_x, panel_y = 300, 300, 20, 150
        overlay = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        overlay.fill(self.palette.ui_background)
        surface.blit(overlay, (panel_x, panel_y))
        pygame.draw.rect(surface, (200, 200, 200), (panel_x, panel_y, panel_w, panel_h), 1)

        title = self.fonts.title.render(country.name, True, self.palette.text)
        surface.blit(title, (panel_x + 10, panel_y + 10))

        pop = max(country.population, 1)
        info_lines = (
            f"Population totale: {country.population:,}",
            f"Personnes affectées: {country.affected:,} ({int(country.affected / pop * 100)}%)",
            f"Personnes décédées: {country.dead:,} ({int(country.dead / pop * 100)}%)",
            "",
            "Indicateurs d'équilibre:",
            f"Résilience Technologique: {int(country.resilience * 100)}%",
            f"Stabilité Sociétale: {int(country.stability * 100)}%",
            f"Régénération Écologique: {int(country.regeneration * 100)}%",
            f"Adaptation Évolutive: {int(country.adaptation * 100)}%",
        )
        for i, line in enumerate(info_lines):
            text = self.fonts.medium.render(line, True, self.palette.text)
            surface.blit(text, (panel_x + 10, panel_y + 50 + i * 25))

        close_rect = pygame.Rect(panel_x + panel_w - 30, panel_y + 10, 20, 20)
        if close_rect.collidepoint(pygame.mouse.get_pos()):
            pygame.draw.rect(surface, self.palette.ui_highlight, close_rect)
        close_text = self.fonts.large.render("X", True, self.palette.text)
        surface.blit(close_text, (panel_x + panel_w - 25, panel_y + 5))


def close_button_rect(config: Config) -> pygame.Rect:
    """Rect used by the input handler to detect close-button clicks."""
    panel_w, panel_x, panel_y = 300, 20, 150
    return pygame.Rect(panel_x + panel_w - 30, panel_y + 10, 20, 20)


def _progress_color(progress: float) -> tuple[int, int, int]:
    if progress < 0.33:
        return (200, 50, 50)
    if progress < 0.66:
        return (200, 150, 50)
    return (50, 200, 50)


def _country_color(country: Country, palette: Palette) -> tuple[int, int, int]:
    if country.state < 0.5:
        ratio = country.state * 2
        start, end = palette.healthy, palette.affected
    else:
        ratio = (country.state - 0.5) * 2
        start, end = palette.affected, palette.dead
    return (
        int(start[0] + (end[0] - start[0]) * ratio),
        int(start[1] + (end[1] - start[1]) * ratio),
        int(start[2] + (end[2] - start[2]) * ratio),
    )
