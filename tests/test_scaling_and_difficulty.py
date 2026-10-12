"""Task 17: geometric map scaling, difficulty tiers and the score placeholder.

These tests pin the ``S`` scaling law (step / view / obstacle / capture all scale
by ``1 / S``), the three difficulty tiers (medium strips the distance detector,
hard is a safe reserved placeholder) and the reserved scoring inputs.
"""

from __future__ import annotations

import pytest

from src.the_curved_world.config import ConfigError, WorldConfig, default_config
from src.the_curved_world.gameplay import GameError, GameplayConfig
from src.the_curved_world.maps import world_config_for
from src.the_curved_world.obstacles import ObstacleField
from src.the_curved_world.server import GameSession
from src.the_curved_world.world import WorldGenerator


def test_step_and_capture_scale_inversely_with_scale_factor() -> None:
    base = GameplayConfig()
    large = GameplayConfig(scale_factor=2.0)
    small = GameplayConfig(scale_factor=0.5)

    assert large.step_length == pytest.approx(base.step_length / 2.0)
    assert small.step_length == pytest.approx(base.step_length * 2.0)
    assert large.effective_capture_radius == pytest.approx(base.effective_capture_radius / 2.0)
    assert small.effective_capture_radius == pytest.approx(base.effective_capture_radius * 2.0)
    assert large.effective_player_radius == pytest.approx(base.effective_player_radius / 2.0)


def test_world_config_scales_obstacle_radius_and_margin() -> None:
    config = world_config_for("torus_genus1")
    scaled = WorldConfig(
        domain=config.domain,
        surface=config.surface,
        obstacle_count=config.obstacle_count,
        obstacle_radius=config.obstacle_radius,
        obstacle_safe_margin=config.obstacle_safe_margin,
        scale_factor=4.0,
    )
    assert scaled.scaled_obstacle_radius == pytest.approx(config.obstacle_radius / 4.0)
    assert scaled.scaled_obstacle_safe_margin == pytest.approx(config.obstacle_safe_margin / 4.0)

    field = ObstacleField.generate(scaled.surface, scaled, 12345, exclude_points=())
    assert len(field) == scaled.obstacle_count
    for obstacle in field.obstacles:
        assert obstacle.radius <= scaled.scaled_obstacle_radius * 1.3 + 1e-9
        assert obstacle.radius >= scaled.scaled_obstacle_radius * 0.8 - 1e-9


def test_session_scale_factor_scales_step_patch_and_obstacles() -> None:
    base = GameSession(seed=12345)
    large = GameSession(seed=12345, scale_factor=2.0)

    assert large.scale_factor == pytest.approx(2.0)
    assert large.summary()["scale_factor"] == pytest.approx(2.0)
    assert large.game.step_length == pytest.approx(base.game.step_length / 2.0)
    assert large.effective_patch_radius == pytest.approx(base.effective_patch_radius / 2.0)
    assert large.player_state()["scale_factor"] == pytest.approx(2.0)
    assert large.player_state()["difficulty"] == "easy"


def test_medium_difficulty_silences_the_player_detector() -> None:
    session = GameSession(seed=12345, difficulty="medium")
    state = session.player_state()
    assert state["difficulty"] == "medium"
    assert state["signal"] == 0.0
    assert state["label"] == "Offline"
    assert state["trend"] == "same"
    assert state["difficulty_reserved"] is False

    scan = session.tool({"tool": "scan"})
    assert scan["signal"] == 0.0
    assert scan["label"] == "Offline"
    assert scan["trend"] == "same"

    # the player payload still never carries the exit or the true distance
    assert "exit_position" not in state
    assert "true_distance" not in state


def test_hard_difficulty_is_a_reserved_placeholder() -> None:
    session = GameSession(seed=12345, difficulty="hard")
    state = session.player_state()
    assert state["difficulty"] == "hard"
    assert state["difficulty_reserved"] is True
    assert state["signal"] == 0.0
    assert state["label"] == "Reserved"
    assert state["trend"] == "same"
    # the world is still playable: a step is accepted and the exit rule still runs
    result = session.game.move(1.0, 0.0)
    assert result.moved is True


def test_invalid_scale_and_difficulty_are_rejected() -> None:
    config = world_config_for("torus_genus1")
    with pytest.raises(ConfigError):
        WorldConfig(domain=config.domain, surface=config.surface, scale_factor=0.1)
    with pytest.raises(ConfigError):
        WorldConfig(domain=config.domain, surface=config.surface, scale_factor=11.0)
    with pytest.raises(ConfigError):
        GameplayConfig(scale_factor=0.05)
    with pytest.raises(ConfigError):
        GameplayConfig(difficulty="impossible")
    with pytest.raises(GameError):
        GameSession(seed=12345, difficulty="impossible")

    session = GameSession(seed=12345)
    with pytest.raises(GameError):
        session.reset_world(scale=99.0)
    with pytest.raises(GameError):
        session.reset_world(difficulty="nope")


def test_score_inputs_are_tracked_and_score_is_a_placeholder() -> None:
    session = GameSession(seed=12345)
    game = session.game
    game.move(1.0, 0.3)
    game.move(1.0, 0.3)
    game.read_detector()
    game.place_marker("P1")
    game.release_pointer()
    game.record_tool_usage("curvature")

    state = session.player_state()
    assert state["score"] == 0.0
    assert state["effective_steps"] > 0.0
    assert state["effective_steps"] >= 2.0  # uphill damping never discounts below 1/step
    assert state["tool_usages"]["detector"] == 1
    assert state["tool_usages"]["marker"] == 1
    assert state["tool_usages"]["pointer"] == 1
    assert state["tool_usages"]["curvature"] == 1
    assert state["tool_usages"]["triangle"] == 0
    assert set(state["tool_usages"]) == {"detector", "pointer", "curvature", "triangle", "marker"}

    # the reserved hook is callable and explicitly returns the placeholder value
    assert game.calculate_score() == 0.0


def test_default_world_config_keeps_the_task16_baseline() -> None:
    config = default_config()
    assert config.obstacle_radius >= 4.0
    assert config.obstacle_safe_margin >= 12.0
    assert config.scale_factor == pytest.approx(1.0)
    assert config.difficulty == "easy"
    # a fresh generator still produces every obstacle
    world = WorldGenerator(config).generate(12345)
    assert len(world.obstacles) == config.obstacle_count