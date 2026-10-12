"""Tests for the traditional (bottle-shaped) Klein bottle level.

The published parametrisation is checked against a literal reference
implementation, and the topological bookkeeping it needs -- a *non-translation*
identification -- is checked numerically instead of being assumed.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.the_curved_world.config import ConfigError
from src.the_curved_world.manifold import BottleKleinBottle, KleinBottle
from src.the_curved_world.maps import MapRegistry, world_config_for
from src.the_curved_world.world import WorldGenerator

MAP_ID = "klein_bottle_traditional"


def reference(u, v):
    """The published bottle formula, written out literally."""
    c, s = np.cos(u), np.sin(u)
    x = -(2 / 15) * c * (3 * np.cos(v) - 30 * s + 90 * c ** 4 * s - 60 * c ** 6 * s + 5 * c * np.cos(v) * s)
    y = -(1 / 15) * s * (
        3 * np.cos(v) - 3 * c ** 2 * np.cos(v) - 48 * c ** 4 * np.cos(v) + 48 * c ** 6 * np.cos(v)
        - 60 * s + 5 * c * np.cos(v) * s - 5 * c ** 3 * np.cos(v) * s
        - 80 * c ** 5 * np.cos(v) * s + 80 * c ** 7 * np.cos(v) * s
    )
    z = (2 / 15) * (3 + 5 * c * s) * np.sin(v)
    return np.stack([x, y, z], axis=-1)


def test_chart_matches_the_published_formula() -> None:
    surface = BottleKleinBottle(scale=1.0)
    rng = np.random.default_rng(7)
    us = rng.uniform(0.0, 2.0 * math.pi, 8)
    vs = rng.uniform(0.0, 2.0 * math.pi, 8)
    mine = np.asarray(surface.position(2.0 * us, vs - 0.5 * math.pi), dtype=float)
    assert np.max(np.abs(mine - reference(us, vs))) < 1e-12
    scaled = BottleKleinBottle(scale=30.0)
    assert np.max(np.abs(np.asarray(scaled.position(2.0 * us, vs - 0.5 * math.pi), dtype=float)
                         - 30.0 * reference(us, vs))) < 1e-9


def test_the_identification_is_a_twist_not_a_translation() -> None:
    surface = BottleKleinBottle(scale=1.0)
    rng = np.random.default_rng(8)
    us = rng.uniform(-3.0, 3.0, 6)
    ws = rng.uniform(-3.0, 3.0, 6)
    # a 2 pi shift in U mirrors w ...
    twisted = np.asarray(surface.position(us + 2.0 * math.pi, ws), dtype=float)
    mirrored = np.asarray(surface.position(us, -ws), dtype=float)
    assert np.allclose(twisted, mirrored, atol=1e-9)
    assert not np.allclose(twisted, np.asarray(surface.position(us, ws), dtype=float), atol=1e-6)
    # ... so the translations are 4 pi and 2 pi, and the chart has two sheets
    assert surface.chart_periods() == pytest.approx((4.0 * math.pi, 2.0 * math.pi))
    assert surface.chart_copy_transforms() == ((0.0, 0.0, False), (2.0 * math.pi, 0.0, True))
    assert surface.twisted is True and surface.orientable is False
    copies = surface.chart_copies(0.7, 0.4)
    assert len(copies) == 2
    assert np.allclose(np.asarray(surface.position(*copies[0]), dtype=float),
                       np.asarray(surface.position(*copies[1]), dtype=float), atol=1e-9)
    assert len(surface.orbit_positions(0.7, 0.4)) == 1     # both sheets, one 3D point


def test_the_immersion_is_regular_and_bottle_shaped() -> None:
    surface = BottleKleinBottle(scale=30.0)
    report = surface.regularity_report(96, 96)
    assert report["min"] > 0.0
    assert report["degenerate_fraction"] == 0.0
    # the classic bottle: the neck passes through the body, so two far-apart
    # chart points share a 3D position
    a = np.asarray(surface.position(0.94, -1.47), dtype=float)
    b = np.asarray(surface.position(-1.13, -0.80), dtype=float)
    assert float(np.linalg.norm(a - b)) < 0.2
    assert abs(0.94 - (-1.13)) > 1.0


def test_curvature_integral_vanishes() -> None:
    surface = BottleKleinBottle(scale=30.0)
    assert surface.euler_characteristic == 0
    assert surface.curvature_integral(240, 240) == pytest.approx(0.0, abs=0.5)


def test_the_god_view_mesh_closes() -> None:
    """The mesh edges are identified, so the drawn bottle has no open seam."""
    surface = BottleKleinBottle(scale=1.0)
    ws = np.linspace(-0.5 * math.pi, 1.5 * math.pi, 60)
    first = np.array([surface.position(0.0, w) for w in ws], dtype=float)
    last = np.array([surface.position(2.0 * math.pi, w) for w in ws], dtype=float)
    mirrored = np.array([surface.position(0.0, -w) for w in ws], dtype=float)
    # the u = 2 pi edge is the u = 0 edge traversed with w reversed
    assert np.max(np.abs(last - mirrored)) < 1e-9
    assert np.max(np.abs(first - last)) > 0.1      # ... and it is NOT the trivial edge
    x, y, z = surface.sample_grid(120, 120)
    # the sampled w-range is a full period, so the v-edges close up exactly
    assert np.allclose(
        np.stack([x[0], y[0], z[0]], axis=-1), np.stack([x[-1], y[-1], z[-1]], axis=-1), atol=1e-9
    )


def test_invalid_scales_are_rejected() -> None:
    with pytest.raises(ConfigError):
        BottleKleinBottle(scale=0.0)
    with pytest.raises(ConfigError):
        BottleKleinBottle(scale=float("nan"))


def test_both_klein_immersions_are_distinct_levels() -> None:
    figure_eight = KleinBottle()
    traditional = BottleKleinBottle(scale=30.0)
    assert figure_eight.cache_key != traditional.cache_key
    assert figure_eight.chart_periods() == traditional.chart_periods()
    assert MAP_ID in MapRegistry.ids()
    entry = MapRegistry.get(MAP_ID).to_dict()
    assert entry["non_orientable"] is True
    assert "klein_bottle" in MapRegistry.ids()
    assert MapRegistry.get("klein_bottle").to_dict()["non_orientable"] is True


def test_the_map_is_playable() -> None:
    config = world_config_for(MAP_ID)
    assert config.distance_mode == "euclidean"
    for seed in (0, 3, 7):
        world = WorldGenerator(config).generate(seed)
        assert len(world.obstacles) == config.obstacle_count
        exit_point = np.asarray(world.exit_position(), dtype=float)
        for obstacle in world.obstacles:
            point = np.asarray(obstacle.position_3d, dtype=float)
            assert float(np.linalg.norm(point - exit_point)) >= config.obstacle_safe_margin - 1e-6
