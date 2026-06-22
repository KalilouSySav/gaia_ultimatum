"""Basic smoke tests for the CLI entry point."""

from __future__ import annotations

import pytest

from gaia_ultimatum import __version__
from gaia_ultimatum.app import parse_args


def test_parse_args_defaults() -> None:
    args = parse_args([])
    assert args.seed is None
    assert args.debug is False
    assert args.no_audio is False
    # ``None`` (not ``False``) because the run path needs to distinguish
    # "user said nothing — defer to config/env/touch-mode chain" from
    # "user explicitly passed --no-fullscreen — force windowed".
    assert args.fullscreen is None


def test_parse_args_flags() -> None:
    args = parse_args(["--seed", "7", "--debug", "--no-audio"])
    assert args.seed == 7
    assert args.debug is True
    assert args.no_audio is True


def test_parse_args_fullscreen_explicit_true() -> None:
    args = parse_args(["--fullscreen"])
    assert args.fullscreen is True


def test_parse_args_fullscreen_explicit_false() -> None:
    """``--no-fullscreen`` lets a Steam Deck or Android dev override the
    auto-fullscreen default and run windowed for debugging."""
    args = parse_args(["--no-fullscreen"])
    assert args.fullscreen is False


def test_version_exits(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out
