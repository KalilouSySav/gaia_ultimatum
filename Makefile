.PHONY: help install dev test lint format typecheck run clean

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

clean:
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
