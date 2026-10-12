"""Tests for the knotted-torus level (a tube around a (2,3) torus knot).

The knot is a property of the *embedding*: the tube around it is still an
ordinary torus, so Gauss-Bonnet still predicts ``iint K dA = 0``. What the
level changes is the gameplay -- strands pass close in R^3 while staying far
apart along the surface, so the ambient detector cannot tell them apart.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.the_curved_world.config import ConfigError
from src.the_curved_world.manifold import (
    DeformedTorus,
    KnottedTorus,
    _knot_strand_gap,
    default_harmonics,
)
from src.the_curved_world.maps import MapRegistry, world_config_for
from src.the_curved_world.world import WorldGenerator

MAP_ID = "knot_garden"


def _knot(**kwargs) -> KnottedTorus:
    params = dict(ring_radius=30.0, carrier_radius=10.0, knot_p=2, knot_q=3, tube_radius=8.0)
    params.update(kwargs)
    return KnottedTorus(**params)


def test_the_tube_is_a_regular_immersion() -> None:
    surface = _knot()
    report = surface.regularity_report(96, 96)
    assert report["min"] > 0.0
    assert report["degenerate_fraction"] == 0.0


def test_first_and_second_partials_are_analytic() -> None:
    surface = _knot()
    rng = np.random.default_rng(3)
    us = rng.uniform(-3.0, 3.0, 6)
    vs = rng.uniform(-3.0, 3.0, 6)
    step = 1e-6
    r_u, r_v = surface.first_partials(us, vs)
    assert np.max(np.abs(r_u - (surface.position(us + step, vs) - surface.position(us - step, vs)) / (2 * step))) < 1e-6
    assert np.max(np.abs(r_v - (surface.position(us, vs + step) - surface.position(us, vs - step)) / (2 * step))) < 1e-6

    step = 1e-4
    base = surface.position(us, vs)
    r_uu, r_uv, r_vv = surface.second_partials(us, vs)
    numeric_uu = (surface.position(us + step, vs) - 2 * base + surface.position(us - step, vs)) / step ** 2
    numeric_uv = (
        surface.position(us + step, vs + step) - surface.position(us + step, vs - step)
        - surface.position(us - step, vs + step) + surface.position(us - step, vs - step)
    ) / (4 * step ** 2)
    numeric_vv = (surface.position(us, vs + step) - 2 * base + surface.position(us, vs - step)) / step ** 2
    assert np.max(np.abs(r_uu - numeric_uu)) < 1e-3
    assert np.max(np.abs(r_uv - numeric_uv)) < 1e-3
    assert np.max(np.abs(r_vv - numeric_vv)) < 1e-3


def test_the_chart_is_the_plain_periodic_square() -> None:
    surface = _knot()
    assert surface.chart_periods() == pytest.approx((2.0 * math.pi, 2.0 * math.pi))
    assert surface.twisted is False
    assert surface.chart_copy_transforms() == ((0.0, 0.0, False),)
    rng = np.random.default_rng(4)
    us = rng.uniform(-3.0, 3.0, 5)
    vs = rng.uniform(-3.0, 3.0, 5)
    assert np.allclose(
        np.asarray(surface.position(us + 2.0 * math.pi, vs), dtype=float),
        np.asarray(surface.position(us, vs), dtype=float),
        atol=1e-9,
    )
    deform = DeformedTorus(ring_radius=130.0, tube_radius=45.0, harmonics=default_harmonics())
    assert surface.cache_key != deform.cache_key


def test_curvature_integral_vanishes_despite_the_knot() -> None:
    # a knot is an embedding, not a topology: the surface is still genus 1
    assert _knot().curvature_integral(200, 200) == pytest.approx(0.0, abs=0.5)
    assert _knot().euler_characteristic == 0
    assert _knot().orientable is True


def test_the_embedding_is_a_genuine_knot() -> None:
    """Different strands really do come close in R^3 while far in the chart."""
    surface = _knot()
    gap = _knot_strand_gap(surface.ring_radius, surface.carrier_radius, surface.knot_p, surface.knot_q)
    # the tightest place is where the strand leaves and re-enters the ring
    assert gap == pytest.approx(20.0, abs=0.05)
    assert 2.0 * surface.tube_radius < gap

    # the two strands' *surfaces* still come within ~12 units of each other while
    # being half the knot apart along the surface: at detector_scale 30 the
    # ambient reading barely changes between them, which is the whole puzzle
    anchor = np.asarray(surface.position(0.0, 2.5), dtype=float)
    closest = min(
        float(np.linalg.norm(np.asarray(surface.position(u, 2.5), dtype=float) - anchor))
        for u in np.linspace(-math.pi, math.pi, 2001)
        if abs(u) > 0.6
    )
    assert closest < 0.7 * gap
    # triangle inequality: two tubes of radius rho around centrelines d apart
    # cannot bring their surfaces closer than d - 2 rho
    assert closest > gap - 2.0 * surface.tube_radius
    assert closest < world_config_for(MAP_ID).detector_scale


def test_too_fat_a_tube_is_rejected() -> None:
    gap = _knot_strand_gap(30.0, 10.0, 2, 3)
    with pytest.raises(ConfigError):
        _knot(tube_radius=0.5 * gap + 0.5)
    with pytest.raises(ConfigError):
        _knot(knot_p=2, knot_q=4)          # a link, not a knot
    with pytest.raises(ConfigError):
        _knot(ring_radius=8.0, carrier_radius=10.0)
    with pytest.raises(ConfigError):
        _knot(tube_radius=-1.0)


def test_other_knot_types_work() -> None:
    for p, q, rho in ((3, 4, 5.0), (2, 5, 4.0)):
        surface = KnottedTorus(ring_radius=30.0, carrier_radius=10.0, knot_p=p, knot_q=q, tube_radius=rho)
        assert surface.regularity_report(48, 48)["min"] > 0.0
        assert surface.curvature_integral(160, 160) == pytest.approx(0.0, abs=1.0)
    # a (1,1) curve is the unknot: the level degenerates to a plain ring-like tube
    unknot = KnottedTorus(ring_radius=30.0, carrier_radius=10.0, knot_p=1, knot_q=1, tube_radius=6.0)
    assert unknot.regularity_report(48, 48)["min"] > 0.0
    assert unknot.surface_area(160, 160) > 0.0
    assert unknot.curvature_integral(160, 160) == pytest.approx(0.0, abs=1.0)


def test_the_map_is_registered_and_playable() -> None:
    assert MAP_ID in MapRegistry.ids()
    entry = MapRegistry.get(MAP_ID).to_dict()
    assert entry["periodic"] is True
    assert entry["non_orientable"] is False
    config = world_config_for(MAP_ID)
    assert config.distance_mode == "euclidean"
    for seed in (0, 1, 2, 5):
        world = WorldGenerator(config).generate(seed)
        assert len(world.obstacles) == config.obstacle_count
        start = np.asarray(world.start_position, dtype=float)
        exit_point = np.asarray(world.exit_position(), dtype=float)
        for obstacle in world.obstacles:
            point = np.asarray(obstacle.position_3d, dtype=float)
            assert float(np.linalg.norm(point - start)) >= config.obstacle_safe_margin - 1e-6
            assert float(np.linalg.norm(point - exit_point)) >= config.obstacle_safe_margin - 1e-6
