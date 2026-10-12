"""Configuration objects for The Curved World.

All configuration is expressed through immutable dataclasses so that a given
``(config, seed)`` pair always reproduces exactly the same world.

Task 7 scales the world up: the default parameter domain is now
``[-50, 50] x [-50, 50]`` and the height function is a *multi-scale* sum of
smooth waves and mixed Gaussian hills (peaks, depressions, broad domes), giving
macroscopic terrain whose Gaussian curvature has clear positive clusters and
negative saddles -- while staying C-infinity everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np


class ConfigError(ValueError):
    """Raised when a configuration value is invalid."""


def _finite(name: str, value: float) -> float:
    v = float(value)
    if not np.isfinite(v):
        raise ConfigError(f"{name} must be finite, got {value!r}")
    return v


def _positive(name: str, value: float) -> float:
    v = _finite(name, value)
    if v <= 0.0:
        raise ConfigError(f"{name} must be > 0, got {value!r}")
    return v


@dataclass(frozen=True)
class Domain:
    """Bounded rectangular parameter domain ``[x_min, x_max] x [y_min, y_max]``."""

    x_min: float
    x_max: float
    y_min: float
    y_max: float

    def __post_init__(self) -> None:
        _finite("Domain.x_min", self.x_min)
        _finite("Domain.x_max", self.x_max)
        _finite("Domain.y_min", self.y_min)
        _finite("Domain.y_max", self.y_max)
        if not self.x_min < self.x_max:
            raise ConfigError("Domain requires x_min < x_max")
        if not self.y_min < self.y_max:
            raise ConfigError("Domain requires y_min < y_max")

    @property
    def width(self) -> float:
        return self.x_max - self.x_min

    @property
    def height(self) -> float:
        return self.y_max - self.y_min

    def contains(self, x, y, *, margin: float = 0.0):
        """Whether ``(x, y)`` is inside the domain, optionally shrunk by ``margin``.

        Works elementwise and returns a ``bool`` for scalar input.
        """
        if margin < 0.0:
            raise ConfigError("margin must be >= 0")
        inside = (
            (x >= self.x_min + margin)
            & (x <= self.x_max - margin)
            & (y >= self.y_min + margin)
            & (y <= self.y_max - margin)
        )
        return bool(inside) if np.ndim(inside) == 0 else inside


@dataclass(frozen=True)
class WaveComponent:
    """Smooth wave term ``amplitude * sin(kx * x) * cos(ky * y)``."""

    amplitude: float
    kx: float
    ky: float

    def __post_init__(self) -> None:
        _finite("WaveComponent.amplitude", self.amplitude)
        _finite("WaveComponent.kx", self.kx)
        _finite("WaveComponent.ky", self.ky)


@dataclass(frozen=True)
class GaussianHill:
    """Smooth Gaussian bump ``amplitude * exp(-((x-cx)^2 + (y-cy)^2) / scale^2)``.

    A positive ``amplitude`` is a peak and a negative one is a depression; both
    are C-infinity and both contribute a positive-curvature cap at their centre
    plus a negative-curvature skirt.
    """

    amplitude: float
    center_x: float
    center_y: float
    scale: float

    def __post_init__(self) -> None:
        _finite("GaussianHill.amplitude", self.amplitude)
        _finite("GaussianHill.center_x", self.center_x)
        _finite("GaussianHill.center_y", self.center_y)
        _positive("GaussianHill.scale", self.scale)


@dataclass(frozen=True)
class SurfaceConfig:
    """Fully specifies the smooth height function ``f(x, y)``.

    ``wave`` is the primary wave term; ``waves`` holds additional multi-scale
    wave terms (all terms are summed). ``hills`` holds the mixed Gaussian hills.
    """

    domain: Domain
    wave: WaveComponent
    hills: Tuple[GaussianHill, ...] = ()
    waves: Tuple[WaveComponent, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.domain, Domain):
            raise ConfigError("SurfaceConfig.domain must be a Domain")
        if not isinstance(self.wave, WaveComponent):
            raise ConfigError("SurfaceConfig.wave must be a WaveComponent")
        if not isinstance(self.hills, tuple):
            object.__setattr__(self, "hills", tuple(self.hills))
        if not isinstance(self.waves, tuple):
            object.__setattr__(self, "waves", tuple(self.waves))
        for hill in self.hills:
            if not isinstance(hill, GaussianHill):
                raise ConfigError("SurfaceConfig.hills must contain GaussianHill instances")
        for wave in self.waves:
            if not isinstance(wave, WaveComponent):
                raise ConfigError("SurfaceConfig.waves must contain WaveComponent instances")

    def wave_terms(self) -> Tuple[WaveComponent, ...]:
        """All wave components: the primary ``wave`` first, then the extras."""
        return (self.wave,) + self.waves


@dataclass(frozen=True)
class WorldConfig:
    """Configuration for world generation.

    Attributes
    ----------
    domain:
        Bounded rectangular parameter domain for the surface.
    surface:
        Base surface configuration. Its ``domain`` must equal ``domain``.
    min_separation:
        Minimum ambient Euclidean distance between start and exit.
    boundary_margin:
        Keep start and exit at least this far from the domain boundary.
    detector_scale:
        Positive scale of the exponential detector model.
    randomize_surface:
        When true the surface is jittered per seed for extra variety.
    max_placement_attempts:
        Maximum rejection-sampling attempts when placing the exit.
    """

    domain: Domain
    surface: SurfaceConfig
    min_separation: float = 25.0
    boundary_margin: float = 3.0
    detector_scale: float = 25.0
    randomize_surface: bool = True
    max_placement_attempts: int = 4000
    obstacle_count: int = 12
    obstacle_radius: float = 3.5
    obstacle_safe_margin: float = 12.0
    # Task 17: geometric scale S in [0.2, 10.0] and the difficulty tier.
    scale_factor: float = 1.0
    difficulty: str = "easy"

    def __post_init__(self) -> None:
        if not isinstance(self.domain, Domain):
            raise ConfigError("WorldConfig.domain must be a Domain")
        if not (isinstance(self.surface, SurfaceConfig) or hasattr(self.surface, "position")):
            raise ConfigError("WorldConfig.surface must be a SurfaceConfig or a closed manifold")
        if self.surface.domain != self.domain:
            raise ConfigError("WorldConfig.surface.domain must equal WorldConfig.domain")
        _positive("WorldConfig.min_separation", self.min_separation)
        _finite("WorldConfig.boundary_margin", self.boundary_margin)
        if self.boundary_margin < 0.0:
            raise ConfigError("WorldConfig.boundary_margin must be >= 0")
        if self.boundary_margin * 2.0 >= min(self.domain.width, self.domain.height):
            raise ConfigError("WorldConfig.boundary_margin leaves no room for positions")
        _positive("WorldConfig.detector_scale", self.detector_scale)
        if int(self.obstacle_count) < 0:
            raise ConfigError("WorldConfig.obstacle_count must be >= 0")
        if float(self.obstacle_radius) <= 0.0:
            raise ConfigError("WorldConfig.obstacle_radius must be > 0")
        if float(self.obstacle_safe_margin) < 0.0:
            raise ConfigError("WorldConfig.obstacle_safe_margin must be >= 0")
        if not np.isfinite(float(self.scale_factor)) or not (0.2 <= float(self.scale_factor) <= 10.0):
            raise ConfigError("WorldConfig.scale_factor must be within [0.2, 10.0]")
        if str(self.difficulty).strip().lower() not in ("easy", "medium", "hard"):
            raise ConfigError("WorldConfig.difficulty must be one of easy/medium/hard")
        if self.max_placement_attempts < 1:
            raise ConfigError("WorldConfig.max_placement_attempts must be >= 1")

    @property
    def scaled_obstacle_radius(self) -> float:
        """Task 17: physical obstacle radius after the 1/S geometric scale."""
        return float(self.obstacle_radius) / float(self.scale_factor)

    @property
    def scaled_obstacle_safe_margin(self) -> float:
        """Task 17: start/exit clearance after the 1/S geometric scale."""
        return float(self.obstacle_safe_margin) / float(self.scale_factor)


def default_domain() -> Domain:
    """The default large-scale parameter domain, ``[-50, 50] x [-50, 50]``."""
    return Domain(-50.0, 50.0, -50.0, 50.0)


def default_surface_config(domain: Domain | None = None) -> SurfaceConfig:
    """A deterministic multi-scale landscape: rolling waves plus mixed hills.

    Four wave terms of decreasing wavelength are combined with eight Gaussian
    hills (peaks, depressions and one broad dome) so the surface has clear
    positive-curvature clusters, negative-curvature saddles and gentle valleys.
    """
    dom = default_domain() if domain is None else domain
    span = min(dom.width, dom.height)
    unit = span / 100.0  # 1.0 for the default 100 x 100 domain
    centre_x = 0.5 * (dom.x_min + dom.x_max)
    centre_y = 0.5 * (dom.y_min + dom.y_max)

    primary = WaveComponent(amplitude=2.8 * unit, kx=0.135 / unit, ky=0.105 / unit)
    waves = (
        WaveComponent(amplitude=1.6 * unit, kx=0.265 / unit, ky=0.215 / unit),
        WaveComponent(amplitude=0.75 * unit, kx=0.52 / unit, ky=0.44 / unit),
        WaveComponent(amplitude=0.32 * unit, kx=1.05 / unit, ky=0.90 / unit),
    )
    hills = (
        GaussianHill(amplitude=7.0 * unit, center_x=centre_x - 28.0 * unit, center_y=centre_y + 22.0 * unit, scale=9.0 * unit),
        GaussianHill(amplitude=-6.0 * unit, center_x=centre_x + 20.0 * unit, center_y=centre_y - 26.0 * unit, scale=8.5 * unit),
        GaussianHill(amplitude=5.0 * unit, center_x=centre_x + 30.0 * unit, center_y=centre_y + 30.0 * unit, scale=7.0 * unit),
        GaussianHill(amplitude=-4.0 * unit, center_x=centre_x - 30.0 * unit, center_y=centre_y - 22.0 * unit, scale=10.0 * unit),
        GaussianHill(amplitude=3.2 * unit, center_x=centre_x + 2.0 * unit, center_y=centre_y + 4.0 * unit, scale=16.0 * unit),
        GaussianHill(amplitude=-3.0 * unit, center_x=centre_x + 14.0 * unit, center_y=centre_y + 20.0 * unit, scale=11.0 * unit),
        GaussianHill(amplitude=2.4 * unit, center_x=centre_x - 8.0 * unit, center_y=centre_y - 34.0 * unit, scale=8.0 * unit),
        GaussianHill(amplitude=-2.0 * unit, center_x=centre_x + 34.0 * unit, center_y=centre_y - 6.0 * unit, scale=9.0 * unit),
    )
    return SurfaceConfig(domain=dom, wave=primary, hills=hills, waves=waves)


def default_config() -> WorldConfig:
    """The default world: a closed deformed torus (genus 1, periodic)."""
    from src.the_curved_world.maps import DEFAULT_MAP_ID, world_config_for

    return world_config_for(DEFAULT_MAP_ID)