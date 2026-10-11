"""Tests for the Matplotlib 3D visualisation layer (Task 3)."""

from __future__ import annotations

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pytest

from src.the_curved_world.config import ConfigError, default_config, default_surface_config
from src.the_curved_world.detector import Detector, DetectorConfig
from src.the_curved_world.gameplay import ExplorationGame
from src.the_curved_world.geometry import SmoothSurface
from src.the_curved_world.render import (
    MatplotlibRenderer,
    PlotMode,
    RenderConfig,
    SurfaceMeshCache,
    build_scene,
)
from src.the_curved_world.world import WorldGenerator, WorldState


def make_world(start=(0.0, 0.0), exit_=(2.5, 2.5), scale=2.5) -> WorldState:
    surface = SmoothSurface(default_surface_config())
    detector = Detector(surface.position(*exit_), DetectorConfig(scale))
    return WorldState(
        surface=surface, seed=0, start=tuple(start), exit=tuple(exit_), detector=detector
    )


def make_game(seed: int = 777) -> ExplorationGame:
    return ExplorationGame(WorldGenerator(default_config()).generate(seed))


def test_scene_geometry_matches_the_simulation_surface() -> None:
    game = make_game()
    game.move(1.0, 0.5)
    game.place_marker("a")
    surface = game.player_view.surface

    scene = build_scene(game, PlotMode.PLAYER)
    config = RenderConfig()
    _, _, grid_z = surface.sample_grid(config.nx, config.ny)
    assert np.allclose(scene.surface_z, grid_z)
    assert np.allclose(scene.player, surface.position(*game.position))
    for marker, (name, point) in zip(game.markers, scene.markers):
        assert name == marker.name
        assert np.allclose(point, surface.position(*marker.position))
    for parameter, point in zip(game.trajectory, scene.trajectory):
        assert np.allclose(point, surface.position(*parameter))


def test_player_scene_leaks_no_hidden_state() -> None:
    world = make_world()
    game = ExplorationGame(world)

    scene = build_scene(game, PlotMode.PLAYER)

    assert scene.exit is None
    assert scene.start is None
    assert scene.true_distance is None
    text = scene.title + "\n" + "\n".join(scene.annotations)
    assert "exit" not in text.lower()
    assert str(world.exit) not in text


def test_player_scene_shows_a_compact_observation_history() -> None:
    game = make_game()
    assert build_scene(game, PlotMode.PLAYER).annotations  # no history yet, still has signal/steps
    game.read_detector("one")
    game.move(1.0, 0.0)
    game.read_detector("two")
    scene = build_scene(game, PlotMode.PLAYER)
    assert "recent readings:" in scene.annotations
    assert sum(1 for line in scene.annotations if line.startswith("  #")) == 2


def test_debug_scene_exposes_exit_and_distance() -> None:
    world = make_world()
    game = ExplorationGame(world)
    game.move(1.0, 0.0)

    scene = build_scene(game, PlotMode.DEBUG)

    assert scene.exit is not None
    assert scene.start is not None
    assert np.allclose(scene.exit, world.exit_position())
    assert np.allclose(scene.start, world.start_position)
    assert scene.true_distance == pytest.approx(world.debug_view().distance_to_exit(game.position))
    assert "DEVELOPER" in scene.title


def test_mesh_cache_rebuilds_only_when_surface_or_resolution_changes() -> None:
    game = make_game()
    surface = game.player_view.surface
    cache = SurfaceMeshCache()

    first = cache.mesh(surface, 10, 8)
    again = cache.mesh(surface, 10, 8)
    finer = cache.mesh(surface, 12, 8)

    assert first is again
    assert finer is not first


def test_scenes_are_reproducible_for_the_same_seed() -> None:
    generator = WorldGenerator(default_config())
    first = build_scene(ExplorationGame(generator.generate(4242)))
    second = build_scene(ExplorationGame(generator.generate(4242)))

    assert np.allclose(first.player, second.player)
    assert np.allclose(first.trajectory, second.trajectory)
    assert np.allclose(first.surface_z, second.surface_z)


def test_matplotlib_renderer_draws_player_and_debug_views() -> None:
    game = make_game()
    game.move(1.0, 0.5)
    game.read_detector()
    game.place_marker("here")

    renderer = MatplotlibRenderer(interactive=False)
    try:
        renderer.render(build_scene(game, PlotMode.PLAYER))
        player_labels = renderer.axes.get_legend_handles_labels()[1]
        assert "player" in player_labels
        assert all("EXIT" not in label for label in player_labels)
        assert "player view" in renderer.axes.get_title()

        renderer.render(build_scene(game, PlotMode.DEBUG))
        debug_labels = renderer.axes.get_legend_handles_labels()[1]
        assert any("EXIT" in label for label in debug_labels)
        assert "start" in debug_labels
        assert "DEVELOPER" in renderer.axes.get_title()
    finally:
        plt.close(renderer.figure)


def test_invalid_render_config_raises() -> None:
    with pytest.raises(ConfigError):
        RenderConfig(nx=1)
    with pytest.raises(ConfigError):
        RenderConfig(wireframe_stride=0)