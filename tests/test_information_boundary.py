"""Automated information-leak audit for The Curved World (Task 4).

These tests try to prove that ordinary, player-facing gameplay cannot reveal the
hidden exit position or the exact player-to-exit distance before victory.
"""

from __future__ import annotations

from src.the_curved_world.cli import GameCLI
from src.the_curved_world.config import default_config
from src.the_curved_world.gameplay import GameSummary, LogEntry, Marker
from src.the_curved_world.observations import PlayerObservation
from src.the_curved_world.world import WorldGenerator

SESSION_COMMANDS = [
    "help",
    "status",
    "read",
    "n",
    "read note one",
    "e",
    "mark P1",
    "markers",
    "log",
    "measure P1 P1",
    "w",
    "s",
    "read again",
    "seed 12345",
    "status",
    "bogus",
    "move 1",
    "move x y",
    "mark P1",
    "measure P1 nope",
    "view debug",
    "quit",
]


def _transcript(seed: int = 12345) -> str:
    cli = GameCLI(echo=lambda _message: None, seed=seed)
    lines = [cli.handle(command) for command in SESSION_COMMANDS]
    return "\n".join(line for line in lines if line)


def test_cli_transcript_never_prints_exit_coordinates_or_true_distance() -> None:
    cli = GameCLI(echo=lambda _message: None, seed=12345)
    developer = cli.game.debug_view()
    exit_x, exit_y = developer.exit
    true_distance = developer.distance_to_exit(cli.game.position)

    assert cli.game.won is False
    text = _transcript()

    # positive control: the transcript really does contain player coordinates,
    # so the absence of the exit coordinates below is meaningful.
    start_x, _start_y = developer.start
    assert f"{start_x:.3f}" in text

    assert f"{exit_x:.3f}" not in text
    assert f"{exit_y:.3f}" not in text
    assert f"{true_distance:.4f}" not in text


def test_player_facing_records_expose_only_allowed_fields() -> None:
    assert set(PlayerObservation.__dataclass_fields__) == {"signal", "label", "trend"}
    assert set(LogEntry.__dataclass_fields__) <= {"index", "position", "signal", "label", "trend", "note"}
    assert set(Marker.__dataclass_fields__) == {"name", "position", "signal", "label"}
    assert set(GameSummary.__dataclass_fields__) == {
        "seed",
        "observations",
        "markers",
        "steps",
        "elapsed_time",
    }


def test_player_view_and_observer_cannot_reach_the_exit() -> None:
    world = WorldGenerator(default_config()).generate(5)
    for obj in (world.player_view(), world.player_observer()):
        assert not hasattr(obj, "exit")
        assert not hasattr(obj, "exit_position")
        assert not hasattr(obj, "distance")
        assert not hasattr(obj, "world")


def test_debug_view_requires_an_explicit_request() -> None:
    world = WorldGenerator(default_config()).generate(5)
    debug = world.debug_view()
    assert debug.exit == world.exit
    # the exit is only reachable through the privileged interface
    assert debug.exit_position().shape == (3,)