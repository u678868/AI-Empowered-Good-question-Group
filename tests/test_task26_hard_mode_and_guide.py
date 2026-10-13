"""Task 26: Hard-mode survival constraints and scale-adaptive quest timers."""

from __future__ import annotations

import pytest

from src.the_curved_world.config import hard_mode_time_limit
from src.the_curved_world.gameplay import GameError, GameplayConfig
from src.the_curved_world.server import GameSession


def test_hard_mode_limits_are_normalized_by_config() -> None:
    config = GameplayConfig(difficulty="hard")
    assert config.max_rope_pool == 500.0
    assert config.max_markers == 8


def test_hard_mode_scale_adaptive_time_limits() -> None:
    assert hard_mode_time_limit(0.5) == 120.0
    assert hard_mode_time_limit(1.0) == 240.0
    assert hard_mode_time_limit(2.0) == 360.0
    assert hard_mode_time_limit(4.0) == 480.0
    assert hard_mode_time_limit(1.5) == 360.0


def test_hard_mode_player_payload_exposes_rope_marker_and_timer_state() -> None:
    session = GameSession(seed=12345, difficulty="hard")
    state = session.player_state()
    assert state["difficulty"] == "hard"
    assert state["difficulty_reserved"] is False
    assert state["difficulty_active"] is True
    assert state["rope_total"] == 500.0
    assert state["max_markers_allowed"] == 8
    assert state["marker_count"] == 0
    assert state["time_limit"] == 240.0
    assert state["time_remaining"] is not None
    assert 0.0 <= state["time_remaining"] <= 240.0
    assert state["is_time_expired"] is False
    assert state["defeated"] is False


def test_hard_mode_blocks_the_ninth_marker() -> None:
    session = GameSession(seed=12345, difficulty="hard")
    for index in range(8):
        session.tool({"tool": "mark", "name": f"P{index + 1}"})
    assert len(session.player_state()["markers"]) == 8
    with pytest.raises(GameError, match="Hard mode limit: Maximum 8 marker pegs reached"):
        session.tool({"tool": "mark", "name": "P9"})


def test_hard_mode_timeout_marks_the_run_defeated() -> None:
    session = GameSession(seed=12345, difficulty="hard")
    game = session.game
    limit = game.quest_time_limit
    assert limit == 240.0
    game.advance_quest_timer(limit + 1.0)
    assert game.is_time_expired is True
    assert game.defeated is True
    assert game.won is False
    state = session.player_state()
    assert state["is_time_expired"] is True
    assert state["defeated"] is True
    assert state["time_remaining"] == 0.0