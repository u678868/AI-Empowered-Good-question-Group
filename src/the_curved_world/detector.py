"""Distance-sensitive detector (a privileged component).

The detector knows the hidden exit position and can therefore compute the true
ambient Euclidean distance. Player-facing code must never receive this object
directly -- use :class:`~src.the_curved_world.observations.PlayerObserver`.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.the_curved_world.config import ConfigError
from src.the_curved_world.geometry import ambient_distance


@dataclass(frozen=True)
class DetectorConfig:
    """Configuration for the exponential detector model.

    ``scale`` must be strictly positive. The signal is
    ``exp(-distance / scale)``, bounded in ``(0, 1]``, and strictly decreasing
    in distance.
    """

    scale: float = 1.0

    def __post_init__(self) -> None:
        if not np.isfinite(self.scale):
            raise ConfigError(f"DetectorConfig.scale must be finite, got {self.scale!r}")
        if self.scale <= 0.0:
            raise ConfigError(f"DetectorConfig.scale must be > 0, got {self.scale!r}")


class Detector:
    """Privileged detector bound to a hidden exit position.

    ``exit_position`` may be a single 3D point or a sequence of them. Several
    points mean "one place with several realizations" -- an antipodal quotient
    world such as the projective plane -- and the detector then reports the
    *nearest* one, because they all denote the same hidden exit. Passing one
    point (every other map) behaves exactly as before.
    """

    def __init__(self, exit_position, config: DetectorConfig | None = None) -> None:
        array = np.asarray(exit_position, dtype=float)
        if array.ndim == 1:
            self._targets = (array.reshape(3),)
        else:
            targets = tuple(row.reshape(3) for row in array)
            if not targets:
                raise ConfigError("Detector requires at least one exit realization")
            self._targets = targets
        self._config = DetectorConfig() if config is None else config

    @property
    def config(self) -> DetectorConfig:
        return self._config

    @property
    def targets(self):
        """PRIVILEGED: the exit's realizations (never exposed to the player)."""
        return self._targets

    def distance(self, player_position) -> float:
        """PRIVILEGED: exact ambient Euclidean distance from ``player_position`` to the exit."""
        return min(ambient_distance(player_position, target) for target in self._targets)

    def signal(self, player_position) -> float:
        """Detector signal in ``(0, 1]``; stronger (larger) when closer to the exit."""
        return float(np.exp(-self.distance(player_position) / self._config.scale))