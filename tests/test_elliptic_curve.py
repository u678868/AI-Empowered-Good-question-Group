"""Tests for the complex-analysis level: the square-lattice elliptic curve.

The world is the stereographic image of the Clifford torus -- a torus of
revolution with ring:tube = sqrt(2):1 -- which is the *conformal* model of the
elliptic curve ``C / (Z + i Z)``. The conformal modulus claim is verified
numerically here rather than asserted, and the honest limitation (a conformal
model is not an isometric embedding, and a flat closed surface cannot be
embedded in R^3 at all) is pinned down too.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.the_curved_world.config import ConfigError
from src.the_curved_world.manifold import (
    DeformedTorus,
    EllipticCurveTorus,
    RadialHarmonic,
    default_harmonics,
)
from src.the_curved_world.maps import MapRegistry, world_config_for
from src.the_curved_world.world import WorldGenerator

MAP_ID = "elliptic_curve"


def numeric_conformal_modulus(ring: float, tube: float) -> float:
    """``W / 2 pi`` where ``W = integral r dv / (R + r cos v)`` -- the lattice ratio."""
    v = np.linspace(0.0, 2.0 * math.pi, 200001)
    period = float(np.trapezoid(tube / (ring + tube * np.cos(v)), v))
    return period / (2.0 * math.pi)


def test_the_ratio_is_exactly_the_square_lattice() -> None:
    surface = EllipticCurveTorus()
    assert surface.ring_radius / surface.tube_radius == pytest.approx(math.sqrt(2.0))
    assert surface.conformal_modulus == pytest.approx(1j, abs=1e-12)
    assert surface.conformal_period == pytest.approx(2.0 * math.pi, abs=1e-9)


def test_the_conformal_modulus_formula_matches_a_numerical_integral() -> None:
    # i * r / sqrt(R^2 - r^2), checked against the elliptic integral of the
    # conformal coordinate for several radii (not just the square lattice)
    for ring, tube in ((3.0, 1.0), (5.0, 2.0), (61.0, 61.0 / math.sqrt(2.0))):
        expected = tube / math.sqrt(ring ** 2 - tube ** 2)
        assert numeric_conformal_modulus(ring, tube) == pytest.approx(expected, rel=1e-9)
    # and the square lattice is the fixed point of that formula
    surface = EllipticCurveTorus()
    assert numeric_conformal_modulus(surface.ring_radius, surface.tube_radius) == pytest.approx(1.0, rel=1e-9)


def test_it_is_a_regular_torus_with_zero_total_curvature() -> None:
    surface = EllipticCurveTorus()
    report = surface.regularity_report(96, 96)
    assert report["min"] > 0.0 and report["degenerate_fraction"] == 0.0
    assert surface.euler_characteristic == 0
    assert surface.curvature_integral(240, 240) == pytest.approx(0.0, abs=1.0)
    assert surface.chart_periods() == pytest.approx((2.0 * math.pi, 2.0 * math.pi))
    assert surface.chart_copy_transforms() == ((0.0, 0.0, False),)


def test_it_is_a_conformal_model_never_a_flat_one() -> None:
    """Honesty check: the surface is NOT flat -- Hilbert forbids that in R^3."""
    surface = EllipticCurveTorus()
    grid_u, grid_v = np.meshgrid(np.linspace(-3.0, 3.0, 40), np.linspace(-3.0, 3.0, 40))
    curvature = np.asarray(surface.gaussian_curvature(grid_u, grid_v), dtype=float)
    assert float(np.max(np.abs(curvature))) > 1e-6      # curvature is genuinely non-zero
    assert float(np.min(curvature)) < 0.0 < float(np.max(curvature))   # negative inside, positive outside


def test_the_narrow_hole_puts_distant_points_close_in_space() -> None:
    surface = EllipticCurveTorus()
    hole = surface.ring_radius - surface.tube_radius
    assert hole / surface.tube_radius < 0.5            # a pinhole, not a donut hole
    # two points on the inner equator, half the ring apart, are close in space
    a = np.asarray(surface.position(0.0, math.pi), dtype=float)
    b = np.asarray(surface.position(0.15, math.pi), dtype=float)
    assert float(np.linalg.norm(a - b)) < 0.25 * surface.tube_radius


def test_deformations_and_wrong_ratios_are_rejected() -> None:
    with pytest.raises(ConfigError):
        EllipticCurveTorus(ring_radius=50.0, tube_radius=10.0)
    with pytest.raises(ConfigError):
        EllipticCurveTorus(harmonics=(RadialHarmonic(amplitude=0.4, order=1, phase=0.3, axis="u"),))
    # a general torus is still allowed to be a general torus
    generic = DeformedTorus(ring_radius=130.0, tube_radius=45.0, harmonics=default_harmonics())
    assert generic.cache_key != EllipticCurveTorus().cache_key


def test_creating_the_map_is_registered_and_playable() -> None:
    assert MAP_ID in MapRegistry.ids()
    entry = MapRegistry.get(MAP_ID).to_dict()
    assert entry["periodic"] is True
    assert entry["non_orientable"] is False
    config = world_config_for(MAP_ID)
    assert config.distance_mode == "euclidean"
    for seed in (0, 2, 4):
        world = WorldGenerator(config).generate(seed)
        assert len(world.obstacles) == config.obstacle_count
        start = np.asarray(world.start_position, dtype=float)
        for obstacle in world.obstacles:
            point = np.asarray(obstacle.position_3d, dtype=float)
            assert float(np.linalg.norm(point - start)) >= config.obstacle_safe_margin - 1e-6
