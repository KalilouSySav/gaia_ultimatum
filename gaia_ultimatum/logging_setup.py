"""Centralised logging setup."""

from __future__ import annotations

import logging
import os


def configure_logging(debug: bool = False) -> None:
    level = logging.DEBUG if debug or os.environ.get("GAIA_DEBUG") else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
