"""Tests for the detector model and the player-facing information boundary."""

from __future__ import annotations

import numpy as np
import pytest

from src.the_curved_world.config import ConfigError, default_config
from src.the_curved_world.detector import Detector, DetectorConfig
from src.the_curved_world.observations import PlayerObservation
from src.the_curved_world.world import WorldGenerator


def test_signal_is_bounded_and_monotone_in_distance() -> None:
    detector = Detector(np.zeros(3), DetectorConfig(scale=2.0))
    far = detector.signal(np.array([10.0, 0.0, 0.0]))
    near = detector.signal(np.array([0.5, 0.0, 0.0]))
    at_exit = detector.signal(np.zeros(3))

    assert 0.0 < far <= 1.0
    assert 0.0 < near <= 1.0
    assert near > far
    assert at_exit == pytest.approx(1.0)


def test_signal_matches_exp_model() -> None:
    detector = Detector(np.zeros(3), DetectorConfig(scale=3.0))
    assert detector.signal(np.array([3.0, 0.0, 0.0])) == pytest.approx(np.exp(-1.0))


def test_invalid_scale_raises() -> None:
    with pytest.raises(ConfigError):
        DetectorConfig(scale=0.0)
    with pytest.raises(ConfigError):
        DetectorConfig(scale=-1.0)


def test_player_observation_contains_only_signal() -> None:
    world = WorldGenerator(default_config()).generate(7)
    observation = world.player_observer().observe(world.start)

    assert isinstance(observation, PlayerObservation)
    assert set(observation.__dataclass_fields__) == {"signal", "label", "trend"}
    assert isinstance(observation.signal, float)
    assert 0.0 <= observation.signal <= 1.0
    # no hidden state leaks through the record or its text representation
    assert not hasattr(observation, "distance")
    assert not hasattr(observation, "position")
    assert str(world.exit) not in repr(observation)


def test_player_view_does_not_expose_exit() -> None:
    world = WorldGenerator(default_config()).generate(7)
    view = world.player_view()
    assert not hasattr(view, "exit")
    assert not hasattr(view, "exit_position")
    assert not hasattr(view, "detector")


def test_debug_view_is_explicit_and_reveals_hidden_state() -> None:
    world = WorldGenerator(default_config()).generate(7)
    debug = world.debug_view()
    assert debug.exit == world.exit
    assert debug.distance_to_exit(debug.start) > 0.0
    assert 0.0 < debug.signal(debug.start) <= 1.0