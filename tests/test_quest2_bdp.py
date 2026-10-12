"""Task 20: Bertrand-Diquet-Puisseux circle deficit quest tests."""

from __future__ import annotations

import math

import pytest

from src.the_curved_world.manifold import wrap_parameter
from src.the_curved_world.maps import MapRegistry, world_config_for
from src.the_curved_world.quest import (
    BertrandDiquetPuisseuxQuest,
    QuestManager,
    GaussBonnetQuest,
    HolonomyMeasurement,
    HomotopyMeasurement,
    ParabolicMeasurement,
    RingMeasurement,
)
from src.the_curved_world.ropes import RopeError, RopeNode, RopeSystem, circumradius_from_sides
from src.the_curved_world.scanner import metric_length, scan_manifold
from src.the_curved_world.server import GameSession


def _metric_ring(surface, features, count: int = 12, radius=None) -> RingMeasurement:
    """Build a constant-geodesic-radius ring measurement on the positive peak."""
    target = features.bdp_reference_radius_world if radius is None else float(radius)
    center = features.peak
    vertices = []
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        low, high = 1e-6, 0.5
        for _ in range(50):
            mid = 0.5 * (low + high)
            u = wrap_parameter(center[0] + mid * math.cos(angle))
            v = wrap_parameter(center[1] + mid * math.sin(angle))
            if metric_length(surface, center, (u, v)) < target:
                low = mid
            else:
                high = mid
        vertices.append(
            (
                wrap_parameter(center[0] + low * math.cos(angle)),
                wrap_parameter(center[1] + low * math.sin(angle)),
            )
        )
    samples = [metric_length(surface, center, point) for point in vertices]
    perimeter = sum(
        metric_length(surface, vertices[index], vertices[(index + 1) % count])
        for index in range(count)
    )
    return RingMeasurement(
        center_label="O",
        vertex_labels=tuple(f"P{index}" for index in range(count)),
        perimeter=float(perimeter),
        mean_radius=float(sum(samples) / count),
        radius_samples=tuple(float(value) for value in samples),
    )


def _place_roped_ring(session, features, count: int = 12) -> int:
    """Place center + ring markers and rope the ring through the real server API."""
    surface = session.game.player_view.surface
    center = features.peak
    session.game.sync_position(*center)
    session.tool({"tool": "mark", "name": "O"})
    ring = []
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        low, high = 1e-6, 0.5
        for _ in range(50):
            mid = 0.5 * (low + high)
            u = wrap_parameter(center[0] + mid * math.cos(angle))
            v = wrap_parameter(center[1] + mid * math.sin(angle))
            if metric_length(surface, center, (u, v)) < features.bdp_reference_radius_world:
                low = mid
            else:
                high = mid
        ring.append(
            (
                wrap_parameter(center[0] + low * math.cos(angle)),
                wrap_parameter(center[1] + low * math.sin(angle)),
            )
        )
    for index, (u, v) in enumerate(ring, start=1):
        session.game.sync_position(u, v)
        session.tool({"tool": "mark", "name": f"R{index}"})
    for index in range(count):
        session.tool({
            "tool": "rope_connect",
            "from_type": "marker", "from_id": f"R{index + 1}",
            "to_type": "marker", "to_id": f"R{(index + 1) % count + 1}",
        })
    return session.player_state()["ropes"][0]["id"]


def _complete_active_quest(session) -> None:
    manager = session.game.quest_manager
    quest = manager.active_quest
    if quest is None:
        return
    features = manager.features
    if quest.id == "gauss_bonnet_excess":
        angles = (
            math.pi / 2.0,
            math.pi / 2.0 + 2.0 * math.pi / 3.0,
            math.pi / 2.0 + 4.0 * math.pi / 3.0,
        )
        for name, angle in zip(("A", "B", "C"), angles):
            u = wrap_parameter(features.peak[0] + features.reference_radius * math.cos(angle))
            v = wrap_parameter(features.peak[1] + features.reference_radius * math.sin(angle))
            session.game.sync_position(u, v)
            session.tool({"tool": "mark", "name": name})
        session.tool({"tool": "measure", "mode": "protractor", "targets": ["A", "B", "C"]})
        return
    if quest.id == "bdp_circle_deficit":
        rope_id = _place_roped_ring(session, features)
        session.tool({"tool": "measure", "mode": "ruler", "targets": [{"type": "rope", "id": rope_id}]})
        return
    raise AssertionError(f"unexpected quest {quest.id}")


def test_scanner_bdp_threshold_is_loose_but_physical() -> None:
    for map_id in MapRegistry.ids():
        features = scan_manifold(
            world_config_for(map_id).surface,
            genus_hint=MapRegistry.get(map_id).genus,
        )
        assert 0.0 < features.bdp_ratio_target < 1.0
        # game_task7 deliberately uses a loose floor of a 1.5% deficit target
        assert features.bdp_ratio_target <= 1.0 - 0.015 + 1e-12
        assert features.bdp_ratio_target >= 1.0 - max(0.015, 0.60 * features.bdp_deficit_peak) - 1e-12
        # the reference ring must fit the 300 m rope pool
        assert 2.0 * math.pi * features.bdp_reference_radius_world < 320.0


