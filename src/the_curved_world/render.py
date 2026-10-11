"""Matplotlib 3D visualisation for The Curved World (Task 3).

The rendering layer is split in two:

* :func:`build_scene` turns game state into a plain :class:`Scene` description
  (NumPy arrays + annotations). It is pure, testable, and *always* uses the same
  :class:`~src.the_curved_world.geometry.SmoothSurface` as the simulation.
* :class:`MatplotlibRenderer` only draws a ``Scene``; it can be replaced by a
  real-time 3D engine later without touching the game logic.

Player scenes never contain the exit position or the hidden distance. Only the
explicitly requested developer scene does.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple

import numpy as np

from src.the_curved_world.config import ConfigError
from src.the_curved_world.gameplay import ExplorationGame
from src.the_curved_world.geometry import SmoothSurface


class PlotMode(str, Enum):
    """Which view a scene (or renderer) shows."""

    PLAYER = "player"
    DEBUG = "debug"


@dataclass(frozen=True)
class RenderConfig:
    """Visualisation sampling and styling parameters."""

    nx: int = 60
    ny: int = 60
    wireframe_stride: int = 6
    trajectory_color: str = "tab:blue"
    player_color: str = "crimson"
    marker_color: str = "tab:orange"

    def __post_init__(self) -> None:
        if self.nx < 2 or self.ny < 2:
            raise ConfigError("RenderConfig.nx and RenderConfig.ny must be >= 2")
        if self.wireframe_stride < 1:
            raise ConfigError("RenderConfig.wireframe_stride must be >= 1")


class SurfaceMeshCache:
    """Caches the sampled surface mesh, rebuilding only when the surface changes.

    This is what keeps per-action updates cheap: the expensive ``sample_grid``
    call happens once per distinct surface, not once per movement step.
    """

    def __init__(self) -> None:
        self._key = None
        self._mesh = None

    def mesh(self, surface: SmoothSurface, nx: int, ny: int):
        key = (surface.config, nx, ny)
        if key != self._key:
            self._mesh = surface.sample_grid(nx, ny)
            self._key = key
        return self._mesh

    def clear(self) -> None:
        self._key = None
        self._mesh = None


@dataclass(frozen=True, eq=False)
class Scene:
    """A plain, renderer-agnostic description of what to draw."""

    mode: PlotMode
    surface_x: np.ndarray
    surface_y: np.ndarray
    surface_z: np.ndarray
    player: np.ndarray
    trajectory: np.ndarray
    markers: Tuple[Tuple[str, np.ndarray], ...]
    detector_signal: float
    detector_label: str
    annotations: Tuple[str, ...]
    title: str
    surface_key: object = None
    start: Optional[np.ndarray] = None
    exit: Optional[np.ndarray] = None
    true_distance: Optional[float] = None


def build_scene(
    game: ExplorationGame,
    mode: PlotMode = PlotMode.PLAYER,
    config: RenderConfig | None = None,
    mesh_cache: SurfaceMeshCache | None = None,
) -> Scene:
    """Build a :class:`Scene` from the current game state.

    The surface is always sampled from the simulation's own height function, so
    the plot and the simulation can never disagree about geometry.
    """
    render_config = RenderConfig() if config is None else config
    plot_mode = mode if isinstance(mode, PlotMode) else PlotMode(mode)
    cache = mesh_cache if mesh_cache is not None else SurfaceMeshCache()

    view = game.player_view
    surface = view.surface
    grid_x, grid_y, grid_z = cache.mesh(surface, render_config.nx, render_config.ny)

    player = view.position(game.position)
    trajectory = np.array([view.position(p) for p in game.trajectory], dtype=float)
    markers = tuple((marker.name, view.position(marker.position)) for marker in game.markers)
    observation = game.peek_detector()

    annotations = [
        f"signal = {observation.signal:.4f} ({observation.label})",
        f"trend  = {observation.trend}",
        f"steps  = {game.steps}   time = {game.elapsed_time:.2f}s",
        f"markers = {len(markers)}   readings = {len(game.log)}",
    ]
    title = "The Curved World - player view"
    start = exit_point = None
    true_distance = None

    if plot_mode is PlotMode.DEBUG:
        debug = game.debug_view()
        start = debug.start_position()
        exit_point = debug.exit_position()
        true_distance = debug.distance_to_exit(game.position)
        surface_config = debug.surface_config
        describe = getattr(surface_config, "describe", None)
        if callable(describe):
            model_text = "model: {}  genus={}".format(
                surface_config.name, getattr(surface_config, "genus", "?")
            )
        else:
            model_text = "surface: A={:.3f} kx={:.3f} ky={:.3f} hills={}".format(
                surface_config.wave.amplitude,
                surface_config.wave.kx,
                surface_config.wave.ky,
                len(surface_config.hills),
            )
        annotations = [
            f"seed = {debug.seed}",
            f"start (x,y) = ({debug.start[0]:.3f}, {debug.start[1]:.3f})   exit (x,y) = ({debug.exit[0]:.3f}, {debug.exit[1]:.3f})",
            f"player (x,y) = ({game.position[0]:.3f}, {game.position[1]:.3f})",
            f"player (3D)  = ({player[0]:.3f}, {player[1]:.3f}, {player[2]:.3f})",
            f"true distance player->exit = {true_distance:.4f}",
            f"signal = {observation.signal:.4f} ({observation.label})",
            model_text,
        ]
        title = "The Curved World - DEVELOPER view (hidden state visible)"

    if game.log:
        annotations = list(annotations) + ["recent readings:"] + [
            "  #{:<3} ({:6.2f},{:6.2f}) s={:.3f} {}".format(
                entry.index, entry.position[0], entry.position[1], entry.signal, entry.label
            )
            for entry in game.log[-5:]
        ]
    return Scene(
        mode=plot_mode,
        surface_x=grid_x,
        surface_y=grid_y,
        surface_z=grid_z,
        player=player,
        trajectory=trajectory,
        markers=markers,
        detector_signal=observation.signal,
        detector_label=observation.label,
        annotations=tuple(annotations),
        title=title,
        surface_key=(surface.cache_key, render_config.nx, render_config.ny),
        start=start,
        exit=exit_point,
        true_distance=true_distance,
    )


class MatplotlibRenderer:
    """Matplotlib 3D renderer with in-place (interactive) updates.

    The expensive surface artists are created once per surface and then reused;
    each update only removes and re-adds the cheap *dynamic* artists (player
    marker, trajectory, markers, annotations) and refreshes the canvas. No new
    window is created and the simulation surface is never re-sampled here -- the
    mesh comes from the caller's :class:`SurfaceMeshCache`.
    """

    def __init__(self, config: RenderConfig | None = None, *, figure=None, interactive: bool = True) -> None:
        import matplotlib.pyplot as plt

        self._plt = plt
        self._config = RenderConfig() if config is None else config
        if interactive:
            plt.ion()
        if figure is None:
            figure = plt.figure(figsize=(9.0, 7.0))
        self._figure = figure
        self._axes = figure.add_subplot(111, projection="3d")
        self._axes_ready = False
        self._surface_key = None
        self._surface_artists = []
        self._dynamic_artists = []
        self._legend = None

    @property
    def figure(self):
        return self._figure

    @property
    def axes(self):
        return self._axes

    def render(self, scene: Scene) -> None:
        """Draw (or update in place) the given scene without rebuilding the surface."""
        axes = self._axes
        if not self._axes_ready:
            axes.clear()
            self._axes_ready = True

        if self._surface_key != scene.surface_key:
            self._remove_artists(self._surface_artists)
            self._surface_artists = self._draw_surface(scene)
            self._surface_key = scene.surface_key

        self._remove_artists(self._dynamic_artists)
        self._dynamic_artists = self._draw_dynamic(scene)

        self._apply_style(scene)
        self._refresh_legend()
        self._figure.canvas.draw_idle()

    def pause(self, interval: float = 0.001) -> None:
        """Let the GUI process pending events (silent on non-GUI backends)."""
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*non-interactive.*")
            self._plt.pause(interval)

    def hold(self) -> None:
        """Block with the window open (returns immediately on non-GUI backends)."""
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", message=".*non-interactive.*")
            self._plt.show(block=True)

    def close(self) -> None:
        """Close the window (called on quit)."""
        self._plt.close(self._figure)


    # -- internals ---------------------------------------------------------

    def _draw_surface(self, scene: Scene):
        axes = self._axes
        surface = axes.plot_surface(
            scene.surface_x, scene.surface_y, scene.surface_z,
            cmap="viridis", alpha=0.85, linewidth=0.0, antialiased=True,
        )
        stride = self._config.wireframe_stride
        wire = axes.plot_wireframe(
            scene.surface_x, scene.surface_y, scene.surface_z,
            rstride=stride, cstride=stride, color="black", linewidth=0.2, alpha=0.2,
        )
        return [surface, wire]

    def _draw_dynamic(self, scene: Scene):
        axes = self._axes
        artists = []

        trajectory = scene.trajectory
        if trajectory.shape[0] >= 2:
            artists.append(axes.plot(
                trajectory[:, 0], trajectory[:, 1], trajectory[:, 2],
                color=self._config.trajectory_color, linewidth=1.6, label="trajectory",
            )[0])
        elif trajectory.shape[0] == 1:
            artists.append(axes.scatter(
                trajectory[:, 0], trajectory[:, 1], trajectory[:, 2],
                color=self._config.trajectory_color, s=8, depthshade=False, label="trajectory",
            ))

        for name, point in scene.markers:
            artists.append(axes.scatter(
                [point[0]], [point[1]], [point[2]],
                marker="o", color=self._config.marker_color, s=34, depthshade=False,
            ))
            artists.append(axes.text(point[0], point[1], point[2], " " + name, fontsize=7))

        artists.append(axes.scatter(
            [scene.player[0]], [scene.player[1]], [scene.player[2]],
            marker="*", color=self._config.player_color, s=150, depthshade=False, label="player",
        ))

        if scene.start is not None:
            artists.append(axes.scatter(
                [scene.start[0]], [scene.start[1]], [scene.start[2]],
                marker="^", color="seagreen", s=70, depthshade=False, label="start",
            ))
        if scene.exit is not None:
            artists.append(axes.scatter(
                [scene.exit[0]], [scene.exit[1]], [scene.exit[2]],
                marker="X", color="black", s=110, depthshade=False, label="EXIT (debug)",
            ))
            artists.append(axes.plot(
                [scene.player[0], scene.exit[0]],
                [scene.player[1], scene.exit[1]],
                [scene.player[2], scene.exit[2]],
                color="black", linestyle="--", linewidth=1.0,
            )[0])

        artists.append(axes.text2D(
            0.02, 0.98, "\n".join(scene.annotations),
            transform=axes.transAxes, va="top", ha="left", family="monospace", fontsize=8,
        ))
        return artists

    def _apply_style(self, scene: Scene) -> None:
        axes = self._axes
        axes.set_title(scene.title)
        if scene.mode is PlotMode.DEBUG:
            axes.set_xlabel("x")
            axes.set_ylabel("y")
            axes.set_zlabel("z")
        else:
            axes.set_xlabel("")
            axes.set_ylabel("")
            axes.set_zlabel("")
        axes.set_xlim(float(scene.surface_x.min()), float(scene.surface_x.max()))
        axes.set_ylim(float(scene.surface_y.min()), float(scene.surface_y.max()))
        low = float(scene.surface_z.min())
        high = float(scene.surface_z.max())
        pad = 0.08 * max(high - low, 1e-6)
        axes.set_zlim(low - pad, high + pad)

    def _refresh_legend(self) -> None:
        if self._legend is not None:
            try:
                self._legend.remove()
            except (ValueError, NotImplementedError):
                pass
            self._legend = None
        handles, labels = self._axes.get_legend_handles_labels()
        if handles:
            self._legend = self._axes.legend(handles=handles, labels=labels, loc="upper right", fontsize=8)

    @staticmethod
    def _remove_artists(artists) -> None:
        for artist in list(artists):
            try:
                artist.remove()
            except (ValueError, NotImplementedError):
                pass
        artists.clear()