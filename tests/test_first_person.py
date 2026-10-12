"""Tests for the first-person tangent frame and relative movement (Task 10)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.the_curved_world.config import default_config
from src.the_curved_world.detector import Detector, DetectorConfig
from src.the_curved_world.gameplay import ExplorationGame
from src.the_curved_world.manifold import default_manifold
from src.the_curved_world.obstacles import Obstacle, ObstacleField
from src.the_curved_world.world import WorldGenerator, WorldState


def _game(seed: int = 12345) -> ExplorationGame:
    return ExplorationGame(WorldGenerator(default_config()).generate(seed))


def test_frame_is_orthonormal() -> None:
    game = _game()
    frame = game.frame()
    forward = np.asarray(frame["forward"])
    right = np.asarray(frame["right"])
    up = np.asarray(frame["up"])

    assert np.linalg.norm(forward) == pytest.approx(1.0, abs=1e-9)
    assert np.linalg.norm(right) == pytest.approx(1.0, abs=1e-9)
    assert np.linalg.norm(up) == pytest.approx(1.0, abs=1e-9)
    assert forward @ up == pytest.approx(0.0, abs=1e-9)
    assert right @ up == pytest.approx(0.0, abs=1e-9)
    assert forward @ right == pytest.approx(0.0, abs=1e-9)


def test_up_axis_is_the_surface_normal() -> None:
    world = WorldGenerator(default_config()).generate(3)
    game = ExplorationGame(world)
    normal = np.asarray(world.surface.normal(*game.position), dtype=float)
    assert np.allclose(np.asarray(game.frame()["up"]), normal, atol=1e-9)


def test_turning_wraps_the_heading() -> None:
    game = _game()
    assert game.yaw == pytest.approx(0.0)
    game.turn(0.5)
    assert game.yaw == pytest.approx(0.5)
    game.turn(10.0)
    assert -math.pi <= game.yaw < math.pi


def test_turning_rotates_the_frame() -> None:
    game = _game()
    before = np.asarray(game.frame()["forward"], dtype=float)
    game.turn(math.pi / 2)
    after = np.asarray(game.frame()["forward"], dtype=float)
    assert float(before @ after) == pytest.approx(0.0, abs=1e-6)
    assert not np.allclose(before, after)


def test_relative_moves_change_position_and_stay_on_the_surface() -> None:
    world = WorldGenerator(default_config()).generate(11)
    game = ExplorationGame(world)
    surface = game.player_view.surface
    start = game.position

    result = game.move_relative("forward", steps=3)
    assert result.moved is True
    assert game.position != start
    u, v = game.position
    assert -math.pi <= u < math.pi
    assert -math.pi <= v < math.pi
    assert bool(surface.contains(u, v)) is True


def test_forward_and_backward_are_opposite() -> None:
    world = WorldGenerator(default_config()).generate(11)
    game = ExplorationGame(world)
    surface = game.player_view.surface
    start = game.position
    forward_point = np.asarray(surface.position(*start), dtype=float)

    game.move_relative("forward", steps=2)
    game.move_relative("backward", steps=2)
    back_point = np.asarray(surface.position(*game.position), dtype=float)
    # two steps out and two steps back land near the original surface point
    assert float(np.linalg.norm(back_point - forward_point)) < 12.0


def test_strafe_is_perpendicular_to_forward() -> None:
    game = _game()
    frame = game.frame()
    forward = np.asarray(frame["forward"])
    right = np.asarray(frame["right"])
    assert forward @ right == pytest.approx(0.0, abs=1e-9)


def test_obstacle_blocks_the_step_and_reports_it() -> None:
    surface = default_manifold()
    start = (0.0, 0.0)
    game = ExplorationGame(WorldState(
        surface=surface, seed=0, start=start, exit=(2.0, 2.0),
        detector=Detector(surface.position(2.0, 2.0), DetectorConfig(12.0)),
    ))
    step = game.step_length
    target = (start[0] + step, start[1])
    point = surface.position(*target)
    field = ObstacleField(surface, [Obstacle(
        id=0, u=target[0], v=target[1],
        position_3d=(float(point[0]), float(point[1]), float(point[2])),
        radius=1.0, kind="boulder",
    )])
    game = ExplorationGame(WorldState(
        surface=surface, seed=0, start=start, exit=(2.0, 2.0),
        detector=Detector(surface.position(2.0, 2.0), DetectorConfig(12.0)),
        obstacles=field,
    ))

    assert not field.check_collision(*start, game.config.player_radius)
    result = game.move(1.0, 0.0)
    assert result.collided is True
    assert not field.check_collision(*game.position, game.config.player_radius)


def test_unknown_relative_direction_raises() -> None:
    game = _game()
    from src.the_curved_world.gameplay import GameError

    with pytest.raises(GameError):
        game.move_relative("sideways")