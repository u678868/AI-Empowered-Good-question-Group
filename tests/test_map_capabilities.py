"""Cross-map capability and unified tool contract tests."""

from __future__ import annotations

from src.the_curved_world.maps import MapRegistry
from src.the_curved_world.server import GameSession


EXPECTED_CAPABILITIES = {
    "movement",
    "markers",
    "ropes",
    "measurement",
    "circumcircle",
    "quests",
}


def test_every_map_publishes_the_same_standard_capabilities() -> None:
    for entry in MapRegistry.list_maps():
        capabilities = entry["capabilities"]
        assert set(capabilities["tools"]) == EXPECTED_CAPABILITIES
        for key in EXPECTED_CAPABILITIES - {"movement"}:
            assert capabilities[key] is True, entry["id"]


def test_circumcircle_pull_is_available_on_every_map() -> None:
    for map_id in MapRegistry.ids():
        session = GameSession(seed=11, map_id=map_id, mode="player")
        domain = session.game.player_view.surface.domain
        center = (
            0.5 * (domain.x_min + domain.x_max),
            0.5 * (domain.y_min + domain.y_max),
        )
        delta = 0.03 * min(domain.width, domain.height)
        points = (
            (center[0] + delta, center[1]),
            (center[0] - 0.5 * delta, center[1] + delta),
            (center[0] - 0.5 * delta, center[1] - delta),
        )
        for name, point in zip(("A", "B", "C"), points):
            session.game.sync_position(*point)
            session.tool({"tool": "mark", "name": name})
        for first, second in (("A", "B"), ("B", "C"), ("C", "A")):
            session.tool({
                "tool": "rope_connect",
                "from_type": "marker",
                "from_id": first,
                "to_type": "marker",
                "to_id": second,
            })
        result = session.tool({
            "tool": "rope_pull_circumcircle",
            "markers": ["A", "B", "C"],
        })
        assert result["ok"] is True, map_id
        assert result["circumcircle"]["kind"] == "circumcircle", map_id
        assert result["circumcircle"]["perimeter"] > 0.0, map_id

def test_standard_measurement_tools_are_available_on_every_map() -> None:
    for map_id in MapRegistry.ids():
        session = GameSession(seed=17, map_id=map_id, mode="player")
        domain = session.game.player_view.surface.domain
        center = (0.5 * (domain.x_min + domain.x_max), 0.5 * (domain.y_min + domain.y_max))
        delta = 0.03 * min(domain.width, domain.height)
        points = (
            (center[0] + delta, center[1]),
            (center[0] - 0.5 * delta, center[1] + delta),
            (center[0] - 0.5 * delta, center[1] - delta),
        )
        for name, point in zip(("A", "B", "C"), points):
            session.game.sync_position(*point)
            session.tool({"tool": "mark", "name": name})
        for first, second in (("A", "B"), ("B", "C"), ("C", "A")):
            session.tool({
                "tool": "rope_connect",
                "from_type": "marker", "from_id": first,
                "to_type": "marker", "to_id": second,
            })

        rope_length = session.tool({
            "tool": "measure", "mode": "ruler",
            "targets": [{"type": "rope", "id": 0}],
        })
        assert rope_length["distance"] > 0.0, map_id

        node_distance = session.tool({
            "tool": "measure", "mode": "ruler",
            "targets": [
                {"type": "marker", "id": "A"},
                {"type": "marker", "id": "B"},
            ],
        })
        assert node_distance["distance"] > 0.0, map_id

        vertex_angle = session.tool({
            "tool": "measure", "mode": "angle",
            "targets": [{"type": "marker", "id": "A"}],
        })
        assert 0.0 <= vertex_angle["angle_degrees"] <= 180.0, map_id

        angle_sum = session.tool({
            "tool": "measure", "mode": "angle_sum",
            "targets": [
                {"type": "marker", "id": "A"},
                {"type": "marker", "id": "B"},
                {"type": "marker", "id": "C"},
            ],
        })
        assert 0.0 < angle_sum["angle_sum_degrees"] < 360.0, map_id

        triangle = session.tool({
            "tool": "measure", "mode": "protractor",
            "targets": ["A", "B", "C"],
        })
        assert 0.0 < triangle["sum"] < 3.0 * 3.141592653589793, map_id

