"""Tests for the interactive session and Task 5 additions (mock input, no GUI)."""

from __future__ import annotations

import pytest

from src.the_curved_world.cli import GameCLI
from src.the_curved_world.config import default_config
from src.the_curved_world.gameplay import ExplorationGame
from src.the_curved_world.session import run_interactive_session
from src.the_curved_world.world import WorldGenerator


def _feed(lines):
    iterator = iter(list(lines))

    def _input(_prompt: str = "") -> str:
        try:
            return next(iterator)
        except StopIteration as exc:
            raise EOFError from exc

    return _input


def _exit_route(seed: int = 12345, max_steps: int = 400):
    """Compute a move route that reaches the exit (offline, for the test only)."""
    world = WorldGenerator(default_config()).generate(seed)
    game = ExplorationGame(world)
    developer = world.debug_view()
    moves = []
    for _ in range(max_steps):
        if game.won:
            break
        exit_x, exit_y = developer.exit
        x, y = game.position
        dx, dy = exit_x - x, exit_y - y
        if abs(dx) < 1e-12 and abs(dy) < 1e-12:
            break
        moves.append(f"move {dx} {dy}")
        game.move(dx, dy)
    return moves, game.won


class _FakeRenderer:
    def __init__(self) -> None:
        self.rendered = 0
        self.closed = False
        self.held = False

    def render(self, scene) -> None:
        self.rendered += 1

    def pause(self, interval: float = 0.001) -> None:
        pass

    def hold(self) -> None:
        self.held = True

    def close(self) -> None:
        self.closed = True


def test_session_plays_a_full_game_and_wins() -> None:
    moves, reachable = _exit_route(12345)
    assert reachable

    cli = GameCLI(echo=lambda _m: None, seed=12345)
    transcript: list[str] = []
    lines = ["scan", "mark start", "curvature"] + moves + ["scan", "log", "quit"]

    run_interactive_session(
        cli, input_func=_feed(lines), echo=transcript.append, hold_window_on_victory=False
    )

    assert cli.game.won is True
    text = "\n".join(transcript)
    assert "EXIT FOUND" in text
    assert "Exit found - session complete." in text


def test_session_survives_invalid_input() -> None:
    lines = ["", "bogus", "move", "move x y", "measure nope nope", "mark", "view sideways", "seed abc", "scan"]
    cli = GameCLI(echo=lambda _m: None, seed=12345)
    transcript: list[str] = []

    run_interactive_session(cli, input_func=_feed(lines), echo=transcript.append)

    text = "\n".join(transcript)
    assert "error:" in text or "usage:" in text
    assert cli.game.won is False


def test_session_shows_a_status_line_each_loop() -> None:
    cli = GameCLI(echo=lambda _m: None, seed=12345)
    transcript: list[str] = []
    run_interactive_session(cli, input_func=_feed(["w", "quit"]), echo=transcript.append)
    status_lines = [line for line in transcript if line.startswith("[status]")]
    assert len(status_lines) >= 2
    assert any("steps=1" in line for line in status_lines)


def test_session_player_mode_leaks_no_hidden_state() -> None:
    probe = GameCLI(echo=lambda _m: None, seed=12345)
    developer = probe.game.debug_view()
    exit_x, exit_y = developer.exit
    true_distance = developer.distance_to_exit(probe.game.position)
    start_x = probe.game.position[0]

    cli = GameCLI(echo=lambda _m: None, seed=12345)
    transcript: list[str] = []
    lines = ["scan", "w", "scan", "a", "mark P1", "measure P1 P1", "curvature", "log", "status", "quit"]
    run_interactive_session(cli, input_func=_feed(lines), echo=transcript.append)
    text = "\n".join(transcript)

    assert f"{start_x:.3f}" in text  # positive control: player coordinates are shown
    assert f"{exit_x:.3f}" not in text
    assert f"{exit_y:.3f}" not in text
    assert f"{true_distance:.4f}" not in text


def test_session_holds_the_window_on_victory() -> None:
    moves, reachable = _exit_route(12345)
    assert reachable

    renderer = _FakeRenderer()
    cli = GameCLI(echo=lambda _m: None, seed=12345)
    cli.attach_renderer(renderer, mode="player")
    assert renderer.rendered >= 1
    before = renderer.rendered

    run_interactive_session(cli, input_func=_feed(moves), echo=lambda _m: None)

    assert cli.game.won is True
    assert renderer.held is True
    assert renderer.rendered > before


def test_session_closes_the_window_on_quit() -> None:
    renderer = _FakeRenderer()
    cli = GameCLI(echo=lambda _m: None, seed=12345)
    cli.attach_renderer(renderer, mode="player")
    run_interactive_session(cli, input_func=_feed(["quit"]), echo=lambda _m: None)
    assert renderer.closed is True


def test_status_line_reports_position_signal_and_steps() -> None:
    cli = GameCLI(echo=lambda _m: None, seed=12345)
    assert "steps=0" in cli.status_line()
    cli.handle("w")
    line = cli.status_line()
    assert "(x,y,z)=" in line
    assert "signal=" in line
    assert "steps=1" in line


def test_scan_curvature_and_wasd_commands() -> None:
    cli = GameCLI(echo=lambda _m: None, seed=12345)
    assert cli.handle("curvature").startswith("Gaussian curvature")
    assert "signal=" in cli.handle("scan")

    start_x, start_y = cli.game.position
    cli.handle("w")
    assert cli.game.position[1] > start_y
    before_s = cli.game.position[1]
    cli.handle("s")
    assert cli.game.position[1] < before_s      # slope damping makes w/s asymmetric
    cli.handle("a")
    assert cli.game.position[0] < start_x