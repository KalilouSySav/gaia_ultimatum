"""Audio playback manager.

Thin wrapper around ``pygame.mixer`` that loads/plays named effects and
manages one or more music *playlists*. Each playlist is a category of
tracks (e.g. ``title`` / ``picker`` / ``playing`` / ``outro``); the
manager auto-advances within a playlist when the current track ends, and
cross-fades between playlists when the caller switches category.

Tracks can be discovered automatically from ``sounds/playlists/<category>/``
or registered explicitly. With no playlist subdirectories, the manager
falls back to the legacy single-track behaviour around ``background.mp3``.
Safe to use in headless environments (all operations degrade gracefully
if the mixer fails to initialise).
"""

from __future__ import annotations

import functools
import logging
import math
import random
import wave
from collections import deque
from pathlib import Path

import pygame

from gaia_ultimatum.assets import SOUNDS_DIR
from gaia_ultimatum.config import AudioConfig

logger = logging.getLogger(__name__)


# Custom SDL event posted by ``pygame.mixer.music`` when a track ends. The
# app loop forwards events to AudioManager.handle_event which advances the
# playlist — gives gapless track changes without polling get_busy each
# frame.
MUSIC_END_EVENT = pygame.USEREVENT + 1
# Subdir under SOUNDS_DIR where each subfolder is a playlist category. The
# user can drop new .mp3 files in `sounds/playlists/playing/` etc. to grow
# the in-game soundtrack without touching code.
PLAYLISTS_SUBDIR = "playlists"

# Short fade-in applied when ``advance_track`` rotates to the next track
# within the same playlist (track ended naturally, no playlist switch
# in flight). MUSIC_END_EVENT delivery lags the actual track end by a
# pygame-internal frame (~10-50 ms) and ``pygame.mixer.music.load`` + a
# first ``play()`` adds another 10-30 ms — so a ``fade_in_ms=0`` advance
# produces an audible silence-then-snap pair on the ambient beds the
# v3 library ships. A 150 ms ramp covers the latency gap *and* the
# attack of the new track in one envelope, so transitions feel like
# gapless playback. Distinct from the 1500 ms cross-fade used for
# playlist *category* switches in ``play_playlist`` — that handles a
# different transition (one track fading out while a different one
# fades in), this one only smooths the start of the incoming track
# because the previous track has already stopped on its own.
WITHIN_PLAYLIST_FADE_MS = 150


# Minimum on-screen lifetime for a single track-load within each
# playlist. The bundled playing tracks have been remix-extended by
# ``tools/extend_playing_remixes.py`` so they all land between 2 and
# 3 minutes already — this threshold is a safety net for user-added
# tracks that come in shorter. With every bundled track at ≥119 s,
# ``_loops_for`` returns 0 for all of them and the auto-advance
# behaves exactly as it would without this feature.
#
# Each playlist gets its own threshold so calmer beds (title / outro)
# can rotate at their natural cadence — those screens are brief
# anyway. ``0`` means "play once, no extra loops" (the original
# behaviour). The MUSIC_END_EVENT auto-advance still fires once
# all loops complete, so the shuffle/mood-weighting cascade keeps
# working — looping just extends each track's slot, it doesn't
# pin the player to one track.
_PLAYLIST_MIN_PLAYTIME_S: dict[str, float] = {
    "playing": 90.0,
}


