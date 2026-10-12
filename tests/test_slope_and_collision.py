"""Tests for eye height, slope penalty and obstacle sliding (Task 11)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.the_curved_world.config import default_config
from src.the_curved_world.gameplay import ExplorationGame
from src.the_curved_world.manifold import (
    DeformedEllipsoid,
    DeformedTorus,
    GenusTwoApproximation,
    default_ellipsoid_harmonics,
    default_genus_two_harmonics,
    default_harmonics,
    default_manifold,
)
from src.the_curved_world.obstacles import Obstacle, ObstacleField
from src.the_curved_world.world import WorldGenerator


def _game(seed: int = 12345) -> ExplorationGame:
    return ExplorationGame(WorldGenerator(default_config()).generate(seed))


# -- anti-clipping eye height ----------------------------------------------


def test_camera_is_lifted_along_the_outward_normal() -> None:
    world = WorldGenerator(default_config()).generate(5)
    game = ExplorationGame(world)
    surface = game.player_view.surface
    u, v = game.position
    point = np.asarray(surface.position(u, v), dtype=float)
    normal = np.asarray(surface.normal(u, v), dtype=float)
    camera = game.camera_position()

    offset = camera - point
    assert float(offset @ normal) == pytest.approx(game.eye_height)
    assert game.eye_height > 0.0
    assert float(np.linalg.norm(offset)) >= game.eye_height - 1e-9


def test_eye_height_must_be_positive() -> None:
    from src.the_curved_world.config import ConfigError
    from src.the_curved_world.gameplay import GameplayConfig

    with pytest.raises(ConfigError):
        GameplayConfig(eye_height=0.0)
    with pytest.raises(ConfigError):
        GameplayConfig(eye_height=-1.0)


def test_project_to_tangent_removes_the_normal_component() -> None:
    world = WorldGenerator(default_config()).generate(5)
    game = ExplorationGame(world)
    normal = np.asarray(world.surface.normal(*game.position), dtype=float)
    projected = game.project_to_tangent(normal * 3.0 + np.array([1.0, 0.0, 0.0]))
    assert float(projected @ normal) == pytest.approx(0.0, abs=1e-9)


# -- outward normals --------------------------------------------------------


def test_normals_point_outward_for_every_model() -> None:
    cases = [
        (DeformedTorus(ring_radius=30.0, tube_radius=10.0, harmonics=default_harmonics()),
         lambda u, v: np.array([30.0 * np.cos(v), 30.0 * np.sin(v), 0.0])),
        (DeformedEllipsoid(harmonics=default_ellipsoid_harmonics()), lambda u, v: np.zeros(3)),
    ]
    for surface, reference in cases:
        for u in np.linspace(-3.0, 3.0, 7):
            for v in np.linspace(-3.0, 3.0, 7):
                point = np.asarray(surface.position(u, v), dtype=float)
                normal = np.asarray(surface.normal(u, v), dtype=float)
                assert float(normal @ (point - reference(u, v))) > 0.0, surface.name

    # Model C is a two-hole *look* approximation whose image is not a clean
    # embedding, so we only require a well-defined unit normal there.
    approx = GenusTwoApproximation(harmonics=default_genus_two_harmonics())
    for u in np.linspace(-3.0, 3.0, 5):
        for v in np.linspace(-3.0, 3.0, 5):
            normal = np.asarray(approx.normal(u, v), dtype=float)
            assert np.linalg.norm(normal) == pytest.approx(1.0, abs=1e-9)


# -- slope penalty ----------------------------------------------------------


def test_slope_penalty_matches_the_formula() -> None:
    game = _game()
    kappa = game.config.slope_damping
    directions = [(0.25, 0.0), (0.0, 0.25), (0.2, -0.2), (-0.3, 0.1), (0.1, 0.24)]
    slopes = []
    for du, dv in directions:
        report = game.calculate_slope_penalty(game.position[0], game.position[1], du, dv)
        slopes.append(report["slope"])
        if report["slope"] > 0.0:
            expected = 1.0 / (1.0 + kappa * report["slope"] ** 2)
            assert report["speed_scale"] == pytest.approx(expected)
            assert 0.0 < report["speed_scale"] < 1.0
        else:
            assert report["speed_scale"] == pytest.approx(1.0)
    assert any(s > 0.0 for s in slopes)


def test_uphill_step_is_actually_shorter() -> None:
    game = _game()
    best_angle = None
    best_slope = -1e9
    for index in range(64):
        angle = index * math.pi / 32.0
        report = game.calculate_slope_penalty(
            game.position[0], game.position[1], 0.25 * math.cos(angle), 0.25 * math.sin(angle)
        )
        if report["slope"] > best_slope:
            best_slope = report["slope"]
            best_angle = angle
    assert best_slope > 0.0

    before = game.position
    result = game.move(math.cos(best_angle), math.sin(best_angle))
    assert result.moved is True
    travelled = math.hypot(game.position[0] - before[0], game.position[1] - before[1])
    assert travelled <= game.step_length + 1e-9
    assert game.last_slope["speed_scale"] < 1.0


def test_downhill_and_flat_are_not_penalised() -> None:
    game = _game()
    downhill_seen = False
    for index in range(64):
        angle = index * math.pi / 32.0
        report = game.calculate_slope_penalty(
            game.position[0], game.position[1], 0.25 * math.cos(angle), 0.25 * math.sin(angle)
        )
        if report["slope"] <= 0.0:
            assert report["speed_scale"] == pytest.approx(1.0)
            downhill_seen = True
    assert downhill_seen


# -- obstacle sliding -------------------------------------------------------


def test_obstacle_sliding_does_not_penetrate() -> None:
    surface = default_manifold()
    start = (0.0, 0.0)
    target = (0.25, 0.0)
    start_point = np.asarray(surface.position(*start), dtype=float)
    target_point = np.asarray(surface.position(*target), dtype=float)

    # Obstacle centred on the target: the target penetrates, the start stays clear.
    clearance = float(np.linalg.norm(start_point - target_point))
    radius = clearance * 0.6
    field = ObstacleField(surface, [Obstacle(
        id=0, u=target[0], v=target[1],
        position_3d=(float(target_point[0]), float(target_point[1]), float(target_point[2])),
        radius=radius, kind="rock",
    )])

    assert field.check_collision(*start, 0.6) is False
    assert field.check_collision(*target, 0.6) is True

    resolved = field.resolve_collision(start, target, 0.6)
    assert resolved is not None
    assert field.check_collision(resolved[0], resolved[1], 0.6) is False
    # sliding keeps some motion (it does not simply snap back to the start)
    assert math.hypot(resolved[0] - start[0], resolved[1] - start[1]) > 0.0

def test_resolve_collision_returns_none_when_clear() -> None:
    surface = default_manifold()
    point = surface.position(1.0, 1.0)
    field = ObstacleField(surface, [Obstacle(0, 1.0, 1.0, tuple(point), 1.0, "pillar")])
    assert field.resolve_collision((0.0, 0.0), (0.05, 0.05), 0.6) is None


def test_sliding_move_reports_collision_and_keeps_the_player_outside() -> None:
    surface = default_manifold()
    start = (0.0, 0.0)
    target_uv = (0.25, 0.0)
    point = surface.position(*target_uv)
    field = ObstacleField(surface, [Obstacle(
        id=0, u=target_uv[0], v=target_uv[1],
        position_3d=(float(point[0]), float(point[1]), float(point[2])),
        radius=1.0, kind="rock",
    )])
    from src.the_curved_world.detector import Detector, DetectorConfig
    from src.the_curved_world.world import WorldState

    game = ExplorationGame(WorldState(
        surface=surface, seed=0, start=start, exit=(2.0, 2.0),
        detector=Detector(surface.position(2.0, 2.0), DetectorConfig(12.0)),
        obstacles=field,
    ))
    result = game.move(1.0, 0.0)
    assert result.collided is True
    assert not field.check_collision(*game.position, game.config.player_radius)