"""Tests for the antipodal projective-plane level and its distance policy.

``RP^2`` is the sphere with antipodal points identified, so a single place has
two 3D realizations. Everything else in the engine measures plain Euclidean
distance between two realizations, which would be simply wrong here; this level
therefore switches on the ``orbit_min`` distance policy
(``WorldConfig.distance_mode``), and these tests pin down both the geometry and
the fact that every other map keeps the default policy untouched.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.the_curved_world.config import ConfigError, WorldConfig
from src.the_curved_world.gameplay import ExplorationGame
from src.the_curved_world.manifold import (
    DeformedEllipsoid,
    ProjectivePlane,
    RadialHarmonic,
    default_ellipsoid_harmonics,
)
from src.the_curved_world.maps import MapRegistry, world_config_for
from src.the_curved_world.world import WorldGenerator

MAP_ID = "projective_plane"


def test_both_identifications_hold() -> None:
    surface = ProjectivePlane()
    rng = np.random.default_rng(5)
    us = rng.uniform(-3.0, 3.0, 6)
    vs = rng.uniform(-3.0, 3.0, 6)
    point = np.asarray(surface.position(us, vs), dtype=float)
    # the chart double-covers the sphere ...
    assert np.allclose(np.asarray(surface.position(us + math.pi, -vs), dtype=float), point, atol=1e-9)
    # ... and the antipodal map is the world's second involution
    assert np.allclose(np.asarray(surface.position(us + math.pi, math.pi - vs), dtype=float), -point, atol=1e-9)
    assert np.allclose(np.asarray(surface.position(us, vs + math.pi), dtype=float), -point, atol=1e-9)


def test_the_chart_has_four_sheets_and_two_realizations() -> None:
    surface = ProjectivePlane()
    assert surface.chart_periods() == pytest.approx((2.0 * math.pi, 2.0 * math.pi))
    transforms = surface.chart_copy_transforms()
    assert len(transforms) == 4
    assert len(surface.chart_copies(0.83, -1.27)) == 4
    orbit = surface.orbit_positions(0.83, -1.27)
    assert len(orbit) == 2                                   # the two antipodes
    assert np.allclose(orbit[0], -orbit[1], atol=1e-9)
    assert surface.twisted is True
    assert surface.orientable is False
    assert surface.euler_characteristic == 1


def test_gauss_bonnet_over_the_double_covered_chart() -> None:
    surface = ProjectivePlane()
    # RP^2 has chi = 1, so its own integral is 2 pi; the chart covers the sphere
    # twice and the world twice, so the raw number is four world-copies: 8 pi.
    raw = surface.curvature_integral(240, 240)
    assert raw == pytest.approx(8.0 * math.pi, rel=0.01)
    assert raw / 4.0 == pytest.approx(2.0 * math.pi, rel=0.01)


def test_modulation_must_respect_the_quotient() -> None:
    with pytest.raises(ConfigError):
        ProjectivePlane(harmonics=(RadialHarmonic(amplitude=0.1, order=3, phase=math.pi / 2, axis="v"),))
    with pytest.raises(ConfigError):
        ProjectivePlane(harmonics=(RadialHarmonic(amplitude=0.1, order=2, phase=0.4, axis="v"),))
    with pytest.raises(ConfigError):
        ProjectivePlane(harmonics=(RadialHarmonic(amplitude=0.1, order=2, phase=math.pi / 2, axis="u"),))
    # the plain ellipsoid keeps its own (non-symmetric) modulation
    plain = DeformedEllipsoid(harmonics=default_ellipsoid_harmonics())
    assert plain.chart_copy_transforms() == ((0.0, 0.0, False),)


def test_the_world_distance_collapses_a_place_and_its_antipode() -> None:
    config = world_config_for(MAP_ID)
    assert config.distance_mode == "orbit_min"
    world = WorldGenerator(config).generate(12345)
    surface = world.surface

    u, v = world.exit
    twin = (u + math.pi, math.pi - v)
    assert world.ambient_distance((u, v), twin) == pytest.approx(0.0)
    # ... while the two realizations are genuinely far apart in space
    assert float(np.linalg.norm(surface.position(u, v) - surface.position(*twin))) > 40.0
    # the start is a place too: its own antipode is the same place
    start_twin = (world.start[0] + math.pi, math.pi - world.start[1])
    assert world.ambient_distance(world.start, start_twin) == pytest.approx(0.0)

    # the detector watches both realizations, so the reading matches
    readings = [world.detector.signal(surface.position(*chart)) for chart in ((u, v), twin)]
    assert readings[0] == pytest.approx(1.0)
    assert readings[1] == pytest.approx(readings[0])
    assert len(world.detector.targets) == 2

    # and the exit can be reached from either realization
    for chart in ((u, v), twin):
        game = ExplorationGame(world)
        game.sync_position(*chart)
        assert game.won is True


def test_markers_and_obstacles_respect_the_policy() -> None:
    config = world_config_for(MAP_ID)
    world = WorldGenerator(config).generate(7)
    surface = world.surface
    u, v = world.exit
    twin = (u + math.pi, math.pi - v)

    game = ExplorationGame(world)
    game.place_marker("A")
    game.sync_position(*twin)
    game.place_marker("B")
    # still the same place? No: A sits at the start, B at the exit's twin, so the
    # honest distance equals the start <-> exit distance.
    assert game.distance_between_markers("A", "B") == pytest.approx(
        world.ambient_distance(world.start, world.exit)
    )
    game.place_marker("C")
    game.sync_position(*twin)
    game.place_marker("D")
    assert game.distance_between_markers("C", "D") == pytest.approx(0.0)

    field = world.obstacles
    assert field.distance_mode == "orbit_min"
    for obstacle in field.obstacles:
        assert world.ambient_distance((obstacle.u, obstacle.v), world.start) >= config.obstacle_safe_margin - 1e-6
        assert world.ambient_distance((obstacle.u, obstacle.v), world.exit) >= config.obstacle_safe_margin - 1e-6


def test_the_policy_leaves_every_other_map_untouched() -> None:
    for map_id in MapRegistry.ids():
        config = world_config_for(map_id)
        if map_id == MAP_ID:
            assert config.distance_mode == "orbit_min"
            continue
        assert config.distance_mode == "euclidean"
        world = WorldGenerator(config).generate(11)
        assert len(world.detector.targets) == 1
        assert world.ambient_distance(world.start, world.exit) == pytest.approx(
            float(np.linalg.norm(world.start_position - world.exit_position()))
        )
    with pytest.raises(ConfigError):
        WorldConfig(domain=world_config_for("torus_genus1").domain, surface=MapRegistry.create("torus_genus1"), distance_mode="nonsense")


def test_the_map_is_registered_and_flagged() -> None:
    assert MAP_ID in MapRegistry.ids()
    entry = MapRegistry.get(MAP_ID).to_dict()
    assert entry["non_orientable"] is True
    assert entry["periodic"] is True
    for seed in (0, 1, 9):
        world = WorldGenerator(world_config_for(MAP_ID)).generate(seed)
        assert len(world.obstacles) == 20