def _wav_duration_s(path: Path) -> float | None:
    """Return WAV duration in seconds, or None on any read failure."""
    try:
        with wave.open(str(path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate <= 0:
                return None
            return frames / rate
    except (wave.Error, OSError, EOFError) as exc:
        logger.warning("Could not measure WAV duration of %s: %s", path, exc)
        return None


# Vorbis identification header magic ('vorbis' preceded by packet-type
# byte 0x01) — used to confirm the first OGG packet is a Vorbis ID
# header before we trust the sample-rate bytes that follow it. Anchored
# bytes object so the search is a single ``b''.find()`` over the page,
# not a hand-rolled byte loop.
_VORBIS_ID_PACKET_MAGIC = b"\x01vorbis"


def _ogg_duration_s(path: Path) -> float | None:
    """Return OGG-Vorbis duration in seconds, or None on read failure.

    Two-step parse, stdlib-only (no audioop / no ffmpeg / no external
    bindings):

    1. Read the first ~8 KB and locate the **Vorbis identification
       header** (packet type 0x01 + magic ``b"vorbis"``). The sample
       rate sits 12 bytes after the magic, as a little-endian uint32.
       8 KB is comfortably larger than any plausible OGG page header
       (max 65 KB but practical pages are ≤ 4 KB), so the ID packet
       always falls inside that window.

    2. Read the last ~64 KB and scan backwards for the last ``OggS``
       page signature. The granule position (sample count up to the
       end of this page) is a little-endian uint64 at offset 6 from
       the page signature start. Vorbis sets the final granule to the
       total decoded sample count, so duration = granule / rate.

    The Android Play Store build transcodes WAVs to OGG via
    ``tools/transcode_to_ogg.py`` to fit the 150 MB APK base cap.
    Without OGG duration support, ``_loops_for`` would return 0 for
    every Vorbis track and the playing-bed's 90 s minimum playtime
    would silently fail to extend short tracks. This restores the
    loop-extension contract for Android.

    Returns None on any malformed file — caller (``_loops_for``)
    treats that as "play once" exactly like the legacy non-WAV path.
    """
    try:
        size = path.stat().st_size
        if size < 64:
            return None
        with open(path, "rb") as f:
            head = f.read(min(8192, size))
            magic_at = head.find(_VORBIS_ID_PACKET_MAGIC)
            if magic_at < 0:
                return None
            # ID-header layout after the 7-byte magic:
            #   uint32 vorbis_version
            #   uint8  audio_channels
            #   uint32 audio_sample_rate     ← target
            #   ... (bitrate fields we ignore)
            rate_off = magic_at + len(_VORBIS_ID_PACKET_MAGIC) + 4 + 1
            if rate_off + 4 > len(head):
                return None
            rate = int.from_bytes(head[rate_off:rate_off + 4], "little")
            if rate <= 0:
                return None
            # Granule position lives in the *last* OggS page. Scan
            # backwards from end-of-file. 64 KB is generous — OGG
            # page size is ≤ 65 535 bytes by spec, so the last page
            # boundary always falls within this window.
            tail_size = min(65_536, size)
            f.seek(size - tail_size)
            tail = f.read(tail_size)
            last_oggs = tail.rfind(b"OggS")
            if last_oggs < 0:
                return None
            # OGG page header layout:
            #   bytes 0..3   capture pattern "OggS"
            #   byte  4      stream structure version
            #   byte  5      header type flag
            #   bytes 6..13  granule position (int64 LE)
            gpos_off = last_oggs + 6
            if gpos_off + 8 > len(tail):
                return None
            granule = int.from_bytes(
                tail[gpos_off:gpos_off + 8], "little", signed=True,
            )
            if granule <= 0:
                return None
            return granule / rate
    except OSError as exc:
        logger.warning("Could not measure OGG duration of %s: %s", path, exc)
        return None


@functools.lru_cache(maxsize=256)
def _track_duration_s(path: Path) -> float | None:
    """Return track duration in seconds, or None when the format isn't
    supported or the file can't be parsed.

    Dispatches by suffix — ``.wav`` reads via stdlib ``wave``, ``.ogg``
    reads via the hand-rolled Vorbis header parser above. MP3 returns
    None (no stdlib path) and ``_loops_for`` falls through to play-once
    semantics for that format — the bundled playlists no longer ship
    MP3, but the discovery whitelist still accepts it for back-compat
    with user-added tracks.

    Cached: track files don't change at runtime, and ``_loops_for``
    can be called multiple times per session.
    """
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return _wav_duration_s(path)
    if suffix == ".ogg":
        return _ogg_duration_s(path)
    return None


def _loops_for(path: Path, playlist: str | None) -> int:
    """Loop count to pass to ``pygame.mixer.music.play`` so the track
    reaches the playlist's minimum playtime.

    Returns ``0`` (play once) when the playlist has no minimum
    configured, when the duration is unknown, or when the track is
    already long enough.
    """
    if playlist is None:
        return 0
    target = _PLAYLIST_MIN_PLAYTIME_S.get(playlist)
    if not target:
        return 0
    duration = _track_duration_s(path)
    if duration is None or duration <= 0:
        return 0
    # ceil(target / duration) total plays minus one means "loops" arg.
    # math.ceil avoids stopping just shy of the target (a 37 s track
    # at target 90 s would otherwise compute floor(90/37)=2 → 74 s,
    # below threshold). Hard cap at 5 extra loops so a hypothetical
    # 1-second file can't pin the player to a single track for 5 min.
    return min(5, max(0, math.ceil(target / duration) - 1))


# Mood-target intensities for track-name keywords. The v3 track filenames
# encode mood explicitly (``04_lull_tension``, ``03_climax_tension``,
# ``06_novelty_absurd``, etc.), so the shuffle can match each track's
# preferred dramatic register against the current music intensity. A
# track whose target intensity is close to ``self._smoothed_intensity``
# gets weighted higher in the shuffle pool than a track whose target is
# far off — calm beds favour calm tracks, peak tension favours intense
# tracks, but nothing is excluded outright (every track keeps non-zero
# weight, so the FIFA-style variety the design intends still holds).
#
# Falls back to 0.5 (neutral) when a track's filename matches no
# keyword — keeps the system robust to user-added tracks with arbitrary
# names. Compound names (e.g. ``00_calm_reflection``) get the **average**
# of matched keywords, so multi-mood tracks land between their pieces.
_MOOD_KEYWORDS: tuple[tuple[str, float], ...] = (
    # Title-bed moods — quiet end of the spectrum.
    ("proverb",      0.15),
    ("calm",         0.20),
    # ``reflect`` covers ``reflect`` / ``reflection`` / ``reflective``
    # via the substring check, so the three-keyword cluster collapses
    # to its shortest stem. Was three separate entries, which left
    # tracks like ``outro/00_reflect_tension.wav`` (token ``reflect``)
    # falling through to neutral 0.5 — neither ``reflection`` nor
    # ``reflective`` is a substring of ``reflect``, so the previous
    # list missed it entirely and the track classified at 0.70 (only
    # ``tension`` matched).
    ("reflect",      0.20),
    ("deep",         0.25),
    ("warm",         0.30),
    ("drone",        0.30),
    # Picker / mid-range moods.
    ("airy",         0.40),
    ("chanson",      0.40),
    ("vocal",        0.40),
    ("anticipation", 0.40),
    # ``appeal`` — earnest mid-low register. Earth-themed call-to-action
    # tracks (the French ``12_chanson_appeal`` source) carry urgency
    # without peak energy; pairs with ``chanson`` (0.40) to blend at
    # ~0.425 — the gentler, more reflective end of the playing bed.
    ("appeal",       0.45),
    # ``light`` — bright but lifted (think orchestral airy register, not
    # peak energy). Sits between ``chanson`` (0.40) and ``bright`` (0.50).
    # Added with the ``09_symphony_light`` track (orchestral grandeur in
    # a bright key); the keyword also fits any future track whose tone
    # is best read as "lit from above" rather than "high-energy".
    ("light",        0.45),
    ("bright",       0.50),
    ("novelty",      0.50),
    ("absurd",       0.50),
    # ``instrumental`` — neutral mid-mood register for tracks named only
    # by their instrumentation (no vocal cue, no emotional descriptor).
    # Used on ``17_instrumental`` (pure instrumental, ambient register)
    # and as a blending partner in ``18_cinematic_instrumental`` where
    # the cinematic 0.65 lifts it to a higher resting point. Sits at
    # 0.50 — the genuine neutral point where the picker would default
    # to anyway in the absence of any classifier signal.
    ("instrumental", 0.50),
    # Both ``rise`` and ``rising`` need their own entries — ``rise``
    # is NOT a substring of ``rising`` (the 4th char differs: ``e``
    # vs ``i``), so a track named ``02_rising_tension.wav`` would only
    # match ``tension`` if ``rising`` were dropped, classifying it at
    # 0.70 (peak tension) instead of the intended 0.625. Keep both
    # entries explicitly even though they share the same target
    # intensity.
    ("rise",         0.55),
    ("rising",       0.55),
    ("swing",        0.55),
    # ``vintage`` — early-recording character (1930s-50s era jazz / swing
    # / ballads). Mid-mood not because the music is calm but because the
    # vintage *texture* (mono-ish balance, narrower frequency range)
    # reads as less aggressive than a modern peak-energy track. Anchors
    # the ``19_frantic_swing`` track's vintage swing source so the
    # nostalgia layer of "Frantic Vintage Swing" pulls the blend down
    # from ``frantic`` alone (0.80) toward a tempered 0.675 with
    # ``swing`` (0.55).
    ("vintage",      0.55),
    # ``symphony`` — orchestral mid-range. Paired with ``light`` on the
    # ``09_symphony_light`` track to blend at 0.50, a deliberately
    # mid-band entry in a playlist otherwise dominated by 0.65+ tension
    # registers. Gives the playing bed a moment of cinematic relief
    # between the energy/climax tracks.
    ("symphony",     0.55),
    # ``irreverent`` — playful subversion. Pairs with ``chanson`` on the
    # ``10_chanson_irreverent`` track (French cabaret with a sardonic
    # edge) to land at ~0.475 — the lowest non-``lull`` slot in the
    # playing bed, surfacing when the run hits its calmer beats.
    ("irreverent",   0.55),
    # ``anthem`` — hopeful, lifted mid-energy register (think the
    # environmental-anthem character of ``11_anthem_bright``). Pairs
    # with ``bright`` (0.50) to blend at 0.575, filling the 0.55-0.60
    # band that was otherwise occupied only by ``_warm`` siblings of
    # the original tension tracks.
    ("anthem",       0.65),
    # Playing-bed moods — high end.
    ("lull",         0.35),  # the calmest of the playing tracks
    ("cinematic",    0.65),
    ("energy",       0.70),
    ("tension",      0.70),
    ("pulse",        0.70),
    # ``chaos`` — high-mid energy of the *playful* kind (Spike-Jones-
    # style swing chaos), distinct from ``drive`` (0.75) which reads as
    # dramatic forward motion. Paired with ``swing`` on the
    # ``08_swing_chaos`` track to blend at 0.625, slotting between the
    # rising-tension and cinematic-drive registers.
    ("chaos",        0.70),
    ("drive",        0.75),
    ("dark",         0.75),
    # ``frantic`` — restless, urgent energy. Distinct from ``drive`` (0.75
    # — dramatic forward motion) and ``climax`` (0.90 — peak intensity):
    # frantic carries the kinetic instability of "everything happening
    # at once" without dramatic build. Used on ``19_frantic_swing``
    # (Spike-Jones-era frantic swing with novelty effects) and tempers
    # to 0.675 via the swing 0.55 blend, restoring the peak-tension end
    # of the playing playlist after the original 0.7+ tracks were cut.
    ("frantic",      0.80),
    ("climax",       0.90),
)


@functools.lru_cache(maxsize=256)
def _track_target_intensity(path: Path) -> float:
    """Estimate a track's preferred play intensity from its filename.

    Returns the **average** of all matching mood-keyword targets, or
    0.5 (neutral) when no keyword matches. Average-of-matches gives
    multi-mood compound names a sensible blended score (``calm_reflection``
    → average of calm 0.20 and reflection 0.20 = 0.20; ``climax_tension``
    → average of climax 0.90 and tension 0.70 = 0.80).

    Cached: filenames don't change at runtime, and every shuffle pick
    re-classifies every candidate. The 256-entry LRU comfortably holds
    even the largest plausible playlist library (the bundled v3 ships
    ~26 tracks across four categories) and the cache is keyed on
    ``Path`` identity — so renames to the same logical track still
    revisit the keyword scan, while the steady-state lookup is a hash
    instead of a 25-keyword substring sweep per candidate.
    """
    name = path.stem.lower()
    matches = [target for keyword, target in _MOOD_KEYWORDS if keyword in name]
    if not matches:
        return 0.5
    return sum(matches) / len(matches)


class AudioManager:
    """Loads and plays named sound effects plus a per-category music playlist."""

    def __init__(self, config: AudioConfig) -> None:
        self._config = config
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        # Per-sound cooldown window (ms) + last-play timestamp (ms). When
        # a sound has a cooldown configured, ``play_sound`` short-circuits
        # if the previous play landed inside the window — prevents
        # identical UI ticks from stacking on rapid clicks or
        # back-to-back same-frame events (e.g. BUTTON_CLICK +
        # EVOLUTION_PURCHASED both route to "click", which would
        # otherwise burn two mixer channels on one 55 ms tick).
        # Dramatic chimes ("effect": milestone / victory / defeat)
        # stay at cooldown 0 so each one fires unconditionally — they
        # carry semantic weight that the listener should hear every
        # time.
        self._sound_cooldown_ms: dict[str, int] = {}
        self._sound_last_play_ms: dict[str, int] = {}
        self._music_loaded = False
        self._available = self._init_mixer()
        self._runtime_muted = config.muted
        # Playlist state.
        self._playlists: dict[str, list[Path]] = {}
        self._current_playlist: str | None = None
        self._current_track_idx: int = 0
        self._current_track_path: Path | None = None
        self._pending_fade_in: int = 0
        # Transition pads — one short (15 s) ambient WAV per regular
        # track, stored in ``<playlist>/transitions/``. ``advance_track``
        # plays one between every two regular tracks so two unrelated
        # remixed pieces don't slap-cut into each other. See
        # ``tools/generate_playing_transitions.py`` for the synthesis
        # chain (low-pass + reverb wash + RMS-under target). ``_last_
        # played_kind`` tracks per-playlist whether the previous load
        # was 'regular' or 'transition' so the scheduler alternates.
        # ``_recent_pad_paths`` is per-playlist memory (2-deep) that the
        # mood-weighted pad picker excludes from the candidate pool —
        # without it the picker would repeatedly land on whichever pad
        # best matches the surrounding tracks' mood, producing a
        # noticeable "same wash again" feel within a single session.
        self._transitions: dict[str, list[Path]] = {}
        self._last_played_kind: dict[str, str] = {}
        self._recent_pad_paths: dict[str, deque[Path]] = {}
        # Per-playlist memory of the most-recent *regular* track (not
        # pad) so the continuity-aware regular picker can blend its
        # mood into the next pick's target. Distinct from
        # ``_current_track_path`` because that field becomes the pad
        # path while the pad is playing — we need to remember what was
        # playing *before* the pad to bridge across both hops of the
        # regular → pad → regular handoff.
        self._last_regular_path: dict[str, Path] = {}
        # FIFA-style shuffled track order. Sequential auto-advance
        # (track[i+1]) makes a 6-track playlist sound like a 90-second
        # loop because the player hears the same neighbour every time
        # — predictability defeats the variety the multi-track
        # playlists exist for. Shuffle picks the next track at random
        # but *avoids* immediately repeating the current one (the
        # "anti-stutter" rule used by every modern music app), so the
        # listener experience is varied without ever sounding like a
        # bug. ``_shuffle_rng`` is a dedicated stream so it doesn't
        # collide with anything else seeding ``random``.
        self._shuffle_rng = random.Random()
        # Recent-track memory for shuffle: ``_pick_next_index`` excludes
        # the last N played indices from the candidate set, so on a
        # 4-track playlist the prior-prior track can't come back after
        # a single detour (the previous logic only avoided the immediate
        # current track, allowing patterns like A→B→A→B→A). Two-deep
        # memory is the sweet spot — enough to break short oscillations
        # without starving smaller playlists of candidates. The deque
        # gracefully degrades on tiny playlists via the
        # "fall back to just-not-current" branch in ``_pick_next_index``.
        self._recent_track_indices: deque[int] = deque(maxlen=2)
        # Dynamic-ducking follower state. The intensity → volume
        # mapping in ``set_music_intensity`` used to write the new
        # volume directly every frame, which meant a single
        # country-tips-critical event produced an audible volume
        # snap on the current music bed. Now the manager keeps a
        # smoothed follow value (``_smoothed_intensity``) and lerps
        # toward each new target with a single-pole IIR so big
        # tension jumps fade in over ~2 s instead of clicking.
        self._smoothed_intensity = 0.0
        # Mute envelope. ``_runtime_muted`` is the *target* state set
        # by the M-key toggle; ``_mute_envelope`` is the actual scalar
        # multiplied into the music volume each frame. Glides toward
        # 1.0 (audible) or 0.0 (silenced) over ~10 frames in
        # ``set_music_intensity``, so toggling mute mid-track no longer
        # clicks the way snapping volume from N → 0 instantaneously
        # did. Initialised in sync with the boot mute state so there's
        # no fade-in from silence on a muted launch (and conversely no
        # fade-out from full volume on an unmuted launch).
        self._mute_envelope = 0.0 if config.muted else 1.0
        if self._available:
            # Lets handle_event know when the track ends.
            pygame.mixer.music.set_endevent(MUSIC_END_EVENT)

    @staticmethod
    def _init_mixer() -> bool:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            return True
        except pygame.error as exc:
            logger.warning("Audio disabled: %s", exc)
            return False

    @property
    def available(self) -> bool:
        return self._available

    def load_sound(
        self,
        name: str,
        path: str | Path,
        *,
        cooldown_ms: int = 0,
    ) -> None:
        """Load and cache a named sound effect.

        ``cooldown_ms`` (default 0) suppresses identical plays inside
        the window. Use a small value (~40-60 ms) on rapid-fire UI
        ticks ("click") to stop the same 55 ms sample from stacking
        on top of itself across consecutive frames; leave at 0 for
        chimes that carry semantic weight (one per event).

        Catches the ``(pygame.error, OSError)`` family — same rationale
        as ``_load_and_play`` for music: ``pygame.mixer.Sound`` can
        raise ``FileNotFoundError`` (an ``OSError`` subclass, not a
        ``pygame.error``) if the file vanishes between the ``is_file``
        pre-check and the actual load (sync daemon, antivirus quarantine,
        external deletion). Without the broader catch, that race would
        crash the audio thread.
        """
        if not self._available:
            return
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = SOUNDS_DIR / resolved
        if not resolved.is_file():
            logger.warning("Sound file not found: %s", resolved)
            return
        try:
            sound = pygame.mixer.Sound(str(resolved))
        except (pygame.error, OSError) as exc:
            logger.warning("Failed to load sound %s: %s", resolved, exc)
            return
        sound.set_volume(self._effective(self._config.effects_volume))
        self._sounds[name] = sound
        if cooldown_ms > 0:
            self._sound_cooldown_ms[name] = cooldown_ms

    def play_sound(self, name: str, *, volume_scale: float = 1.0) -> None:
        """Play a named sound. ``volume_scale`` lets callers vary intensity
        per-event (e.g. dramatic milestones louder than UI clicks) without
        having to load duplicate samples.

        Volume is set on the Sound object before play. The previous
        implementation did ``set_volume(scaled); play(); set_volume(base)``,
        but ``Sound.set_volume`` propagates *to currently-playing channels*
        of that sound — so the post-play "reset" silently un-did the
        scale partway through playback. Most audible on the ~1 s VICTORY
        / DEFEAT chimes (clicks are too short for the bug to register).

        The fix: always set the volume explicitly before each play,
        including for the volume_scale=1.0 path (the prior code's
        else-branch played at *whatever volume the last scaled call
        left in place* — also wrong, since a 0.55-scaled click would
        leave subsequent plays running at 55 %). Side effect: concurrent
        plays of the same sound at different scales share the latest
        scale. Acceptable for this game — overlapping audio events are
        rare in single-player strategy gameplay.

        **Music-aware SFX gain.** Adds a `1 + 0.30 × smoothed_intensity`
        multiplier so the effects channel rises *with* the music bed.
        Was a flat volume regardless of music state: at peak intensity
        the music plays at 110 % of baseline and the SFX still played at
        their 64 % default — dramatic chimes (country collapse, critical
        milestone) could vanish under the loud bed at exactly the moment
        they were meant to cut through. The 30 % cap leaves head-room
        under the 1.0 clamp on every reasonable (volume × scale) combo
        (default config: ``0.8 × 0.8 × 1.0 × 1.30 = 0.832``), and the
        smoothed intensity is already IIR-smoothed so the gain never
        clicks on sudden tension jumps.
        """
        sound = self._sounds.get(name)
        if sound is None:
            return
        base = self._effective(self._config.effects_volume)
        # Short-circuit when muted (config.muted or runtime mute): the
        # computed volume would be 0, so playing would just burn a
        # mixer channel on an inaudible sound. SFX volume is set once
        # at play time (not per-frame like music), so an unmute mid-
        # sound wouldn't make this play audible anyway — skipping is
        # functionally identical to "play at 0 then finish silent".
        if base <= 0.0:
            return
        # Per-sound cooldown — drops the call if the same sound played
        # less than ``cooldown_ms`` ago. Prevents UI tick stacking on
        # rapid clicks (the default pygame mixer ships 8 channels;
        # eight clicks inside ~440 ms would preempt the oldest, and
        # the perceptible artefact is a crowded "machine-gun click"
        # smear that adds no information). Configured per-sound at
        # ``load_sound`` time so dramatic chimes (no cooldown
        # registered) still fire unconditionally.
        cooldown = self._sound_cooldown_ms.get(name, 0)
        if cooldown > 0:
            now_ms = pygame.time.get_ticks()
            last_ms = self._sound_last_play_ms.get(name)
            if last_ms is not None and (now_ms - last_ms) < cooldown:
                return
            self._sound_last_play_ms[name] = now_ms
        music_gain = 1.0 + 0.30 * self._smoothed_intensity
        sound.set_volume(max(0.0, min(1.0, base * volume_scale * music_gain)))
        sound.play()

    def stop_sound(self, name: str) -> None:
        sound = self._sounds.get(name)
        if sound is not None:
            sound.stop()

    def load_music(self, path: str | Path) -> None:
        """Load a single music file (legacy entry point).

        Kept for the original ``background.mp3`` flow. Most callers should
        prefer ``discover_playlists()`` + ``play_playlist(category)`` so
        the in-game soundtrack can grow simply by adding files to
        ``sounds/playlists/<category>/``.

        Catches the ``(pygame.error, OSError)`` family — same rationale
        as ``_load_and_play``: ``pygame.mixer.music.load`` raises
        ``FileNotFoundError`` (an ``OSError`` subclass, not a
        ``pygame.error``) on missing paths, so a sync-daemon race
        between the ``is_file`` pre-check and the actual load would
        otherwise crash the audio thread.
        """
        if not self._available:
            return
        resolved = Path(path)
        if not resolved.is_absolute():
            resolved = SOUNDS_DIR / resolved
        if not resolved.is_file():
            logger.warning("Music file not found: %s", resolved)
            return
        try:
            pygame.mixer.music.load(str(resolved))
            # Use the *modulated* volume rather than plain baseline,
            # so a track loaded via the legacy path lands at the same
            # ducked/muted value the per-frame loop would write. Was
            # ``self._effective(self._config.music_volume)`` — fine
            # at startup (smoothed_intensity = 0, no envelope work)
            # but stale during a mid-game load (e.g., a debug hot-
            # swap to background.mp3 while in tense gameplay).
            pygame.mixer.music.set_volume(self._current_music_volume())
            self._music_loaded = True
            self._current_track_path = resolved
        except (pygame.error, OSError) as exc:
            logger.warning("Failed to load music %s: %s", resolved, exc)

    def play_music(self, loops: int = -1) -> None:
        if self._available and self._music_loaded:
            pygame.mixer.music.play(loops)

    def stop_music(self) -> None:
        """Hard-stop the music and clear all playlist state.

        ``pygame.mixer.music.stop()`` fires ``MUSIC_END_EVENT`` —
        exactly the same event the auto-advance loop listens for. So
        a naive ``stop()`` here would route through ``handle_event``
        → ``advance_track`` → load+play the next playlist track,
        which is the *opposite* of "stop". Today the only caller is
        the app-exit teardown (``app.py:497``), where the pygame
        event loop has already halted so the misroute is dormant; but
        any future caller wanting "silence the music" would have hit
        this bug. Clear the endevent across the stop, then restore
        it so natural track-ends keep auto-advancing.

        Also clears ``_current_playlist`` / ``_pending_fade_in`` /
        ``_recent_track_indices``. Without this, a stop mid-crossfade
        left ``_pending_fade_in > 0`` and ``_current_playlist`` set,
        so the next MUSIC_END_EVENT (if the endevent re-registers and
        any future natural end fires) walked the rotation loop and
        loaded the next track — music silently resumed after a stop.
        After this call the manager is in a clean "no music, no
        playlist" state; resuming requires an explicit
        ``play_playlist`` or ``load_music`` + ``play_music``.
        """
        if not self._available:
            return
        pygame.mixer.music.set_endevent()  # no-arg clears the endevent
        pygame.mixer.music.stop()
        pygame.mixer.music.set_endevent(MUSIC_END_EVENT)
        self._music_loaded = False
        self._current_track_path = None
        self._current_playlist = None
        self._pending_fade_in = 0
        self._recent_track_indices.clear()
        # Clear the transition scheduler tracker too — a fresh play_-
        # playlist after stop_music should treat the first track as
        # "no prior kind" so the first auto-advance correctly picks
        # a pad (since the first track was 'regular').
        self._last_played_kind.clear()
        # Anti-repeat memory for pad picks is also playlist-local — a
        # restart resets it so the resumed session doesn't carry
        # exclusions for pads played long ago in the prior run.
        self._recent_pad_paths.clear()
        # Continuity-blend memory: drop the last-regular tracking so
        # a fresh play_playlist after stop_music picks the first track
        # against pure game state, not against whatever was playing
        # before the stop.
        self._last_regular_path.clear()
        # Snap the smoothed-intensity follower back to neutral. Without
        # this, the slow-release IIR (α=0.015, ~3.3 s to 95 %) keeps
        # the smoother elevated long after a tense game ends — and
        # since the next ``play_playlist`` picks its first track
        # immediately, that elevated value gets read as "what register
        # to pick at". Concretely, a 0.7 game-tension reading at game-
        # over would bias the post-stop title-screen first-pick toward
        # the title pool's most-tense track (anticipation / novelty
        # at ~0.50 mood) when a 0.175 proverb would actually fit the
        # calm new context. Per-frame ``set_music_intensity(0)`` can't
        # catch up in the single frame between stop_music and
        # play_playlist; the snap here is the only opportunity to
        # align mood reading with the "clean state" semantics the rest
        # of this method implements.
        self._smoothed_intensity = 0.0

    # ---------------------------------------------------------- playlist

    def discover_playlists(self) -> dict[str, int]:
        """Scan ``sounds/playlists/<category>/`` and register playlists.

        Returns a ``{category: track_count}`` summary. Tracks are
        gathered in alphabetical order (so filenames remain a stable
        external handle), but playback order is **shuffled** at
        runtime by ``_pick_next_index`` — see that method for the
        anti-repeat memory rules. The alphabetical sort here therefore
        only controls which track ``start_index=0`` (or fixed-index
        replay seeds) lands on, not the order the player hears tracks
        during a session.

        The prior docstring claimed "deterministic across runs" which
        was true before the shuffle landed; this version reflects the
        actual behaviour.
        """
        summary: dict[str, int] = {}
        if not self._available:
            return summary
        root = SOUNDS_DIR / PLAYLISTS_SUBDIR
        if not root.is_dir():
            return summary
        for category_dir in sorted(root.iterdir()):
            if not category_dir.is_dir():
                continue
            tracks = sorted(
                p for p in category_dir.iterdir()
                if p.is_file() and p.suffix.lower() in {".mp3", ".ogg", ".wav"}
            )
            # Transition pads — short bridging WAVs that the auto-advance
            # interleaves between regular tracks for inter-track flow.
            # Live in ``<category>/transitions/`` so they don't appear in
            # the regular shuffle pool; the iteration above already
            # skipped this subdir because ``is_file()`` returns False.
            transitions_dir = category_dir / "transitions"
            transitions: list[Path] = []
            if transitions_dir.is_dir():
                transitions = sorted(
                    p for p in transitions_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in {".mp3", ".ogg", ".wav"}
                )
                if transitions:
                    self._transitions[category_dir.name] = transitions
                    logger.info(
                        "Discovered %d transition pad(s) for playlist %r",
                        len(transitions), category_dir.name,
                    )
            if tracks:
                self._playlists[category_dir.name] = tracks
                summary[category_dir.name] = len(tracks)
                logger.info(
                    "Discovered %d music track(s) in playlist %r",
                    len(tracks), category_dir.name,
                )
            elif any(category_dir.iterdir()):
                # Directory exists with files but none match the audio
                # whitelist (.mp3 / .ogg / .wav). Debug-level so the
                # default ops view stays quiet, but available when
                # someone drops a cover JPG, a README, or a .flac (not
                # currently in the whitelist) into a playlist folder
                # and wonders why nothing plays. Without this the
                # directory was silently skipped with no trace.
                logger.debug(
                    "Playlist %r: directory present but no usable "
                    "audio tracks (expected .mp3 / .ogg / .wav).",
                    category_dir.name,
                )
        return summary

    def register_playlist(self, name: str, tracks: list[str | Path]) -> int:
        """Manually register a playlist (or override one). Returns track count."""
        resolved: list[Path] = []
        for t in tracks:
            p = Path(t)
            if not p.is_absolute():
                p = SOUNDS_DIR / p
            if p.is_file():
                resolved.append(p)
            else:
                logger.warning("Playlist %r: file missing %s", name, p)
        if resolved:
            self._playlists[name] = resolved
        return len(resolved)

    def has_playlist(self, name: str) -> bool:
        return name in self._playlists and bool(self._playlists[name])

    @property
    def current_playlist(self) -> str | None:
        return self._current_playlist

    def play_playlist(
        self,
        name: str,
        *,
        crossfade_ms: int = 1500,
        start_index: int = -1,
    ) -> bool:
        """Switch to the named playlist, cross-fading from the current track.

        Cross-fade is implemented as ``fadeout(crossfade_ms)`` on the
        outgoing track + ``play(fade_ms=crossfade_ms)`` on the incoming
        one. With one track playing this gives a smooth handoff at phase
        boundaries (TITLE → PICKER, PLAYING → OUTRO).

        ``start_index`` defaults to ``-1`` which means *pick a random
        starting track*. With multi-track playlists, always starting at
        index 0 means every PLAYING session opens on the same "tension"
        track — predictable and counter to the FIFA-style shuffle the
        playlists are designed for. Pass an explicit index to force a
        specific track (used by tests / deterministic replays).

        Returns False when the playlist is missing or empty — caller can
        fall back to the legacy single-track loop in that case.
        """
        if not self._available or not self.has_playlist(name):
            return False
        if self._current_playlist == name and pygame.mixer.music.get_busy():
            return True
        tracks = self._playlists[name]
        # Capture the outgoing track once — it's needed by both the
        # cross-playlist mood bridge (first-pick weighting) and the
        # mood-aware crossfade scaling below. ``_current_track_path``
        # gets overwritten with the incoming ``track`` further down,
        # so the read has to happen here.
        outgoing = self._current_track_path
        outgoing_is_pad = (
            outgoing is not None
            and outgoing.parent.name == "transitions"
        )
        # Resolve the *effective* outgoing mood used for the bridge
        # and the crossfade scaling. When the outgoing track is a pad,
        # its filename mood doesn't actually represent the playlist's
        # signature — the pad was picked as a midpoint between the
        # previous regular and game intensity, so it sits between
        # those two points but isn't anchored to either. The previous
        # regular IS the playlist signature, so substitute its path
        # for distance calculations whenever a pad is mid-air at
        # switch time. Falls back to None (which skips both bridge
        # and scaling) only when neither a regular nor a pad-with-
        # prior-regular is available — i.e. a pad somehow started
        # before any regular played, which the pad scheduler can't
        # actually produce.
        effective_outgoing: Path | None
        if outgoing_is_pad and self._current_playlist is not None:
            effective_outgoing = self._last_regular_path.get(
                self._current_playlist,
            )
        else:
            effective_outgoing = outgoing
        is_real_switch = (
            effective_outgoing is not None
            and self._current_playlist is not None
            and self._current_playlist != name
            and pygame.mixer.music.get_busy()
        )
        if start_index < 0:
            # Mood-weighted initial pick — first track of the new
            # playlist matches the current music-intensity register
            # instead of being a uniform-random uncurated open. See
            # ``_mood_weighted_pick`` for the rationale.
            #
            # Cross-playlist mood bridge: when something is currently
            # playing AND it's a regular track (not a pad — pads carry
            # the *previous* track's mood, not the playlist's), blend
            # its mood into the first-pick target with the same 0.4 /
            # 0.6 ratio ``_continuity_target`` uses for post-pad
            # emergence. The crossfade puts both tracks audible
            # together — picking the new playlist's track against the
            # outgoing mood (instead of game intensity alone) keeps
            # the audible overlap inside one register. Without the
            # bridge, a calm 0.20 title track could hand off to a
            # tense 0.70 playing track for the full crossfade window
            # of audible mood collision; with it, the picker prefers
            # a playing track closer to ~0.50 — the same listener
            # experiences one progression instead of two layered moods.
            if is_real_switch:
                prev_mood = _track_target_intensity(effective_outgoing)
                blended = 0.4 * prev_mood + 0.6 * self._smoothed_intensity
                idx = self._mood_weighted_pick(
                    list(range(len(tracks))), tracks,
                    target_intensity=blended,
                )
            else:
                idx = self._mood_weighted_pick(
                    list(range(len(tracks))), tracks,
                )
        else:
            idx = max(0, min(start_index, len(tracks) - 1))
        track = tracks[idx]
        # Clear the recent-track memory when switching *playlists*.
        # The deque holds integer indices into the *current* playlist,
        # so carrying them across a category switch made the first
        # pick in the new playlist needlessly skip a couple of
        # candidates (e.g., title's last-two-indices [1, 2] silently
        # excluded the second and third tracks of "playing" on its
        # first shuffle pick). Indices are playlist-local; reset on
        # boundary. Skip the clear when re-entering the same playlist
        # — that's not a real switch, just a resume that should keep
        # its anti-repeat memory.
        if self._current_playlist != name:
            self._recent_track_indices.clear()
        self._current_playlist = name
        self._current_track_idx = idx
        self._current_track_path = track
        # Fade out the current track if one is playing.
        if pygame.mixer.music.get_busy() and crossfade_ms > 0:
            # Mood-distance crossfade scaling. The uniform 1500 ms fade
            # was a one-size-fits-all compromise — too short for similar
            # moods (the gradual musical merge gets cut off), too long
            # for distant moods (1500 ms of audible mood collision when
            # a calm 0.20 outgoing overlaps a tense 0.70 incoming).
            # Scale around the caller's intent:
            #   * Distance 0 (same mood)  → 1.4×, glide smoothly merges
            #   * Distance 0.5 (mid jump) → 1.0×, the caller's baseline
            #   * Distance 1.0 (max jump) → 0.6×, fast switch minimises
            #     the collision window
            # Only applied to real playlist switches (not stop-then-play
            # resumes or pad-to-anything handoffs — the outgoing path
            # has to be a regular track for the distance to be musically
            # meaningful). The caller's ``crossfade_ms`` stays as the
            # *baseline*; scaling moves it within ±40 % of that.
            scaled_fade = crossfade_ms
            incoming_fade = crossfade_ms
            if is_real_switch:
                outgoing_mood = _track_target_intensity(effective_outgoing)
                incoming_mood = _track_target_intensity(track)
                dist = min(1.0, abs(incoming_mood - outgoing_mood))
                scale = 1.4 - 0.8 * dist
                scaled_fade = max(200, int(crossfade_ms * scale))
                # Asymmetric profile when moods are distant: outgoing
                # exits at the scaled tempo (quick at high distance),
                # incoming enters with an extra ramp so the listener
                # is *eased into* the new mood instead of being dropped
                # into it the moment the outgoing track stops.
                #
                # ``pygame.mixer.music`` plays one stream at a time, so
                # the outgoing fadeout and the incoming fade-in are
                # sequential, not overlapping: outgoing fades to silence
                # over ``scaled_fade`` ms, MUSIC_END_EVENT fires, then
                # the incoming starts with its own ramp. Lengthening the
                # incoming ramp turns the boundary from "outgoing stops,
                # new mood at full" into "outgoing stops, new mood
                # gently arrives" — the higher the mood gap, the gentler
                # the arrival.
                #
                # Extension: 1.0× at zero distance (already a long
                # merge), 1.5× at max distance (slow entry over a short
                # exit). Floored at 200 ms so degenerate cases never
                # produce a click on the incoming side.
                extension = 1.0 + 0.5 * dist
                incoming_fade = max(200, int(scaled_fade * extension))
            else:
                incoming_fade = scaled_fade
            pygame.mixer.music.fadeout(scaled_fade)
            # Stash the desired fade-in; the actual load happens on the
            # MUSIC_END_EVENT so the outgoing track gets its full fadeout.
            # The MUSIC_END_EVENT handler (``advance_track``) already
            # carries bad-file resilience — if the handoff target dies
            # it walks the playlist for an alternative before giving up.
            self._pending_fade_in = incoming_fade
            return True
        # Immediate-play branch (nothing currently playing, or
        # crossfade_ms == 0). Mirror ``advance_track``'s bad-file
        # resilience: if the chosen initial track fails to load, walk
        # the rest of the playlist via the same shuffle pool before
        # giving up. Previously the bool return from
        # ``_load_and_play`` was discarded, so a broken initial track
        # left the manager committed to the playlist but silent —
        # observable on a fresh run if the title-screen MP3 happened
        # to be unreadable.
        if self._load_and_play(track, fade_in_ms=crossfade_ms):
            return True
        logger.warning(
            "Initial playlist track %s unloadable; trying alternatives.",
            track.name,
        )
        for _ in range(len(tracks) - 1):
            prev_idx = self._current_track_idx
            self._current_track_idx = self._pick_next_index(
                current=prev_idx, total=len(tracks),
            )
            self._recent_track_indices.append(prev_idx)
            next_track = tracks[self._current_track_idx]
            self._current_track_path = next_track
            if self._load_and_play(next_track, fade_in_ms=crossfade_ms):
                return True
            logger.warning(
                "Skipping unloadable track %s; trying next.",
                next_track.name,
            )
        logger.error(
            "Playlist %r couldn't open any track. Music silent.", name,
        )
        return False

    def advance_track(self) -> None:
        """Move to the next track in the current playlist (called on
        MUSIC_END_EVENT).

        Bad-file resilience: if a track fails to load (corrupted file,
        unsupported codec, vanished between boot and playback) the
        method now skips it and tries the next shuffle pick, capped at
        ``len(tracks)`` attempts so a fully-broken playlist gives up
        gracefully instead of looping. Previously a single bad file
        left ``_music_loaded`` stale and the player in silence until
        the next phase change.
        """
        if not self._available:
            return
        # Default fade-in for natural within-playlist advance; see
        # ``WITHIN_PLAYLIST_FADE_MS`` for the 150 ms rationale.
        fade_in_ms = WITHIN_PLAYLIST_FADE_MS
        # A cross-fade switch was in flight — load the new playlist's track.
        if self._pending_fade_in > 0 and self._current_track_path is not None:
            # Preserve the original cross-fade duration through to the
            # shuffle-loop fallback too. Was: ``fade`` captured here
            # then ``WITHIN_PLAYLIST_FADE_MS`` hard-coded in the loop
            # below, so a failed cross-fade target left the outgoing
            # track to fade cleanly over 1500 ms then the fallback
            # came in over 150 ms — audibly abrupt vs the intended
            # crossfade timing. Bind the cross-fade duration to the
            # function-level ``fade_in_ms`` so the fallback inherits it.
            fade_in_ms = self._pending_fade_in
            self._pending_fade_in = 0
            if self._load_and_play(
                self._current_track_path, fade_in_ms=fade_in_ms,
            ):
                return
            # Handoff target died (corrupt / missing file). Fall through
            # to the shuffle loop below so the player isn't stranded
            # mid-crossfade — the loop will pick a different track from
            # the same playlist. (The previous form here was a literal
            # no-op self-assignment ``self._current_playlist =
            # self._current_playlist``; the intent was "preserve the
            # playlist and fall through", but the statement does
            # nothing — clarified to fall through implicitly.)
        # Otherwise rotate within the current playlist.
        if self._current_playlist is None:
            return
        tracks = self._playlists.get(self._current_playlist) or []
        if not tracks:
            return
        # Transition pad scheduler — if the previous load was a regular
        # track and this playlist has transition pads registered, play
        # one pad before the next regular track. Reads the
        # ``_last_played_kind`` tracker that ``_load_and_play`` writes
        # after each successful load. Result: regular → pad → regular →
        # pad → … instead of cutting straight between two unrelated
        # remixed pieces. Wider 800 ms fade-in so the pad's head ramps
        # in over the previous track's tail rather than slap-cutting.
        # If no pads are registered for this playlist (legacy install,
        # other categories), the conditional is skipped and the original
        # shuffle behaviour kicks in.
        transitions = self._transitions.get(self._current_playlist) or []
        last_kind = self._last_played_kind.get(self._current_playlist)
        # Post-pad regular: soften the fade-in. After a pad the previous
        # audio has tapered to silence (the pad WAV bakes in a 6 s
        # fade-out), so the next regular comes in over silence — a 150 ms
        # ramp reads as "sudden return". Extend to 500 ms so the listener
        # gets a gentle re-introduction after the silence period. The
        # regular's intrinsic WAV envelope (0.5 s fade-in) combined with
        # this 500 ms pygame ramp gives ~1 s of effective musical entry,
        # matching the 800 ms used in the opposite direction (regular →
        # pad). Only applied when the previous load was a pad; pure
        # regular → regular keeps the 150 ms click-absorber baseline so
        # gapless playback stays gapless when no pad bridged the cut.
        if last_kind == "transition":
            fade_in_ms = 500
        if transitions and last_kind == "regular":
            pad = self._pick_pad(self._current_playlist, transitions)
            if pad is not None and self._load_and_play(pad, fade_in_ms=800):
                # Remember which pads played recently so the next pad
                # selection excludes them — prevents the mood-weighted
                # picker from repeatedly landing on whichever pad best
                # matches the surrounding tracks' average mood.
                recent = self._recent_pad_paths.setdefault(
                    self._current_playlist, deque(maxlen=2),
                )
                recent.append(pad)
                return
            if pad is not None:
                logger.warning(
                    "Transition pad %s failed to load; falling through "
                    "to regular shuffle.", pad.name,
                )
        # Try up to ``len(tracks)`` candidates — the recent-N memory
        # plus the "exclude current" rule means each iteration advances
        # to a different index, so this caps total attempts at the
        # playlist size. Bad files get skipped + logged.
        for _ in range(len(tracks)):
            prev_idx = self._current_track_idx
            self._current_track_idx = self._pick_next_index(
                current=prev_idx, total=len(tracks),
            )
            # Push the just-departed track into recent memory so the
            # next call to ``_pick_next_index`` excludes it. Pushing
            # *prev* not *next* — the deque accumulates the trail of
            # tracks we've moved through, and the next pick reads
            # from it.
            self._recent_track_indices.append(prev_idx)
            next_track = tracks[self._current_track_idx]
            # Within-playlist mood-distance fade-in scaling. Mirrors the
            # cross-playlist asymmetric profile: the bigger the mood gap
            # between the outgoing track and the incoming pick, the
            # longer the fade-in. The regular → regular bias already
            # keeps actual distances small (the picker prefers nearby
            # moods), so the scaling kicks in only on the occasional
            # exploratory jump — e.g. a title-phase proverb (0.175) →
            # novelty (0.50) pick that the picker's k=2.0 weighting
            # admits with non-zero probability.
            #
            # Skip the scaling when the override branches above already
            # set fade_in_ms (cross-playlist crossfade with its own
            # mood-aware duration, or post-pad 500 ms re-entry over
            # silence). Only apply to the base WITHIN_PLAYLIST_FADE_MS
            # case so we don't double up.
            outgoing_track = self._current_track_path
            if (
                fade_in_ms == WITHIN_PLAYLIST_FADE_MS
                and outgoing_track is not None
                and outgoing_track.parent.name != "transitions"
            ):
                out_mood = _track_target_intensity(outgoing_track)
                in_mood = _track_target_intensity(next_track)
                dist = min(1.0, abs(in_mood - out_mood))
                if dist > 0.15:
                    # Stretch the 150 ms baseline by up to ~3× at max
                    # distance. Small jumps (< 0.15) keep the click-
                    # absorber baseline because no perceptible mood
                    # shift needs cushioning.
                    fade_in_ms = max(
                        WITHIN_PLAYLIST_FADE_MS,
                        int(WITHIN_PLAYLIST_FADE_MS + 600 * dist),
                    )
            self._current_track_path = next_track
            if self._load_and_play(next_track, fade_in_ms=fade_in_ms):
                return
            logger.warning(
                "Skipping unloadable track %s; trying next shuffle pick.",
                next_track.name,
            )
        logger.error(
            "Playlist %r exhausted — no loadable track. Music silent.",
            self._current_playlist,
        )

    def _pick_next_index(self, current: int, total: int) -> int:
        """Shuffled-advance with mood-weighted selection.

        Two-stage:

        1. **Anti-repeat candidate pool** — ``range(total)`` minus
           ``{current}`` minus ``self._recent_track_indices``. On
           ``total == 1`` returns 0; on ``total == 2`` returns the
           forced other slot. If the recent-memory exclusion would
           leave the pool empty (small playlist / large memory),
           falls back to "anything except current". Guarantees a
           candidate exists for any ``total ≥ 2``.

        2. **Mood-aware weighting** — within the candidate pool, each
           track is weighted by ``exp(-2.0 × dist)`` where ``dist`` is
           the absolute gap between the track's mood-target intensity
           (see ``_track_target_intensity``) and the current smoothed
           music intensity. Closer match → higher weight. Tracks whose
           filenames carry no mood keyword fall back to neutral 0.5,
           so user-added tracks with arbitrary names participate at
           a sensible default. Nothing is excluded outright — every
           candidate keeps non-zero weight, so the FIFA-style variety
           the design intends still holds (calm titles occasionally
           play the warm chanson; tense gameplay occasionally drops
           into the lull bed).

        At ``intensity = 0.2`` (calm title), a calm track with target
        0.20 weights 1.00; a peak tension track at 0.90 weights
        ``exp(-1.4) ≈ 0.25`` — still a 1-in-5 chance of surfacing,
        not a hard exclusion. At ``intensity = 0.9`` (peak playing),
        the relationship inverts: tense tracks weight 1.00, calm
        tracks weight ~0.25.
        """
        if total <= 1:
            return 0
        if total == 2:
            return 1 - current
        excluded = set(self._recent_track_indices)
        excluded.add(current)
        candidates = [i for i in range(total) if i not in excluded]
        if not candidates:
            # Pool starved — recent-N covers ≥ all-but-self. Fall
            # back to "anything except current".
            candidates = [i for i in range(total) if i != current]
        tracks = (
            self._playlists.get(self._current_playlist)
            if self._current_playlist
            else None
        )
        if not tracks:
            return self._shuffle_rng.choice(candidates)
        return self._mood_weighted_pick(candidates, tracks)

    def _continuity_target(self) -> float:
        """Mood target for the next regular pick, with continuity bias.

        Default: current ``_smoothed_intensity`` (game tension) — same
        signal the regular picker has always used. Adds a
        previous-regular-mood blend in two cases:

        **Post-pad emergence** (last load was a transition pad,
        playing-phase only): the pad blurred the listener's mood
        reference for ~15 s. Anchoring the next pick toward the
        track that played *before* the pad keeps the regular → pad
        → regular sequence reading as one musical arc, not three
        unrelated moments. Strong blend (0.4 prev / 0.6 intensity)
        because the pad has already softened the prior mood — the
        listener won't perceive the bias as "the music ignoring my
        game state".

        **Regular → regular** (no pad between, e.g. title / picker /
        outro playlists which ship no transition pads): apply a
        milder version of the same blend (0.2 prev / 0.8 intensity).
        Without a pad to reset the listener's reference, every track
        change would otherwise jump fully to whatever game intensity
        has drifted to — perceptible mid-phase even though intensity
        itself is smoothed. The 0.2 bias is small enough that the
        music still tracks tension responsively but large enough to
        round off the edges of consecutive picks. On the title screen
        (intensity locked at 0.0 ± nothing) the blend has no effect
        regardless of weight — only the dynamic phases benefit.

        Game state always dominates so the music keeps tracking
        tension — the previous-regular weight is a continuity *bias*,
        not a lock.
        """
        base = self._smoothed_intensity
        pl = self._current_playlist
        if pl is None:
            return base
        kind = self._last_played_kind.get(pl)
        last_regular = self._last_regular_path.get(pl)
        if last_regular is None:
            return base
        prev_mood = _track_target_intensity(last_regular)
        if kind == "transition":
            # Post-pad emergence: strong anchor toward prior mood.
            return 0.4 * prev_mood + 0.6 * base
        if kind == "regular":
            # Direct regular → regular: milder bias so the music
            # still tracks game tension but consecutive tracks read
            # as a sequence instead of independent picks.
            return 0.2 * prev_mood + 0.8 * base
        return base

    def _mood_weighted_pick(
        self, candidates: list[int], tracks: list[Path],
        target_intensity: float | None = None,
    ) -> int:
        """Pick one index from ``candidates``, weighted by mood-target
        proximity to ``_continuity_target()`` (which falls back to
        ``self._smoothed_intensity`` outside the post-pad emergence case).

        Extracted from ``_pick_next_index`` so the initial-track pick in
        ``play_playlist`` can use the same weighting. Previously the
        first track of every playlist switch used a uniform
        ``randrange`` — so a TITLE→PLAYING handoff opened on a random
        track regardless of whether the simulation was calm (turn 1)
        or already tense (mid-game restart). For ~30 s after every
        playlist switch, the bed was mood-blind; only the second pick
        (after the first track ended) re-introduced weighting.

        ``target_intensity`` is an optional override used by
        ``play_playlist`` to seed the first pick with a blended
        outgoing-track-mood × current-game-intensity target. Skipping
        it falls back to ``_continuity_target()`` — the within-playlist
        behaviour. Provided externally instead of read from state so
        the blend logic stays local to the caller that knows about
        the playlist boundary (this method has no view of "what was
        playing in the previous playlist").
        """
        if len(candidates) <= 1:
            return candidates[0] if candidates else 0
        current_int = (
            target_intensity if target_intensity is not None
            else self._continuity_target()
        )
        weights: list[float] = []
        for idx in candidates:
            track_target = _track_target_intensity(tracks[idx])
            dist = abs(track_target - current_int)
            # Exponential falloff: k=2.0 gives ~0.25 weight at dist=0.7
            # (e.g. calm track on tense bed) so mismatches still have a
            # chance but matches dominate.
            weights.append(math.exp(-2.0 * dist))
        total_w = sum(weights)
        if total_w <= 0.0:
            # Numerical edge case; uniform fallback.
            return self._shuffle_rng.choice(candidates)
        roll = self._shuffle_rng.uniform(0.0, total_w)
        cumulative = 0.0
        for idx, w in zip(candidates, weights):
            cumulative += w
            if roll <= cumulative:
                return idx
        return candidates[-1]

    def _pick_pad(
        self, playlist: str, transitions: list[Path],
    ) -> Path | None:
        """Pick a transition pad weighted by mood-distance to the previous
        regular track.

        Previously this was a uniform random pick — but transition pads
        carry their source track's mood keywords in the filename (e.g.,
        ``pad_03_climax_tension.wav`` parses as
        ``avg(climax=0.90, tension=0.70) = 0.80``), so a calm pad
        landing between two intense regular tracks sounded mismatched.
        Weighting by closeness to the just-played track's mood ties the
        pad's character acoustically to whatever lingers in the
        listener's ear.

        Anti-repeat memory: the last 2 pads played for this playlist
        are excluded from the candidate pool first. Without this, the
        mood-weighted picker would repeatedly land on whichever pad
        best matches the surrounding tracks' average mood, producing a
        noticeable "same wash again" feel within a single session.
        Fall back to including recent pads if exclusion would empty
        the pool (small pad library / heavy churn).
        """
        if not transitions:
            return None
        if len(transitions) == 1:
            return transitions[0]
        recent = self._recent_pad_paths.get(playlist) or ()
        pool = [p for p in transitions if p not in recent]
        if not pool:
            pool = list(transitions)
        # Target = the midpoint between the just-played regular's mood
        # and the *expected* next regular's mood — so the pad sits
        # acoustically *on* the bridge instead of behind it.
        #
        # When this pad ends, the next-regular pick will use
        # ``_continuity_target()`` which (in the post-pad case) returns
        # ``0.4 * prev_mood + 0.6 * intensity``. Pure prev-mood pad
        # targeting (the prior behaviour) meant the pad lingered on the
        # old register while the post-pad regular had already moved
        # toward intensity — listeners heard prev_mood → prev_mood →
        # intensity instead of a smooth gradient. Targeting the
        # midpoint between prev_mood and that next-regular target
        # produces prev_mood → bridge_mood → intensity-leaning_mood,
        # one continuous slope across three picks.
        #
        # Algebra: midpoint(prev, 0.4·prev + 0.6·int)
        #        = (prev + 0.4·prev + 0.6·int) / 2
        #        = 0.7·prev_mood + 0.3·intensity.
        # Falls back to ``_smoothed_intensity`` alone when we don't
        # know what just played — covers the first auto-advance after
        # a stop_music + play_playlist resume.
        prev_path = self._current_track_path
        if prev_path is not None and prev_path.parent.name != "transitions":
            prev_mood = _track_target_intensity(prev_path)
            target = 0.7 * prev_mood + 0.3 * self._smoothed_intensity
        else:
            target = self._smoothed_intensity
        # Sharper exponential than ``_mood_weighted_pick`` (k=4.0 vs
        # k=2.0) — regular tracks are picked against game tension, a
        # moving signal where mismatches still have value (variety on a
        # slowly-changing bed). Pad picks target a *fixed* point: the
        # just-played track's mood. A pad whose mood is 0.3 away from
        # the previous track sounds genuinely mismatched — exp(-1.2)
        # ≈ 0.30 weight is still too forgiving. k=4.0 brings that to
        # exp(-2.4) ≈ 0.09, forcing the picker onto the close-match
        # cluster without making it deterministic.
        weights = [
            math.exp(-4.0 * abs(_track_target_intensity(p) - target))
            for p in pool
        ]
        total = sum(weights)
        if total <= 0.0:
            return self._shuffle_rng.choice(pool)
        roll = self._shuffle_rng.uniform(0.0, total)
        cumulative = 0.0
        for p, w in zip(pool, weights):
            cumulative += w
            if roll <= cumulative:
                return p
        return pool[-1]

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Consume music end events so the playlist auto-advances. Returns
        True when the event was an audio event (caller should not forward
        it to the input handler)."""
        if event.type == MUSIC_END_EVENT:
            self.advance_track()
            return True
        return False

    def _load_and_play(self, path: Path, fade_in_ms: int = 0) -> bool:
        """Load and play ``path``. Returns True on success, False on
        any load error (file missing / corrupt / unsupported format).

        Was a void function that only caught ``pygame.error``. But
        ``pygame.mixer.music.load`` raises ``FileNotFoundError`` for
        missing paths (not a pygame.error subclass), so a deleted
        playlist file used to crash the audio thread. Catches the
        full ``(pygame.error, OSError)`` family now so any I/O-side
        failure converts cleanly into a False return, and the caller
        can fall back to the next shuffle pick instead of leaving the
        player in silence.
        """
        try:
            pygame.mixer.music.load(str(path))
            # Use the *modulated* volume the ducking loop would write,
            # not plain baseline. Without this, every track switch
            # briefly snapped to baseline (audible blip on tense
            # auto-advance) and mute-fade auto-advances bypassed the
            # envelope entirely. See _current_music_volume() docstring.
            pygame.mixer.music.set_volume(self._current_music_volume())
            # Detect transition pads by path (they live under
            # ``<playlist>/transitions/``). Pads always play once
            # (loops=0) regardless of the playlist's loop-extension
            # threshold — they're bridges, not bedded material.
            is_transition = path.parent.name == "transitions"
            if is_transition:
                loops = 0
            else:
                # Extend short tracks within the active playlist by
                # looping the file in-place before the natural
                # MUSIC_END_EVENT fires. See ``_PLAYLIST_MIN_PLAYTIME_S``
                # / ``_loops_for`` for the per-playlist threshold and
                # rationale — the playing-stage 22 s tracks used to
                # restart every 30 s, this brings them up to ~90 s
                # before the shuffle rotates to a new pick.
                loops = _loops_for(path, self._current_playlist)
                # Single-track playlists loop the underlying file in
                # place via ``loops=-1`` instead of relying on the
                # MUSIC_END_EVENT roundtrip — when ``advance_track``
                # "shuffles" within a 1-track playlist it can only land
                # on the same track again, so reloading + re-firing the
                # event each cycle is pure churn. Applies to the legacy
                # ``"default"`` fallback (``background.mp3``) and any
                # user-dropped 1-track playlist. Cross-playlist
                # switches still work because ``play_playlist``'s
                # ``fadeout()`` fires its own MUSIC_END_EVENT
                # independent of the loop state, and ``stop_music``
                # clears the endevent before stopping.
                if self._current_playlist is not None:
                    tracks = self._playlists.get(self._current_playlist) or ()
                    if len(tracks) == 1:
                        loops = -1
            pygame.mixer.music.play(loops, fade_ms=max(0, fade_in_ms))
            self._music_loaded = True
            self._current_track_path = path
            # Track-kind tracker for the transition scheduler in
            # ``advance_track``. Skip when the playlist is unknown
            # (legacy code paths that hit ``_load_and_play`` directly
            # without going through ``play_playlist`` first).
            if self._current_playlist is not None:
                self._last_played_kind[self._current_playlist] = (
                    "transition" if is_transition else "regular"
                )
                # Remember the most-recent regular path so the
                # continuity-aware picker can blend its mood into the
                # next regular pick. Only updated on regular loads —
                # pad loads don't overwrite this field, because the
                # whole point is to remember what was playing *before*
                # the pad bridge.
                if not is_transition:
                    self._last_regular_path[self._current_playlist] = path
            return True
        except (pygame.error, OSError) as exc:
            logger.warning("Failed to load music %s: %s", path, exc)
            return False

    def set_music_intensity(self, intensity: float) -> None:
        """Dynamically duck / boost the background music with simulation tension.

        ``intensity`` ∈ [0, 1] maps from "calm" (planet stable, low
        mortality) to "tense" (cascade in progress). Volume swings
        from 70 % of the configured baseline at calm to 110 % at full
        tension. ``pygame.mixer.music`` doesn't expose runtime pitch
        control on a playing stream, so this is volume-only — the
        prior docstring mentioned "+pitch" which was aspirational.

        The intensity input is **smoothed** before mapping to volume,
        with **asymmetric attack/release time constants** so the music
        responds the way perception expects: notice escalation
        immediately, let go of fear gradually. Was a symmetric
        single-pole IIR at α=0.02 (~2.5 s both directions) which
        treated a cascade-in-progress and a player-stabilisation
        moment with identical responsiveness — felt sluggish on
        the way up (a country tipping into collapse didn't lift the
        music fast enough to register as "something happened") and
        jittery on the way down (the music snapped back to calm as
        soon as one critical country recovered, undoing the dread).

        Standard adaptive-music compressor pattern — fast attack,
        slow release:
          - Attack (rising intensity): α=0.06 → ~50 frames (~0.8 s)
            to 95 % of the step. The cascade or critical event lifts
            the music promptly enough that the player perceives
            cause and effect.
          - Release (falling intensity): α=0.015 → ~200 frames
            (~3.3 s) to 95 %. The tension decays gracefully instead
            of snapping back, so brief stabilisation moments
            (one country recovering) don't reset the dramatic arc.
          - Hard duck (target == 0): α=0.04 → ~75 frames (~1.2 s)
            to 95 %. Used when something explicitly wants silence —
            a cinematic taking over the audio stage, or the player
            bouncing back to the title screen. The slow release is
            wrong here: it would leave the music competing with
            the cinematic's visual focus for the first second or two.

        All α values still produce smooth volume sweeps (no audible
        clicks); the asymmetry just shifts *where* the smoothing
        budget is spent. Still cheap (one comparison + one
        multiply-add per frame).
        """
        if not self._available or not self._music_loaded:
            # NB: we no longer early-return on ``_runtime_muted`` — the
            # mute envelope below has to keep gliding so the M-key
            # toggle produces a smooth fade instead of an instant snap.
            return
        intensity = max(0.0, min(1.0, intensity))
        # Three-state IIR: fast attack on rising intensity, slow release
        # on falling, medium decay when the caller explicitly wants
        # silence. Switching α per-frame can't chatter at the boundaries
        # because intensity itself is smoothed game-side (population in
        # critical state changes by fractions per turn), so the smoother
        # never oscillates around its own equilibrium.
        if intensity > self._smoothed_intensity:
            alpha = 0.06  # fast attack — escalation feels causal
        elif intensity <= 0.0:
            # Explicit silence target — cinematic dampening or the
            # title screen handing the audio stage to another player.
            # 0.04 lands at 95 % in ~1.2 s, faster than the 3.3 s
            # release that would otherwise leave the music loud
            # under the first second of a cinematic.
            alpha = 0.04
        else:
            alpha = 0.015  # slow release — fear lingers
        self._smoothed_intensity = (
            (1.0 - alpha) * self._smoothed_intensity + alpha * intensity
        )
        # Mute envelope: glides toward 0 when ``_runtime_muted`` is
        # True, toward 1 when False. β=0.18 → ~16 frames (~270 ms
        # @60fps) to 95 % of the step — fast enough that the player
        # perceives the toggle as immediate, slow enough that the
        # mixer doesn't click on the volume edge. Snap when the
        # remaining gap is sub-perceptible so the value parks
        # exactly at 0/1 instead of drifting forever.
        mute_target = 0.0 if self._runtime_muted else 1.0
        self._mute_envelope = (
            (1.0 - 0.18) * self._mute_envelope + 0.18 * mute_target
        )
        if abs(self._mute_envelope - mute_target) < 1e-3:
            self._mute_envelope = mute_target
        # Volume swings from 70 % to 110 % of the configured baseline,
        # driven by the *smoothed* intensity, then scaled by the mute
        # envelope. Shared with ``_load_and_play`` so a freshly-loaded
        # track inherits the same modulated volume rather than briefly
        # snapping to baseline before the next ducking tick catches up.
        # ``pygame.mixer.music.set_volume`` is cheap to call every frame.
        pygame.mixer.music.set_volume(self._current_music_volume())

    def _current_music_volume(self) -> float:
        """Compute the volume the ducking loop would write right now.

        Centralises the (base × intensity-modulation × mute-envelope)
        formula so two call sites stay in lockstep:

        * ``set_music_intensity`` — writes this every frame.
        * ``_load_and_play`` — writes this on every track load so
          incoming tracks land at the *current* modulated volume
          instead of plain baseline. Previously a track-end auto-
          advance during a tense moment briefly snapped down to
          baseline before the next ducking tick lifted it back; and
          during a mute fade-out, an auto-advance bypassed the
          envelope entirely because ``_effective(music_volume)``
          returns 0 the instant ``_runtime_muted`` flips.

        ``_config.muted`` (persisted preference) still gates hard:
        if you boot muted, _mute_envelope starts at 0 and nothing
        writes a non-zero volume until you toggle it on.
        """
        base_unmuted = (
            0.0 if self._config.muted else max(
                0.0, min(1.0, self._config.music_volume * self._config.master_volume),
            )
        )
        return max(
            0.0,
            min(
                1.0,
                base_unmuted
                * (0.7 + 0.4 * self._smoothed_intensity)
                * self._mute_envelope,
            ),
        )

    @property
    def muted(self) -> bool:
        return self._runtime_muted

    def set_muted(self, muted: bool) -> None:
        """Runtime mute. Idempotent; cheap when state hasn't changed.

        Music takes the **mute envelope** path (a per-frame glide
        toward 0/1 inside ``set_music_intensity``), so toggling M
        mid-track no longer clicks — what used to be a baseline → 0
        snap is now a ~270 ms ramp. SFX still snap because they're
        short transient sounds; a fade-in on a critical-event ping
        would just sound mistimed.
        """
        if self._runtime_muted == muted:
            return
        self._runtime_muted = muted
        if not self._available:
            return
        # Music: do nothing here. The ducking loop in
        # set_music_intensity reads _runtime_muted next frame and
        # glides _mute_envelope toward the new target. Writing a
        # final volume here would defeat the envelope.
        for sound in self._sounds.values():
            sound.set_volume(self._effective(self._config.effects_volume))

    def _effective(self, volume: float) -> float:
        if self._config.muted or self._runtime_muted:
            return 0.0
        return max(0.0, min(1.0, volume * self._config.master_volume))
