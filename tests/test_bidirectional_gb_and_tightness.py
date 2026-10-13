"""Task 26: bidirectional Gauss-Bonnet and prechecked tight targets."""

from __future__ import annotations

import math

import pytest

from src.the_curved_world.maps import world_config_for
from src.the_curved_world.quest import GaussBonnetQuest, QuestManager, TriangleMeasurement
from src.the_curved_world.scanner import (
    TRIANGLE_DIFFICULTY_FRACTIONS,
    scan_manifold,
    verify_triangle_feasibility,
)


@pytest.fixture(scope="module")
def torus_features():
    return scan_manifold(world_config_for("torus_genus1").surface, genus_hint=1)


def test_precheck_confirms_both_directions_and_difficulties(torus_features) -> None:
    manifold = world_config_for("torus_genus1").surface
    for mode, center in (("excess", torus_features.peak), ("deficit", torus_features.saddle)):
        for difficulty in ("easy", "medium"):
            target = float(getattr(torus_features, f"{mode}_target_{difficulty}"))
            report = verify_triangle_feasibility(
                manifold,
                mode,
                target,
                difficulty,
                center=center,
            )
            assert report["feasible"] is True
            assert report["attempts"] > 0
            assert report["best_sum"] > 0.0


def test_medium_targets_are_tighter_but_still_feasible(torus_features) -> None:
    assert torus_features.excess_target_medium > torus_features.excess_target_easy
    assert torus_features.deficit_target_medium < torus_features.deficit_target_easy
    assert torus_features.excess_target_easy > math.pi
    assert torus_features.deficit_target_medium < math.pi

    manifold = world_config_for("torus_genus1").surface
    for mode, target, center in (
        ("excess", torus_features.excess_target_medium, torus_features.peak),
        ("deficit", torus_features.deficit_target_medium, torus_features.saddle),
    ):
        report = verify_triangle_feasibility(
            manifold,
            mode,
            target,
            "medium",
            center=center,
        )
        assert report["feasible"] is True
        assert report["attempts"] > 0


def test_deficit_quest_completes_on_the_saddle(torus_features) -> None:
    quest = GaussBonnetQuest(mode="deficit", difficulty="medium")
    assert quest.is_applicable(torus_features) is True
    target = quest.target_value(torus_features)
    result = quest.evaluate(torus_features, TriangleMeasurement(angle_sum=target - 0.01))
    assert result.completed is True
    assert result.detail["is_deficit"] is True
    assert result.detail["target_relation"] == "<="
    assert result.detail["area_flux_negative"] is True
    assert result.detail["angle_deficit_deg"] > 0.0


def test_medium_is_tighter_than_easy_for_both_modes(torus_features) -> None:
    easy_excess = GaussBonnetQuest(mode="excess", difficulty="easy").target_value(torus_features)
    medium_excess = GaussBonnetQuest(mode="excess", difficulty="medium").target_value(torus_features)
    easy_deficit = GaussBonnetQuest(mode="deficit", difficulty="easy").target_value(torus_features)
    medium_deficit = GaussBonnetQuest(mode="deficit", difficulty="medium").target_value(torus_features)

    assert medium_excess > easy_excess
    assert medium_deficit < easy_deficit
    assert easy_excess - math.pi == pytest.approx(
        TRIANGLE_DIFFICULTY_FRACTIONS["easy"] * max(0.0, torus_features.reference_excess),
        rel=0.2,
        abs=1e-6,
    )
    assert math.pi - medium_deficit == pytest.approx(
        TRIANGLE_DIFFICULTY_FRACTIONS["medium"] * max(0.0, torus_features.reference_deficit),
        rel=0.2,
        abs=1e-6,
    )


def test_quest_manager_dispatches_a_deficit_variant_deterministically(torus_features) -> None:
    first = QuestManager(torus_features, seed=12345, difficulty="medium", gauss_mode="deficit")
    second = QuestManager(torus_features, seed=12345, difficulty="medium", gauss_mode="deficit")
    assert first.gauss_mode == "deficit"
    assert second.gauss_mode == "deficit"
    assert first.active_quest is not None
    assert first.active_quest.mode == "deficit"
    assert first.state_payload()["objective_relation"] == "<="