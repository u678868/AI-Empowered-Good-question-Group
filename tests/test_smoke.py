"""Smoke test for the command-line entry point."""

from src.main import main


def test_demo_entry_point_returns_zero() -> None:
    """The non-interactive demo entry point should run and return exit code 0."""
    assert main(["--demo"]) == 0