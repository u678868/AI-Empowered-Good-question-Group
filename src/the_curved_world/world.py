"""Internal world state and deterministic world generation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np

from src.the_curved_world.config import (
    ConfigError,
    GaussianHill,
    SurfaceConfig,
    WaveComponent,
    WorldConfig,
)
from src.the_curved_world.detector import Detector, DetectorConfig
from src.the_curved_world.geometry import SmoothSurface, ambient_distance
from src.the_curved_world.obstacles import ObstacleField
from src.the_curved_world.observations import PlayerObserver, PlayerView

ParameterPosition = Tuple[float, float]


@dataclass(frozen=True)
class WorldState:
    """Internal (privileged) world state.

    It knows the surface, the start, the hidden exit and the detector, and can
    therefore compute exact distances. Ordinary player-facing components must be
    obtained through :meth:`player_view` / :meth:`player_observer` instead of
    receiving this object directly.
    """

    surface: SmoothSurface
    seed: int
    start: ParameterPosition
    exit: ParameterPosition
    detector: Detector
    obstacles: ObstacleField | None = None

    def position(self, parameter_position: ParameterPosition) -> np.ndarray:
        """Embedded 3D position of a parameter-space location."""
        return self.surface.position(float(parameter_position[0]), float(parameter_position[1]))

    @property
    def start_position(self) -> np.ndarray:
        return self.position(self.start)

    def exit_position(self) -> np.ndarray:
        """PRIVILEGED: the true embedded exit position."""
        return self.position(self.exit)

    def ambient_distance(self, p: ParameterPosition, q: ParameterPosition) -> float:
        """Ambient Euclidean distance between two surface positions."""
        return ambient_distance(self.position(p), self.position(q))

    def player_view(self) -> PlayerView:
        """Build a player-facing view that cannot see the exit."""
        return PlayerView(self.surface, self.start)

    def player_observer(self, observation_config=None) -> PlayerObserver:
        """Build a player-facing detector interface returning only the signal."""
        return PlayerObserver(self.surface, self.detector.signal, observation_config)

    def debug_view(self) -> "DebugView":
        """Build a privileged developer interface (must be requested explicitly)."""
        return DebugView(self)


class DebugView:
    """Privileged developer interface over a :class:`WorldState`.

    Exposes hidden state (exit position, exact distance, world parameters) for
    testing and visualisation. It must only ever be created explicitly.
    """

    def __init__(self, world: WorldState) -> None:
        self._world = world

    @property
    def world(self) -> WorldState:
        return self._world

    @property
    def seed(self) -> int:
        return self._world.seed

    @property
    def start(self) -> ParameterPosition:
        return self._world.start

    @property
    def exit(self) -> ParameterPosition:
        return self._world.exit

    @property
    def surface_config(self) -> SurfaceConfig:
        return self._world.surface.config

    def start_position(self) -> np.ndarray:
        return self._world.start_position

    def exit_position(self) -> np.ndarray:
        return self._world.exit_position()

    def distance_to_exit(self, parameter_position: ParameterPosition) -> float:
        return ambient_distance(self._world.position(parameter_position), self._world.exit_position())

    def signal(self, parameter_position: ParameterPosition) -> float:
        return self._world.detector.signal(self._world.position(parameter_position))


class WorldGenerator:
    """Deterministic generator of :class:`WorldState` objects.

    The same ``(config, seed)`` pair always produces the same world; different
    seeds normally produce different surfaces and placements.
    """

    def __init__(self, config: WorldConfig) -> None:
        if not isinstance(config, WorldConfig):
            raise TypeError("WorldGenerator requires a WorldConfig")
        self._config = config

    @property
    def config(self) -> WorldConfig:
        return self._config

    def generate(self, seed: int | None = None) -> WorldState:
        """Generate a world.

        ``seed=None`` draws a fresh seed from OS entropy; the concrete seed is
        stored on the returned :class:`WorldState` so the world stays reproducible.
        """
        cfg = self._config
        if seed is None:
            seed = int(np.random.default_rng().integers(0, 2 ** 63 - 1))
        seed = int(seed)
        rng = np.random.default_rng(seed)

        base = cfg.surface
        # A graph surface is jittered per seed; a closed manifold is used as-is.
        surface = SmoothSurface(self._build_surface_config(rng)) if isinstance(base, SurfaceConfig) else base
        start = self._sample_parameter(rng)
        exit_ = self._place_exit(rng, surface, start)
        detector = Detector(surface.position(*exit_), DetectorConfig(cfg.detector_scale))
        # Stage 2: obstacles are scattered *after* the smooth surface exists, and are
        # kept clear of the start and the exit by a safe margin.
        obstacles = ObstacleField.generate(surface, cfg, seed, exclude_points=(start, exit_))
        return WorldState(
            surface=surface,
            seed=seed,
            start=start,
            exit=exit_,
            detector=detector,
            obstacles=obstacles,
        )

    # -- internals ---------------------------------------------------------

    def _build_surface_config(self, rng: np.random.Generator) -> SurfaceConfig:
        """Jitter a graph-surface configuration (closed manifolds bypass this)."""
        cfg = self._config
        base = cfg.surface
        if not cfg.randomize_surface:
            return base
        dom = cfg.domain
        margin = cfg.boundary_margin
        wave = WaveComponent(
            amplitude=base.wave.amplitude * float(rng.uniform(0.6, 1.4)),
            kx=base.wave.kx * float(rng.uniform(0.85, 1.15)),
            ky=base.wave.ky * float(rng.uniform(0.85, 1.15)),
        )
        hills = tuple(
            GaussianHill(
                amplitude=hill.amplitude * float(rng.uniform(0.6, 1.4)),
                center_x=float(rng.uniform(dom.x_min + margin, dom.x_max - margin)),
                center_y=float(rng.uniform(dom.y_min + margin, dom.y_max - margin)),
                scale=hill.scale * float(rng.uniform(0.85, 1.15)),
            )
            for hill in base.hills
        )
        return SurfaceConfig(domain=dom, wave=wave, hills=hills)

    def _sample_parameter(self, rng: np.random.Generator) -> ParameterPosition:
        cfg = self._config
        dom = cfg.domain
        margin = cfg.boundary_margin
        x = float(rng.uniform(dom.x_min + margin, dom.x_max - margin))
        y = float(rng.uniform(dom.y_min + margin, dom.y_max - margin))
        return (x, y)

    def _place_exit(
        self, rng: np.random.Generator, surface: SmoothSurface, start: ParameterPosition
    ) -> ParameterPosition:
        cfg = self._config
        start_position = surface.position(*start)
        for _ in range(cfg.max_placement_attempts):
            candidate = self._sample_parameter(rng)
            if ambient_distance(surface.position(*candidate), start_position) >= cfg.min_separation:
                return candidate
        raise ConfigError(
            "could not place the exit with the requested min_separation after "
            f"{cfg.max_placement_attempts} attempts; relax the constraint"
        )