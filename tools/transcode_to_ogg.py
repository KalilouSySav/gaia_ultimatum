"""Transcode all bundled WAV playlists/sounds to OGG Vorbis for the Android build.

Why: ``gaia_ultimatum/sounds/`` is **~394 MB** of uncompressed 16-bit PCM WAV
across ~30 tracks. The Play Store base APK cap is **150 MB** (200 MB with
expansion files, which require extra Play Console plumbing); a single
desktop-quality playlist category alone blows past that. OGG Vorbis at
128 kbps cuts each track ~10× with no perceptible quality loss for the
ambient/cinematic register the bundle uses, dropping the audio bundle to
~40 MB — fits comfortably in a base APK with room for the rest of the
package (data, code, fonts, icon).

pygame.mixer reads OGG natively (no code change needed in audio.py) —
``pygame.mixer.music.load`` and ``pygame.mixer.Sound`` both accept .ogg
paths. The discovery glob in ``audio.discover_playlists`` walks the
playlist dirs and matches ``*.wav`` today; we'll widen it to ``*.wav``
+ ``*.ogg`` in a separate step (deferred — desktop builds keep WAV).

Build pipeline:

  # Desktop dev: keep the WAV files in place, no action needed.
  # Android APK build:
  python tools/transcode_to_ogg.py             # produces .ogg sidecars
  buildozer android debug                       # picks .ogg via source.include_exts

This script does NOT delete the source WAVs — it produces OGG sidecars
next to each WAV. ``buildozer.spec`` excludes ``.wav`` from the APK
source-set so only the OGG variant ships to Android.

Requires **ffmpeg** on PATH. Detection prints a clear install message
when missing instead of silently failing partway through the run.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SOUNDS_DIR = REPO_ROOT / "gaia_ultimatum" / "sounds"

# 128 kbps VBR — the standard "transparent for ambient/dialog" Vorbis
# rate. Going lower (96 kbps) starts to show on the cinematic tracks'
# stereo reverb tails; going higher (160+) brings minimal quality gain
# at meaningful size cost. The Vorbis quality scale ``-q:a 4`` maps to
# ~128 kbps VBR and is what every Vorbis encoder agrees on as
# "transparent" — see Xiph's quality-mode table.
VORBIS_QUALITY = "4"


def _have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def _transcode_one(src: Path) -> tuple[Path, int, int] | None:
    dst = src.with_suffix(".ogg")
    cmd = [
        "ffmpeg",
        "-y",                          # overwrite without prompt
        "-i", str(src),
        "-vn",                         # no video stream
        "-c:a", "libvorbis",
        "-q:a", VORBIS_QUALITY,
        "-loglevel", "error",
        str(dst),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  FAIL {src.relative_to(REPO_ROOT)}: {result.stderr.strip()}")
        return None
    return dst, src.stat().st_size, dst.stat().st_size


def main() -> int:
    if not _have_ffmpeg():
        print(
            "ffmpeg not found on PATH.\n"
            "Install:\n"
            "  Windows: https://www.gyan.dev/ffmpeg/builds/ (extract, add bin/ to PATH)\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   apt install ffmpeg  (or distro equivalent)\n"
        )
        return 1
    if not SOUNDS_DIR.is_dir():
        print(f"Sounds dir missing: {SOUNDS_DIR}")
        return 1
    sources = sorted(SOUNDS_DIR.rglob("*.wav"))
    if not sources:
        print(f"No .wav files under {SOUNDS_DIR}")
        return 0
    print(f"Transcoding {len(sources)} WAV → OGG (Vorbis q={VORBIS_QUALITY}).")
    print(f"Source: {SOUNDS_DIR.relative_to(REPO_ROOT)}\n")
    total_wav = total_ogg = 0
    fails = 0
    for src in sources:
        rel = src.relative_to(REPO_ROOT)
        res = _transcode_one(src)
        if res is None:
            fails += 1
            continue
        dst, w, o = res
        total_wav += w
        total_ogg += o
        ratio = w / o if o else 0
        print(f"  {rel}  {w/1e6:6.1f} MB → {o/1e6:5.2f} MB  ({ratio:5.1f}×)")
    print()
    print(
        f"Done. {len(sources) - fails}/{len(sources)} transcoded.\n"
        f"Total: {total_wav/1e6:.1f} MB WAV → {total_ogg/1e6:.1f} MB OGG "
        f"({(total_wav/total_ogg if total_ogg else 0):.1f}× compression)."
    )
    if fails:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
