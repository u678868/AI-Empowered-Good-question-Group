"""Player-facing observation interfaces (the information boundary).

This module holds *only* player-facing types. By construction none of them can
reveal the hidden exit position or the exact player-to-exit distance.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Tuple

import numpy as np

from src.the_curved_world.config import ConfigError
from src.the_curved_world.geometry import SmoothSurface

TREND_FIRST = "first"
TREND_UP = "up"
TREND_DOWN = "down"
TREND_SAME = "same"
_TRENDS = (TREND_FIRST, TREND_UP, TREND_DOWN, TREND_SAME)
_LABELS = ("Weak", "Moderate", "Strong")


@dataclass(frozen=True)
class ObservationConfig:
    """Configurable thresholds for the qualitative signal label.

    ``label`` returns ``Weak`` below ``weak_threshold``, ``Strong`` above
    ``strong_threshold`` and ``Moderate`` in between.
    """

    weak_threshold: float = 0.33
    strong_threshold: float = 0.66
    relative_tolerance: float = 1e-9

    def __post_init__(self) -> None:
        if not 0.0 <= self.weak_threshold < self.strong_threshold <= 1.0:
            raise ConfigError("require 0 <= weak_threshold < strong_threshold <= 1")
        if self.relative_tolerance < 0.0:
            raise ConfigError("ObservationConfig.relative_tolerance must be >= 0")

    def label(self, signal: float) -> str:
        if signal < self.weak_threshold:
            return "Weak"
        if signal > self.strong_threshold:
            return "Strong"
        return "Moderate"


@dataclass(frozen=True)
class PlayerObservation:
    """A single player-visible detector reading.

    Invariant: this record carries only player-permitted information -- the
    normalised signal, a qualitative label and the trend relative to the
    previous reading. It must never carry the exit coordinates, the exact
    distance, or a direction vector.
    """

    signal: float
    label: str
    trend: str

    def __post_init__(self) -> None:
        if not 0.0 <= self.signal <= 1.0:
            raise ValueError(f"signal must be within [0, 1], got {self.signal!r}")
        if self.label not in _LABELS:
            raise ValueError(f"unexpected label {self.label!r}")
        if self.trend not in _TRENDS:
            raise ValueError(f"unexpected trend {self.trend!r}")


class PlayerObserver:
    """Player-facing detector interface.

    It is constructed from the surface and a *signal function* only; it keeps no
    reference to the exit and therefore cannot report distance or direction. It
    remembers the previous reading so it can report whether the signal rose or
    fell.
    """

    def __init__(
        self,
        surface: SmoothSurface,
        signal_function: Callable[[np.ndarray], float],
        config: ObservationConfig | None = None,
    ) -> None:
        self._surface = surface
        self._signal_function = signal_function
        self._config = ObservationConfig() if config is None else config
        self._previous_signal: float | None = None

    @property
    def config(self) -> ObservationConfig:
        return self._config

    def reset(self) -> None:
        """Forget the previous reading (used when a new world starts)."""
        self._previous_signal = None

    def observe(self, parameter_position: Tuple[float, float]) -> PlayerObservation:
        """Take a reading at ``(x, y)`` and advance the trend baseline."""
        signal, label = self._reading(parameter_position)
        trend = self._trend(signal)
        self._previous_signal = signal
        return PlayerObservation(signal=signal, label=label, trend=trend)

    def peek(self, parameter_position: Tuple[float, float]) -> PlayerObservation:
        """Like :meth:`observe` but does not advance the trend baseline."""
        signal, label = self._reading(parameter_position)
        return PlayerObservation(signal=signal, label=label, trend=self._trend(signal))

    # -- internals ---------------------------------------------------------

    def _reading(self, parameter_position: Tuple[float, float]) -> Tuple[float, str]:
        point = self._surface.position(float(parameter_position[0]), float(parameter_position[1]))
        signal = float(self._signal_function(point))
        return signal, self._config.label(signal)

    def _trend(self, signal: float) -> str:
        if self._previous_signal is None:
            return TREND_FIRST
        delta = signal - self._previous_signal
        if abs(delta) <= self._config.relative_tolerance:
            return TREND_SAME
        return TREND_UP if delta > 0 else TREND_DOWN


class PlayerView:
    """Player-facing view of the world.

    Exposes the surface and the start position only. It deliberately keeps no
    reference to the hidden exit, so it cannot leak exit data even by accident.
    """

    def __init__(self, surface: SmoothSurface, start: Tuple[float, float]) -> None:
        self._surface = surface
        self._start = (float(start[0]), float(start[1]))

    @property
    def surface(self) -> SmoothSurface:
        return self._surface

    @property
    def start(self) -> Tuple[float, float]:
        return self._start

    def position(self, parameter_position: Tuple[float, float]) -> np.ndarray:
        return self._surface.position(float(parameter_position[0]), float(parameter_position[1]))

    def contains(self, parameter_position: Tuple[float, float], *, margin: float = 0.0) -> bool:
        return self._surface.contains(
            float(parameter_position[0]), float(parameter_position[1]), margin=margin
        )