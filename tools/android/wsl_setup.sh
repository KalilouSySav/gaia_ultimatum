#!/usr/bin/env bash
# One-shot WSL setup for Android builds of Gaia Ultimatum.
#
# Run inside a fresh Ubuntu WSL session:
#
#   bash tools/android/wsl_setup.sh
#
# What this does:
#
#   1. Installs system packages buildozer + python-for-android need to
#      build pygame_ce, SDL2, etc. for arm64-v8a. The list is the one
#      buildozer's own docs recommend, plus ffmpeg for the WAV→OGG
#      transcoder that runs before each build.
#
#   2. Installs OpenJDK 17 — the Android SDK build tools require Java
#      17 since SDK Tools 35 (target API 34). Older Java versions
#      silently fail with "Unsupported class file major version 65".
#
#   3. Creates a Python 3.11 virtualenv at ~/buildozer-venv and installs
#      buildozer + cython + cookiecutter. Python 3.11 (not 3.14) is the
#      load-bearing choice: python-for-android's stable recipes target
#      3.11. Using 3.14 risks p4a crashing during recipe builds.
#
#   4. Prints what to run next.
#
# Idempotent — safe to re-run.

set -euo pipefail

echo "==> Installing system packages..."
sudo apt-get update
sudo apt-get install -y --no-install-recommends \
    build-essential \
    git \
    rsync \
    ffmpeg \
    autoconf \
    automake \
    libtool \
    libltdl-dev \
    pkg-config \
    zlib1g-dev \
    libncurses5-dev \
    libncursesw5-dev \
    libtinfo5 \
    libffi-dev \
    libssl-dev \
    unzip \
    zip \
    cmake \
    libgl1 \
    libgles2-mesa-dev \
    libsdl2-dev \
    libsdl2-image-dev \
    libsdl2-mixer-dev \
    libsdl2-ttf-dev \
    python3-pip \
    python3-venv \
    python3-setuptools

echo "==> Installing OpenJDK 17 (required by Android SDK build tools)..."
sudo apt-get install -y --no-install-recommends openjdk-17-jdk

echo "==> Installing Python 3.11 (python-for-android's stable target)..."
sudo apt-get install -y --no-install-recommends \
    software-properties-common
# Python 3.11 is in the default Ubuntu 22.04 repos; on 20.04 you'd need
# deadsnakes. Check the apt source first.
if ! apt-cache show python3.11 >/dev/null 2>&1; then
    echo "  python3.11 not in default repos — adding deadsnakes PPA"
    sudo add-apt-repository -y ppa:deadsnakes/ppa
    sudo apt-get update
fi
sudo apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev

VENV="${HOME}/buildozer-venv"
if [ ! -d "${VENV}" ]; then
    echo "==> Creating buildozer venv at ${VENV}..."
    python3.11 -m venv "${VENV}"
fi

echo "==> Installing buildozer + cython + cookiecutter into venv..."
# shellcheck disable=SC1091
source "${VENV}/bin/activate"
pip install --upgrade pip wheel
# Cython 0.29.x is what p4a's pygame_ce recipe expects. Newer Cython
# 3.x has caused build failures on the pygame_ce recipe path. Pin to
# the older stable line until p4a's recipe upgrades.
pip install "cython==0.29.36" cookiecutter
pip install buildozer

cat <<'NEXT'

==============================================================
WSL setup complete. Next steps:

  1. Activate the buildozer venv (every new WSL session):

       source ~/buildozer-venv/bin/activate

  2. Build the APK:

       bash tools/android/build_apk.sh

     First build downloads the Android SDK + NDK (~5 GB, ~30 min).
     Subsequent builds are 1-3 minutes.

  3. Output lands in:

       ~/builds/gaia_ultimatum/bin/gaiaultimatum-1.0.0-arm64-v8a-debug.apk

  4. Sideload to phone (USB debugging enabled):

       adb install ~/builds/gaia_ultimatum/bin/*.apk

==============================================================
NEXT
