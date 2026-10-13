"""Task 27: structured scoring ledger, frugality and scholar ranks."""

from __future__ import annotations

from dataclasses import replace

from src.the_curved_world.gameplay import Marker
from src.the_curved_world.server import GameSession


def _configure_score_state(
    session: GameSession,
    *,
    won: bool,
    elapsed: float,
    markers: int,
    steps: float,
    measure_calls: int,
    rope_used: float,
    completed: int,
    difficulty: str | None = None,
    scale: float | None = None,
) -> dict:
    game = session.game
    game._won = won
    game._elapsed = elapsed
    game._effective_steps = steps
    game._tool_usages["triangle"] = measure_calls
    game._tool_usages["curvature"] = 0
    game._markers = {f"P{index}": Marker(f"P{index}", (0.0, 0.0), 0.0, "Weak") for index in range(markers)}
    game._ropes._used = min(game._ropes.total_pool, max(0.0, rope_used))
    if game._quest_manager is not None:
        game._quest_manager._completed = [f"q{index}" for index in range(completed)]
    if difficulty is not None or scale is not None:
        game._config = replace(
            game._config,
            difficulty=difficulty if difficulty is not None else game._config.difficulty,
            scale_factor=scale if scale is not None else game._config.scale_factor,
        )
    return game.calculate_score()


def test_fast_frugal_clear_reaches_s_rank() -> None:
    session = GameSession(seed=12345)
    score = _configure_score_state(
        session,
        won=True,
        elapsed=0.0,
        markers=3,
        steps=0.0,
        measure_calls=20,
        rope_used=0.0,
        completed=5,
    )
    assert score["rank"] == "S"
    assert score["total_score"] >= 8000
    assert set(score["breakdown"]) >= {
        "base",
        "time_bonus",
        "marker_bonus",
        "rope_bonus",
        "tool_bonus",
        "step_penalty",
        "multipliers",
    }
    state = session.player_state()
    assert state["score"] == score["total_score"]
    assert state["rank"] == "S"
    assert state["score_breakdown"]["total_score"] == score["total_score"]


def test_long_wasteful_run_decays_but_keeps_floor_score() -> None:
    session = GameSession(seed=12345)
    fast = _configure_score_state(
        session,
        won=True,
        elapsed=0.0,
        markers=3,
        steps=0.0,
        measure_calls=20,
        rope_used=0.0,
        completed=5,
    )
    slow = _configure_score_state(
        session,
        won=True,
        elapsed=5000.0,
        markers=100,
        steps=5000.0,
        measure_calls=1000,
        rope_used=session.game.rope_system.total_pool * 0.9,
        completed=5,
    )
    assert slow["total_score"] < fast["total_score"]
    assert slow["total_score"] >= 100
    assert slow["breakdown"]["step_penalty"] == 1000.0


def test_difficulty_and_scale_multipliers_are_applied() -> None:
    session = GameSession(seed=12345)
    easy = _configure_score_state(
        session,
        won=True,
        elapsed=60.0,
        markers=3,
        steps=10.0,
        measure_calls=20,
        rope_used=0.0,
        completed=5,
        difficulty="easy",
        scale=1.0,
    )
    medium = _configure_score_state(
        session,
        won=True,
        elapsed=60.0,
        markers=3,
        steps=10.0,
        measure_calls=20,
        rope_used=0.0,
        completed=5,
        difficulty="medium",
        scale=1.0,
    )
    hard = _configure_score_state(
        session,
        won=True,
        elapsed=60.0,
        markers=3,
        steps=10.0,
        measure_calls=20,
        rope_used=0.0,
        completed=5,
        difficulty="hard",
        scale=4.0,
    )
    assert medium["total_score"] > easy["total_score"]
    assert hard["total_score"] > medium["total_score"]
    assert hard["breakdown"]["multipliers"]["difficulty_mult"] == 2.2
    assert hard["breakdown"]["multipliers"]["scale_mult"] == 1.5