#!/usr/bin/env bash
# Build the signed release AAB for Play Store submission.
#
# This is the production sibling of ``build_apk.sh``. Key differences:
#
#   1. Output is ``.aab`` (Android App Bundle), not ``.apk``. Play Store
#      requires AAB for all new apps since August 2021. AAB lets Google
#      generate per-device splits at install time so users only download
#      the arch + densities they need (35 MB instead of 90 MB).
#
#   2. Drops ``x86_64`` from the arch list. x86_64 is only useful for
#      Android Studio emulators; real Play Store users are all ARM and
#      shipping the x86_64 .so files adds ~30 MB they'd never use.
#      Debug builds keep x86_64 so local emulator testing still works
#      — this script edits a *copy* of buildozer.spec for the release
#      run and restores the original at exit (trap handler).
#
#   3. Requires a release keystore. Buildozer signs the AAB during the
#      release build using the keystore + alias + passwords from the
#      four ``P4A_RELEASE_*`` env vars below. Generate the keystore
#      once with ``keytool`` (see Privacy + Release setup section of
#      this script's tail) and store the passwords in a secret manager
#      — losing them means losing your ability to update the app on
#      Play Store, ever.
#
# Usage:
#
#   export P4A_RELEASE_KEYSTORE="$HOME/keys/terre-vivante-release.jks"
#   export P4A_RELEASE_KEYSTORE_PASSWD="..."
#   export P4A_RELEASE_KEYALIAS="terre-vivante"
#   export P4A_RELEASE_KEYALIAS_PASSWD="..."
#   bash tools/android/build_aab.sh
#
# Or from Windows PowerShell:
#
#   wsl bash -c "source ~/buildozer-venv/bin/activate && \
#                export P4A_RELEASE_KEYSTORE=... && \
#                ... && \
#                cd '/mnt/c/.../gaia_ultimatum' && \
#                bash tools/android/build_aab.sh"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BUILD_ROOT="${HOME}/builds/gaia_ultimatum"

echo "==> Source: ${REPO_ROOT}"
echo "==> Build:  ${BUILD_ROOT}"

# Sanity check — venv activated?
if ! command -v buildozer >/dev/null 2>&1; then
    echo "ERROR: ``buildozer`` not on PATH. Activate the venv first:" >&2
    echo "    source ~/buildozer-venv/bin/activate" >&2
    exit 1
fi

# Sanity check — release keystore env vars present? Fail fast so a
# 30-minute build doesn't die at the signing step with an opaque
# error from jarsigner. All four are required; checking the path
# also catches typos that would otherwise produce an "unsigned"
# AAB that Play Store will reject at upload time.
missing=()
for v in P4A_RELEASE_KEYSTORE P4A_RELEASE_KEYSTORE_PASSWD \
         P4A_RELEASE_KEYALIAS P4A_RELEASE_KEYALIAS_PASSWD; do
    if [ -z "${!v:-}" ]; then
        missing+=("$v")
    fi
done
if [ ${#missing[@]} -ne 0 ]; then
    cat <<EOF >&2
ERROR: missing release-signing env vars: ${missing[*]}

Generate a keystore once (DO NOT REGENERATE — losing the key means
permanently losing the ability to update this app on Play Store):

  keytool -genkey -v -keystore ~/keys/terre-vivante-release.jks \\
    -alias terre-vivante -keyalg RSA -keysize 2048 -validity 10000

Then export the four variables and re-run this script:

  export P4A_RELEASE_KEYSTORE="\$HOME/keys/terre-vivante-release.jks"
  export P4A_RELEASE_KEYSTORE_PASSWD="<password you set above>"
  export P4A_RELEASE_KEYALIAS="terre-vivante"
  export P4A_RELEASE_KEYALIAS_PASSWD="<password you set above>"

Back the .jks file + the passwords up to a password manager + an
offline encrypted location. Treat them like a Play Store account
recovery code.
EOF
    exit 1
fi

if [ ! -f "${P4A_RELEASE_KEYSTORE}" ]; then
    echo "ERROR: P4A_RELEASE_KEYSTORE points at a non-existent file:" >&2
    echo "    ${P4A_RELEASE_KEYSTORE}" >&2
    exit 1
fi

if [ ! -f "${REPO_ROOT}/buildozer.spec" ]; then
    echo "ERROR: buildozer.spec missing at ${REPO_ROOT}" >&2
    exit 1
fi

# Stage source to Linux-clean build root (same rationale as build_apk.sh).
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

echo "==> Transcoding WAV → OGG (skip if up to date)..."
python tools/transcode_to_ogg.py || {
    echo "WARN: transcode_to_ogg.py failed — the AAB will be larger" >&2
    echo "      than expected but should still build." >&2
}

# Edit buildozer.spec *in the staged copy only* (REPO_ROOT version is
# untouched) to drop x86_64 from the arch list. Trap restores the
# original on exit so a Ctrl-C / failure mid-build doesn't leave a
# broken release spec around — though since we modify the staged
# copy, this is belt + suspenders.
SPEC="${BUILD_ROOT}/buildozer.spec"
SPEC_BACKUP="${SPEC}.bak"
cp "${SPEC}" "${SPEC_BACKUP}"
trap 'mv "${SPEC_BACKUP}" "${SPEC}" 2>/dev/null || true' EXIT
echo "==> Dropping x86_64 from android.archs (release build)..."
sed -i 's/^android\.archs = .*$/android.archs = arm64-v8a,armeabi-v7a/' "${SPEC}"

# SDK license acceptance (same workaround as build_apk.sh).
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

echo "==> Running buildozer android release (AAB)..."
# 16 KB page-size alignment (same as debug; required by Play Store
# for apps targeting API 35+ from Nov 2025 onward).
export LDFLAGS="-Wl,-z,max-page-size=16384 -Wl,-z,common-page-size=16384 ${LDFLAGS:-}"
export CFLAGS="-Wl,-z,max-page-size=16384 ${CFLAGS:-}"
export CXXFLAGS="-Wl,-z,max-page-size=16384 ${CXXFLAGS:-}"

# Buildozer's release path reads P4A_RELEASE_* env vars (already
# verified above) and produces a signed AAB when called with the
# ``release`` build type. The ``aab`` argument is what flips the
# output format from APK to AAB.
#
# Pipe ``y\n`` so the "Buildozer is running as root!" interactive
# prompt resolves automatically — under WSL/CI everything runs as
# root and there's no realistic way to drop privileges mid-build
# (the Android SDK lives under /root/.buildozer/). Without the
# pipe the build hangs waiting on stdin and dies with EOFError when
# called non-interactively (background job, CI worker, etc.).
yes y | buildozer android release aab

# Locate the produced AAB.
AAB="$(ls -t bin/*-release.aab 2>/dev/null | head -1)"
if [ -z "${AAB}" ]; then
    # Some buildozer versions name it differently; fall back to any
    # .aab in bin/ produced in the last 5 minutes.
    AAB="$(find bin -name '*.aab' -mmin -5 2>/dev/null | head -1)"
fi
if [ -z "${AAB}" ]; then
    echo "ERROR: build produced no AAB — check the log above." >&2
    exit 1
fi

cat <<EOF

==============================================================
Release build complete.

  AAB: ${BUILD_ROOT}/${AAB}

This file is signed and ready to upload to Play Console:

  1. Open https://play.google.com/console
  2. Pick your app → Production (or Internal testing for first deploy)
  3. Create new release → upload this AAB
  4. Fill in release notes, save, send for review

For local Play-Store-simulating install via bundletool (optional
sanity check before upload), see https://developer.android.com/tools/bundletool

==============================================================
EOF
