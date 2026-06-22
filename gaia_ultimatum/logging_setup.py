"""Centralised logging setup."""

from __future__ import annotations

import logging


def configure_logging(debug: bool = False) -> None:
    """Configure root logging. Idempotent across re-calls.

    Two correctness fixes over the prior implementation:

    * **``force=True`` on basicConfig** — without it, ``basicConfig``
      is a silent no-op when handlers are already attached (pytest
      installs its own handlers; a second call from a re-entered
      app path would also no-op). That meant a debug-flag flip
      during the session (e.g. an interactive ``--debug`` reload)
      didn't actually bump the level. ``force=True`` tears down
      existing handlers first so the new level / format take effect.
    * **Removed the duplicate ``GAIA_DEBUG`` env-var check.** The
      prior code did ``debug or os.environ.get("GAIA_DEBUG")``
      using Python truthiness — but a non-empty string is truthy,
      so ``GAIA_DEBUG=0`` and ``GAIA_DEBUG=false`` both *enabled*
      debug logging, contradicting how ``config.py`` parses the
      same variable (``.lower() in ("1", "true", "yes")``). The
      caller in ``app.py`` already passes the env-resolved flag
      (``debug=args.debug or config.debug``, where ``config.debug``
      includes the canonical env-var parse), so the duplicate
      check here was both redundant and wrong on falsy strings.
    """
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
