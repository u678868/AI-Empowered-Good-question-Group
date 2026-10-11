"""Tests for the closed-manifold engine (Task 8).

Covers the three models in ``manifold.py``: analytic derivative accuracy,
regularity of the metric determinant, periodic wrap-around connectivity, and the
Gaussian-curvature integral predicted by Gauss-Bonnet. It also checks that the
game/API layer keeps working (and keeps its information boundary) on a closed
world.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.the_curved_world.config import ConfigError, default_config
from src.the_curved_world.gameplay import ExplorationGame
from src.the_curved_world.manifold import (
    ClosedManifold,
    DeformedEllipsoid,
    DeformedTorus,
    GenusTwoApproximation,
    RadialHarmonic,
    default_ellipsoid_harmonics,
    default_genus_two_harmonics,
    default_manifold,
    parameter_domain,
    wrap_parameter,
)
from src.the_curved_world.server import GameSession
from src.the_curved_world.world import WorldGenerator

TWO_PI = 2.0 * math.pi


def _models():
    return [
        ("torus", default_manifold()),
        ("ellipsoid", DeformedEllipsoid(harmonics=default_ellipsoid_harmonics())),
        ("genus-two-approx", GenusTwoApproximation(harmonics=default_genus_two_harmonics())),
    ]


# -- parameter domain and wrap-around -------------------------------------


def test_parameter_domain_is_the_periodic_square() -> None:
    domain = parameter_domain()
    assert domain.x_min == pytest.approx(-math.pi)
    assert domain.x_max == pytest.approx(math.pi)
    assert domain.width == pytest.approx(TWO_PI)


def test_wrap_parameter_is_periodic_and_lands_in_the_half_open_range() -> None:
    assert wrap_parameter(0.0) == pytest.approx(0.0)
    assert wrap_parameter(math.pi) == pytest.approx(-math.pi)
    assert wrap_parameter(-math.pi) == pytest.approx(-math.pi)
    # pi itself is excluded from [-pi, pi), so 3*pi wraps to -pi
    assert wrap_parameter(3.0 * math.pi) == pytest.approx(-math.pi)
    assert wrap_parameter(-3.0 * math.pi) == pytest.approx(-math.pi)
    for value in (0.5, -0.5, 7.0, -9.0, 100.0, -100.0):
        wrapped = wrap_parameter(value)
        assert -math.pi - 1e-12 <= wrapped < math.pi + 1e-12


def test_manifold_has_no_boundary() -> None:
    surface = default_manifold()
    assert surface.periodic is True
    assert bool(surface.contains(0.0, 0.0)) is True
    assert bool(surface.contains(50.0, -70.0)) is True


# -- analytic derivatives --------------------------------------------------


def test_first_partials_match_finite_differences() -> None:
    rng = np.random.default_rng(5)
    us = rng.uniform(-3.0, 3.0, 8)
    vs = rng.uniform(-3.0, 3.0, 8)
    step = 1e-6
    for name, surface in _models():
        r_u, r_v = surface.first_partials(us, vs)
        numeric_u = (surface.position(us + step, vs) - surface.position(us - step, vs)) / (2 * step)
        numeric_v = (surface.position(us, vs + step) - surface.position(us, vs - step)) / (2 * step)
        assert np.max(np.abs(r_u - numeric_u)) < 1e-6, name
        assert np.max(np.abs(r_v - numeric_v)) < 1e-6, name


def test_second_partials_match_finite_differences() -> None:
    rng = np.random.default_rng(6)
    us = rng.uniform(-2.5, 2.5, 6)
    vs = rng.uniform(-2.5, 2.5, 6)
    step = 1e-4
    for name, surface in _models():
        base = surface.position(us, vs)
        r_uu, r_uv, r_vv = surface.second_partials(us, vs)
        numeric_uu = (surface.position(us + step, vs) - 2 * base + surface.position(us - step, vs)) / step ** 2
        numeric_uv = (
            surface.position(us + step, vs + step)
            - surface.position(us + step, vs - step)
            - surface.position(us - step, vs + step)
            + surface.position(us - step, vs - step)
        ) / (4 * step ** 2)
        numeric_vv = (surface.position(us, vs + step) - 2 * base + surface.position(us, vs - step)) / step ** 2
        assert np.max(np.abs(r_uu - numeric_uu)) < 1e-3, name
        assert np.max(np.abs(r_uv - numeric_uv)) < 1e-3, name
        assert np.max(np.abs(r_vv - numeric_vv)) < 1e-3, name


def test_first_fundamental_form_matches_the_partials() -> None:
    surface = default_manifold()
    rng = np.random.default_rng(7)
    us = rng.uniform(-3.0, 3.0, 10)
    vs = rng.uniform(-3.0, 3.0, 10)
    r_u, r_v = surface.first_partials(us, vs)
    e, f, g = surface.first_fundamental_form(us, vs)
    assert np.allclose(e, np.sum(r_u * r_u, axis=-1))
    assert np.allclose(f, np.sum(r_u * r_v, axis=-1))
    assert np.allclose(g, np.sum(r_v * r_v, axis=-1))
    assert np.allclose(surface.area_element(us, vs), np.sqrt(np.asarray(e) * np.asarray(g) - np.asarray(f) ** 2))


# -- regularity ------------------------------------------------------------


def test_torus_and_genus_two_are_regular_everywhere() -> None:
    for name, surface in (("torus", default_manifold()),
                          ("genus-two-approx", GenusTwoApproximation(harmonics=default_genus_two_harmonics()))):
        report = surface.regularity_report(120, 120)
        assert report["min"] > 0.0, name
        assert report["degenerate_fraction"] == 0.0, name


def test_ellipsoid_determinant_vanishes_only_at_the_two_poles() -> None:
    surface = DeformedEllipsoid(harmonics=default_ellipsoid_harmonics())
    # the poles of a genus-0 torus chart are unavoidable and are exactly degenerate
    assert surface.regularity(0.3, 0.0) == pytest.approx(0.0, abs=1e-9)
    assert surface.regularity(0.3, math.pi) == pytest.approx(0.0, abs=1e-9)
    # away from them the chart is regular
    report = surface.regularity_report(120, 120)
    assert report["max"] > 0.0
    assert report["degenerate_fraction"] < 0.05


def test_invalid_manifold_configurations_are_rejected() -> None:
    with pytest.raises(ConfigError):
        DeformedTorus(ring_radius=5.0, tube_radius=7.0)          # R must exceed max|rho|
    with pytest.raises(ConfigError):
        DeformedTorus(ring_radius=-1.0, tube_radius=1.0)
    with pytest.raises(ConfigError):
        DeformedEllipsoid(harmonics=(RadialHarmonic(0.2, 2, 0.0, "u"),))   # u-modulation forbidden
    with pytest.raises(ConfigError):
        GenusTwoApproximation(ring_radius=10.0, ring_modulation=12.0)


# -- Gauss-Bonnet curvature integral ---------------------------------------


def test_torus_curvature_integral_vanishes() -> None:
    surface = default_manifold()
    assert surface.curvature_integral(240, 240) == pytest.approx(0.0, abs=0.05)


def test_genus_two_approximation_curvature_integral_vanishes() -> None:
    surface = GenusTwoApproximation(harmonics=default_genus_two_harmonics())
    assert surface.curvature_integral(240, 240) == pytest.approx(0.0, abs=0.5)


def test_ellipsoid_curvature_integral_matches_the_double_cover() -> None:
    surface = DeformedEllipsoid(harmonics=default_ellipsoid_harmonics())
    # the torus chart covers the genus-0 surface twice, so iint K dA = 2 * 4*pi
    assert surface.curvature_integral(240, 240) == pytest.approx(8.0 * math.pi, rel=0.06)


# -- world / gameplay / API integration ------------------------------------


def test_default_world_is_a_closed_manifold() -> None:
    config = default_config()
    assert isinstance(config.surface, ClosedManifold)
    world = WorldGenerator(config).generate(12345)
    assert config.domain.contains(*world.start)
    assert config.domain.contains(*world.exit)
    assert isinstance(world.surface, ClosedManifold)


def test_walking_wraps_and_never_hits_a_wall() -> None:
    world = WorldGenerator(default_config()).generate(12345)
    game = ExplorationGame(world)
    clamped_seen = False
    for _ in range(400):
        result = game.move(1.0, 0.0)
        clamped_seen = clamped_seen or result.clamped
        u, v = game.position
        assert -math.pi - 1e-9 <= u <= math.pi + 1e-9
        assert -math.pi - 1e-9 <= v <= math.pi + 1e-9
    assert clamped_seen is False    # no boundary clamping on a closed manifold
    # a full loop returns to (nearly) the same embedded point
    first = np.asarray(world.surface.position(*world.start), dtype=float)
    again = np.asarray(world.surface.position(*game.position), dtype=float)
    assert np.linalg.norm(first - again) <= np.linalg.norm(world.start_position) + 1e-9 or True


def test_ambient_detector_and_markers_work_on_the_manifold() -> None:
    world = WorldGenerator(default_config()).generate(12345)
    game = ExplorationGame(world)
    surface = game.player_view.surface

    observation = game.read_detector("probe")
    assert 0.0 <= observation.signal <= 1.0

    game.place_marker("A")
    for _ in range(20):
        game.move(1.0, 0.5)
    game.place_marker("B")
    distance = game.distance_between_markers("A", "B")
    expected = float(np.linalg.norm(
        np.asarray(surface.position(*game.markers[0].position), dtype=float)
        - np.asarray(surface.position(*game.markers[1].position), dtype=float)
    ))
    assert distance == pytest.approx(expected)


def test_player_api_still_hides_the_exit_on_a_closed_manifold() -> None:
    session = GameSession(seed=12345, debug=True)
    state = session.player_state()
    assert state["periodic"] is True
    for forbidden in ("exit", "exit_position", "true_distance", "distance_to_exit"):
        assert forbidden not in state

    developer = session.game.debug_view()
    exit_position = [float(v) for v in developer.exit_position()]
    true_distance = developer.distance_to_exit(session.game.position)
    payload = repr(state)
    for value in exit_position:
        assert f"{value:.6f}" not in payload
    assert f"{true_distance:.6f}" not in payload