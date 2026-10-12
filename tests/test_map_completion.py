"""Every built-in map can complete its applicable quest chain and win."""

from __future__ import annotations

import math

from src.the_curved_world.maps import MapRegistry, world_config_for
from src.the_curved_world.quest import (
    HolonomyMeasurement,
    HomotopyMeasurement,
    ParabolicMeasurement,
    RingMeasurement,
    TriangleMeasurement,
)
from src.the_curved_world.server import GameSession
from src.the_curved_world.world import WorldGenerator


def _complete_active_quest(session: GameSession) -> None:
    manager = session.game.quest_manager
    assert manager is not None
    quest = manager.active_quest
    if quest is None:
        return
    features = manager.features
    if quest.id == "gauss_bonnet_excess":
        manager.evaluate_measurement(TriangleMeasurement(
            angle_sum=features.reference_angle_sum,
            markers=("A", "B", "C"),
        ))
        return
    if quest.id == "bdp_circle_deficit":
        radius = features.bdp_reference_radius_world
        manager.evaluate_ring_measurement(RingMeasurement(
            center_label="O",
            vertex_labels=tuple(f"R{i}" for i in range(12)),
            perimeter=0.5 * 2.0 * math.pi * radius,
            mean_radius=radius,
            flat_perimeter=2.0 * math.pi * radius,
            is_circumcircle=True,
        ))
        return
    if quest.id == "holonomy_loop":
        manager.evaluate_holonomy_measurement(HolonomyMeasurement(
            start_label="A",
            vertex_labels=("A", "B", "C"),
            angle=features.holonomy_target_angle + 0.01,
        ))
        return
    if quest.id == "parabolic_line":
        manager.evaluate_parabolic_measurement(ParabolicMeasurement(
            labels=("P1", "P2", "P3"),
            curvatures=(0.0, 0.0, 0.0),
            pairwise_distances=(features.parabolic_min_distance,) * 3,
        ))
        return
    if quest.id == "homotopy_loop":
        manager.evaluate_homotopy_measurement(HomotopyMeasurement(
            origin_label="O",
            phase_u=2.0 * math.pi,
            phase_v=0.0,
            closure_distance=0.0,
            capture_radius=features.homotopy_capture_radius,
        ))
        return
    raise AssertionError(f"unknown active quest {quest.id}")


def test_every_map_can_unlock_and_reach_the_exit() -> None:
    for map_id in MapRegistry.ids():
        session = GameSession(seed=12345, map_id=map_id, mode="player")
        manager = session.game.quest_manager
        assert manager is not None
        while manager.active_quest is not None:
            _complete_active_quest(session)
        assert manager.exit_unlocked is True, map_id

        world = WorldGenerator(world_config_for(map_id)).generate(12345)
        session.game.sync_position(float(world.exit[0]), float(world.exit[1]))
        assert session.game.won is True, map_id
