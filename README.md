# Gaia Ultimatum

A strategy game where humanity races to restore its balance with Earth while
Gaia unleashes catastrophes across the globe. Click red points to harvest
evolution energy, watch countries and their balance indicators react, and
steer humankind to equilibrium before it is decimated.

Built with [Pygame](https://www.pygame.org/).

## Requirements

- Python 3.10 or newer
- A system capable of running SDL 2 (for Pygame)
- The operating system's usual audio/video stack

## Installation

```bash
git clone https://github.com/KalilouSySav/gaia_ultimatum.git
cd gaia_ultimatum
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e .
```

For development:

```bash
pip install -e ".[dev]"
```

## Running the game

```bash
gaia-ultimatum
# or
python -m gaia_ultimatum
```

### Command-line flags

| Flag           | Description                                   |
| -------------- | --------------------------------------------- |
| `--seed N`     | Seed the RNG for deterministic runs           |
| `--map PATH`   | Use a different GeoJSON map file              |
| `--debug`      | Verbose logging                               |
| `--no-audio`   | Disable music and sound effects               |
| `--version`    | Print version and exit                        |

### Environment variables

| Variable          | Effect                                        |
| ----------------- | --------------------------------------------- |
| `GAIA_WIDTH`      | Override window width                         |
| `GAIA_HEIGHT`     | Override window height                        |
| `GAIA_FPS`        | Override target frame rate                    |
| `GAIA_FULLSCREEN` | `1`/`true` to start fullscreen                |
| `GAIA_MUTED`      | `1`/`true` to start muted                     |
| `GAIA_DEBUG`      | `1`/`true` to enable debug logging            |

### Runtime config file

If `gaia_ultimatum/data/config.json` exists, its values override defaults
(before environment variables are applied). Example:

```json
{
  "display": { "width": 1600, "height": 900, "fps": 60 },
  "audio":   { "muted": false, "master_volume": 0.7 },
  "gameplay": { "victory_threshold": 0.9 }
}
```

## Controls

| Input               | Action                            |
| ------------------- | --------------------------------- |
| Left click (country)| Open country info panel           |
| Left click (red)    | Harvest an evolution point        |
| Left-drag (empty)   | Pan the map                       |
| Mouse wheel         | Zoom in / out                     |
| `Space`             | Advance to the next turn          |
| `C`                 | Cycle active catastrophe          |
| `Esc`               | Close info panel                  |

## Project layout

```
gaia_ultimatum/
├── gaia_ultimatum/          # package
│   ├── __init__.py
│   ├── __main__.py          # python -m gaia_ultimatum
│   ├── app.py               # orchestration + game loop
│   ├── assets.py            # bundled asset path helpers
│   ├── audio.py             # AudioManager
│   ├── config.py            # typed Config dataclasses
│   ├── logging_setup.py
│   ├── models/              # domain state (no rendering)
│   ├── view/                # pygame rendering
│   ├── controller/          # pygame event handling
│   ├── data/                # maps, fonts, images
│   ├── sounds/
│   └── cinematics/
├── tests/
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── Makefile
└── README.md
```

The package follows a Model / View / Controller split:

- **Model** (`gaia_ultimatum.models`) — pure game state. No pygame surfaces
  are created here, so unit tests run headlessly and deterministically.
- **View** (`gaia_ultimatum.view`) — the only place allowed to draw on a
  `pygame.Surface`.
- **Controller** (`gaia_ultimatum.controller`) — translates pygame events
  into calls on the model.
- **app.py** — wires them together and owns the frame loop.

## Development

```bash
make dev         # install in editable mode with dev deps
make test        # pytest
make lint        # ruff check
make typecheck   # mypy
make format      # ruff format + --fix
make run         # launch the game
```

## Testing

The tests run without a display (`SDL_VIDEODRIVER=dummy`) and without audio
(`SDL_AUDIODRIVER=dummy`), so CI boxes can run them. See `tests/conftest.py`.

```bash
pytest -v
pytest --cov=gaia_ultimatum
```

## License

MIT — see `LICENSE`.
