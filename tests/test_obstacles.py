"""Tests for the decoupled obstacle system (Task 10)."""

from __future__ import annotations

import math

import pytest

from src.the_curved_world.config import ConfigError, WorldConfig
from src.the_curved_world.detector import Detector, DetectorConfig
from src.the_curved_world.manifold import default_manifold
from src.the_curved_world.obstacles import (
    Obstacle,
    ObstacleField,
    periodic_parameter_distance,
)
from src.the_curved_world.world import WorldGenerator, WorldState

from src.the_curved_world.config import default_config


def test_generation_is_two_stage_and_deterministic() -> None:
    config = default_config()
    first = WorldGenerator(config).generate(12345)
    second = WorldGenerator(config).generate(12345)

    assert len(first.obstacles) == config.obstacle_count
    assert [o.to_dict() for o in first.obstacles] == [o.to_dict() for o in second.obstacles]

    # identical surface, independent of the obstacle stage
    assert first.surface.cache_key == second.surface.cache_key
    assert first.surface.height(0.3, -0.4) == second.surface.height(0.3, -0.4)


def test_different_seeds_scatter_differently() -> None:
    config = default_config()
    first = WorldGenerator(config).generate(1)
    second = WorldGenerator(config).generate(2)
    assert [o.to_dict() for o in first.obstacles] != [o.to_dict() for o in second.obstacles]


def test_start_and_exit_keep_a_safe_margin() -> None:
    config = default_config()
    for seed in range(6):
        world = WorldGenerator(config).generate(seed)
        field = world.obstacles
        start_point = world.start_position
        exit_point = world.exit_position()
        for obstacle in field.obstacles:
            point = [float(v) for v in obstacle.position_3d]
            assert float(((point[0] - start_point[0]) ** 2 + (point[1] - start_point[1]) ** 2 + (point[2] - start_point[2]) ** 2) ** 0.5) >= config.obstacle_safe_margin - 1e-6
            assert float(((point[0] - exit_point[0]) ** 2 + (point[1] - exit_point[1]) ** 2 + (point[2] - exit_point[2]) ** 2) ** 0.5) >= config.obstacle_safe_margin - 1e-6


def test_collision_detects_across_the_periodic_seam() -> None:
    surface = default_manifold()
    near_positive = (0.4, math.pi - 0.05)
    near_negative = (0.4, -math.pi + 0.05)
    point = surface.position(*near_positive)
    field = ObstacleField(
        surface,
        [Obstacle(id=0, u=near_positive[0], v=near_positive[1],
                  position_3d=(float(point[0]), float(point[1]), float(point[2])),
                  radius=4.0, kind="pillar")],
    )

    # 0.1 of parameter distance is ~3 units of ambient distance on this torus
    assert periodic_parameter_distance(near_positive[0], near_positive[1], near_negative[0], near_negative[1]) < 0.2
    assert field.check_collision(near_negative[0], near_negative[1], 0.5) is True
    assert field.check_collision(0.4, 0.0, 0.5) is False


def test_obstacles_near_is_bounded() -> None:
    world = WorldGenerator(default_config()).generate(4)
    field = world.obstacles
    near = field.obstacles_near(*world.start, 5.0)
    assert len(near) <= len(field)
    for obstacle in near:
        assert field.distance_to(world.start[0], world.start[1], obstacle) <= 5.0 + 1e-9


def test_obstacle_can_be_empty() -> None:
    surface = default_manifold()
    field = ObstacleField.generate(surface, default_config(), 1, exclude_points=())
    assert len(field) == default_config().obstacle_count
    empty = ObstacleField(surface, ())
    assert len(empty) == 0
    assert empty.check_collision(0.0, 0.0, 1.0) is False
    assert empty.obstacles_near(0.0, 0.0, 1e9) == []


def test_invalid_obstacle_config_is_rejected() -> None:
    config = default_config()
    with pytest.raises(ConfigError):
        WorldConfig(domain=config.domain, surface=config.surface, obstacle_count=-1)
    with pytest.raises(ConfigError):
        WorldConfig(domain=config.domain, surface=config.surface, obstacle_radius=0.0)
    with pytest.raises(ConfigError):
        WorldConfig(domain=config.domain, surface=config.surface, obstacle_safe_margin=-1.0)


def test_generator_places_obstacles_only_on_the_surface() -> None:
    world = WorldGenerator(default_config()).generate(7)
    surface = world.surface
    for obstacle in world.obstacles:
        expected = surface.position(obstacle.u, obstacle.v)
        assert float(((expected[0] - obstacle.position_3d[0]) ** 2 + (expected[1] - obstacle.position_3d[1]) ** 2 + (expected[2] - obstacle.position_3d[2]) ** 2) ** 0.5) < 1e-9