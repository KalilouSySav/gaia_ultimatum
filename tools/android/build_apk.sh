#!/usr/bin/env bash
# Build the Android APK from a Linux-clean working tree.
#
# Why the rsync dance: this repo lives at
# /mnt/c/Users/<you>/OneDrive/Desktop/projet logciel/gaia_ultimatum,
# which has three things buildozer hates:
#
#   * Spaces in the path break some shell-out calls inside p4a recipes
#     (they don't all quote their arguments).
#   * OneDrive sync grabs file handles unpredictably, causing buildozer's
#     temp-file writes to fail with EBUSY mid-build.
#   * /mnt/c is the Windows filesystem mounted via 9P — file IO is
#     ~20× slower than ext4. A first build that takes 30 min on ext4
#     can take 90+ min on /mnt/c.
#
# So we rsync the project to ~/builds/gaia_ultimatum (ext4, no spaces,
# no OneDrive) and run buildozer there.
#
# Usage:
#
#   source ~/buildozer-venv/bin/activate    # activate the venv set up
#                                            # by wsl_setup.sh
#   bash tools/android/build_apk.sh         # build the debug APK
#
# Or from the host (Windows PowerShell):
#
#   wsl bash -c "source ~/buildozer-venv/bin/activate && \
#                cd '/mnt/c/Users/<you>/OneDrive/Desktop/projet logciel/gaia_ultimatum' && \
#                bash tools/android/build_apk.sh"

set -euo pipefail

# Resolve the script's own location → source repo root (parent of tools/).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_ROOT="${HOME}/builds/gaia_ultimatum"

echo "==> Source: ${REPO_ROOT}"
echo "==> Build:  ${BUILD_ROOT}"

# Sanity check — confirm buildozer is on PATH (= venv activated).
if ! command -v buildozer >/dev/null 2>&1; then
    cat <<'EOF' >&2
ERROR: ``buildozer`` not on PATH.
Activate the venv first:

    source ~/buildozer-venv/bin/activate

If you haven't run the setup yet:

    bash tools/android/wsl_setup.sh
EOF
    exit 1
fi

# Sanity check — buildozer.spec must exist at the source root.
if [ ! -f "${REPO_ROOT}/buildozer.spec" ]; then
    echo "ERROR: buildozer.spec missing at ${REPO_ROOT}" >&2
    exit 1
fi

# Stage to the Linux-clean build root via rsync. Excludes:
#   .git              — multi-GB history, irrelevant to APK
#   .venv             — desktop venv, would confuse p4a
#   tests, tools/     — buildozer.spec excludes these too, but skipping
#                       at rsync time avoids the I/O
#   bin/, .buildozer/ — buildozer's own outputs from prior runs on the
#                       /mnt/c side (avoid stale state)
#   *.pyc, __pycache__ — bytecode that'll just be regenerated
echo "==> Staging source to ${BUILD_ROOT}..."
mkdir -p "${BUILD_ROOT}"
rsync -a --delete \
    --exclude='.git/' \
    --exclude='.venv/' \
    --exclude='__pycache__/' \
    --exclude='*.pyc' \
    --exclude='bin/' \
    --exclude='.buildozer/' \
    --exclude='build/' \
    --exclude='dist/' \
    "${REPO_ROOT}/" "${BUILD_ROOT}/"

cd "${BUILD_ROOT}"

# Transcode WAV → OGG once per build (idempotent — script skips files
# whose OGG sidecar is already up to date relative to the WAV). Wraps
# in a python -c so we can use the existing venv's Python rather than
# hunting for a system Python with the right path resolution.
echo "==> Transcoding WAV → OGG (skip if up to date)..."
python tools/transcode_to_ogg.py || {
    echo "WARN: transcode_to_ogg.py failed — the APK will be larger" >&2
    echo "      than expected but should still build." >&2
}

