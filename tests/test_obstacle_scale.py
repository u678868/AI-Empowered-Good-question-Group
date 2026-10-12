"""Task 16: enlarged obstacle footprints stay fair and deterministic.

The Task 16 tuning doubles-to-triples the obstacle radius and widens the safe
margin around the start / hidden exit. These tests pin the new scale and verify
that the placement stage still succeeds and still keeps both anchors clear on
every built-in map.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.the_curved_world.config import default_config
from src.the_curved_world.maps import MapRegistry, world_config_for
from src.the_curved_world.world import WorldGenerator


# The Task 16 per-map obstacle scale (ambient world units).
EXPECTED_RADIUS = {
    "torus_genus1": 4.2,
    "ellipsoid_genus0": 2.4,
    "double_torus": 4.5,
    "klein_bottle": 4.5,
    "planar_landscape": 4.5,
    # Task 18 maps
    "knot_garden": 3.0,
    "klein_bottle_traditional": 3.2,
    "elliptic_curve": 4.0,
    "projective_plane": 3.0,
}


def test_builtin_maps_use_larger_obstacle_footprints() -> None:
    for map_id, expected in EXPECTED_RADIUS.items():
        config = world_config_for(map_id)
        assert config.obstacle_radius == pytest.approx(expected)
        assert config.obstacle_safe_margin >= 12.0
    # the generic default config shares the larger baseline too
    base = default_config()
    assert base.obstacle_radius >= 4.0
    assert base.obstacle_safe_margin >= 12.0


def test_enlarged_obstacles_keep_start_and_exit_clear() -> None:
    for map_id in MapRegistry.ids():
        config = world_config_for(map_id)
        for seed in range(4):
            world = WorldGenerator(config).generate(seed)
            assert len(world.obstacles) == config.obstacle_count
            start = np.asarray(world.start_position, dtype=float)
            exit_point = np.asarray(world.exit_position(), dtype=float)
            for obstacle in world.obstacles:
                point = np.asarray(obstacle.position_3d, dtype=float)
                assert float(np.linalg.norm(point - start)) >= config.obstacle_safe_margin - 1e-6
                assert float(np.linalg.norm(point - exit_point)) >= config.obstacle_safe_margin - 1e-6