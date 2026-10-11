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
    """Privileged detector bound to a hidden exit position."""

    def __init__(self, exit_position, config: DetectorConfig | None = None) -> None:
        self._exit = np.asarray(exit_position, dtype=float).reshape(3)
        self._config = DetectorConfig() if config is None else config

    @property
    def config(self) -> DetectorConfig:
        return self._config

    def distance(self, player_position) -> float:
        """PRIVILEGED: exact ambient Euclidean distance from ``player_position`` to the exit."""
        return ambient_distance(player_position, self._exit)

    def signal(self, player_position) -> float:
        """Detector signal in ``(0, 1]``; stronger (larger) when closer to the exit."""
        return float(np.exp(-self.distance(player_position) / self._config.scale))