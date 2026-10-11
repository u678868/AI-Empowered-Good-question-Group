"""Tests for the exploration mechanics (Task 2)."""

from __future__ import annotations

import math

import pytest

from src.the_curved_world.config import ConfigError, default_surface_config
from src.the_curved_world.detector import Detector, DetectorConfig
from src.the_curved_world.gameplay import ExplorationGame, GameError, GameplayConfig, LogEntry
from src.the_curved_world.geometry import SmoothSurface, ambient_distance
from src.the_curved_world.observations import PlayerObservation
from src.the_curved_world.world import WorldState


def make_world(start=(0.0, 0.0), exit_=(2.5, 2.5), scale=1.0) -> WorldState:
    surface = SmoothSurface(default_surface_config())
    detector = Detector(surface.position(*exit_), DetectorConfig(scale))
    return WorldState(surface=surface, seed=0, start=tuple(start), exit=tuple(exit_), detector=detector)


def make_game(world: WorldState, **cfg) -> ExplorationGame:
    config = GameplayConfig(**cfg) if cfg else None
    return ExplorationGame(world, config)


def test_move_updates_position_and_recomputes_height() -> None:
    world = make_world((0.0, 0.0), (2.5, 2.5))
    game = make_game(world)
    result = game.move(1.0, 0.0)

    assert result.moved
    assert game.position == pytest.approx((game.step_length, 0.0))
    assert game.steps == 1
    assert game.elapsed_time == pytest.approx(0.25)
    height = game.player_view.position(game.position)[2]
    assert height == pytest.approx(world.surface.height(*game.position))


def test_diagonal_movement_is_normalised() -> None:
    world = make_world((0.0, 0.0), (2.5, 2.5))
    game = make_game(world)
    start = game.position
    game.move(1.0, 1.0)
    dx = game.position[0] - start[0]
    dy = game.position[1] - start[1]
    assert math.hypot(dx, dy) == pytest.approx(game.step_length)
    assert dx == pytest.approx(dy)


def test_movement_is_clamped_to_domain() -> None:
    world = make_world((2.0, 2.0), (-2.0, -2.0))
    game = make_game(world)
    domain = world.surface.domain
    result = None
    for _ in range(400):
        result = game.move(1.0, 0.0)
    assert result is not None and result.clamped
    assert game.position[0] == pytest.approx(domain.x_max)
    assert game.player_view.contains(game.position)


def test_zero_move_is_a_noop() -> None:
    world = make_world((0.0, 0.0), (2.5, 2.5))
    game = make_game(world)
    result = game.move(0.0, 0.0)
    assert not result.moved
    assert game.steps == 0


def test_marker_placement_and_duplicate_name() -> None:
    world = make_world((0.0, 0.0), (2.5, 2.5))
    game = make_game(world)
    marker = game.place_marker("home")
    assert marker.name == "home"
    assert marker.position == game.position
    assert 0.0 <= marker.signal <= 1.0
    assert len(game.markers) == 1

    with pytest.raises(GameError):
        game.place_marker("home")
    with pytest.raises(GameError):
        game.place_marker("   ")


def test_measurement_between_markers_uses_ambient_distance() -> None:
    world = make_world((0.0, 0.0), (2.5, 2.5))
    game = make_game(world)
    game.place_marker("a")
    game.move(1.0, 0.0)
    game.place_marker("b")

    measured = game.distance_between_markers("a", "b")
    expected = ambient_distance(
        world.position(game.markers[0].position), world.position(game.markers[1].position)
    )
    assert measured == pytest.approx(expected)
    assert measured > 0.0


def test_unknown_marker_raises() -> None:
    world = make_world((0.0, 0.0), (2.5, 2.5))
    game = make_game(world)
    game.place_marker("a")
    with pytest.raises(GameError):
        game.distance_between_markers("a", "missing")


def test_observation_and_log_expose_no_hidden_state() -> None:
    world = make_world((0.0, 0.0), (2.5, 2.5))
    game = make_game(world)
    observation = game.read_detector("first probe")

    assert set(PlayerObservation.__dataclass_fields__) == {"signal", "label", "trend"}
    assert set(LogEntry.__dataclass_fields__) <= {"index", "position", "signal", "label", "trend", "note"}

    entry = game.log[-1]
    assert entry.index == 1
    assert entry.note == "first probe"
    assert not hasattr(observation, "distance")
    assert str(world.exit) not in repr(observation)
    assert str(world.exit) not in repr(entry)


def test_victory_within_capture_radius() -> None:
    world = make_world((2.0, 0.0), (0.0, 0.0))
    game = make_game(world, move_speed=2.0, time_step=0.25, capture_radius=0.75)
    assert not game.won

    for _ in range(60):
        if game.won:
            break
        ex, ey = world.exit
        px, py = game.position
        game.move(ex - px, ey - py)

    assert game.won
    summary = game.summary()
    assert summary.seed == world.seed
    assert summary.steps > 0


def test_no_victory_outside_capture_radius() -> None:
    world = make_world((2.0, 0.0), (0.0, 0.0))
    game = make_game(world, move_speed=2.0, time_step=0.25, capture_radius=0.5)
    game.move(1.0, 0.0)
    assert not game.won
    assert ambient_distance(game.player_view.position(game.position), world.exit_position()) > 0.5


def test_invalid_gameplay_config_raises() -> None:
    with pytest.raises(ConfigError):
        GameplayConfig(move_speed=-1.0)
    with pytest.raises(ConfigError):
        GameplayConfig(move_speed=2.0, time_step=0.25, capture_radius=0.1)