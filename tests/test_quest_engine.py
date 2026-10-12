"""Task 18: manifold feasibility scanner, quest engine and exit-seal tests."""

from __future__ import annotations

import json
import math

import pytest

from src.the_curved_world.manifold import wrap_parameter
from src.the_curved_world.maps import MapRegistry, world_config_for
from src.the_curved_world.quest import (
    GaussBonnetQuest,
    GeometricQuest,
    QuestManager,
    QuestResult,
    TriangleMeasurement,
)
from src.the_curved_world.scanner import clear_scan_cache, scan_manifold
from src.the_curved_world.server import GameSession
from src.the_curved_world.world import WorldGenerator


def _reference_markers(features):
    """The exact triangle the scanner used, in wrapped parameter coordinates."""
    angles = (
        math.pi / 2.0,
        math.pi / 2.0 + 2.0 * math.pi / 3.0,
        math.pi / 2.0 + 4.0 * math.pi / 3.0,
    )
    return [
        (
            wrap_parameter(features.peak[0] + features.reference_radius * math.cos(angle)),
            wrap_parameter(features.peak[1] + features.reference_radius * math.sin(angle)),
        )
        for angle in angles
    ]


def test_scanner_extracts_curvature_extremes_and_topology() -> None:
    clear_scan_cache()
    torus = scan_manifold(world_config_for("torus_genus1").surface, genus_hint=1)
    assert torus.closed is True
    assert torus.genus == 1
    assert torus.k_max > 0.0 > torus.k_min
    assert torus.has_parabolic_line is True
    assert torus.reference_excess > 0.0

    ellipsoid = scan_manifold(world_config_for("ellipsoid_genus0").surface, genus_hint=0)
    assert ellipsoid.closed is True
    assert ellipsoid.genus == 0
    assert ellipsoid.k_max >= ellipsoid.k_min

    planar = scan_manifold(world_config_for("planar_landscape").surface)
    assert planar.closed is False
    assert planar.genus is None

    # the cache is keyed by the surface, so a second scan returns the same object
    assert scan_manifold(world_config_for("torus_genus1").surface, genus_hint=1) is torus


def test_adaptive_target_stays_inside_the_physical_window() -> None:
    quest = GaussBonnetQuest()
    for map_id in MapRegistry.ids():
        features = scan_manifold(
            world_config_for(map_id).surface,
            genus_hint=MapRegistry.get(map_id).genus,
        )
        if not quest.is_applicable(features):
            continue
        target = quest.target_value(features)
        assert target > math.pi
        assert target < math.pi + features.reference_excess + 1e-12
        # the reference triangle itself always passes: never unwinnable
        result = quest.evaluate(features, TriangleMeasurement(angle_sum=features.reference_angle_sum))
        assert result.completed is True
        assert 0.0 < result.progress <= 1.0


def test_quest_manager_completes_and_awards_the_relic() -> None:
    features = scan_manifold(world_config_for("torus_genus1").surface, genus_hint=1)
    manager = QuestManager(features, seed=12345)
    assert manager.exit_sealed is True
    assert manager.active_quest is not None
    assert manager.active_quest.id == "gauss_bonnet_excess"

    result = manager.evaluate_measurement(
        TriangleMeasurement(angle_sum=features.reference_angle_sum, markers=("A", "B", "C"))
    )
    assert result is not None and result.completed is True
    assert manager.exit_unlocked is True
    assert manager.relics == ("Curvature Seal",)
    assert manager.completed_quests == ("gauss_bonnet_excess",)


def test_quest_manager_filters_inapplicable_quests() -> None:
    class ImpossibleLoopQuest(GeometricQuest):
        id = "non_contractible_loop"
        title = "Non-contractible Loop"
        description = "Only meaningful on a surface with at least two holes."
        hint = "N/A"

        def is_applicable(self, features) -> bool:  # type: ignore[override]
            return bool(features.genus is not None and features.genus >= 2)

        def target_value(self, features) -> float:  # type: ignore[override]
            return 0.0

        def evaluate(self, features, measurement) -> QuestResult:  # type: ignore[override]
            return QuestResult(self.id, False, 0.0, 0.0, 0.0, {})

    features = scan_manifold(world_config_for("ellipsoid_genus0").surface, genus_hint=0)
    first = QuestManager(features, seed=7, quests=[ImpossibleLoopQuest(), GaussBonnetQuest()])
    second = QuestManager(features, seed=7, quests=[ImpossibleLoopQuest(), GaussBonnetQuest()])

    assert first.chain == second.chain  # deterministic
    assert "non_contractible_loop" not in first.chain  # filtered by the scanner
    assert first.active_quest is not None and first.active_quest.id == "gauss_bonnet_excess"


def test_exit_seal_blocks_victory_until_the_quest_is_complete() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    manager = session.game.quest_manager
    assert manager is not None
    features = manager.features
    world = WorldGenerator(world_config_for("torus_genus1")).generate(12345)

    # standing on the hidden exit while sealed must not end the run
    session.game.sync_position(float(world.exit[0]), float(world.exit[1]))
    state = session.player_state()
    assert state["won"] is False
    assert state["quest"]["exit_sealed"] is True
    assert state["quest"]["seal_contact"] is True

    for name, (u, v) in zip(("A", "B", "C"), _reference_markers(features)):
        session.game.sync_position(u, v)
        session.tool({"tool": "mark", "name": name})

    # step back onto the (still sealed) exit and finish the quest from there
    session.game.sync_position(float(world.exit[0]), float(world.exit[1]))
    assert session.game.won is False
    response = session.tool({"tool": "triangle", "markers": ["A", "B", "C"]})
    assert response["quest_completed"] is True
    assert response["proof"]["relic"] == "Curvature Seal"
    assert len(response["proof"]["steps"]) >= 4
    assert response["quest"]["exit_sealed"] is False
    assert response["quest"]["relics"] == ["Curvature Seal"]
    # the player was standing on the exit when the seal opened
    assert session.game.won is True


def test_quest_payload_never_leaks_hidden_state() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    state = session.player_state()
    text = json.dumps(state, ensure_ascii=False)
    assert "exit_position" not in text
    assert "true_distance" not in text
    features = state["quest"]["features"]
    assert set(features) == {
        "k_max",
        "k_min",
        "k_mean",
        "has_parabolic_line",
        "genus",
        "closed",
        "has_positive_peak",
    }
    # no raw parameter peak / coordinate hatch is shipped to the player
    assert "peak" not in features
    assert "position" not in state["quest"]