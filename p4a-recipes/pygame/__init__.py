# Local p4a recipe — pygame at v2.6.1 (overrides upstream v2.1.0).
#
# Why this override exists:
#
# python-for-android ships a ``pygame`` recipe pinned to v2.1.0 (Oct 2021).
# That version's ``src_c/_sdl2/sdl2.c`` does ``#include "longintrepr.h"``,
# which CPython **removed from public headers in 3.12** (moved to
# ``Include/internal``). p4a's current ``python3`` recipe builds CPython
# 3.14, so the upstream pygame recipe fails to compile during the
# ``setup.py build_ext`` step with:
#
#   src_c/_sdl2/sdl2.c:211:12: fatal error: 'longintrepr.h' file not found
#
# pygame **2.6.1** (Sep 2024) dropped ``_sdl2/sdl2.c`` entirely (the dir
# now only ships ``touch.c``) and is compatible with CPython 3.12+. The
# Android build path is preserved — ``buildconfig/Setup.Android.SDL2.in``
# still exists in 2.6.1, so the recipe's ``prebuild_arch`` template
# substitution continues to work without modification.
#
# This file inherits ``Pygame2Recipe`` from the upstream recipe and
# only bumps ``version`` + ``url``. Everything else (depends on
# sdl2/sdl2_image/sdl2_mixer/sdl2_ttf/jpeg/png, USE_SDL2=1 env, the
# Setup template substitution) is unchanged.
#
# Maintenance:
#   * If/when p4a upstream bumps its pygame recipe past 2.6.1, delete
#     this file + the ``p4a.local_recipes`` line in buildozer.spec.
#   * Newer pygame versions can be tested by bumping ``version`` here.
#     Compatibility check before bumping: confirm
#     ``buildconfig/Setup.Android.SDL2.in`` still exists in that version
#     on GitHub (was the load-bearing file in v2.6.1).
#
# Activation: ``buildozer.spec`` must point ``p4a.local_recipes`` at the
# parent of this file. See the corresponding comment block in that file.

import os
import subprocess

from pythonforandroid.logger import info
from pythonforandroid.recipes.pygame import Pygame2Recipe


class GaiaPygameRecipe(Pygame2Recipe):
    version = "2.6.1"

    # ``surface`` extension line as shipped in pygame 2.6.1's
    # ``buildconfig/Setup.Android.SDL2.in``. The template hasn't been
    # updated since pygame 2.1.0 even though pygame 2.6.x moved its
    # SIMD blitter implementations into separate translation units
    # (``simd_blitters_sse2.c``, ``simd_blitters_avx2.c``). Without
    # patching the line, ``surface.so`` is built referencing symbols
    # like ``alphablit_alpha_sse2_argb_surf_alpha`` whose
    # implementations never get linked in — runtime
    # ``dlopen failed: cannot locate symbol`` when ``from pygame
    # import display`` runs (display pulls in surface).
    _SURFACE_ORIGINAL = (
        "surface src_c/surface.c src_c/alphablit.c src_c/surface_fill.c"
    )
    _SURFACE_PATCHED = (
        "surface src_c/surface.c src_c/alphablit.c src_c/surface_fill.c "
        "src_c/simd_blitters_sse2.c src_c/simd_blitters_avx2.c"
    )

    def prebuild_arch(self, arch):
        super().prebuild_arch(arch)
        # Patch the ``Setup`` file the upstream recipe just generated
        # so the ``surface`` extension compiles + links the SIMD
        # blitter sources. ``alphablit.c`` declares functions like
        # ``alphablit_alpha_sse2_argb_surf_alpha`` whose bodies live
        # in ``simd_blitters_sse2.c``; pygame's regular ``setup.py``
        # knows this but ``Setup.Android.SDL2.in`` doesn't.
        #
        # The SIMD files are self-guarded with ``#if defined(__SSE2__)``
        # / ``__AVX2__`` so they compile to empty on ARM (where Android
        # x86_64 ABI mandates SSE2; AVX2 is opt-in but the file's
        # own ``#pragma GCC target`` handles that).
        setup_path = os.path.join(self.get_build_dir(arch.arch), "Setup")
        if not os.path.exists(setup_path):
            info(f"pygame Setup file not found at {setup_path}; skipping patch")
            return
        with open(setup_path) as fh:
            content = fh.read()
        if self._SURFACE_PATCHED in content:
            info("pygame Setup already patched for SIMD blitters")
            return
        if self._SURFACE_ORIGINAL not in content:
            info(
                "pygame Setup surface line doesn't match expected "
                "pygame 2.6.1 layout; skipping SIMD patch (build may fail "
                "with a missing-symbol error)"
            )
            return
        patched = content.replace(self._SURFACE_ORIGINAL, self._SURFACE_PATCHED)
        with open(setup_path, "w") as fh:
            fh.write(patched)
        info(
            f"Patched {setup_path}: added simd_blitters_sse2.c + "
            "simd_blitters_avx2.c to surface extension"
        )

    def build_arch(self, arch):
        # pygame 2.6.x compiles Cython modules at ``setup.py build_ext``
        # time (the upstream 2.1.0 recipe didn't need this because that
        # release shipped no .pyx files). Install Cython into the
        # hostpython3 interpreter just before this recipe's build runs.
        # Idempotent — pip exits 0 if Cython is already present.
        #
        # Why ``build_arch`` and not ``prebuild_arch``: p4a calls
        # ``prebuild_arch`` for ALL recipes before any recipe's
        # ``build_arch`` runs, so at prebuild time the hostpython3
        # binary at ``self.ctx.hostpython`` hasn't been built yet
        # (FileNotFoundError on the pip subprocess). By the time
        # ``build_arch`` runs, hostpython3 is up — its own
        # ``build_arch`` was already executed because it precedes
        # pygame in the dependency order.
        hostpython = self.ctx.hostpython
        if hostpython:
            info(
                f"Installing Cython into hostpython for pygame build: "
                f"{hostpython}"
            )
            subprocess.check_call(
                [hostpython, "-m", "pip", "install", "--upgrade", "Cython"],
            )
        super().build_arch(arch)


recipe = GaiaPygameRecipe()
