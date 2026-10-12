"""Task 19: finite rope system, dual measurement tool and the sealed detector."""

from __future__ import annotations

import json
import math

import numpy as np

import pytest

from src.the_curved_world.gameplay import GameError
from src.the_curved_world.manifold import wrap_parameter
from src.the_curved_world.ropes import RopeError, RopeNode, RopeSystem
from src.the_curved_world.server import GameSession


def _node(kind: str, node_id: str, position) -> RopeNode:
    return RopeNode(kind, node_id, node_id, (0.0, 0.0), tuple(float(v) for v in position))


def _reference_markers(features):
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


def _close_marker_session() -> GameSession:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    start = session.game.position
    offsets = (("A", (0.0, 0.0)), ("B", (0.15, 0.0)), ("C", (0.0, 0.1)))
    for name, (du, dv) in offsets:
        session.game.sync_position(wrap_parameter(start[0] + du), wrap_parameter(start[1] + dv))
        session.tool({"tool": "mark", "name": name})
    return session


def test_rope_system_supports_all_node_combinations() -> None:
    system = RopeSystem(max_segment=30.0, total_pool=100.0)
    marker_a = _node("marker", "A", (0, 0, 0))
    marker_b = _node("marker", "B", (3, 4, 0))
    rock = _node("obstacle", "9", (6, 8, 0))
    rock_two = _node("obstacle", "10", (6, 0, 0))

    first = system.connect(marker_a, marker_b)
    second = system.connect(marker_b, rock)
    third = system.connect(rock, rock_two)

    assert first.length_3d == pytest.approx(5.0)
    assert second.is_obstacle_b is True
    assert third.is_obstacle_a is True and third.is_obstacle_b is True
    assert system.remaining == pytest.approx(100.0 - (5.0 + 5.0 + 8.0))

    with pytest.raises(RopeError):
        system.connect(marker_a, marker_b)  # duplicate
    with pytest.raises(RopeError):
        system.connect(marker_a, marker_a)  # self connection

    assert system.clear(first.id) == 1
    assert system.remaining == pytest.approx(100.0 - 13.0)
    assert system.clear() == 2
    assert system.remaining == pytest.approx(100.0)
    assert system.ropes == ()


def test_overlong_segment_and_pool_exhaustion_are_rejected() -> None:
    system = RopeSystem(max_segment=30.0, total_pool=100.0)
    origin = _node("marker", "A", (0, 0, 0))
    with pytest.raises(RopeError):
        system.connect(origin, _node("marker", "F", (100, 0, 0)))

    stops = [_node("marker", f"P{index}", (25 * index, 0, 0)) for index in range(5)]
    for index in range(4):
        system.connect(stops[index], stops[index + 1])
    assert system.remaining == pytest.approx(0.0)
    with pytest.raises(RopeError):
        system.connect(stops[4], _node("marker", "Q", (101, 0, 0)))


def test_rope_connect_and_ruler_measurement() -> None:
    session = _close_marker_session()
    connected = session.tool({
        "tool": "rope_connect",
        "from_type": "marker", "from_id": "A",
        "to_type": "marker", "to_id": "B",
    })
    assert connected["rope"]["id"] == 0
    assert 0.0 < connected["rope"]["length_3d"] <= 100.0
    assert connected["rope_remaining"] < connected["rope_total"]

    ruler = session.tool({"tool": "measure", "mode": "ruler", "targets": [{"type": "rope", "id": 0}]})
    assert ruler["kind"] == "rope_length"
    assert ruler["distance"] == pytest.approx(connected["rope"]["length_3d"])

    two_nodes = session.tool({
        "tool": "measure",
        "mode": "ruler",
        "targets": [{"type": "marker", "id": "A"}, {"type": "marker", "id": "B"}],
    })
    assert two_nodes["kind"] == "node_distance"
    assert two_nodes["distance"] == pytest.approx(ruler["distance"])


def test_rope_rejects_unknown_invisible_or_self_endpoints() -> None:
    session = _close_marker_session()
    with pytest.raises(GameError):
        session.tool({
            "tool": "rope_connect",
            "from_type": "marker", "from_id": "ZZ",
            "to_type": "marker", "to_id": "A",
        })
    with pytest.raises(GameError):
        session.tool({
            "tool": "rope_connect",
            "from_type": "marker", "from_id": "A",
            "to_type": "obstacle", "to_id": 999999,
        })
    with pytest.raises(GameError):
        session.tool({
            "tool": "rope_connect",
            "from_type": "marker", "from_id": "A",
            "to_type": "marker", "to_id": "A",
        })


def test_overlong_marker_pair_is_rejected_on_the_server() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    surface = session.game.player_view.surface
    start = session.game.position
    start_point = np.asarray(surface.position(*start), dtype=float)
    far = None
    for offset in (math.pi, 2.0, 1.5):
        candidate = (start[0], wrap_parameter(start[1] + offset))
        distance = float(np.linalg.norm(np.asarray(surface.position(*candidate), dtype=float) - start_point))
        if distance > 120.0:
            far = candidate
            break
    assert far is not None
    for name, point in (("A", start), ("B", far)):
        session.game.sync_position(*point)
        session.tool({"tool": "mark", "name": name})
    with pytest.raises(GameError):
        session.tool({
            "tool": "rope_connect",
            "from_type": "marker", "from_id": "A",
            "to_type": "marker", "to_id": "B",
        })


