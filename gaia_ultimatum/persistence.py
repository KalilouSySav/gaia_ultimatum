"""Lightweight JSON persistence for prefs + run history.

Two files in the user's app-data directory:
  * ``prefs.json``    — settings + last-used picker config (loaded once at boot,
                        rewritten whenever the player toggles something).
  * ``history.json``  — append-only run records (one entry per completed run).

Both files are best-effort: corrupt JSON is renamed with a `.corrupted-{ts}`
suffix and replaced with defaults so the game never crashes on startup. No
external deps; everything goes through ``json``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _atomic_write_text(path: Path, content: str) -> None:
    """Write ``content`` to ``path`` atomically via tmp + ``os.replace``.

    Two failure modes the non-atomic ``path.write_text`` exposed:

    * **Mid-write process kill** — power loss / OS kill / Ctrl-C
      during the write leaves the target file truncated. On next
      boot, ``load_prefs`` / ``load_history`` parses an incomplete
      JSON, hits the ``json.JSONDecodeError`` branch, renames the
      file to ``.corrupted-...``, and the player silently loses
      their settings + run history.
    * **OneDrive sync collision** — this project's save dir often
      sits under ``%APPDATA%`` which is *not* OneDrive-synced on
      Windows, but ``GAIA_SAVE_DIR`` overrides land users in
      arbitrary directories that *might* be (per-user tests under
      project tree). The sync daemon briefly locks the target
      file after a write to fingerprint it; a second write
      within ~1 s raises ``PermissionError``.

    Atomic pattern: write to a ``.tmp`` sibling first (always a
    fresh file, never on the sync daemon's "currently syncing"
    list), then ``os.replace`` onto the target. ``os.replace`` is
    atomic on Windows for same-filesystem renames and silently
    overwrites the destination. Retry the replace with backoff
    when the destination is briefly locked so a single sync-daemon
    collision doesn't lose the write.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    last_exc: OSError | None = None
    for attempt in range(8):
        try:
            os.replace(str(tmp), str(path))
            return
        except PermissionError as exc:
            last_exc = exc
            time.sleep(0.25 * (attempt + 1))
    if last_exc is not None:
        # Last resort: remove the destination explicitly and rename.
        # If the file's truly locked this still raises, but most
        # sync-daemon holds release within ~2 s of write.
        try:
            if path.exists():
                os.remove(str(path))
            os.rename(str(tmp), str(path))
        except OSError as exc:
            logger.warning(
                "Atomic write of %s failed after retries: %s", path, exc,
            )


def _save_dir() -> Path:
    """Resolve the per-user save directory across platforms.

    Resolution order:

    1. ``GAIA_SAVE_DIR`` env override always wins — used by tests and
       by the Steam wrapper when Cloud-sync paths need to land outside
       the default.
    2. **Android** (``sys.platform == "android"``): use the app's
       private internal-storage dir, which is the only writable
       location that survives APK upgrade + isn't a permission gate.
       python-for-android exposes it via ``ANDROID_PRIVATE`` (the
       canonical buildozer/p4a path) — falls back to ``getFilesDir()``
       through ``android.storage`` if installed, then to
       ``~/files`` as a final shim. Never returns ``/`` or another
       process-shared directory: scribbling JSON there would either
       fail with permission denied or silently land outside the app's
       sandbox where Android's auto-cleanup can reap it.
    3. **Windows**: ``%APPDATA%\\GaiaUltimatum``.
    4. **Everything else** (Linux, macOS): ``~/.config/gaia_ultimatum``.

    Pygbag/emscripten (browser wasm): falls through to the Linux
    default, which is in-memory under emscripten's MEMFS. State is
    lost on tab reload — documented limitation of the web build.
    """
    override = os.environ.get("GAIA_SAVE_DIR")
    if override:
        return Path(override)
    # ``sys.platform`` may report ``linux`` under p4a even when running
    # on Android — combine signals so the Android branch fires
    # reliably.
    _is_android = (
        sys.platform == "android"
        or "ANDROID_ARGUMENT" in os.environ
        or hasattr(sys, "getandroidapilevel")
    )
    if _is_android:
        android_private = os.environ.get("ANDROID_PRIVATE")
        if android_private:
            return Path(android_private)
        try:
            from android.storage import app_storage_path  # type: ignore[import-not-found]
        except ImportError:
            pass
        else:
            return Path(app_storage_path())
        return Path.home() / "files"
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "GaiaUltimatum"
    # ``Path.home()`` can raise ``RuntimeError`` on emscripten when
    # ``$HOME`` is unset (pygbag doesn't always export it). Falling
    # back to ``/tmp`` keeps the per-tab MEMFS sandbox usable —
    # state still wipes on reload (already documented in the
    # docstring above), but at least the prefs file can be written
    # within the session.
    try:
        return Path.home() / ".config" / "gaia_ultimatum"
    except RuntimeError:
        return Path("/tmp/gaia_ultimatum")


