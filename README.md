# Terre Vivante

> *Comprendre la planète. S'émerveiller du vivant. Agir.*

A strategy game where you play either **Gaïa** (unleashing one of five
elemental catastrophes — Eau, Feu, Terre, Air, Vie) or **Humanité**
(deploying the defences and ecological repair that science already
knows). Each run is a short, replayable thought experiment in
coexistence with a living planet.

Built with [Pygame-CE](https://pygame-community.github.io/).
The Python package is still named ``gaia_ultimatum`` for backwards
compatibility with prior builds; the player-facing name is
**Terre Vivante**.

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

## Web build & GitHub Pages

The game ships with a [pygbag](https://pygame-web.github.io)-based WebAssembly
entry point (`main.py` at the repo root) that runs the game inside any modern
browser via Pyodide. A GitHub Actions workflow builds and deploys it to
GitHub Pages on every push to `master`, `main`, or `claude/**`.

### Local web preview

```bash
pip install -e ".[web]"
make web-serve          # http://localhost:8000
# or
python -m pygbag --ume_block 0 main.py
```

### Produce a static bundle

```bash
make web-build          # outputs build/web/
```

The `build/web/` directory is a self-contained static site you can host
anywhere (GitHub Pages, Netlify, Cloudflare Pages, S3, nginx, etc.).

### Enabling GitHub Pages

1. Push this repo to GitHub.
2. Go to **Settings → Pages**.
3. Under **Build and deployment → Source**, pick **GitHub Actions**.
4. The next push (or a manual run of the *Deploy to GitHub Pages* workflow
   from the **Actions** tab) will publish to
   `https://<user>.github.io/<repo>/`.

### Web-build tradeoffs

- The browser build uses the lighter `zones.geo.json` (~1 MB) instead of the
  24 MB `zones.geojson`, so the initial load is reasonable.
- Audio is disabled by default in the web build (`--no-audio`) to avoid
  browsers that block autoplay.
- The RNG is seeded (`--seed 42`) so refreshes produce the same game. Edit
  `main.py` to change or remove the seed.

## Android build (Play Store APK)

Built via [buildozer](https://buildozer.readthedocs.io/) +
[python-for-android](https://python-for-android.readthedocs.io/) on a
Linux host. On Windows, that means **WSL Ubuntu**. The build can't run
on `/mnt/c` reliably (OneDrive holds file handles + spaces in the path
break shell-outs inside p4a recipes); the build script stages the
project to a Linux-clean path (`~/builds/gaia_ultimatum`) automatically.

### Prerequisites

1. WSL Ubuntu installed. From PowerShell as Administrator:

   ```powershell
   wsl --install -d Ubuntu
   ```

2. Inside WSL:

   ```bash
   cd '/mnt/c/Users/<you>/OneDrive/Desktop/projet logciel/gaia_ultimatum'
   make android-setup        # one-time, ~5 min
   ```

   This installs system packages (build tools, SDL2-dev, ffmpeg, Java 17),
   Python 3.11 (python-for-android's stable target — **not** 3.14, which
   p4a doesn't yet support), and creates a buildozer venv at
   `~/buildozer-venv`.

3. Activate the venv (every new WSL session):

   ```bash
   source ~/buildozer-venv/bin/activate
   ```

### Build the APK

```bash
make android-debug
```

What it does:

1. Rsyncs the project to `~/builds/gaia_ultimatum` (off OneDrive, off
   the Windows mount — 20× faster IO).
2. Runs `tools/transcode_to_ogg.py` to compress the 394 MB of WAV
   audio down to ~40 MB of OGG (Play Store base APK cap is 150 MB).
3. Runs `buildozer android debug` — **first build downloads the
   Android SDK + NDK (~5 GB, ~30 min)**. Subsequent builds: 1–3 min.
4. Drops the APK at
   `~/builds/gaia_ultimatum/bin/gaiaultimatum-1.0.0-arm64-v8a-debug.apk`.

### Sideload to your phone

1. Enable USB Debugging on the phone (Settings → About → tap *Build
   number* 7 times → Developer options → USB Debugging).
2. Plug in via USB. Confirm the RSA fingerprint prompt.
3. From inside WSL:

   ```bash
   adb install -r ~/builds/gaia_ultimatum/bin/*.apk
   ```

   (If `adb` isn't installed: `sudo apt install adb`.)

### Expected failures + how to react

The Android toolchain is finicky. Failures during first build are
normal — the build script's output points at the line.

| Symptom | Cause | Fix |
| --- | --- | --- |
| `ERROR: Aidl not found` during SDK setup | License not accepted | `~/.buildozer/android/platform/android-sdk/cmdline-tools/latest/bin/sdkmanager --licenses` then accept all |
| `Cython.Build` import error in `pygame_ce` recipe build | Cython 3.x pinned | `wsl_setup.sh` pins 0.29.36; re-run `make android-setup` |
| `Unsupported class file major version 65` | Java version mismatch | `sudo apt install openjdk-17-jdk`; export `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64` |
| `ModuleNotFoundError: No module named 'gaia_ultimatum'` at runtime | Asset paths missing | Check `buildozer.spec` `source.include_exts` matches your file extensions |
| App crashes on launch with "couldn't start mixer" | Audio init order | Pass `--no-audio` via `app.py` Android branch as a temporary workaround while debugging |

When in doubt: `logcat` from a connected phone shows the real error:

```bash
adb logcat | grep -E 'python|gaia|AndroidRuntime'
```

### Play Store submission checklist

Code-side is done. Process-side:

| Item | Owner | Lead time |
| --- | --- | --- |
| Google Play Developer account ($25 one-time) | you | 1–2 days ID verification |
| Privacy policy URL (required even for offline games) | you | 30 min — host on GitHub Pages |
| Data Safety questionnaire | you | 15 min |
| Content rating (IARC questionnaire) | you | 10 min |
| 512×512 app icon + 1024×500 feature graphic + ≥2 screenshots | you | 1–2 hr |
| Short description (≤80 chars), long description (≤4000 chars) | you | 30 min |
| Internal test track → ≥14 days with ≥12 testers | you | calendar critical path |

The 14-day test-track requirement is the actual gating step for new
developer accounts. Start the Play Console signup in parallel with
the first APK build.

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
