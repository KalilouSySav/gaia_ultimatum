"""Application entry point: wires up model, view, controller and runs the loop."""

from __future__ import annotations

import argparse
import dataclasses
import logging
import sys
from pathlib import Path

import pygame

from gaia_ultimatum import __version__
from gaia_ultimatum.assets import ZONES_GEOJSON
from gaia_ultimatum.audio import AudioManager
from gaia_ultimatum.config import Config, load_config
from gaia_ultimatum.controller import InputHandler
from gaia_ultimatum.logging_setup import configure_logging
from gaia_ultimatum.models import Game, GameOutcome
from gaia_ultimatum.models.world import GeoJsonLoadError
from gaia_ultimatum.view import Renderer
from gaia_ultimatum.view.fonts import Fonts

logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gaia-ultimatum", description="Gaia Ultimatum")
    parser.add_argument("--version", action="version", version=f"Gaia Ultimatum {__version__}")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible runs")
    parser.add_argument("--map", type=Path, default=ZONES_GEOJSON, help="Path to the map GeoJSON")
    parser.add_argument("--debug", action="store_true", help="Enable verbose logging")
    parser.add_argument("--no-audio", action="store_true", help="Disable audio playback")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config()
    if args.debug:
        config = dataclasses.replace(config, debug=True)
    configure_logging(debug=args.debug or config.debug)

    pygame.init()
    try:
        return _run_game(config, args)
    finally:
        pygame.quit()


def _run_game(config: Config, args: argparse.Namespace) -> int:
    flags = pygame.FULLSCREEN if config.display.fullscreen else 0
    screen = pygame.display.set_mode(
        (config.display.width, config.display.height), flags
    )
    pygame.display.set_caption(config.display.title)
    clock = pygame.time.Clock()
    fonts = Fonts.create()

    audio: AudioManager | None = None
    if not args.no_audio:
        audio = AudioManager(config.audio)
        audio.load_sound("click", "button-click.mp3")
        audio.load_sound("effect", "effect1.wav")
        audio.load_music("background.mp3")
        audio.play_music()

    try:
        game = Game.create(config=config, geojson_path=args.map, seed=args.seed)
    except GeoJsonLoadError as exc:
        logger.error("%s", exc)
        return 1

    renderer = Renderer(config, fonts)
    input_handler = InputHandler(config)

    running = True
    while running and not game.game_over:
        for event in pygame.event.get():
            if not input_handler.handle(event, game):
                running = False
                break
        renderer.draw(screen, game)
        pygame.display.flip()
        clock.tick(config.display.fps)

    if game.outcome is GameOutcome.VICTORY:
        logger.info("Final outcome: VICTORY")
    elif game.outcome is GameOutcome.DEFEAT:
        logger.info("Final outcome: DEFEAT")

    if audio is not None:
        audio.stop_music()
    return 0


if __name__ == "__main__":
    sys.exit(run())