def _ensure_dir() -> Path:
    d = _save_dir()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("Could not create save dir %s: %s", d, exc)
    return d


@dataclass
class Prefs:
    # Five fields previously lived here — ``master_volume`` /
    # ``music_volume`` / ``effects_volume`` (no slider UI exists; the
    # only audio setting is the mute toggle, which routes through
    # ``audio_muted``), ``onboarded`` (the tutorial-seen flag lives
    # on ``Game.tutorial_seen``), and ``last_country`` (picker
    # remembers catastrophe + difficulty but the country choice is
    # fresh per run). Verified via grep: none were read anywhere
    # outside this file's own ``to_dict``. ``Prefs.from_dict``
    # ignores unknown keys via the ``hasattr`` check, so existing
    # ``prefs.json`` files written before the cleanup still load
    # cleanly — the removed keys are silently dropped.
    audio_muted: bool = False
    reduce_motion: bool = False
    disable_flash: bool = False
    high_contrast: bool = False
    last_catastrophe: str | None = None
    last_difficulty: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "audio_muted": self.audio_muted,
            "reduce_motion": self.reduce_motion,
            "disable_flash": self.disable_flash,
            "high_contrast": self.high_contrast,
            "last_catastrophe": self.last_catastrophe,
            "last_difficulty": self.last_difficulty,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Prefs:
        out = cls()
        for k, v in data.items():
            if hasattr(out, k):
                setattr(out, k, v)
        return out


@dataclass
class RunRecord:
    catastrophe: str
    difficulty: str
    country: str
    outcome: str         # "victory" / "defeat" / "abandoned"
    turns: int
    timestamp: str       # ISO-8601 UTC

    def to_dict(self) -> dict[str, Any]:
        return {
            "catastrophe": self.catastrophe,
            "difficulty": self.difficulty,
            "country": self.country,
            "outcome": self.outcome,
            "turns": self.turns,
            "timestamp": self.timestamp,
        }


def load_prefs() -> Prefs:
    path = _save_dir() / "prefs.json"
    if not path.is_file():
        return Prefs()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("prefs.json root must be an object")
        return Prefs.from_dict(data)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not read prefs.json (%s); resetting", exc)
        _backup_corrupt(path)
        return Prefs()


def save_prefs(prefs: Prefs) -> None:
    _ensure_dir()
    path = _save_dir() / "prefs.json"
    try:
        _atomic_write_text(
            path,
            json.dumps(prefs.to_dict(), ensure_ascii=False, indent=2),
        )
    except OSError as exc:
        logger.warning("Could not write prefs.json: %s", exc)


def load_history() -> list[RunRecord]:
    path = _save_dir() / "history.json"
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("history.json root must be a list")
        out: list[RunRecord] = []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            try:
                out.append(RunRecord(
                    catastrophe=str(entry.get("catastrophe", "?")),
                    difficulty=str(entry.get("difficulty", "?")),
                    country=str(entry.get("country", "?")),
                    outcome=str(entry.get("outcome", "?")),
                    turns=int(entry.get("turns", 0)),
                    timestamp=str(entry.get("timestamp", "")),
                ))
            except (TypeError, ValueError):
                continue
        return out
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        logger.warning("Could not read history.json (%s); resetting", exc)
        _backup_corrupt(path)
        return []


def append_run(record: RunRecord, cap: int = 50) -> None:
    history = load_history()
    history.append(record)
    history = history[-cap:]
    _ensure_dir()
    path = _save_dir() / "history.json"
    try:
        _atomic_write_text(
            path,
            json.dumps(
                [r.to_dict() for r in history], ensure_ascii=False, indent=2,
            ),
        )
    except OSError as exc:
        logger.warning("Could not write history.json: %s", exc)


def now_iso() -> str:
    # ``datetime.utcnow()`` is deprecated since Python 3.12 (issues
    # DeprecationWarning in 3.14 which this project targets). The
    # timezone-aware ``datetime.now(timezone.utc)`` is the supported
    # replacement; ``.isoformat()`` emits ``+00:00`` which we strip
    # and replace with the canonical ``Z`` suffix to keep the on-disk
    # format identical for existing history.json files. The naive
    # ``utcnow + "Z"`` pattern produced the same wire format but
    # via an API the runtime warns against using.
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None).isoformat() + "Z"


def _backup_corrupt(path: Path) -> None:
    try:
        # Timezone-aware UTC replacement for the deprecated
        # ``datetime.utcnow().strftime(...)`` — preserves the
        # ``YYYYMMDDTHHMMSSZ`` suffix format used in existing
        # ``.corrupted-*.json`` filenames so any housekeeping tooling
        # (manual cleanup, log scrapers) that pattern-matches the
        # suffix keeps working unchanged.
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path.rename(path.with_suffix(f".corrupted-{ts}.json"))
    except OSError as exc:
        logger.warning("Could not back up corrupt save %s: %s", path, exc)
