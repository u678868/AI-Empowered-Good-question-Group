"""Mathematical audit for The Curved World (Task 4).

These are *numerical* checks over finite sample sets. They give strong evidence
of correctness on the tested configurations, but they do NOT prove global
smoothness for arbitrary user-supplied height functions. The built-in surface
family is smooth by construction because every term is C-infinity and the
partial derivatives are computed analytically (no numerical differentiation is
used at runtime).
"""

from __future__ import annotations

import numpy as np
import pytest

from src.the_curved_world.config import (
    ConfigError,
    Domain,
    WorldConfig,
    default_config,
    default_surface_config,
)
from src.the_curved_world.detector import Detector, DetectorConfig
from src.the_curved_world.gameplay import ExplorationGame, GameplayConfig
from src.the_curved_world.geometry import SmoothSurface, ambient_distance
from src.the_curved_world.render import PlotMode, build_scene
from src.the_curved_world.world import WorldGenerator


def test_analytic_gradient_matches_central_differences_on_a_sample() -> None:
    surface = SmoothSurface(default_surface_config())
    rng = np.random.default_rng(7)
    xs = rng.uniform(-3.0, 3.0, 120)
    ys = rng.uniform(-3.0, 3.0, 120)

    grad_x, grad_y = surface.gradient(xs, ys)
    step = 1e-6
    approx_x = (surface.height(xs + step, ys) - surface.height(xs - step, ys)) / (2 * step)
    approx_y = (surface.height(xs, ys + step) - surface.height(xs, ys - step)) / (2 * step)

    assert np.allclose(grad_x, approx_x, atol=1e-4)
    assert np.allclose(grad_y, approx_y, atol=1e-4)


def test_surface_is_finite_and_normals_are_unit_on_a_dense_grid() -> None:
    surface = SmoothSurface(default_surface_config())
    grid_x, grid_y, grid_z = surface.sample_grid(160, 160)

    assert np.all(np.isfinite(grid_z))
    assert np.all(surface.contains(grid_x, grid_y))
    normals = surface.normal(grid_x, grid_y)
    assert np.allclose(np.linalg.norm(normals, axis=-1), 1.0, atol=1e-12)


def test_detector_signal_matches_model_and_decreases_with_distance() -> None:
    detector = Detector(np.zeros(3), DetectorConfig(scale=2.5))
    distances = np.linspace(0.0, 8.0, 60)
    signals = [detector.signal(np.array([d, 0.0, 0.0])) for d in distances]

    assert all(0.0 < value <= 1.0 for value in signals)
    assert all(later < earlier for earlier, later in zip(signals, signals[1:]))
    for distance, value in zip(distances, signals):
        assert value == pytest.approx(float(np.exp(-distance / 2.5)))


def test_start_and_exit_are_inside_the_domain_for_many_seeds() -> None:
    config = default_config()
    generator = WorldGenerator(config)
    for seed in range(30):
        world = generator.generate(seed)
        assert config.domain.contains(*world.start)
        assert config.domain.contains(*world.exit)
        separation = ambient_distance(world.start_position, world.exit_position())
        assert separation >= config.min_separation - 1e-9


def test_player_stays_on_the_surface_during_a_random_walk() -> None:
    world = WorldGenerator(default_config()).generate(2024)
    game = ExplorationGame(world)
    surface = game.player_view.surface
    rng = np.random.default_rng(0)

    for _ in range(200):
        dx, dy = rng.uniform(-1.0, 1.0, 2)
        game.move(float(dx), float(dy))
        x, y = game.position
        assert surface.contains(x, y)
        assert game.player_view.position(game.position)[2] == pytest.approx(surface.height(x, y))


def test_visualisation_uses_the_same_height_function_as_the_simulation() -> None:
    from src.the_curved_world.render import RenderConfig

    world = WorldGenerator(default_config()).generate(11)
    game = ExplorationGame(world)
    scene = build_scene(game, PlotMode.PLAYER)
    surface = game.player_view.surface
    config = RenderConfig()
    _, _, grid_z = surface.sample_grid(config.nx, config.ny)
    # the plot mesh is exactly the simulation surface, whatever its type
    assert np.allclose(scene.surface_z, grid_z)
    assert np.allclose(scene.player, surface.position(*game.position))


def test_invalid_configurations_are_rejected() -> None:
    with pytest.raises(ConfigError):
        Domain(0.0, 0.0, 0.0, 1.0)
    with pytest.raises(ConfigError):
        DetectorConfig(scale=0.0)
    with pytest.raises(ConfigError):
        GameplayConfig(capture_radius=0.01)
    with pytest.raises(ConfigError):
        WorldConfig(domain=Domain(-1.0, 1.0, -1.0, 1.0), surface=default_surface_config())