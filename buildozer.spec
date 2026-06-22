[app]

# (str) Title of the application — shown in the app drawer + as the
# initial window title on first launch. Matches ``config.py``'s
# ``DisplayConfig.title`` so the in-game window title and the
# launcher icon read the same.
title = Terre Vivante

# (str) Package name — ASCII slug, no spaces.
package.name = gaiaultimatum

# (str) Package domain — used for the APK's java package
# (``com.kalilou.gaiaultimatum``) and the Play Store listing's
# reverse-DNS id. Update before publishing.
package.domain = com.kalilou

# (str) Source code where the main.py lives.
source.dir = .

# (list) Source files to include (let empty to include all the files).
# Limit to the extensions that actually exist in the package + OGG
# (transcoded via ``tools/transcode_to_ogg.py`` before each Android
# build). Excluding ``.wav`` is the load-bearing line: WAVs are ~394
# MB and would blow past the 150 MB Play Store base APK cap. The OGG
# variants are ~10× smaller at no perceptible quality loss for the
# ambient/cinematic register the bundle uses.
#
# ``mp4`` is excluded — cinematics rely on OpenCV which we don't
# ship to Android (heavy dep + the existing procedural fallback at
# ``cinematics_player.py:33-40`` covers a missing cv2 gracefully).
#
# ``zones.geo.json`` (the light 968 KB variant) ends in ``.json`` so
# it's covered by the ``json`` extension below. ``zones.geojson``
# (the 24 MB full variant) ends in ``.geojson`` — excluded both via
# ``source.exclude_exts`` and explicitly via ``source.exclude_patterns``
# (belt + suspenders against extension-matcher quirks across p4a
# versions).
source.include_exts = py,json,ogg,png,ico,ttf,otf

# (list) Source files to exclude (let empty to not exclude anything)
source.exclude_exts = wav,mp4,geojson

# (list) List of directory to exclude (let empty to not exclude anything)
source.exclude_dirs = tests,tools,docs,.git,.github,.venv,__pycache__,build,dist

# (list) List of exclusions using pattern matching
# Drop the heavy GeoJSON explicitly even though the extension is
# excluded — paranoia against the ``.geojson`` → ``.geo.json``
# ambiguity in path filters.
source.exclude_patterns = gaia_ultimatum/data/zones.geojson

# (str) Application versioning (method 1)
version = 1.0.0

# (list) Application requirements — Python distribution + libraries
# bundled into the APK. Order matters: python-for-android resolves
# bottom-up. Keep this list minimal because every extra requirement
# inflates the APK and adds an extra recipe to maintain.
#
#   * python3            — the interpreter (p4a's bundled CPython).
#   * pygame             — upstream pygame (NOT pygame_ce). p4a has a
#                          recipe for ``pygame`` at v2.1.0 that builds
#                          against p4a's bundled SDL2/SDL2_image/
#                          SDL2_mixer/SDL2_ttf stack. There is NO p4a
#                          recipe for ``pygame_ce``: listing it here
#                          made p4a fall through to a pip install of
#                          the PyPI wheel, which is an auditwheel-
#                          repaired manylinux build bundling its own
#                          hashed SDL2 (``libSDL2-2-50d19f93.0.so.…``).
#                          The Android linker can't see that bundled
#                          .so (it's inside the wheel's private
#                          ``pygame.libs/`` directory, not on the app's
#                          loader path), so ``import pygame`` died at
#                          ``base.so`` load with:
#                            ImportError: dlopen failed: library
#                            "libSDL2-2-50d19f93.0.so.0.3200.10" not found
#                          ``pygame`` (the recipe-built upstream)
#                          dynamically links the SDL2 ``.so`` files p4a
#                          already places under ``lib/<arch>/``, so the
#                          linker resolves them cleanly. The code is
#                          neutral between the two (``import pygame``)
#                          and avoids pygame_ce-only API, so the desktop
#                          → Android switch needs no source edits. If
#                          the Android build ever drifts because pygame
#                          2.1.0 lacks a CE-only feature, the fix is to
#                          author a local ``pygame_ce`` recipe under
#                          ``p4a.local_recipes`` modeled on the upstream
#                          ``pygame`` recipe.
#   * pillow             — used for icon loading + image processing in
#                          the cinematics player path; also a hard dep
#                          in ``pyproject.toml``.
#
# Intentionally NOT here:
#   * pygame_ce          — see above; no p4a recipe, ships as a
#                          manylinux wheel with a hashed SDL2 that
#                          collides with p4a's bundled SDL2.
#   * opencv-python      — ~70 MB extra and not needed; the
#                          cinematics player already gates the import
#                          and falls back to procedural envelopes when
#                          cv2 is missing.
#   * pygbag             — desktop/web only, no Android role.
requirements = python3,pygame,pillow

# (str) Custom source folders for requirements
# Sets custom source for any requirements with recipes
# requirements.source.kivy = ../../kivy

# (str) Presplash of the application
presplash.filename = %(source.dir)s/gaia_ultimatum/data/images/app_icon.png

# (str) Icon of the application
icon.filename = %(source.dir)s/gaia_ultimatum/data/images/app_icon.png

# (str) Supported orientation — buildozer's validator accepts only
# ``landscape``/``portrait``/``all``/``sensor``/``user``/``behind`` here.
# (Android's own manifest field accepts ``sensorLandscape`` but
# buildozer rejects it client-side before generating the manifest.)
# ``landscape`` locks left-landscape only. Acceptable for v1; if users
# complain about the charging port landing under their hand, we can
# generate the manifest patch via the ``android.add_src`` /
# ``android.manifest.intent_filters`` hooks instead.
orientation = landscape

# (list) List of services to declare
#services =

#
# OSX Specific
#
# author = Kalilou Sy Savane