def test_protractor_rope_triangle_measures_and_reports_quest_progress() -> None:
    session = _close_marker_session()
    for first, second in (("A", "B"), ("B", "C"), ("A", "C")):
        session.tool({
            "tool": "rope_connect",
            "from_type": "marker", "from_id": first,
            "to_type": "marker", "to_id": second,
        })
    result = session.tool({
        "tool": "measure",
        "mode": "protractor",
        "targets": [{"type": "rope", "id": 0}, {"type": "rope", "id": 1}, {"type": "rope", "id": 2}],
    })
    assert result["kind"] == "rope_triangle_angle_sum"
    assert len(result["nodes"]) == 3
    assert result["sum"] == pytest.approx(math.pi, abs=0.2)
    # a <=100 m rope triangle is still a local patch on the huge torus, so the
    # big Gauss-Bonnet target is not reached by it; the quest state is reported.
    assert result["quest_completed"] is False
    assert "quest" in result


def test_protractor_marker_triangle_completes_quest_one() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    features = session.game.quest_manager.features
    for name, (u, v) in zip(("A", "B", "C"), _reference_markers(features)):
        session.game.sync_position(u, v)
        session.tool({"tool": "mark", "name": name})

    result = session.tool({"tool": "measure", "mode": "protractor", "targets": ["A", "B", "C"]})
    assert result["kind"] == "triangle_angle_sum"
    assert result["quest_completed"] is True
    assert result["proof"]["relic"] == "Curvature Seal"
    assert result["quest"]["exit_sealed"] is False


def test_detector_is_sealed_until_the_quest_is_complete() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    state = session.player_state()
    assert state["detector_locked"] is True
    assert state["signal"] == 0.0
    assert state["label"] == "Sealed"

    scan = session.tool({"tool": "scan"})
    assert scan["locked"] is True
    assert scan["signal"] == 0.0
    assert scan["label"] == "Sealed"

    features = session.game.quest_manager.features
    for name, (u, v) in zip(("A", "B", "C"), _reference_markers(features)):
        session.game.sync_position(u, v)
        session.tool({"tool": "mark", "name": name})
    session.tool({"tool": "measure", "mode": "protractor", "targets": ["A", "B", "C"]})

    after = session.player_state()
    assert after["detector_locked"] is False
    assert after["label"] in ("Weak", "Moderate", "Strong")
    assert after["signal"] > 0.0


def test_rope_payload_only_contains_player_known_nodes() -> None:
    session = _close_marker_session()
    obstacles = session.player_state()["obstacles"]
    assert obstacles
    session.game.sync_position(obstacles[0]["u"] + 0.15, obstacles[0]["v"])
    session.tool({"tool": "mark", "name": "D"})
    connected = session.tool({
        "tool": "rope_connect",
        "from_type": "marker", "from_id": "D",
        "to_type": "obstacle", "to_id": obstacles[0]["id"],
    })
    assert connected["rope"]["a"]["type"] == "marker"
    assert connected["rope"]["b"]["type"] == "obstacle"

    state = session.player_state()
    assert state["rope_remaining"] < state["rope_total"]
    assert all(rope["a"]["type"] in ("marker", "obstacle") for rope in state["ropes"])
    text = json.dumps(state, ensure_ascii=False)
    assert "exit_position" not in text
    assert "true_distance" not in text

def test_path_point_binds_at_most_two_ropes() -> None:
    system = RopeSystem(max_segment=30.0, total_pool=100.0)
    a = _node("marker", "A", (0, 0, 0))
    b = _node("marker", "B", (3, 0, 0))
    c = _node("marker", "C", (6, 0, 0))
    d = _node("marker", "D", (3, 4, 0))
    system.connect(a, b)
    system.connect(b, c)
    with pytest.raises(RopeError):
        system.connect(b, d)


def test_angle_mode_returns_one_vertex_and_angle_sum_needs_three() -> None:
    session = _close_marker_session()
    for first, second in (("A", "B"), ("B", "C"), ("A", "C")):
        session.tool({
            "tool": "rope_connect",
            "from_type": "marker", "from_id": first,
            "to_type": "marker", "to_id": second,
        })
    # one click measures one vertex only and must NOT finish the quest
    single = session.tool({
        "tool": "measure",
        "mode": "angle",
        "targets": [{"type": "marker", "id": "A"}],
    })
    assert single["kind"] == "node_angle"
    assert 0.0 < single["angle_degrees"] < 180.0
    assert "angle_sum_degrees" not in single
    assert "quest_completed" not in single

    # after all three vertex angles the sum is evaluated once and may complete
    summed = session.tool({
        "tool": "measure",
        "mode": "angle_sum",
        "targets": [{"type": "marker", "id": "A"}, {"type": "marker", "id": "B"}, {"type": "marker", "id": "C"}],
    })
    assert summed["kind"] == "rope_triangle_angle"
    assert summed["angle_sum_degrees"] == pytest.approx(180.0, abs=15.0)
    assert "quest" in summed

def test_default_rope_limits_fit_the_large_maps() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    state = session.player_state()
    assert state["rope_max_segment"] == pytest.approx(100.0)
    assert state["rope_total"] == pytest.approx(300.0)
    assert state["rope_remaining"] == pytest.approx(300.0)
