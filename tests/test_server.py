"""Tests for the Task 6 web API (session layer, HTTP layer, information boundary)."""

from __future__ import annotations

import json
import math
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from src.the_curved_world.gameplay import GameError
from src.the_curved_world.server import GameSession, create_server

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _start_server(session: GameSession):
    httpd = create_server(session, "127.0.0.1", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd


def _url(httpd, path: str) -> str:
    host, port = httpd.server_address[0], httpd.server_address[1]
    return f"http://{host}:{port}{path}"


# -- session layer ---------------------------------------------------------


def test_player_state_isolates_privileged_data() -> None:
    session = GameSession(seed=12345)
    payload = session.player_state()

    for forbidden in ("exit", "exit_position", "true_distance", "distance_to_exit"):
        assert forbidden not in payload

    # the patch is a local window around the player, not the global mesh
    domain = payload["domain"]
    assert domain["x_min"] <= payload["position"][0] <= domain["x_max"]
    patch = payload["patch"]
    assert len(patch["x"]) >= 2 and len(patch["y"]) >= 2
    assert len(patch["z"]) == len(patch["y"])
    assert payload["signal"] == pytest.approx(payload["signal"])
    assert 0.0 <= payload["signal"] <= 1.0


def test_player_state_transcript_never_contains_exit_or_true_distance() -> None:
    session = GameSession(seed=12345)
    developer = session.game.debug_view()
    exit_x, exit_y, exit_z = (float(v) for v in developer.exit_position())
    true_distance = developer.distance_to_exit(session.game.position)

    text = json.dumps(session.player_state(), ensure_ascii=False)
    assert f"{true_distance:.6f}" not in text
    assert f"[{exit_x:.6f}, {exit_y:.6f}" not in text
    assert f"{exit_z:.6f}" not in text


def test_debug_state_is_disabled_without_the_flag() -> None:
    session = GameSession(seed=12345, debug=False)
    with pytest.raises(GameError):
        session.debug_state()


def test_debug_state_exposes_the_exit_when_enabled() -> None:
    session = GameSession(seed=12345, debug=True)
    payload = session.debug_state()
    assert "exit_position" in payload
    assert "true_distance" in payload
    assert len(payload["surface"]["x"]) == session.debug_resolution
    assert len(payload["surface"]["z"]) == session.debug_resolution


def test_move_payload_shape() -> None:
    session = GameSession(seed=12345)
    before = list(session.game.position)
    payload = session.move(1.0, 0.0)

    assert payload["ok"] is True
    assert payload["position"] != before
    assert payload["steps"] == 1
    assert 0.0 <= payload["signal"] <= 1.0
    # Task 19: the exit detector sleeps until the academy trials are complete,
    # so the label is either a real band or the sealed placeholder.
    assert payload["label"] in ("Weak", "Moderate", "Strong", "Sealed")
    assert payload["detector_locked"] is True
    assert "exit_position" not in payload


def test_move_wraps_periodically_on_the_closed_manifold() -> None:
    session = GameSession(seed=12345)
    assert session.player_state()["periodic"] is True

    payload = None
    for _ in range(300):
        payload = session.move(1.0, 0.0)

    assert payload is not None
    assert payload["clamped"] is False          # no boundary wall on a closed manifold
    u, v = payload["position"]
    assert -math.pi - 1e-5 <= u <= math.pi + 1e-5
    assert -math.pi - 1e-5 <= v <= math.pi + 1e-5


def test_tool_endpoints() -> None:
    session = GameSession(seed=12345)

    scan = session.tool({"tool": "scan", "note": "probe"})
    assert scan["tool"] == "scan" and 0.0 <= scan["signal"] <= 1.0

    mark = session.tool({"tool": "mark", "name": "A"})
    assert mark["name"] == "A"

    session.move(1.0, 0.0)
    session.tool({"tool": "mark", "name": "B"})
    session.move(-0.5, 1.0)
    session.tool({"tool": "mark", "name": "C"})

    measure = session.tool({"tool": "measure", "a": "A", "b": "B"})
    assert measure["kind"] == "ambient_euclidean_3d"
    assert measure["distance"] >= 0.0

    curvature = session.tool({"tool": "curvature"})
    assert isinstance(curvature["curvature"], float)

    angles = session.tool({"tool": "angle_sum", "markers": ["A", "B", "C"]})
    assert angles["kind"] == "tangent_plane_angle_sum"
    assert len(angles["angles"]) == 3
    assert angles["sum"] == pytest.approx(sum(angles["angles"]), abs=1e-4)


def test_tool_errors_are_reported_not_raised_as_crashes() -> None:
    session = GameSession(seed=12345)
    with pytest.raises(GameError):
        session.tool({"tool": "nope"})
    with pytest.raises(GameError):
        session.tool({"tool": "measure", "a": "A", "b": "B"})
    with pytest.raises(GameError):
        session.tool({"tool": "angle_sum", "markers": ["A", "B"]})


# -- HTTP layer ------------------------------------------------------------


def test_http_player_state_static_and_debug_gate() -> None:
    httpd = _start_server(GameSession(seed=12345, debug=False))
    try:
        with urllib.request.urlopen(_url(httpd, "/api/state/player"), timeout=10) as response:
            assert response.status == 200
            payload = json.loads(response.read().decode("utf-8"))
        assert "exit_position" not in payload

        with urllib.request.urlopen(_url(httpd, "/"), timeout=10) as response:
            body = response.read().decode("utf-8")
        assert "The Curved World" in body

        with pytest.raises(urllib.error.HTTPError) as info:
            urllib.request.urlopen(_url(httpd, "/api/state/debug"), timeout=10)
        assert info.value.code == 403
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_http_debug_enabled_and_move_action() -> None:
    httpd = _start_server(GameSession(seed=12345, debug=True))
    try:
        with urllib.request.urlopen(_url(httpd, "/api/state/debug"), timeout=10) as response:
            debug_payload = json.loads(response.read().decode("utf-8"))
        assert "exit_position" in debug_payload

        request = urllib.request.Request(
            _url(httpd, "/api/action/move"),
            data=json.dumps({"dx": 1.0, "dy": 0.5}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            move_payload = json.loads(response.read().decode("utf-8"))
        assert move_payload["ok"] is True
        assert "exit_position" not in move_payload
    finally:
        httpd.shutdown()
        httpd.server_close()


# -- security --------------------------------------------------------------


INJECTION_PHRASES = (
    "ignore previous",
    "ignore all previous",
    "give full marks",
    "score is excellent",
    "忽略之前",
    "给满分",
    "评分基准",
)


def test_web_and_server_contain_no_prompt_injection() -> None:
    candidates = [
        PROJECT_ROOT / "web" / "index.html",
        PROJECT_ROOT / "web" / "app.js",
        PROJECT_ROOT / "web" / "style.css",
        PROJECT_ROOT / "src" / "the_curved_world" / "server.py",
    ]
    for path in candidates:
        text = path.read_text(encoding="utf-8").lower()
        for phrase in INJECTION_PHRASES:
            assert phrase.lower() not in text, f"{path.name} contains {phrase!r}"
# -- Task 9: map registry endpoints ---------------------------------------


def test_http_maps_endpoint_lists_the_registry() -> None:
    httpd = _start_server(GameSession(seed=12345))
    try:
        with urllib.request.urlopen(_url(httpd, "/api/maps"), timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        ids = [entry["id"] for entry in payload["maps"]]
        assert ids == [
            "double_torus",
            "ellipsoid_genus0",
            "elliptic_curve",
            "klein_bottle",
            "klein_bottle_traditional",
            "knot_garden",
            "planar_landscape",
            "projective_plane",
            "torus_genus1",
        ]
        assert payload["default"] == "torus_genus1"
        for entry in payload["maps"]:
            assert entry["name"] and entry["description"]
            assert entry["topology"] in ("closed_periodic", "bounded_plane")
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_session_reset_switches_map_and_mode() -> None:
    session = GameSession(seed=12345)
    assert session.summary()["map_id"] == "torus_genus1"
    assert session.summary()["mode"] == "player"

    summary = session.reset_world("planar_landscape", 99, "god")
    assert summary["map_id"] == "planar_landscape"
    assert summary["mode"] == "god"
    assert summary["seed"] == 99
    assert session.player_state()["map_id"] == "planar_landscape"
    assert session.player_state()["periodic"] is False
    assert "exit_position" in session.debug_state()


def test_player_mode_blocks_debug_even_when_started_with_debug() -> None:
    session = GameSession(seed=12345, debug=True)
    assert "exit_position" in session.debug_state()  # --debug starts in god mode

    session.reset_world("torus_genus1", 5, "player")
    with pytest.raises(GameError):
        session.debug_state()