# First-build warm-up note. Buildozer downloads SDK + NDK lazily on
# first ``buildozer android`` invocation; this prints the size so the
# user knows the wait is expected.
if [ ! -d "${HOME}/.buildozer/android/platform/android-sdk" ]; then
    echo "==> First build — buildozer will download Android SDK + NDK"
    echo "    (~5 GB total, ~20-30 min on a typical connection)."
fi

# Idempotent license acceptance. Buildozer's bundled commandlinetools
# 6514223 (2020 vintage) can't run ``sdkmanager --licenses`` under
# Java 17 — throws IllegalArgumentException in SdkManagerCliSettings
# init. The well-known Google license hashes below are public (every
# CI script that builds Android uses them) and writing them directly
# under ``licenses/`` is the canonical workaround. Idempotent: re-run
# any time, harmless if already present.
SDK_LICENSES="${HOME}/.buildozer/android/platform/android-sdk/licenses"
if [ -d "${HOME}/.buildozer/android/platform/android-sdk" ] && [ ! -f "${SDK_LICENSES}/android-sdk-license" ]; then
    echo "==> Writing Android SDK license-acceptance files..."
    mkdir -p "${SDK_LICENSES}"
    printf '24333f8a63b6825ea9c5514f83c2829b004d1fee\n8933bad161af4178b1185d1a37fbf41ea5269c55\nd56f5187479451eabf01fb78af6dfcb131a6481e\n' \
        > "${SDK_LICENSES}/android-sdk-license"
    printf '859f317696f67ef3d7f30a50a5560e7834b43903\n' \
        > "${SDK_LICENSES}/android-sdk-arm-dbt-license"
    printf '84831b9409646a918e30573bab4c9c91346d8abd\n' \
        > "${SDK_LICENSES}/android-sdk-preview-license"
    printf '601085b94cd77f0b54ff86406957099ebe79c4d6\n' \
        > "${SDK_LICENSES}/android-googletv-license"
    printf 'd975f751698a77b662f1254ddbeed3901e976f5a\n' \
        > "${SDK_LICENSES}/intel-android-extra-license"
    printf 'e9acab5b5fbb560a72cfaecce8946896ff6aab9d\n' \
        > "${SDK_LICENSES}/mips-android-sysimage-license"
fi

echo "==> Running buildozer android debug..."
# 16 KB page-size alignment for Play Store + Pixel 8/9 / Galaxy S24+
# compatibility. NDK r27+ supports it, but every recipe's linker has
# to be told to emit ``-Wl,-z,max-page-size=16384`` (and matching
# ``-z common-page-size=16384`` on some). The cleanest p4a-side hook
# is via the LDFLAGS env var which p4a's recipes thread into the
# underlying ndk-build / autotools invocations.
#
# Without this, every .so in the APK lands at 0x1000 (4 KB) alignment
# and Android 15+ device runtime refuses to map them — manifests as
# UnsatisfiedLinkError on SDL2.nativeSetenv at boot.
export LDFLAGS="-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384 ${LDFLAGS:-}"
export CFLAGS="-Wl,-z,max-page-size=16384 ${CFLAGS:-}"
export CXXFLAGS="-Wl,-z,max-page-size=16384 ${CXXFLAGS:-}"
buildozer android debug

# Locate the produced APK. Buildozer's naming includes the version
# from buildozer.spec; glob to whatever it produced rather than
# hard-coding.
APK="$(ls -t bin/*.apk 2>/dev/null | head -1)"
if [ -z "${APK}" ]; then
    echo "ERROR: build produced no APK — check the log above." >&2
    exit 1
fi

cat <<EOF

==============================================================
Build complete.

  APK: ${BUILD_ROOT}/${APK}

To sideload (phone needs USB Debugging enabled in Developer options):

  adb install -r '${BUILD_ROOT}/${APK}'

To pull the APK back to the Windows side (so File Explorer can see it):

  cp '${BUILD_ROOT}/${APK}' '${REPO_ROOT}/bin/'

==============================================================
EOF
