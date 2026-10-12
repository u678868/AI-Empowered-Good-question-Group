"""Tests for the Klein-bottle level (non-orientable closed world).

The Klein bottle cannot be embedded in R^3 at all, so this level ships an
*immersion*: it is regular (``E G - F^2 > 0`` everywhere), but it necessarily
passes through itself, and it is non-orientable, so no globally consistent
"outside" normal exists. Those are properties of the model, not bugs, so the
tests pin them down explicitly:

* the chart is a genuine immersion with exact analytic derivatives;
* ``r(u + 2 pi, v) = r(u, -v)`` -- a ``2 pi`` shift in ``u`` mirrors ``v`` and is
  therefore *not* the identity, which is why the chart publishes ``(4 pi, 2 pi)``;
* the self-intersection is real: ``r(u, 0) = r(u, pi)`` for every ``u``, with
  transverse tangent planes;
* the normal reverses along the ``u`` loop, so "outward" is a local notion here;
* Gauss-Bonnet still holds: ``chi = 0``, hence ``iint K dA = 0``;
* and the gameplay/API layers keep working, including their information boundary.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.the_curved_world.config import ConfigError
from src.the_curved_world.gameplay import ExplorationGame, GameError
from src.the_curved_world.manifold import (
    ClosedManifold,
    DeformedTorus,
    KleinBottle,
    default_harmonics,
)
from src.the_curved_world.maps import MapRegistry, world_config_for
from src.the_curved_world.server import GameSession
from src.the_curved_world.world import WorldGenerator

TWO_PI = 2.0 * math.pi
KLEIN_MAP_ID = "klein_bottle"


def _sample_points(count: int = 7, seed: int = 11):
    rng = np.random.default_rng(seed)
    return rng.uniform(-3.0, 3.0, count), rng.uniform(-3.0, 3.0, count)


# -- the chart is a regular immersion --------------------------------------


def test_the_chart_is_a_regular_immersion() -> None:
    surface = KleinBottle()
    report = surface.regularity_report(120, 120)
    assert report["min"] > 0.0
    assert report["degenerate_fraction"] == 0.0


def test_invalid_configurations_are_rejected() -> None:
    with pytest.raises(ConfigError):
        KleinBottle(ring_radius=0.0)
    with pytest.raises(ConfigError):
        KleinBottle(tube_radius=-3.0)


def test_first_partials_match_finite_differences() -> None:
    surface = KleinBottle()
    us, vs = _sample_points()
    step = 1e-6
    r_u, r_v = surface.first_partials(us, vs)
    numeric_u = (surface.position(us + step, vs) - surface.position(us - step, vs)) / (2 * step)
    numeric_v = (surface.position(us, vs + step) - surface.position(us, vs - step)) / (2 * step)
    assert np.max(np.abs(r_u - numeric_u)) < 1e-6
    assert np.max(np.abs(r_v - numeric_v)) < 1e-6


def test_second_partials_match_finite_differences() -> None:
    surface = KleinBottle()
    us, vs = _sample_points(6, seed=12)
    step = 1e-4
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
    assert np.max(np.abs(r_uu - numeric_uu)) < 1e-3
    assert np.max(np.abs(r_uv - numeric_uv)) < 1e-3
    assert np.max(np.abs(r_vv - numeric_vv)) < 1e-3


# -- honest topology: the twist, the self-intersection, the flipped normal --


def test_shift_by_two_pi_mirrors_v_instead_of_closing() -> None:
    surface = KleinBottle()
    us, vs = _sample_points(5, seed=13)
    shifted = np.asarray(surface.position(us + TWO_PI, vs), dtype=float)
    mirrored = np.asarray(surface.position(us, -vs), dtype=float)
    assert np.allclose(shifted, mirrored, atol=1e-9)
    # ... and it is genuinely not the identity, which is why the chart periods
    # are (4 pi, 2 pi) rather than the plain periodic square.
    assert not np.allclose(np.asarray(surface.position(us + TWO_PI, vs), dtype=float),
                           np.asarray(surface.position(us, vs), dtype=float), atol=1.0)
    assert surface.chart_periods() == pytest.approx((2.0 * TWO_PI, TWO_PI))


def test_the_self_intersection_circle_is_real() -> None:
    surface = KleinBottle()
    radius = surface.ring_radius
    for u in (0.0, 0.7, -2.1, 2.8):
        # two *different* surface points share one 3D position: the immersion
        # passes through itself along the circle of radius R in the z = 0 plane
        on_seam = np.asarray(surface.position(u, 0.0), dtype=float)
        on_other = np.asarray(surface.position(u, math.pi), dtype=float)
        assert np.allclose(on_seam, on_other, atol=1e-9)
        assert np.allclose(on_seam, [radius * math.cos(u), radius * math.sin(u), 0.0], atol=1e-9)
        # the crossing is transverse: the tangent planes disagree there
        r_u_a, r_v_a = surface.first_partials(u, 0.0)
        r_u_b, r_v_b = surface.first_partials(u, math.pi)
        normal_a = np.cross(np.asarray(r_u_a, dtype=float), np.asarray(r_v_a, dtype=float))
        normal_b = np.cross(np.asarray(r_u_b, dtype=float), np.asarray(r_v_b, dtype=float))
        cosine = abs(float(normal_a @ normal_b)) / (float(np.linalg.norm(normal_a)) * float(np.linalg.norm(normal_b)))
        assert cosine < 0.999


def test_the_normal_reverses_along_the_u_loop() -> None:
    surface = KleinBottle()
    us, vs = _sample_points(6, seed=14)
    # the same 3D point, reached through the twist, carries the opposite normal:
    # this is non-orientability made numerically explicit
    flipped = np.asarray(surface.normal(us + TWO_PI, vs), dtype=float)
    original = np.asarray(surface.normal(us, -vs), dtype=float)
    assert np.max(np.abs(flipped + original)) < 1e-9


def test_the_model_reports_itself_as_non_orientable() -> None:
    surface = KleinBottle()
    assert isinstance(surface, ClosedManifold)
    assert surface.periodic is True
    assert surface.orientable is False
    assert surface.twisted is True
    assert surface.euler_characteristic == 0
    assert bool(surface.contains(123.0, -456.0)) is True


def test_curvature_integral_vanishes() -> None:
    # Gauss-Bonnet for a closed surface: iint K dA = 2 pi * chi, and chi = 0 here
    surface = KleinBottle()
    assert surface.curvature_integral(240, 240) == pytest.approx(0.0, abs=0.05)


# -- chart bookkeeping across the seam -------------------------------------


def test_wrap_preserves_the_embedded_point_and_stays_in_the_window() -> None:
    surface = KleinBottle()
    period_u, period_v = surface.chart_periods()
    for u, v in ((7.0, 0.3), (-9.0, -2.0), (13.0, 3.0), (-TWO_PI - 0.4, 4.0)):
        wrapped_u, wrapped_v = surface.wrap(u, v)
        assert -period_u / 2 <= wrapped_u < period_u / 2
        assert -period_v / 2 <= wrapped_v < period_v / 2
        original = np.asarray(surface.position(u, v), dtype=float)
        wrapped = np.asarray(surface.position(wrapped_u, wrapped_v), dtype=float)
        assert np.linalg.norm(original - wrapped) < 1e-9


def test_wrap_crosses_the_seam_without_a_jump() -> None:
    surface = KleinBottle()
    for seam in (2.0 * math.pi, -2.0 * math.pi, 0.0):
        us = np.linspace(seam - 0.02, seam + 0.02, 41)
        points = np.array([surface.position(*surface.wrap(u, 0.7)) for u in us], dtype=float)
        steps = np.linalg.norm(np.diff(points, axis=0), axis=1)
        # one 1e-3 parameter step in u; |r_u| is O(100) here, so any wrapping
        # mistake (a mirrored or translated chart point) would show up as a jump
        # of order 10-100 instead of order 0.1
        assert steps.max() < 1.0


def test_chart_relative_finds_the_flipped_sheet() -> None:
    surface = KleinBottle()
    reference = (1.0, 0.5)
    twin = (1.0 + TWO_PI, -0.5)
    near_u, near_v = surface.chart_relative(reference[0], reference[1], twin[0], twin[1])
    assert (near_u, near_v) == pytest.approx(reference)
    # the result still denotes the same surface point
    assert np.linalg.norm(
        np.asarray(surface.position(*reference), dtype=float)
        - np.asarray(surface.position(*surface.wrap(*twin)), dtype=float)
    ) < 1e-9
    # and a genuinely distant point is not smuggled in
    far_u, far_v = surface.chart_relative(reference[0], reference[1], 1.0 + math.pi, 0.5)
    assert abs(far_u - reference[0]) > math.pi / 2.0


def test_plain_models_keep_the_periodic_square() -> None:
    torus = DeformedTorus(ring_radius=130.0, tube_radius=45.0, harmonics=default_harmonics())
    assert torus.chart_periods() == pytest.approx((TWO_PI, TWO_PI))
    assert torus.twisted is False
    assert torus.chart_copies(0.3, -0.4) == ((0.3, -0.4),)
    assert torus.wrap(7.0, 3.0) == pytest.approx((7.0 - TWO_PI, 3.0))


# -- registry, world generation, gameplay and API --------------------------


def test_the_map_is_registered_and_flagged_non_orientable() -> None:
    assert KLEIN_MAP_ID in MapRegistry.ids()
    metadata = MapRegistry.get(KLEIN_MAP_ID)
    entry = metadata.to_dict()
    assert entry["non_orientable"] is True
    assert entry["periodic"] is True
    surface = MapRegistry.create(KLEIN_MAP_ID)
    assert isinstance(surface, KleinBottle)


def test_world_generation_keeps_the_anchors_and_the_obstacles_apart() -> None:
    config = world_config_for(KLEIN_MAP_ID)
    for seed in range(4):
        world = WorldGenerator(config).generate(seed)
        assert len(world.obstacles) == config.obstacle_count
        start = np.asarray(world.start_position, dtype=float)
        exit_point = np.asarray(world.exit_position(), dtype=float)
        assert float(np.linalg.norm(exit_point - start)) >= config.min_separation - 1e-6
        for obstacle in world.obstacles:
            point = np.asarray(obstacle.position_3d, dtype=float)
            assert float(np.linalg.norm(point - start)) >= config.obstacle_safe_margin - 1e-6
            assert float(np.linalg.norm(point - exit_point)) >= config.obstacle_safe_margin - 1e-6


def test_walking_the_seam_never_teleports_the_player() -> None:
    config = world_config_for(KLEIN_MAP_ID)
    period_u, period_v = KleinBottle().chart_periods()

    # a generous bound on |r_u| / |r_v| over the whole chart
    probe = KleinBottle()
    grid_u, grid_v = np.meshgrid(np.linspace(-math.pi, math.pi, 120), np.linspace(-math.pi, math.pi, 120))
    r_u, r_v = probe.first_partials(grid_u, grid_v)
    speed_bound = 1.05 * max(
        float(np.max(np.linalg.norm(np.asarray(r_u, dtype=float), axis=-1))),
        float(np.max(np.linalg.norm(np.asarray(r_v, dtype=float), axis=-1))),
    )

    for direction in ((1.0, 0.0), (0.0, 1.0), (1.0, 1.0)):
        world = WorldGenerator(config).generate(12345)
        game = ExplorationGame(world)
        surface = game.player_view.surface
        previous = np.asarray(surface.position(*game.position), dtype=float)
        max_step = 0.0
        for _ in range(400):
            result = game.move(*direction)
            assert result.clamped is False
            assert result.moved is True
            current = np.asarray(surface.position(*game.position), dtype=float)
            max_step = max(max_step, float(np.linalg.norm(current - previous)))
            previous = current
            u, v = game.position
            assert -period_u / 2 - 1e-9 <= u < period_u / 2 + 1e-9
            assert -period_v / 2 - 1e-9 <= v < period_v / 2 + 1e-9
        assert max_step <= speed_bound * game.step_length + 1e-6


def test_player_api_keeps_the_information_boundary() -> None:
    session = GameSession(seed=12345, map_id=KLEIN_MAP_ID)
    state = session.player_state()
    assert state["periodic"] is True
    assert state["twisted"] is True
    assert state["orientable"] is False
    assert state["chart_periods"] == pytest.approx([2.0 * TWO_PI, TWO_PI])
    for forbidden in ("exit", "exit_position", "true_distance", "distance_to_exit"):
        assert forbidden not in state

    # debug is still gated behind god mode / --debug
    with pytest.raises(GameError):
        session.debug_state()

    session.reset_world(KLEIN_MAP_ID, 12345, "god")
    assert "exit_position" in session.debug_state()

    # the detached player surface cannot reach the exit either
    game = session.game
    assert not hasattr(game.player_view, "exit")
    assert not hasattr(game.player_view, "exit_position")
