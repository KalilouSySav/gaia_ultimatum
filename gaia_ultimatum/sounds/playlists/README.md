# Music playlists

Drop `.mp3` / `.ogg` / `.wav` files into any of these folders to expand the
in-game soundtrack. The game auto-discovers tracks at boot and **shuffles**
through them within each category — the previous track never plays again
immediately, but otherwise the order is randomised, FIFA / EA-style. Each
new PLAYING session opens on a different track too (the `start_index=-1`
default in `AudioManager.play_playlist`).

## What ships (v3 library)

All bundled tracks are **WAV 44.1 kHz / 16-bit / stereo**, mastered phase-
safe, mono-compatible, with per-phase loudness and presence (-1 dBTP).
v3 replaces the legacy proc-cut library (slices of `background.mp3` re-
coloured by mood) with 26 genuinely different full-length tracks — each
folder is now a varied EA-style shuffle instead of one re-coloured source.

| Folder      | When it plays                            | Bundled tracks |
|-------------|------------------------------------------|-----------------|
| `title/`    | Main menu                                | 7 — 4 calm/airy beds + Tibetan proverb (spoken ambient) + vocal chanson + novelty_absurd |
| `picker/`   | Side · catastrophe · difficulty · origin | 7 — 5 anticipation beds + upbeat swing + warmed cinematic variant (-2 st) |
| `playing/`  | During the simulation                    | 8 — 6 tension/energy beds + cinematic drive (builds/drops, LRA ~31 dB) + dark dynamic pulse |
| `outro/`    | Game-over recap                          | 4 — 3 reflective beds + spoken reflection proverb |

**26 tracks total**. With shuffle on, the listener perceives each phase as
a fresh playlist rather than a single looping bed.

### Track personality notes

* `title/04_proverb_tibetan` — very static + in-phase = ideal calm bed;
  spoken proverb suits an awareness game.
* `title/05_chanson_vocal` — vocal character piece; vocals on a menu
  are on-brand for FIFA/EA playlists.
* `title/06_novelty_absurd` — Spike-Jones-style chaotic novelty with
  LRA ~30 dB swells. Installs in the title pool as a personality
  track; it WILL clash with the steady beds when it lands, but that
  variance is the point in a menu context (not a gameplay one).
* `picker/05_swing_upbeat` — upbeat, bright; light menu energy.
* `picker/06_cinematic_calm` — warmed variant of the cinematic source
  (pitched -2 st), so the picker/playing copies are no longer
  identical to each other.
* `playing/06_cinematic_drive` — dynamic builds and drops, the
  energetic "drive" cut for tense gameplay stretches.
* `playing/07_dark_pulse` — dark, dynamic pulse for contrast against
  the warmer tension beds.
* `outro/03_proverb_reflection` — spoken reflection recap, matches
  the tone of a game-over screen looking back at the run.

## Order, fades, dynamic ducking

* **Shuffle**: `_pick_next_index` avoids immediate repeats (the
  anti-stutter rule every modern music app uses). On a 1- or 2-track
  playlist it falls back to sequential rotation; from 3 tracks up it
  picks uniformly from "anything except the current one".
* **Cross-fades**: phase changes (TITLE → PICKER, PLAYING → OUTRO, etc.)
  fade out the outgoing track over ~1.5 s while the incoming one fades
  up. Within a playlist, auto-advance on `MUSIC_END_EVENT` is gapless.
* **Dynamic ducking**: `set_music_intensity(0..1)` swings volume from
  70 % of the configured baseline at calm to 110 % at peak tension,
  driven each frame by `_music_intensity(game)` in `app.py`. The input
  is **smoothed** with a single-pole IIR (α = 0.02) so big tension
  jumps fade in over ~2.5 s instead of clicking on the music bed.

## Adding your own tracks

User-supplied files named with a sortable prefix (e.g. `07_…`, `08_…`)
will be picked up at next boot. They participate in the shuffle pool
equally — no priority over the bundled cuts and no risk of overwriting
them.

Supported formats: `.mp3`, `.ogg`, `.wav`. The mixer is initialised at
its default rate (44.1 kHz) so files at other rates will resample on
load; for best results match the v3 spec: 44.1 kHz / 16-bit / stereo.

## Rights

The v3 tracks read like AI-generated homages (named after their
inspirations — Tibetan proverb, swing, chanson, cinematic, etc.). If any
source music is third-party, confirm rights before shipping a public build.

## Source library

The v3 library lives in `documentation/game_music_v3/game_music/` at the
repo root, organised as:

* `title/`, `picker/`, `playing/`, `outro/` — the four shuffled folders
  (installed here).
* `extras/novelty_absurd.wav` — the novelty track, originally kept out
  of auto-shuffle per the v3 README ("LRA ~30 dB swells/ducks erratically
  and clashes with a steady bed"). Installed into `title/` only as a
  deliberate menu-personality choice; do NOT promote into `picker/` or
  `playing/` without re-mastering.

`tools/cut_playlist_from_background.py` (the legacy proc-cut generator)
is superseded by v3 and no longer the source of truth for the bundled
library. It's preserved in the repo only as a reference for the old
mood-DSP chain; running it would re-introduce the proc cuts and they
would shuffle alongside v3 unless explicitly removed.
