"""Tests for the command-driven terminal interface (Task 2)."""

from __future__ import annotations

from src.the_curved_world.cli import GameCLI


def make_cli(seed: int = 12345) -> GameCLI:
    return GameCLI(echo=lambda _message: None, seed=seed)


def test_help_lists_commands() -> None:
    cli = make_cli()
    assert "move <dx> <dy>" in cli.handle("help")


def test_unknown_command_is_reported() -> None:
    cli = make_cli()
    assert cli.handle("frobnicate").startswith("error:")


def test_move_command_moves_the_player() -> None:
    cli = make_cli()
    before = cli.game.position
    output = cli.handle("move 1 0")
    assert output.startswith("moved to")
    assert cli.game.position != before


def test_move_rejects_non_numeric_input_without_crashing() -> None:
    cli = make_cli()
    before = cli.game.position
    output = cli.handle("move x y")
    assert output.startswith("error:")
    assert cli.game.position == before


def test_move_requires_two_arguments() -> None:
    cli = make_cli()
    assert cli.handle("move 1").startswith("usage:")


def test_read_reports_signal_label_and_trend() -> None:
    cli = make_cli()
    output = cli.handle("read")
    assert "signal=" in output
    assert any(label in output for label in ("Weak", "Moderate", "Strong"))


def test_marker_duplicate_is_reported() -> None:
    cli = make_cli()
    assert "placed" in cli.handle("mark a")
    assert cli.handle("mark a").startswith("error:")


def test_measure_requires_known_markers() -> None:
    cli = make_cli()
    cli.handle("mark a")
    cli.handle("move 1 0")
    cli.handle("mark b")
    assert "straight-line 3D distance" in cli.handle("measure a b")
    assert cli.handle("measure a zzz").startswith("error:")


def test_seed_restart_is_reproducible() -> None:
    cli = make_cli()
    cli.handle("seed 999")
    start_position = cli.game.position
    cli.handle("move 1 0")
    assert cli.game.steps == 1
    cli.handle("seed 999")
    assert cli.game.position == start_position
    assert cli.game.steps == 0


def test_new_with_explicit_seed() -> None:
    cli = make_cli()
    cli.handle("new 555")
    assert cli.game.summary().seed == 555


def test_invalid_seed_is_reported() -> None:
    cli = make_cli()
    assert cli.handle("seed abc").startswith("error:")


def test_log_command_lists_readings() -> None:
    cli = make_cli()
    assert cli.handle("log") == "log is empty"
    cli.handle("read note one")
    assert "note one" in cli.handle("log")


def test_quit_stops_the_loop() -> None:
    cli = make_cli()
    cli.handle("quit")
    assert cli.running is False