#
# Android specific
#

# (bool) Indicate if the application should be fullscreen or not
# 1 = immersive sticky — hides system bars during gameplay. Standard
# for games. The pause menu + settings overlays show without
# revealing the bars because pygame draws over the entire surface.
fullscreen = 1

# (string) Presplash background color (for android toolchain)
# A hex color in the form #RRGGBB e.g. #FF0000
presplash_color = #0F1320

# (list) Permissions
# Minimal — no internet, no storage, no location. The game runs
# entirely offline and saves to internal storage via Android's
# default sandbox (no permission needed for that).
android.permissions =

# (int) Target Android API, should be as high as possible.
# Play Store requires API 33+ as of August 2023 for new apps and
# 34+ for updates as of August 2024. Target 34 to avoid imminent
# deprecation; min API 21 (Android 5.0) covers ~99% of devices.
android.api = 34
android.minapi = 21

# (str) Android NDK version to use.
#
# 16 KB-page-size compatibility (required for Play Store from Nov 2025
# onward when targeting API 35+, and increasingly enforced at runtime
# on Pixel 8/9 / Galaxy S24+ / any device shipping with the 16 KB
# kernel patch) needs NDK r27 or newer. r25b can only emit 4 KB-aligned
# .so files; the Android linker on a 16 KB-page device refuses to map
# them and PythonActivity dies with UnsatisfiedLinkError on
# nativeSetenv (the very first JNI call after SDL2 load). r27c is the
# stable line; r28b/c is what p4a's master branch recommends.
#
# NOTE: bumping the NDK is necessary but may not be sufficient — p4a
# still needs to pass ``-Wl,-z,max-page-size=16384`` to the linker for
# every recipe (SDL2, libSDL2_mixer, freetype, libpng, openssl, etc.).
# How that flag gets injected depends on the p4a recipe version.
# If a rebuild with this NDK still produces 4 KB-aligned libs, the
# next step is to patch p4a's NDK invocation or use ``p4a.extra_args``
# to pass the flag globally. For now, bumping the NDK is the
# cheapest first attempt.
android.ndk = 27c

# (int) Android SDK version to use
android.sdk = 34

# (bool) Use --private data storage (True) or --dir public storage (False)
# True — game saves go under the app's internal-storage dir
# (``getFilesDir()``). ``persistence._save_dir()`` reads
# ``ANDROID_PRIVATE`` env var which p4a sets to this path at boot.
android.private_storage = True

# (str) Android logcat filters to use
android.logcat_filters = *:S python:D

# (list) The Android archs to build for, choices: armeabi-v7a, arm64-v8a, x86, x86_64
# arm64-v8a covers every Android device made since ~2017 (Play Store
# requires arm64 for app updates). armeabi-v7a covers a handful of
# older budget devices. x86_64 is for Android Studio emulators on
# Intel/AMD host PCs — real devices are always ARM, but the emulator
# variant ships native x86_64 libs that run at full host speed, which
# is the only realistic way to iterate during local dev without the
# ARM-emulation slowdown.
#
# For Play Store **release** AABs we'll drop x86_64 (Google Play
# splits per-arch so users don't download it anyway, and stripping
# it from debug builds is a measurable size win). For development:
# keep it on so the emulator install path works.
android.archs = arm64-v8a,armeabi-v7a,x86_64

# (bool) enables Android auto backup feature (Android API >=23)
android.allow_backup = True

#
# Python for android (p4a) specific
#

# (str) python-for-android branch to use, defaults to master
p4a.branch = master

# (str) The directory in which python-for-android should look for your own build recipes (if any)
#
# Points at ``p4a-recipes/`` in this repo where a local override of the
# ``pygame`` recipe lives. The upstream p4a pygame recipe is pinned to
# v2.1.0 (Oct 2021), which references ``longintrepr.h`` — a CPython
# header removed in 3.12. p4a's current ``python3`` recipe builds
# CPython 3.14, so the upstream pygame build fails at compile time.
# The local recipe inherits ``Pygame2Recipe`` and bumps ``version`` to
# 2.6.1 (Sep 2024) which dropped the offending file. See
# ``p4a-recipes/pygame/__init__.py`` for the full rationale + the
# maintenance steps for retiring this override.
p4a.local_recipes = ./p4a-recipes

# ---------------------------------------------------------------------------
# Play Store release signing
# ---------------------------------------------------------------------------
#
# Release signing is configured via the ``P4A_RELEASE_*`` environment
# variables that ``tools/android/build_aab.sh`` validates and passes
# through to buildozer. We do NOT bake keystore paths or passwords
# into this file because:
#
#   * The .jks file is private — it should never be checked into git.
#   * Hardcoding passwords here would put them in shell history every
#     time anyone reads the spec.
#   * Different developers / CI runners need different keystore paths.
#
# To produce a Play-Store-ready AAB:
#
#   export P4A_RELEASE_KEYSTORE="$HOME/keys/terre-vivante-release.jks"
#   export P4A_RELEASE_KEYSTORE_PASSWD="..."
#   export P4A_RELEASE_KEYALIAS="terre-vivante"
#   export P4A_RELEASE_KEYALIAS_PASSWD="..."
#   make android-release
#
# The release script also drops ``x86_64`` from ``android.archs`` for
# the release build (it modifies a *staged copy* of this spec — the
# version on disk stays untouched so debug builds keep emulator
# support).
#
# First-time setup (one-time only, save the resulting .jks somewhere
# safe + back it up — losing it means losing the ability to update
# this app on Play Store, forever):
#
#   keytool -genkey -v -keystore ~/keys/terre-vivante-release.jks \
#     -alias terre-vivante -keyalg RSA -keysize 2048 -validity 10000

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
