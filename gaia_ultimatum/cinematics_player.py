"""MP4 cinematic playback for intro/outro moments.

Backed by OpenCV (``cv2``) when available; degrades to ``None`` everywhere
when it isn't installed (browser/pygbag builds, minimal environments). The
caller is expected to check :pyattr:`VideoClip.available` and fall back to
the existing procedural cinematic when the clip can't be opened.

Design:
- ``VideoClip`` is a lazy frame iterator that maps elapsed-ms to a pygame
  ``Surface`` for the corresponding frame. Sequential decoding is fast;
  random seeks (skip-back) trigger ``cv2.CAP_PROP_POS_FRAMES``.
- The most recently decoded surface is cached so re-querying within the same
  frame is free.
- The class is intentionally synchronous — pygame's loop is the master clock
  and the decoder is fast enough at ~30 fps that an async pipeline isn't
  worth the complexity.
- ``CinematicLibrary`` stores paths *without* opening on construction by
  default (``from_paths_lazy``), so boot is instant. Each clip is
  ``open()``-ed on first ``get(name)``. Optional ``preload_in_background``
  fires a daemon thread that walks the path map and pre-opens entries so
  later first-plays don't pay the file-open cost either; preload exists
  for desktop where boot perf isn't a concern. Android avoids the
  3–5 s boot hitch from 16 sequential ``cv2.VideoCapture.open`` calls.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:  # pragma: no cover — type-only import
    import cv2 as _cv2_module

logger = logging.getLogger(__name__)

try:
    import cv2 as _cv2  # type: ignore[import-not-found]

    _CV2_AVAILABLE = True
except Exception as _exc:  # noqa: BLE001 — any import failure is "not available"
    _cv2 = None  # type: ignore[assignment]
    _CV2_AVAILABLE = False
    logger.info("OpenCV unavailable, MP4 cinematics disabled: %s", _exc)


@dataclass
class VideoClip:
    """Lazy MP4 → pygame.Surface frame iterator.

    Lifecycle:
        clip = VideoClip(path)
        clip.open()                       # returns False if cv2 missing / bad file
        frame = clip.frame_at(elapsed_ms) # pygame.Surface or None
        if clip.is_finished(elapsed_ms):  ...
        clip.close()
    """

    path: Path
    _cap: object = None  # cv2.VideoCapture; typed loosely so the field is import-safe
    _fps: float = 30.0
    _frame_count: int = 0
    _duration_ms: int = 0
    _current_frame_idx: int = -1
    _current_surface: pygame.Surface | None = None
    _size: tuple[int, int] = (0, 0)

    @property
    def available(self) -> bool:
        """True iff cv2 is importable, the file exists, and the cap is open."""
        return _CV2_AVAILABLE and self.path.is_file() and self._cap is not None

    @property
    def size(self) -> tuple[int, int]:
        """Native (width, height) of the source video, (0, 0) before open()."""
        return self._size

    def open(self) -> bool:
        """Open the underlying ``VideoCapture``. Returns False on failure."""
        if not _CV2_AVAILABLE:
            return False
        if not self.path.is_file():
            logger.warning("Cinematic file missing: %s", self.path)
            return False
        if self._cap is not None:
            return True
        try:
            cap = _cv2.VideoCapture(str(self.path))  # type: ignore[union-attr]
            if not cap.isOpened():
                logger.warning("Cinematic could not be opened: %s", self.path)
                return False
            self._cap = cap
            self._fps = cap.get(_cv2.CAP_PROP_FPS) or 30.0  # type: ignore[union-attr]
            self._frame_count = int(
                cap.get(_cv2.CAP_PROP_FRAME_COUNT) or 0,  # type: ignore[union-attr]
            )
            width = int(cap.get(_cv2.CAP_PROP_FRAME_WIDTH) or 0)  # type: ignore[union-attr]
            height = int(cap.get(_cv2.CAP_PROP_FRAME_HEIGHT) or 0)  # type: ignore[union-attr]
            self._size = (width, height)
            self._duration_ms = (
                int((self._frame_count / self._fps) * 1000) if self._fps else 0
            )
            logger.info(
                "Cinematic ready: %s (%dx%d @ %.1ffps, %d frames, %d ms)",
                self.path.name, width, height,
                self._fps, self._frame_count, self._duration_ms,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cinematic open failed for %s: %s", self.path, exc)
            self._cap = None
            return False

    def close(self) -> None:
        if self._cap is not None:
            try:
                self._cap.release()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass
            self._cap = None
        self._current_frame_idx = -1
        self._current_surface = None

    def duration_ms(self) -> int:
        return self._duration_ms

    # Maximum forward gap (in frames) bridged by read-and-discard
    # catch-up instead of a seek. H.264 ``CAP_PROP_POS_FRAMES`` is
    # O(keyframe-distance) — typically 30-100 ms per seek on the
    # codec the cinematics encode with; sequential ``cap.read()`` is
    # 3-5 ms per frame. The crossover sits around 8 frames: at
    # 30 fps clip that's ~270 ms of game-loop jitter, well past
    # anything a healthy frame budget produces but still cheaper to
    # read-and-discard than to seek. Beyond this we fall back to
    # the keyframe seek.
    _SEQUENTIAL_CATCHUP_THRESHOLD = 8

    def frame_at(self, elapsed_ms: int) -> pygame.Surface | None:
        """Return the surface for the frame at ``elapsed_ms``.

        Returns the previously-decoded surface (or ``None``) when the request
        is beyond the clip's end so the caller can hold the last frame while
        showing a fade-out.

        Two refinements over a single ``seek-or-sequential`` policy:

        * **Small-gap catch-up via read-and-discard**: when game-loop
          jitter puts ``target_idx`` a few frames ahead of where the
          cap naturally lands, walking the gap with sequential
          ``cap.read()`` calls is much cheaper than one
          ``CAP_PROP_POS_FRAMES`` seek (which has to re-decode from
          the previous keyframe on H.264 / H.265 / VP9). Only gaps
          beyond ``_SEQUENTIAL_CATCHUP_THRESHOLD`` fall through to
          the seek path.
        * **State invalidation on read/seek failure**: any
          OpenCV-side failure resets ``_current_frame_idx = -1`` so
          the next call seeks unconditionally instead of relying on
          a stale sequence assumption. Without this, a single
          transient ``cap.read()`` failure left the player decoding
          off-by-one for the rest of the clip — silent desync the
          caller couldn't detect.
        """
        if self._cap is None or self._frame_count <= 0:
            return self._current_surface
        target_idx = int((elapsed_ms / 1000.0) * self._fps)
        if target_idx >= self._frame_count:
            return self._current_surface
        if target_idx < 0:
            target_idx = 0
        if target_idx == self._current_frame_idx:
            return self._current_surface

        # ``gap`` = frames between where the cap will naturally land
        # on the next read (``current + 1``) and the target. Negative
        # for rewinds, 0 for the in-sequence case, positive for
        # forward catch-up.
        gap = target_idx - (self._current_frame_idx + 1)
        if gap < 0 or gap > self._SEQUENTIAL_CATCHUP_THRESHOLD:
            # Backward seek OR forward jump too large to be cheaper
            # than the keyframe seek. Both paths use CAP_PROP_POS_FRAMES.
            try:
                self._cap.set(  # type: ignore[union-attr]
                    _cv2.CAP_PROP_POS_FRAMES, target_idx,  # type: ignore[union-attr]
                )
            except Exception:  # noqa: BLE001
                self._current_frame_idx = -1
                return self._current_surface
        elif gap > 0:
            # Small forward gap: read-and-discard catch-up. Reads are
            # sequential decodes, cheap on every codec we ship.
            for _ in range(gap):
                try:
                    ok, _ = self._cap.read()  # type: ignore[union-attr]
                except Exception:  # noqa: BLE001
                    self._current_frame_idx = -1
                    return self._current_surface
                if not ok:
                    self._current_frame_idx = -1
                    return self._current_surface
        # gap == 0: cap is already positioned to deliver target_idx
        # on the next read; no extra work needed.

        try:
            ok, frame = self._cap.read()  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            self._current_frame_idx = -1
            return self._current_surface
        if not ok or frame is None:
            self._current_frame_idx = -1
            return self._current_surface
        # OpenCV gives BGR; pygame wants RGB.
        frame = _cv2.cvtColor(frame, _cv2.COLOR_BGR2RGB)  # type: ignore[union-attr]
        h, w = frame.shape[:2]
        try:
            surf = pygame.image.frombuffer(frame.tobytes(), (w, h), "RGB")
        except Exception as exc:  # noqa: BLE001
            logger.debug("Frame buffer conversion failed at %d: %s", target_idx, exc)
            # The read succeeded (cap advanced) but the buffer
            # conversion failed; the cap is now one ahead of what
            # we think. Invalidate so the next call seeks rather
            # than relying on the stale sequence.
            self._current_frame_idx = -1
            return self._current_surface
        self._current_surface = surf
        self._current_frame_idx = target_idx
        return surf

    def is_finished(self, elapsed_ms: int) -> bool:
        return self._duration_ms > 0 and elapsed_ms >= self._duration_ms


@dataclass
class CinematicLibrary:
    """Bundle of named cinematics for the run, lazily opened.

    ``clips`` holds already-opened ``VideoClip`` objects keyed by name;
    ``pending_paths`` holds the path for entries that haven't been
    opened yet. ``get(name)`` opens lazily, moves the clip into
    ``clips``, and returns it. Failures from ``cv2.VideoCapture.open``
    drop the entry permanently — callers see ``None`` from ``get`` and
    fall back to the procedural envelope just like they do when ``cv2``
    itself is missing.

    Use ``from_paths_lazy`` for instant boot (Android, Steam Deck,
    anywhere a 16-clip ``cv2.VideoCapture.open`` sweep would hitch the
    main thread). Use ``from_paths`` for eager open at boot when boot
    latency doesn't matter — primarily a back-compat shim for any
    caller that depended on every clip being available the instant the
    library was constructed.
    """

    clips: dict[str, VideoClip] = field(default_factory=dict)
    pending_paths: dict[str, Path] = field(default_factory=dict)
    # Guards concurrent ``get()`` + background preload from racing on
    # the same path. Without this two threads could double-open the
    # same clip when the preloader is still mid-sweep and the player
    # triggers an early cinematic. The lock is held only across the
    # ``pop`` → ``open`` → ``insert`` window per clip, so contention is
    # negligible.
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False, compare=False,
    )

    @classmethod
    def from_paths(cls, paths: dict[str, Path]) -> CinematicLibrary:
        """Eager-open every clip at construction (legacy back-compat).

        Use ``from_paths_lazy`` instead unless you specifically need
        every clip's metadata available the instant the library is
        constructed.
        """
        lib = cls()
        for name, path in paths.items():
            clip = VideoClip(path=path)
            if clip.open():
                lib.clips[name] = clip
            else:
                logger.info("Cinematic %r not available (path=%s)", name, path)
        return lib

    @classmethod
    def from_paths_lazy(cls, paths: dict[str, Path]) -> CinematicLibrary:
        """Store paths without opening — boot is instant.

        ``get(name)`` opens the matching clip on first request. Use
        ``preload_in_background()`` after construction to pre-open
        every remaining clip on a daemon thread; ``get`` still races
        cleanly with the preloader.
        """
        return cls(pending_paths=dict(paths))

    def get(self, name: str) -> VideoClip | None:
        """Return the clip, opening lazily if it's still pending.

        Returns ``None`` when (a) the name was never registered, or
        (b) the open failed — in both cases the caller falls back to
        the procedural envelope.
        """
        clip = self.clips.get(name)
        if clip is not None:
            return clip
        with self._lock:
            # Re-check under the lock — another thread may have opened
            # it between the first dict read and our acquire.
            clip = self.clips.get(name)
            if clip is not None:
                return clip
            path = self.pending_paths.pop(name, None)
            if path is None:
                return None
            clip = VideoClip(path=path)
            if not clip.open():
                logger.info("Cinematic %r not available (path=%s)", name, path)
                return None
            self.clips[name] = clip
            return clip

    def preload_in_background(self) -> threading.Thread:
        """Start a daemon thread that pre-opens every pending clip.

        Returns the thread handle so callers can join() on shutdown if
        they care. Safe to call multiple times — duplicate threads
        will see an empty ``pending_paths`` after the first sweep
        completes and exit immediately. The lock ensures ``get()`` and
        the preloader can't race on the same clip.

        Boot perf trade-off: with preload, the file-open cost is paid
        on a background thread instead of on the main thread; the
        player sees neither a boot hitch nor a first-play hitch.
        Without preload, boot is free and the first play of each clip
        pays ~30-100 ms of open latency (invisible behind the fade-in
        the renderer already uses on cinematic entry).
        """
        def _preload() -> None:
            # Snapshot keys upfront so the iteration isn't perturbed by
            # ``get()`` calls draining pending_paths under us.
            with self._lock:
                names = list(self.pending_paths.keys())
            for name in names:
                # Route every open through ``get`` so the lock + dict
                # bookkeeping stays in one place.
                self.get(name)

        # Skip the preload thread entirely when cv2 isn't available
        # (browser/WASM, p4a without opencv recipe). ``get()`` would
        # short-circuit to ``None`` on every clip anyway — the thread
        # would just iterate, find nothing to open, and exit — but on
        # pygame-web ``threading.Thread.start()`` is shimmed to a no-op
        # that can still log a pygbag warning. Better to skip outright.
        if not _CV2_AVAILABLE:
            t = threading.Thread(target=lambda: None, daemon=True, name="cinematic-preload-noop")
            return t  # not started — caller's contract is just "got a handle"
        t = threading.Thread(target=_preload, daemon=True, name="cinematic-preload")
        t.start()
        return t

    def close_all(self) -> None:
        for clip in self.clips.values():
            clip.close()
        self.clips.clear()
        self.pending_paths.clear()
