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


def test_parse_args_flags() -> None:
    args = parse_args(["--seed", "7", "--debug", "--no-audio"])
    assert args.seed == 7
    assert args.debug is True
    assert args.no_audio is True


def test_version_exits(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        parse_args(["--version"])
    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out
