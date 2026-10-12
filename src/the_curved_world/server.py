"""Lightweight local HTTP API and static file server for The Curved World (Task 6).

The Python *mathematical kernel* stays authoritative (deterministic world
generation, analytic geometry and curvature, detector decay, information
boundary). A small browser front-end provides the interaction and the two
views. Only the standard library is used -- no new runtime dependency.

Information boundary (CRITICAL): the player endpoints never expose the hidden
exit or the true distance. The privileged ``/api/state/debug`` endpoint only
exists when the server is started with ``debug=True``.
"""

from __future__ import annotations

import json
import math
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

import numpy as np

from src.the_curved_world.config import ConfigError, WorldConfig, default_config
from src.the_curved_world.maps import DEFAULT_MAP_ID, MapNotFound, MapRegistry, map_id_for, world_config_for
from src.the_curved_world.gameplay import ExplorationGame, GameError, GameplayConfig
from src.the_curved_world.observations import ObservationConfig
from src.the_curved_world.world import WorldGenerator

WEB_ROOT = Path(__file__).resolve().parents[2] / "web"

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


class GameSession:
    """Owns one exploration game and turns actions/state into JSON payloads.

    This class is deliberately independent of HTTP so it can be unit tested
    without sockets.
    """

    def __init__(
        self,
        seed: Optional[int] = 12345,
        *,
        map_id: Optional[str] = None,
        world_config: Optional[WorldConfig] = None,
        gameplay_config: Optional[GameplayConfig] = None,
        observation_config: Optional[ObservationConfig] = None,
        mode: Optional[str] = None,
        debug: bool = False,
        patch_radius: Optional[float] = None,
        patch_resolution: int = 49,
        debug_resolution: int = 61,
    ) -> None:
        self.startup_debug = bool(debug)
        if world_config is None:
            self.map_id = map_id or DEFAULT_MAP_ID
            self.world_config = world_config_for(self.map_id)
        else:
            self.world_config = world_config
            self.map_id = map_id or map_id_for(world_config)
        self.mode = mode if mode in ("player", "god") else ("god" if debug else "player")
        self.debug = self.startup_debug
        self._last_collided = False
        self.gameplay_config = GameplayConfig() if gameplay_config is None else gameplay_config
        self.observation_config = ObservationConfig() if observation_config is None else observation_config
        self.patch_radius = None if patch_radius is None else float(patch_radius)
        self.patch_resolution = int(patch_resolution)
        self.debug_resolution = int(debug_resolution)
        self._generator = WorldGenerator(self.world_config)
        self.seed = seed
        self._game = self._build(seed)

    # -- lifecycle ---------------------------------------------------------

    @property
    def game(self) -> ExplorationGame:
        return self._game

    def reset(self, seed: Optional[int] = None) -> None:
        self.seed = seed
        self._game = self._build(seed)

    def reset_world(self, map_id: Optional[str] = None, seed: Optional[int] = None, mode: Optional[str] = None) -> Dict[str, Any]:
        """Rebuild the world from a map id, seed and play mode (lobby entry)."""
        if map_id is not None:
            self.map_id = str(map_id)
            self.world_config = world_config_for(self.map_id)
            self._generator = WorldGenerator(self.world_config)
        if mode in ("player", "god"):
            self.mode = mode
        self.reset(seed)
        return self.summary()

    def summary(self) -> Dict[str, Any]:
        """Current session identity (map, mode, seed)."""
        return {
            "map_id": self.map_id,
            "mode": self.mode,
            "seed": self._game.summary().seed,
            "periodic": bool(getattr(self._game.player_view.surface, "periodic", False)),
            **self._chart_payload(),
        }

    def _build(self, seed: Optional[int]) -> ExplorationGame:
        world = self._generator.generate(seed)
        return ExplorationGame(world, self.gameplay_config, self.observation_config)

    # -- payload helpers ---------------------------------------------------

    @property
    def effective_patch_radius(self) -> float:
        """Patch radius: explicit if given, else a fraction of the parameter domain."""
        if self.patch_radius is not None:
            return float(self.patch_radius)
        domain = self._game.player_view.surface.domain
        return 0.22 * min(domain.width, domain.height)
    def _domain_payload(self) -> Dict[str, float]:
        domain = self._game.player_view.surface.domain
        return {
            "x_min": _round(domain.x_min),
            "x_max": _round(domain.x_max),
            "y_min": _round(domain.y_min),
            "y_max": _round(domain.y_max),
        }

    def _chart_payload(self) -> Dict[str, Any]:
        """How the chart identifies its own points (periods and sheets).

        The front-end must wrap parameter deltas exactly the way the kernel
        does. That is ``2 pi`` per axis for the torus-like charts, but the Klein
        bottle needs ``4 pi`` in ``u`` because a ``2 pi`` shift there mirrors
        ``v`` -- and it carries two chart copies of every surface point. The
        projective plane carries four. ``chart_copies`` publishes those sheets as
        ``[du, dv, flip_v]`` triples so the browser never has to guess.

        This payload stays purely geometric: it says nothing about the hidden
        exit.
        """
        surface = self._game.player_view.surface
        periods = getattr(surface, "chart_periods", None)
        period_u, period_v = periods() if callable(periods) else (2.0 * math.pi, 2.0 * math.pi)
        transforms = getattr(surface, "chart_copy_transforms", None)
        copies = transforms() if callable(transforms) else ((0.0, 0.0, False),)
        return {
            "twisted": bool(getattr(surface, "twisted", False)),
            "orientable": bool(getattr(surface, "orientable", True)),
            "chart_periods": [_round(period_u), _round(period_v)],
            "chart_copies": [[_round(du), _round(dv), bool(flip)] for du, dv, flip in copies],
        }

    def _observation_payload(self) -> Dict[str, Any]:
        observation = self._game.peek_detector()
        return {
            "signal": _round(observation.signal),
            "label": observation.label,
            "trend": observation.trend,
        }

    def _surface_patch(self, position) -> Dict[str, Any]:
        """Local patch centred on the player, plus its first fundamental form.

        The window is deliberately centred (never clamped) so the player is
        always in the middle of the view. ``E``, ``F`` and ``G`` are the first
        fundamental form coefficients the front-end uses to compress or stretch
        the coordinate grid -- the visual hint that the world is not flat.
        """
        surface = self._game.player_view.surface
        x, y = float(position[0]), float(position[1])
        count = max(2, self.patch_resolution)
        radius = self.effective_patch_radius
        xs = np.linspace(x - radius, x + radius, count)
        ys = np.linspace(y - radius, y + radius, count)
        grid_x, grid_y = np.meshgrid(xs, ys)
        # Full embedded coordinates are needed for the first-person projection;
        # z alone (the graph-surface analogue) is not enough on a manifold.
        points = np.asarray(surface.position(grid_x, grid_y), dtype=float)
        grid_x3, grid_y3, grid_z = points[..., 0], points[..., 1], points[..., 2]
        grid_e, grid_f, grid_g = surface.first_fundamental_form(grid_x, grid_y)
        player_point = np.asarray(surface.position(x, y), dtype=float)
        vision_radius = float(np.max(np.linalg.norm(points - player_point, axis=-1)))

        def rows(grid):
            return [[_round(v) for v in row] for row in grid]

        return {
            "x": [_round(v) for v in xs],
            "y": [_round(v) for v in ys],
            "radius": _round(radius),
            "vision_radius": _round(vision_radius),
            "X": rows(grid_x3),
            "Y": rows(grid_y3),
            "z": rows(grid_z),
            "E": rows(grid_e),
            "F": rows(grid_f),
            "G": rows(grid_g),
        }
    def _visible_obstacles(self, patch: Dict[str, Any], position) -> List[Dict[str, Any]]:
        """Obstacles inside the rendered patch only -- far ones are never sent."""
        field = getattr(self._game, "_obstacles", None)
        if field is None or len(field) == 0:
            return []
        radius = float(patch.get("vision_radius", 0.0))
        point = np.asarray(self._game.player_view.position(position), dtype=float)
        visible: List[Dict[str, Any]] = []
        for obstacle in field.obstacles:
            # Measured with the world's own distance policy, so a quotient world
            # (projective plane) treats an antipodal twin as the same place.
            distance = field.nearest_realization(point, obstacle)[1]
            if distance > radius:
                continue
            visible.append({**obstacle.to_dict(), "distance": _round(distance)})
        visible.sort(key=lambda entry: entry["distance"])
        return visible
    # -- player-facing state ----------------------------------------------

    def player_state(self) -> Dict[str, Any]:
        """Player-visible state. Never contains the exit or the true distance."""
        game = self._game
        position = game.position
        position3d = game.player_view.position(position)
        patch = self._surface_patch(position)
        local_obstacles = self._visible_obstacles(patch, position)
        return {
            "seed": game.summary().seed,
            "periodic": bool(getattr(game.player_view.surface, "periodic", False)),
            "map_id": self.map_id,
            "mode": self.mode,
            "domain": self._domain_payload(),
            **self._chart_payload(),
            "position": [_round(position[0]), _round(position[1])],
            "position3d": [_round(v) for v in position3d],
            "curvature": _round(game.curvature(), 8),
            "patch": patch,
            "obstacles": local_obstacles,
            "local_obstacles": local_obstacles,
            "camera_position_3d": [_round(v) for v in game.camera_position()],
            "eye_height": _round(game.eye_height),
            "slope": {key: _round(value, 6) for key, value in game.last_slope.items()},
            "collided": bool(self._last_collided),
            "trajectory": [[_round(px), _round(py)] for px, py in game.trajectory],
            "markers": [
                {
                    "name": marker.name,
                    "position": [_round(marker.position[0]), _round(marker.position[1])],
                    "signal": _round(marker.signal),
                    "label": marker.label,
                }
                for marker in game.markers
            ],
            "steps": game.steps,
            "pointer_uses_remaining": game.pointer_uses_remaining,
            "yaw": _round(game.yaw, 6),
            "forward_3d": [_round(v) for v in game.frame()["forward"]],
            "right_3d": [_round(v) for v in game.frame()["right"]],
            "up_3d": [_round(v) for v in game.frame()["up"]],
            "elapsed_time": _round(game.elapsed_time),
            "won": bool(game.won),
            **self._observation_payload(),
        }

    def debug_state(self) -> Dict[str, Any]:
        """Privileged state. Only available when the server was started with debug=True."""
        if self.mode != "god":
            # player mode never exposes privileged state, whatever the client asks
            raise GameError(
                "debug endpoint is disabled in player mode; choose god mode in the lobby "
                "or start the server with --debug"
            )
        game = self._game
        developer = game.debug_view()
        surface = game.player_view.surface
        domain = surface.domain
        count = max(2, self.debug_resolution)
        grid_x, grid_y, grid_z = surface.sample_grid(count, count)

        def rows(grid):
            return [[_round(v) for v in row] for row in grid]

        describe = getattr(surface, "describe", None)
        if callable(describe):
            model = {"kind": surface.name, "parameters": list(describe())}
        else:
            surface_config = developer.surface_config
            model = {
                "kind": "height field",
                "wave": {
                    "amplitude": _round(surface_config.wave.amplitude),
                    "kx": _round(surface_config.wave.kx),
                    "ky": _round(surface_config.wave.ky),
                },
                "hills": [
                    {
                        "amplitude": _round(hill.amplitude),
                        "center_x": _round(hill.center_x),
                        "center_y": _round(hill.center_y),
                        "scale": _round(hill.scale),
                    }
                    for hill in surface_config.hills
                ],
            }
        return {
            "seed": developer.seed,
            "domain": self._domain_payload(),
            "periodic": bool(getattr(surface, "periodic", False)),
            "surface": {"x": rows(grid_x), "y": rows(grid_y), "z": rows(grid_z)},
            "obstacles": (self._game._obstacles.to_list() if getattr(self._game, "_obstacles", None) is not None else []),
            "surface_config": model,
            "start_position": [_round(v) for v in developer.start_position()],
            "exit_position": [_round(v) for v in developer.exit_position()],
            "player_position": [_round(v) for v in game.player_view.position(game.position)],
            "true_distance": _round(developer.distance_to_exit(game.position)),
        }

    # -- actions -----------------------------------------------------------

    def _move_payload(self, result) -> Dict[str, Any]:
        self._last_collided = bool(getattr(result, "collided", False))
        position3d = self._game.player_view.position(result.position)
        return {
            "ok": True,
            "position": [_round(result.position[0]), _round(result.position[1])],
            "position3d": [_round(v) for v in position3d],
            "moved": bool(result.moved),
            "clamped": bool(result.clamped),
            "collided": bool(getattr(result, "collided", False)),
            "won": bool(result.won),
            "steps": self._game.steps,
            "yaw": _round(self._game.yaw, 6),
            **self._observation_payload(),
        }

    @staticmethod
    def _step_count(steps) -> int:
        try:
            count = int(steps)
        except (TypeError, ValueError):
            raise GameError(f"steps must be an integer, got {steps!r}")
        return max(1, min(10, count))

    def move(self, dx: float, dy: float, steps: int = 1) -> Dict[str, Any]:
        """Legacy parameter-space move (kept for compatibility)."""
        count = self._step_count(steps)
        result = self._game.move(float(dx), float(dy))
        for _ in range(count - 1):
            if not result.moved:
                break
            result = self._game.move(float(dx), float(dy))
        return self._move_payload(result)

    def sync_position(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Low-frequency client sync: adopt the local (u, v) and answer with world facts."""
        u = payload.get("u")
        v = payload.get("v")
        if u is None or v is None:
            raise GameError("sync_position requires u and v")
        try:
            result = self._game.sync_position(float(u), float(v))
        except (TypeError, ValueError) as exc:
            raise GameError(f"u and v must be numbers: {exc}") from exc
        patch = self._surface_patch(result.position)
        position3d = self._game.player_view.position(result.position)
        return {
            "ok": True,
            "position": [_round(result.position[0]), _round(result.position[1])],
            "position3d": [_round(value) for value in position3d],
            "camera_position_3d": [_round(value) for value in self._game.camera_position()],
            "won": bool(result.won),
            "steps": self._game.steps,
            "curvature": _round(self._game.curvature(), 8),
            "slope": {key: _round(value, 6) for key, value in self._game.last_slope.items()},
            "patch": patch,
            "obstacles": self._visible_obstacles(patch, result.position),
            **self._chart_payload(),
            **self._observation_payload(),
        }
    def step_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """First-person action: turn the view and/or step along the heading.

        Body: ``{"action": "step", "direction": "forward", "angle": 0.1, "steps": 1}``.
        ``direction`` is optional, so a pure rotation is allowed.
        """
        angle = payload.get("angle")
        if angle is not None:
            try:
                self._game.turn(float(angle))
            except (TypeError, ValueError) as exc:
                raise GameError(f"angle must be a number, got {angle!r}") from exc

        direction = payload.get("direction")
        if not direction:
            position3d = self._game.player_view.position(self._game.position)
            return {
                "ok": True,
                "moved": False,
                "clamped": False,
                "collided": False,
                "won": bool(self._game.won),
                "steps": self._game.steps,
                "yaw": _round(self._game.yaw, 6),
                "position": [_round(self._game.position[0]), _round(self._game.position[1])],
                "position3d": [_round(v) for v in position3d],
                **self._chart_payload(),
                **self._observation_payload(),
            }

        count = self._step_count(payload.get("steps", 1))
        return self._move_payload(self._game.move_relative(str(direction), count))
    def tool(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tool = str(payload.get("tool", "")).strip().lower()
        game = self._game

        if tool == "scan":
            observation = game.read_detector(payload.get("note"))
            return {
                "ok": True,
                "tool": "scan",
                "signal": _round(observation.signal),
                "label": observation.label,
                "trend": observation.trend,
                "readings": len(game.log),
            }
        if tool == "mark":
            marker = game.place_marker(str(payload.get("name", "")))
            return {
                "ok": True,
                "tool": "mark",
                "name": marker.name,
                "position": [_round(marker.position[0]), _round(marker.position[1])],
                "signal": _round(marker.signal),
                "label": marker.label,
            }
        if tool == "measure":
            distance = game.distance_between_markers(str(payload.get("a", "")), str(payload.get("b", "")))
            return {
                "ok": True,
                "tool": "measure",
                "a": str(payload.get("a", "")),
                "b": str(payload.get("b", "")),
                "distance": _round(distance),
                "kind": "ambient_euclidean_3d",
            }
        if tool == "curvature":
            return {"ok": True, "tool": "curvature", "curvature": _round(game.curvature(), 8)}
        if tool == "angle_sum":
            names = payload.get("markers")
            if not isinstance(names, (list, tuple)) or len(names) != 3:
                raise GameError("angle_sum requires exactly three marker names")
            result = game.triangle_angle_sum(str(names[0]), str(names[1]), str(names[2]))
            return {
                "ok": True,
                "tool": "angle_sum",
                "markers": [str(name) for name in names],
                "angles": [_round(value, 6) for value in result["angles"]],
                "sum": _round(result["sum"], 6),
                "excess": _round(result["excess"], 6),
                "kind": "tangent_plane_angle_sum",
            }
        if tool == "triangle":
            names = payload.get("markers")
            if not isinstance(names, (list, tuple)) or len(names) != 3:
                raise GameError("triangle requires exactly three marker names")
            report = game.triangle_report(str(names[0]), str(names[1]), str(names[2]))
            return {
                "ok": True,
                "tool": "triangle",
                "markers": [str(name) for name in names],
                "angles": [_round(value, 6) for value in report["angles"]],
                "sum": _round(report["sum"], 6),
                "excess": _round(report["excess"], 6),
                "curvature_integral": _round(report["curvature_integral"], 8),
                "gauss_bonnet_residual": _round(report["gauss_bonnet_residual"], 8),
                "parameter_area": _round(report["parameter_area"], 6),
                "samples": report["samples"],
                "character": report["character"],
                "kind": report["kind"],
            }
        if tool == "pointer":
            hint = game.release_pointer()
            return {
                "ok": True,
                "tool": "pointer",
                "bearing_degrees": hint["bearing_degrees"],
                "pitch_degrees": hint["pitch_degrees"],
                "tangent_direction": hint["tangent_direction"],
                "sector_width_degrees": hint["sector_width_degrees"],
                "uses_remaining": hint["uses_remaining"],
                "kind": hint["kind"],
            }
        raise GameError(f"unknown tool {tool!r}")


class CurvedWorldHandler(BaseHTTPRequestHandler):
    """Serves the JSON API and the static web front-end."""

    server_version = "TheCurvedWorld/0.1"
    session: GameSession = None  # type: ignore[assignment]
    web_root: Path = WEB_ROOT

    def log_message(self, fmt: str, *args: Any) -> None:  # keep console quiet
        return

    # -- helpers -----------------------------------------------------------

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GameError(f"invalid JSON body: {exc}") from exc
        if not isinstance(data, dict):
            raise GameError("JSON body must be an object")
        return data

    # -- routes ------------------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        path = urlparse(self.path).path
        if path == "/api/maps":
            self._send_json(200, {"maps": MapRegistry.list_maps(), "default": DEFAULT_MAP_ID})
            return
        if path == "/api/state/player":
            self._send_json(200, self.session.player_state())
            return
        if path == "/api/state/debug":
            try:
                self._send_json(200, self.session.debug_state())
            except GameError as exc:
                self._send_json(403, {"error": str(exc)})
            return
        if path.startswith("/api/"):
            self._send_json(404, {"error": f"unknown endpoint {path}"})
            return
        self._serve_static(path)

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/action/sync_position":
                self._send_json(200, self.session.sync_position(payload))
                return
            if path == "/api/session/new":
                self._send_json(200, self.session.reset_world(
                    payload.get("map_id"), payload.get("seed"), payload.get("mode")
                ))
                return
            if path == "/api/action/move":
                if payload.get("action") == "step" or "direction" in payload or "angle" in payload:
                    self._send_json(200, self.session.step_action(payload))
                else:
                    self._send_json(200, self.session.move(payload.get("dx", 0.0), payload.get("dy", 0.0), payload.get("steps", 1)))
                return
            if path == "/api/action/tool":
                self._send_json(200, self.session.tool(payload))
                return
        except (GameError, ConfigError, MapNotFound) as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except (TypeError, ValueError) as exc:
            self._send_json(400, {"error": f"invalid request: {exc}"})
            return

        if path.startswith("/api/"):
            self._send_json(404, {"error": f"unknown endpoint {path}"})
        else:
            self._send_json(405, {"error": "POST is only supported on /api/action/*"})

    def _serve_static(self, path: str) -> None:
        relative = unquote(path).lstrip("/")
        if not relative or relative.endswith("/"):
            relative = relative + "index.html"
        root = self.web_root.resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            self._send_json(403, {"error": "forbidden"})
            return
        if not candidate.is_file():
            self._send_json(404, {"error": "not found"})
            return
        body = candidate.read_bytes()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            CONTENT_TYPES.get(candidate.suffix.lower(), "application/octet-stream"),
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def create_server(
    session: GameSession,
    host: str = "127.0.0.1",
    port: int = 8000,
    web_root: Optional[Path] = None,
) -> ThreadingHTTPServer:
    """Build a threaded HTTP server bound to ``session``."""
    handler = type(
        "BoundCurvedWorldHandler",
        (CurvedWorldHandler,),
        {"session": session, "web_root": Path(web_root) if web_root is not None else WEB_ROOT},
    )
    httpd = ThreadingHTTPServer((host, port), handler)
    httpd.daemon_threads = True
    return httpd


def serve(
    seed: Optional[int] = 12345,
    *,
    host: str = "127.0.0.1",
    port: int = 8000,
    debug: bool = False,
    map_id: Optional[str] = None,
    world_config: Optional[WorldConfig] = None,
    echo=print,
) -> None:
    """Run the blocking local web server."""
    session = GameSession(seed=seed, map_id=map_id, world_config=world_config, debug=debug)
    httpd = create_server(session, host, port)
    url = f"http://{host}:{httpd.server_address[1]}/"
    echo("The Curved World - web session")
    echo(f"  UI        : {url}")
    echo(f"  player API: {url}api/state/player")
    echo(f"  debug API : {'enabled' if debug else 'disabled (start with --debug)'}")
    echo("Press Ctrl+C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        echo("")
    finally:
        httpd.server_close()