def test_bdp_quest_is_applicable_on_the_default_torus() -> None:
    features = scan_manifold(world_config_for("torus_genus1").surface, genus_hint=1)
    assert BertrandDiquetPuisseuxQuest().is_applicable(features) is True
    assert features.k_max * features.bdp_reference_radius_world ** 2 <= 2.0


def test_bdp_quest_completes_with_a_constructed_metric_ring() -> None:
    surface = world_config_for("torus_genus1").surface
    features = scan_manifold(surface, genus_hint=1)
    quest = BertrandDiquetPuisseuxQuest()
    measurement = _metric_ring(surface, features, count=12)
    result = quest.evaluate_ring(features, measurement)
    assert result.completed is True
    assert result.detail["ratio"] <= features.bdp_ratio_target
    assert result.detail["k_estimate"] > 0.0
    assert result.detail["relic"] == "Metric Seal"
    assert len(result.detail["steps"]) == 5


def test_bdp_ring_through_the_server_awards_metric_seal_and_unlocks_detector() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    manager = session.game.quest_manager
    assert manager.chain[:2] == ("gauss_bonnet_excess", "bdp_circle_deficit")

    _complete_active_quest(session)
    first = session.player_state()
    assert "Curvature Seal" in first["quest"]["relics"]
    assert first["detector_locked"] is True

    _complete_active_quest(session)
    features = manager.features
    while manager.active_quest is not None:
        active = manager.active_quest
        if active.id == "holonomy_loop":
            manager.evaluate_holonomy_measurement(HolonomyMeasurement(
                start_label="A", vertex_labels=("A", "B", "C"),
                angle=features.holonomy_target_angle + 0.01,
            ))
        elif active.id == "parabolic_line":
            manager.evaluate_parabolic_measurement(ParabolicMeasurement(
                labels=("P1", "P2", "P3"), curvatures=(0.0, 0.0, 0.0),
                pairwise_distances=(features.parabolic_min_distance,) * 3,
            ))
        elif active.id == "homotopy_loop":
            manager.evaluate_homotopy_measurement(HomotopyMeasurement(
                origin_label="O", phase_u=2.0 * math.pi, phase_v=0.0,
                closure_distance=0.0, capture_radius=features.homotopy_capture_radius,
            ))
        else:
            raise AssertionError(f"unexpected quest {active.id}")

    state = session.player_state()
    assert "Metric Seal" in state["quest"]["relics"]
    assert state["quest"]["exit_sealed"] is False
    assert state["detector_locked"] is False
    assert state["label"] in ("Weak", "Moderate", "Strong")

def test_flat_circumradius_formula_for_three_four_five_triangle() -> None:
    # A 3-4-5 right triangle has hypotenuse as diameter, so R = 5 / 2.
    assert circumradius_from_sides(3.0, 4.0, 5.0) == pytest.approx(2.5)


def test_pull_circumcircle_blocks_when_rope_pool_is_insufficient() -> None:
    nodes = (
        RopeNode("marker", "A", "A", (0.0, 0.0), (0.0, 0.0, 0.0)),
        RopeNode("marker", "B", "B", (0.0, 0.1), (3.0, 0.0, 0.0)),
        RopeNode("marker", "C", "C", (0.1, 0.0), (0.0, 3.0, 0.0)),
    )
    ropes = RopeSystem(max_segment=100.0, total_pool=12.0)
    ropes.connect(nodes[0], nodes[1])
    ropes.connect(nodes[1], nodes[2])
    ropes.connect(nodes[2], nodes[0])
    with pytest.raises(RopeError, match="rope pool exhausted"):
        ropes.pull_circumcircle(
            nodes[0], nodes[1], nodes[2],
            surface=world_config_for("torus_genus1").surface,
        )


def test_pull_circumcircle_on_peak_awards_metric_seal_and_can_recover() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    features = session.game.quest_manager.features
    session._game._quest_manager = QuestManager(
        features, seed=1, quests=[BertrandDiquetPuisseuxQuest()]
    )
    surface = session.game.player_view.surface
    center = features.peak
    names = ("A", "B", "C")
    angles = (0.0, 2.0 * math.pi / 3.0, 4.0 * math.pi / 3.0)
    for name, angle in zip(names, angles):
        u = wrap_parameter(center[0] + 0.25 * features.reference_radius * math.cos(angle))
        v = wrap_parameter(center[1] + 0.25 * features.reference_radius * math.sin(angle))
        session.game.sync_position(u, v)
        session.tool({"tool": "mark", "name": name})
    for first, second in (("A", "B"), ("B", "C"), ("C", "A")):
        session.tool({
            "tool": "rope_connect",
            "from_type": "marker", "from_id": first,
            "to_type": "marker", "to_id": second,
        })

    before = session.player_state()["rope_remaining"]
    result = session.tool({"tool": "rope_pull_circumcircle", "markers": list(names)})
    assert result["quest_completed"] is True
    assert result["proof"]["relic"] == "Metric Seal"
    assert result["proof"]["detail"]["is_circumcircle"] is True
    assert result["proof"]["detail"]["flat_perimeter"] > result["proof"]["detail"]["perimeter"]
    assert result["circumcircle"]["kind"] == "circumcircle"
    assert session.player_state()["rope_remaining"] < before

    recovered = session.tool({"tool": "rope_recover_circumcircle"})
    assert recovered["removed"] == 1
    assert session.player_state()["circumcircles"] == []
    assert session.player_state()["rope_remaining"] == pytest.approx(before)

