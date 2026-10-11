"""Tests for the large-scale manifold, metric tools and Gauss-Bonnet (Task 7)."""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.the_curved_world.config import default_config, default_domain, default_surface_config
from src.the_curved_world.detector import Detector, DetectorConfig
from src.the_curved_world.gameplay import ExplorationGame, GameError
from src.the_curved_world.geometry import SmoothSurface, ambient_distance
from src.the_curved_world.world import WorldGenerator, WorldState


def _go_to(game: ExplorationGame, x: float, y: float, max_steps: int = 400) -> None:
    for _ in range(max_steps):
        px, py = game.position
        dx, dy = x - px, y - py
        if math.hypot(dx, dy) < game.step_length * 0.25:
            break
        game.move(dx, dy)


# -- large-scale domain ----------------------------------------------------


def test_default_domain_is_large_scale() -> None:
    domain = default_domain()
    assert domain.width == pytest.approx(100.0)
    assert domain.height == pytest.approx(100.0)
    assert domain.contains(0.0, 0.0)
    assert not domain.contains(60.0, 0.0)


def test_surface_has_multi_scale_waves_and_mixed_hills() -> None:
    config = default_surface_config()
    assert len(config.wave_terms()) >= 3
    amplitudes = [hill.amplitude for hill in config.hills]
    assert any(value > 0 for value in amplitudes)
    assert any(value < 0 for value in amplitudes)


def test_large_world_places_start_and_exit_inside_and_separated() -> None:
    config = default_config()
    generator = WorldGenerator(config)
    for seed in range(12):
        world = generator.generate(seed)
        assert config.domain.contains(*world.start)
        assert config.domain.contains(*world.exit)
        separation = ambient_distance(world.start_position, world.exit_position())
        assert separation >= config.min_separation - 1e-6


def test_curvature_has_positive_clusters_and_negative_saddles() -> None:
    surface = SmoothSurface(default_surface_config())
    grid_x, grid_y, _ = surface.sample_grid(120, 120)
    curvature = np.asarray(surface.gaussian_curvature(grid_x, grid_y), dtype=float)
    assert np.isfinite(curvature).all()
    assert (curvature > 0.02).mean() > 0.05
    assert (curvature < -0.02).mean() > 0.05


def test_coordinates_are_clamped_inside_the_large_domain() -> None:
    surface = SmoothSurface(default_surface_config())  # planar large landscape
    detector = Detector(surface.position(25.0, 25.0), DetectorConfig(2.5))
    world = WorldState(surface=surface, seed=3, start=(2.0, 2.0), exit=(25.0, 25.0), detector=detector)
    game = ExplorationGame(world)
    domain = surface.domain

    result = None
    for _ in range(400):
        result = game.move(1.0, 0.0)
    assert result is not None and result.clamped
    assert game.position[0] == pytest.approx(domain.x_max)
    assert game.player_view.contains(game.position)

    for _ in range(900):
        game.move(-1.0, -1.0)
    x, y = game.position
    assert domain.contains(x, y)
    assert x == pytest.approx(domain.x_min)
    assert y == pytest.approx(domain.y_min)


def test_first_fundamental_form_is_consistent_with_the_area_element() -> None:
    surface = SmoothSurface(default_surface_config())
    rng = np.random.default_rng(11)
    xs = rng.uniform(-45.0, 45.0, 40)
    ys = rng.uniform(-45.0, 45.0, 40)
    grad_x, grad_y = surface.gradient(xs, ys)
    e, f, g = surface.first_fundamental_form(xs, ys)
    determinant = np.asarray(e) * np.asarray(g) - np.asarray(f) ** 2
    assert np.allclose(determinant, 1.0 + grad_x ** 2 + grad_y ** 2, atol=1e-9)
    assert np.allclose(surface.area_element(xs, ys), np.sqrt(determinant), atol=1e-9)


# -- Gauss-Bonnet triangle -------------------------------------------------


def test_triangle_report_agrees_with_the_curvature_area_integral() -> None:
    surface = SmoothSurface(default_surface_config())
    peak = default_surface_config().hills[0]
    centre_x, centre_y = peak.center_x, peak.center_y
    detector = Detector(surface.position(centre_x, centre_y + 25.0), DetectorConfig(2.5))
    world = WorldState(
        surface=surface, seed=7, start=(centre_x, centre_y),
        exit=(centre_x, centre_y + 25.0), detector=detector,
    )
    game = ExplorationGame(world)

    game.place_marker("A")
    _go_to(game, centre_x + 10.0, centre_y)
    game.place_marker("B")
    _go_to(game, centre_x, centre_y + 10.0)
    game.place_marker("C")

    report = game.triangle_report("A", "B", "C")
    excess = float(report["excess"])
    integral = float(report["curvature_integral"])

    # Gauss-Bonnet: iint_T K dA = sum(theta) - pi (exact for geodesic triangles).
    # Our angles live in tangent planes, so a larger triangle has a larger
    # residual; we require the same sign and the same order of magnitude.
    assert abs(excess - integral) < 0.3
    assert np.sign(excess) == np.sign(integral)
    assert report["samples"] > 10
    assert report["parameter_area"] > 0.0


def test_triangle_report_rejects_degenerate_markers() -> None:
    world = WorldGenerator(default_config()).generate(7)
    game = ExplorationGame(world)
    game.place_marker("A")
    game.move(1.0, 0.0)
    game.place_marker("B")
    game.move(-1.0, 0.0)
    game.place_marker("C")
    with pytest.raises(GameError):
        game.triangle_report("A", "B", "C")
    with pytest.raises(GameError):
        game.triangle_report("A", "B", "missing")


# -- limited-use tangent pointer ------------------------------------------


def test_pointer_is_limited_and_quantised() -> None:
    world = WorldGenerator(default_config()).generate(21)
    game = ExplorationGame(world)
    assert game.pointer_uses_remaining == game.config.max_pointer_uses

    hints = []
    for _ in range(game.config.max_pointer_uses):
        hints.append(game.release_pointer())
    assert game.pointer_uses_remaining == 0
    with pytest.raises(GameError):
        game.release_pointer()

    sector = 360.0 / game.config.pointer_sectors
    for hint in hints:
        bearing = float(hint["bearing_degrees"])
        pitch = float(hint["pitch_degrees"])
        assert -180.0 <= bearing <= 180.0
        assert abs(bearing / sector - round(bearing / sector)) < 1e-9
        assert abs(pitch) <= 90.0
        assert abs(pitch / 15.0 - round(pitch / 15.0)) < 1e-9
        direction = hint["tangent_direction"]
        assert math.isclose(math.hypot(direction[0], direction[1]), 1.0, rel_tol=1e-9)


def test_pointer_never_returns_exit_coordinates_or_distance() -> None:
    world = WorldGenerator(default_config()).generate(21)
    developer = world.debug_view()
    exit_position = [float(v) for v in developer.exit_position()]
    true_distance = developer.distance_to_exit(world.start)

    game = ExplorationGame(world)
    hint = game.release_pointer()
    allowed = {
        "bearing_degrees",
        "pitch_degrees",
        "tangent_direction",
        "sector_width_degrees",
        "uses_remaining",
        "kind",
    }
    assert set(hint) <= allowed
    for value in exit_position:
        assert f"{value:.6f}" not in repr(hint)
    assert f"{true_distance:.6f}" not in repr(hint)