.PHONY: help install dev test lint format typecheck run web-build web-serve \
        android-setup android-debug android-release clean

PYTHON ?= python3

help:
	@echo "Available targets:"
	@echo "  install     Install the package"
	@echo "  dev         Install the package with dev dependencies"
	@echo "  run         Launch the game"
	@echo "  test        Run the test suite"
	@echo "  lint        Run ruff linter"
	@echo "  format      Auto-format with ruff"
	@echo "  typecheck   Run mypy"
	@echo "  web-build   Build the WebAssembly bundle with pygbag"
	@echo "  web-serve   Build + serve the web bundle locally on :8000"
	@echo "  android-setup    One-time WSL setup for Android builds"
	@echo "  android-debug    Build the Android debug APK (all archs, unsigned)"
	@echo "  android-release  Build a signed release AAB for Play Store (ARM only)"
	@echo "  clean       Remove build + cache artifacts"

install:
	$(PYTHON) -m pip install -e .

dev:
	$(PYTHON) -m pip install -e ".[dev]"

run:
	$(PYTHON) -m gaia_ultimatum

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check gaia_ultimatum tests

format:
	$(PYTHON) -m ruff format gaia_ultimatum tests
	$(PYTHON) -m ruff check --fix gaia_ultimatum tests

typecheck:
	$(PYTHON) -m mypy gaia_ultimatum

web-build:
	$(PYTHON) -m pygbag --build --archive --ume_block 0 --disable-sound-format-error main.py

web-serve:
	$(PYTHON) -m pygbag --ume_block 0 --disable-sound-format-error main.py

# Android — run from inside WSL Ubuntu. From Windows host use:
#   wsl make android-setup
#   wsl make android-debug
#
# ``android-setup`` is one-time per WSL install. ``android-debug``
# stages the project to ~/builds/gaia_ultimatum (off OneDrive + off
# the Windows mount, both of which slow buildozer down 20×) then runs
# the build. First build downloads ~5 GB of SDK + NDK; subsequent
# builds are 1-3 min.
android-setup:
	bash tools/android/wsl_setup.sh

android-debug:
	bash tools/android/build_apk.sh

# Release AAB for Play Store. Requires the four P4A_RELEASE_* env
# vars to be set (keystore path + passwords). See the header of
# tools/android/build_aab.sh for the one-time keystore-generation
# walkthrough. Run from WSL like the debug target.
android-release:
	bash tools/android/build_aab.sh

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
