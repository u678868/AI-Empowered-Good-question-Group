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
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

import numpy as np

from src.the_curved_world.config import ConfigError, WorldConfig, default_config
from src.the_curved_world.maps import DEFAULT_MAP_ID, MapNotFound, MapRegistry, map_id_for, world_config_for
from src.the_curved_world.gameplay import ExplorationGame, GameError, GameplayConfig
from src.the_curved_world.observations import ObservationConfig
from src.the_curved_world.quest import HolonomyMeasurement, ParabolicMeasurement, QuestManager, RingMeasurement
from src.the_curved_world.ropes import RopeNode
from src.the_curved_world.differential import (
    asymptotic_direction,
    parallel_transport_polyline,
    principal_curvatures,
)
from src.the_curved_world.manifold import wrap_parameter
from src.the_curved_world.scanner import metric_length, scan_manifold
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


DIFFICULTY_TIERS = ("easy", "medium", "hard")


def node_key_for(node) -> tuple:
    """(kind, id) tuple used to match rope endpoints."""
    return (str(node.kind), str(node.id))


def _normalized_difficulty(value: Any) -> str:
    key = str(value if value is not None else "easy").strip().lower()
    if key not in DIFFICULTY_TIERS:
        raise GameError(
            f"difficulty must be one of {', '.join(DIFFICULTY_TIERS)}; got {value!r}"
        )
    return key


def _validated_scale(value: Any) -> float:
    try:
        scale = float(value)
    except (TypeError, ValueError) as exc:
        raise GameError(f"scale must be a number within [0.2, 10.0]; got {value!r}") from exc
    if not np.isfinite(scale) or not (0.2 <= scale <= 10.0):
        raise GameError(f"scale must be within [0.2, 10.0]; got {value!r}")
    return scale


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
        scale_factor: float = 1.0,
        difficulty: str = "easy",
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
        try:
            metadata = MapRegistry.get(self.map_id)
            self.capabilities = metadata.capabilities.to_dict()
        except MapNotFound:
            from src.the_curved_world.maps.map_capabilities import MapCapabilities
            self.capabilities = MapCapabilities().to_dict()
        self.scale_factor = _validated_scale(scale_factor)
        self.difficulty = _normalized_difficulty(difficulty)
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

    def reset_world(
        self,
        map_id: Optional[str] = None,
        seed: Optional[int] = None,
        mode: Optional[str] = None,
        scale: Optional[float] = None,
        difficulty: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Rebuild the world from a map id, seed, mode, geometric scale and difficulty."""
        if scale is not None:
            self.scale_factor = _validated_scale(scale)
        if difficulty is not None:
            self.difficulty = _normalized_difficulty(difficulty)
        if map_id is not None:
            self.map_id = str(map_id)
            self.world_config = world_config_for(self.map_id)
            self._generator = WorldGenerator(self.world_config)
            try:
                self.capabilities = MapRegistry.get(self.map_id).capabilities.to_dict()
            except MapNotFound:
                from src.the_curved_world.maps.map_capabilities import MapCapabilities
                self.capabilities = MapCapabilities().to_dict()
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
            "scale_factor": _round(self.scale_factor),
            "difficulty": self.difficulty,
            "capabilities": dict(self.capabilities),
            **self._chart_payload(),
        }

    def _build(self, seed: Optional[int]) -> ExplorationGame:
        world_config = replace(
            self.world_config, scale_factor=self.scale_factor, difficulty=self.difficulty
        )
        gameplay_config = replace(
            self.gameplay_config, scale_factor=self.scale_factor, difficulty=self.difficulty
        )
        self._generator = WorldGenerator(world_config)
        world = self._generator.generate(seed)
        genus_hint = None
        try:
            genus_hint = MapRegistry.get(self.map_id).genus
        except MapNotFound:
            genus_hint = None
        obstacles = getattr(world, "obstacles", None)
        blocked = (
            lambda u, v: bool(obstacles.check_collision(float(u), float(v), 0.0))
            if obstacles is not None
            else False
        )
        features = scan_manifold(
            world.surface,
            samples=31,
            genus_hint=genus_hint,
            blocked=blocked,
            blocked_key=(int(world.seed), float(self.scale_factor)),
        )
        quest_manager = QuestManager(
            features,
            seed=int(world.seed),
            difficulty=self.difficulty,
        )
        self._holonomy_start_label = None
        self._holonomy_vector = (1.0, 0.0)
        self._holonomy_calibrated = False
        return ExplorationGame(
            world,
            gameplay_config,
            self.observation_config,
            quest_manager=quest_manager,
        )

    # -- payload helpers ---------------------------------------------------

    @property
    def effective_patch_radius(self) -> float:
        """Patch radius: explicit if given, else a fraction of the parameter domain."""
        scale = float(self.scale_factor) or 1.0
        if self.patch_radius is not None:
            return float(self.patch_radius) / scale
        domain = self._game.player_view.surface.domain
        return (0.22 * min(domain.width, domain.height)) / scale
    def _domain_payload(self) -> Dict[str, float]:
        domain = self._game.player_view.surface.domain
        return {
            "x_min": _round(domain.x_min),
            "x_max": _round(domain.x_max),
            "y_min": _round(domain.y_min),
            "y_max": _round(domain.y_max),
        }

    def _chart_payload(self) -> Dict[str, Any]:
        """Player-visible chart periods and sheet transforms for periodic maps."""
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

    def _require_capability(self, name: str) -> None:
        if not bool(self.capabilities.get(str(name), False)):
            raise GameError(f"the current map does not support {name}")

    def _observation_payload(self) -> Dict[str, Any]:
        if self.difficulty in ("medium", "hard"):
            # Task 17: medium strips the distance detector; hard is a reserved
            # placeholder. Both return a neutral reading with no distance cue.
            return {
                "signal": 0.0,
                "label": "Offline" if self.difficulty == "medium" else "Reserved",
                "trend": "same",
            }
        if self._game.detector_locked:
            # Task 19: the exit detector is sealed until the geometric trials are done.
            return {"signal": 0.0, "label": "Sealed", "trend": "same"}
        observation = self._game.peek_detector()
        return {
            "signal": _round(observation.signal),
            "label": observation.label,
            "trend": observation.trend,
        }

    def _scoring_payload(self) -> Dict[str, Any]:
        """Task 17: reserved scoring inputs; score itself is 0 until a formula lands."""
        return {
            "scale_factor": _round(self.scale_factor),
            "difficulty": self.difficulty,
            "difficulty_reserved": self.difficulty == "hard",
            "score": _round(self._game.score),
            "effective_steps": _round(self._game.effective_steps),
            "tool_usages": {key: int(value) for key, value in self._game.tool_usages.items()},
        }

    def _holonomy_payload(self) -> Dict[str, Any]:
        """Player-safe calibration and loop state for Quest 3."""
        manager = self._game.quest_manager
        quest = manager.active_quest if manager is not None else None
        if quest is None or quest.id != "holonomy_loop":
            return {}
        return {
            "calibrated": bool(self._holonomy_calibrated),
            "start_label": self._holonomy_start_label,
            "vector": [float(self._holonomy_vector[0]), float(self._holonomy_vector[1])],
        }

    @staticmethod
    def _short_metric_length(surface, first, second) -> float:
        """Metric length using the shortest periodic parameter representative."""
        first_uv = (float(first[0]), float(first[1]))
        second_uv = (float(second[0]), float(second[1]))
        du = second_uv[0] - first_uv[0]
        dv = second_uv[1] - first_uv[1]
        if bool(getattr(surface, "periodic", False)):
            du = wrap_parameter(du)
            dv = wrap_parameter(dv)
        return float(metric_length(surface, first_uv, (first_uv[0] + du, first_uv[1] + dv)))

    def _marker_uv(self, name: str):
        marker = next((item for item in self._game.markers if item.name == str(name)), None)
        if marker is None:
            raise GameError(f"unknown marker {name!r}")
        return marker

    def _measure_holonomy(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        game = self._game
        manager = game.quest_manager
        quest = manager.active_quest if manager is not None else None
        if quest is None or quest.id != "holonomy_loop":
            raise GameError("holonomy measurement requires the active holonomy quest")
        targets = payload.get("targets")
        if not isinstance(targets, (list, tuple)) or not targets:
            raise GameError("holonomy measurement needs marker names or one closed rope loop")
        points = []
        labels = []
        first = targets[0]
        if isinstance(first, dict) and str(first.get("type", "")).lower() == "rope":
            if len(targets) != 1:
                raise GameError("holonomy with ropes expects one rope id")
            rope = game.rope_system.get(int(first.get("id")))
            loop = game.rope_system.closed_loop_containing(rope.id)
            if loop is None:
                raise GameError("the selected rope is not part of a closed loop")
            nodes, _ropes = loop
            for node in nodes:
                labels.append(str(node.label))
                points.append((float(node.uv[0]), float(node.uv[1])))
        else:
            for item in targets:
                if isinstance(item, dict):
                    name = str(item.get("id"))
                else:
                    name = str(item)
                marker = self._marker_uv(name)
                labels.append(marker.name)
                points.append((float(marker.position[0]), float(marker.position[1])))
        if len(points) < 3:
            raise GameError("holonomy loop needs at least three path points")
        start_label = str(payload.get("start") or (labels[0] if labels else ""))
        if self._holonomy_calibrated and self._holonomy_start_label == start_label:
            vector = self._holonomy_vector
        else:
            # The UI asks for an explicit calibration; this fallback keeps the
            # mathematical API usable for scripted tests without leaking any
            # hidden world state.
            vector = (1.0, 0.0)
        surface = game.player_view.surface
        transport = parallel_transport_polyline(
            surface,
            points,
            vector,
            samples_per_segment=32,
        )
        # Marker lists and rope cycles are treated as closed polygons: the
        # transport helper explicitly joins the last point back to the first.
        # A repeated first marker is also accepted, but it must not be required
        # from the player before the system can recognise the loop.
        closure_error = 0.0
        if len(points) > 1:
            same_first = (
                abs(float(points[0][0]) - float(points[-1][0])) < 1e-9
                and abs(float(points[0][1]) - float(points[-1][1])) < 1e-9
            )
            if not same_first and labels and labels[0] == labels[-1]:
                closure_error = 0.0
        measurement = HolonomyMeasurement(
            start_label=start_label,
            vertex_labels=tuple(labels),
            angle=float(transport["angle"]),
            closure_error=closure_error,
            vector_start=tuple(float(value) for value in transport["vector_start"]),
            vector_end=tuple(float(value) for value in transport["vector_end"]),
            steps=int(transport["steps"]),
        )
        completion = game.evaluate_holonomy_measurement(measurement)
        out = {
            "ok": True,
            "tool": "measure",
            "mode": "holonomy",
            "kind": "levi_civita_holonomy",
            "start": start_label,
            "vertices": labels,
            "angle_degrees": _round(math.degrees(measurement.angle), 6),
            "abs_angle_degrees": _round(math.degrees(abs(measurement.angle)), 6),
            "closure_error": _round(closure_error),
            "vector_start": [_round(value, 8) for value in measurement.vector_start],
            "vector_end": [_round(value, 8) for value in measurement.vector_end],
            "integration_steps": measurement.steps,
            "calibrated": bool(self._holonomy_calibrated and self._holonomy_start_label == start_label),
            "quest": game.quest_state(),
            "quest_completed": False,
        }
        if completion is not None:
            out.update({
                "quest": completion["quest"],
                "proof": completion["proof"],
                "quest_completed": True,
            })
        return out

    def _measure_parabolic(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        game = self._game
        manager = game.quest_manager
        quest = manager.active_quest if manager is not None else None
        if quest is None or quest.id != "parabolic_line":
            raise GameError("parabolic measurement requires the active parabolic quest")
        targets = payload.get("targets")
        if not isinstance(targets, (list, tuple)) or len(targets) != 3:
            raise GameError("parabolic validation needs exactly three marker names")
        markers = []
        for item in targets:
            name = str(item.get("id")) if isinstance(item, dict) else str(item)
            markers.append(self._marker_uv(name))
        points = [(float(marker.position[0]), float(marker.position[1])) for marker in markers]
        surface = game.player_view.surface
        curvatures = tuple(float(surface.gaussian_curvature(*point)) for point in points)
        principal = tuple(principal_curvatures(surface, *point) for point in points)
        asymptotic = tuple(asymptotic_direction(surface, *point) for point in points)
        distances = []
        for i in range(3):
            for j in range(i + 1, 3):
                distances.append(self._short_metric_length(surface, points[i], points[j]))
        measurement = ParabolicMeasurement(
            labels=tuple(marker.name for marker in markers),
            curvatures=curvatures,
            principal_curvatures=principal,
            asymptotic_directions=asymptotic,
            pairwise_distances=tuple(distances),
        )
        completion = game.evaluate_parabolic_measurement(measurement)
        out = {
            "ok": True,
            "tool": "measure",
            "mode": "parabolic",
            "kind": "parabolic_line",
            "labels": [marker.name for marker in markers],
            "curvatures": [_round(value, 10) for value in curvatures],
            "principal_curvatures": [[_round(a, 8), _round(b, 8)] for a, b in principal],
            "asymptotic_directions": [
                [_round(direction[0], 8), _round(direction[1], 8)]
                for direction in asymptotic
            ],
            "asymptotic_direction": [
                _round(asymptotic[0][0], 8),
                _round(asymptotic[0][1], 8),
            ] if asymptotic else [0.0, 0.0],
            "pairwise_distances": [_round(value) for value in distances],
            "tolerance": _round(float(manager.features.parabolic_tolerance), 10) if manager is not None else 0.0,
            "min_distance": _round(float(manager.features.parabolic_min_distance)) if manager is not None else 0.0,
            "quest": game.quest_state(),
            "quest_completed": False,
        }
        if completion is not None:
            out.update({
                "quest": completion["quest"],
                "proof": completion["proof"],
                "quest_completed": True,
            })
        return out

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
            delta = np.asarray(obstacle.position_3d, dtype=float) - point
            distance = float(np.linalg.norm(delta))
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
            "capabilities": dict(self.capabilities),
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
            "detector_locked": bool(game.detector_locked),
            "quest": game.quest_state(),
            "homotopy": game.homotopy_state(),
            "holonomy": self._holonomy_payload(),
            **game.rope_state(),
            **self._scoring_payload(),
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
            "detector_locked": bool(self._game.detector_locked),
            "quest": self._game.quest_state(),
            **self._chart_payload(),
            "homotopy": self._game.homotopy_state(),
            "holonomy": self._holonomy_payload(),
            **self._scoring_payload(),
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
            "detector_locked": bool(self._game.detector_locked),
            "quest": self._game.quest_state(),
            **self._game.rope_state(),
            **self._scoring_payload(),
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
                **self._observation_payload(),
            }

        count = self._step_count(payload.get("steps", 1))
        return self._move_payload(self._game.move_relative(str(direction), count))
    @staticmethod
    def _best_center_marker(game: ExplorationGame, nodes):
        """Pick the player marker closest to the ring centroid as the ring center (Task 20)."""
        loop_keys = {(node.kind, str(node.id)) for node in nodes}
        candidates = [marker for marker in game.markers if ("marker", marker.name) not in loop_keys]
        if not candidates:
            return None
        centroid = [
            sum(float(node.position_3d[index]) for node in nodes) / len(nodes) for index in range(3)
        ]
        best = None
        for marker in candidates:
            point = game.player_view.position(marker.position)
            distance = math.sqrt(sum((float(point[i]) - centroid[i]) ** 2 for i in range(3)))
            if best is None or distance < best[0]:
                best = (distance, marker)
        return None if best is None else best[1]

    def _ring_measurement(self, center, nodes, ropes) -> tuple:
        """Metric (geodesic-ish) ring measurement around a center peg (Task 20)."""
        surface = self._game.player_view.surface
        center_uv = (float(center.position[0]), float(center.position[1]))
        samples = [
            metric_length(surface, center_uv, (float(node.uv[0]), float(node.uv[1])))
            for node in nodes
        ]
        perimeter = 0.0
        for index, node in enumerate(nodes):
            nxt = nodes[(index + 1) % len(nodes)]
            perimeter += metric_length(
                surface,
                (float(node.uv[0]), float(node.uv[1])),
                (float(nxt.uv[0]), float(nxt.uv[1])),
            )
        mean_radius = sum(samples) / len(samples) if samples else 0.0
        rope_perimeter = sum(float(rope.length_3d) for rope in ropes)
        measurement = RingMeasurement(
            center_label=center.name,
            vertex_labels=tuple(node.label for node in nodes),
            perimeter=float(perimeter),
            mean_radius=float(mean_radius),
            radius_samples=tuple(float(value) for value in samples),
        )
        payload = {
            "center": center.name,
            "vertices": [node.label for node in nodes],
            "vertex_count": len(nodes),
            "perimeter": _round(perimeter),
            "mean_radius": _round(mean_radius),
            "radius_samples": [_round(value) for value in samples],
            "rope_perimeter": _round(rope_perimeter),
        }
        return payload, measurement

    @staticmethod
    def _circumcircle_measurement(circle) -> RingMeasurement:
        return RingMeasurement(
            center_label=str(circle.center_label),
            vertex_labels=tuple(str(label) for label in circle.labels),
            perimeter=float(circle.perimeter),
            mean_radius=float(circle.surface_radius),
            flat_perimeter=float(circle.flat_perimeter),
            center_curvature=float(circle.curvature),
            center=(float(circle.center[0]), float(circle.center[1])),
            triangle_labels=tuple(str(label) for label in circle.labels),
            is_circumcircle=True,
        )

    def _visible_obstacles_now(self) -> List[Dict[str, Any]]:
        position = self._game.position
        patch = self._surface_patch(position)
        return self._visible_obstacles(patch, position)

    def _resolve_rope_node(self, spec: Any, obstacles: List[Dict[str, Any]]) -> RopeNode:
        """Resolve a player-known rope endpoint (marker or in-view obstacle)."""
        if not isinstance(spec, dict):
            raise GameError("rope endpoints must be {type, id} objects")
        kind = str(spec.get("type", "")).strip().lower()
        raw_id = spec.get("id")
        if kind == "marker":
            name = str(raw_id)
            marker = next((m for m in self._game.markers if m.name == name), None)
            if marker is None:
                raise GameError(f"unknown marker {name!r}")
            point = self._game.player_view.position(marker.position)
            return RopeNode(
                "marker",
                marker.name,
                marker.name,
                (float(marker.position[0]), float(marker.position[1])),
                tuple(float(value) for value in point),
            )
        if kind == "obstacle":
            try:
                obstacle_id = int(raw_id)
            except (TypeError, ValueError) as exc:
                raise GameError(f"obstacle id must be an integer, got {raw_id!r}") from exc
            entry = next((item for item in obstacles if int(item["id"]) == obstacle_id), None)
            if entry is None:
                raise GameError("that obstacle is not in view")
            return RopeNode(
                "obstacle",
                str(obstacle_id),
                f"{entry.get('kind', 'obstacle')} #{obstacle_id}",
                (float(entry["u"]), float(entry["v"])),
                tuple(float(value) for value in entry["position"]),
            )
        raise GameError(f"unknown rope node type {kind!r}")

    def _measure_tool(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Task 19: ruler / protractor measurement modes."""
        mode = str(payload.get("mode", "")).strip().lower()
        targets = payload.get("targets")
        if not isinstance(targets, (list, tuple)) or not targets:
            raise GameError("measure requires a non-empty targets list")
        game = self._game
        if mode == "ruler":
            first = targets[0]
            if isinstance(first, dict) and str(first.get("type", "")).lower() == "circumcircle":
                circle = next(
                    (item for item in game.rope_system.circumcircles if item.id == int(first.get("id"))),
                    None,
                )
                if circle is None:
                    raise GameError("unknown circumcircle id")
                measurement = self._circumcircle_measurement(circle)
                out: Dict[str, Any] = {
                    "ok": True,
                    "tool": "measure",
                    "mode": "ruler",
                    "kind": "circumcircle_perimeter",
                    "circumcircle": circle.to_dict(),
                    "distance": _round(circle.perimeter),
                    "quest": game.quest_state(),
                    "quest_completed": False,
                }
                completion = game.evaluate_ring_measurement(measurement)
                if completion is not None:
                    out.update({
                        "quest": completion["quest"],
                        "proof": completion["proof"],
                        "quest_completed": True,
                    })
                return out
            if isinstance(first, dict) and str(first.get("type", "")).lower() == "rope":
                rope = game.rope_system.get(int(first.get("id")))
                out: Dict[str, Any] = {
                    "ok": True,
                    "tool": "measure",
                    "mode": "ruler",
                    "kind": "rope_length",
                    "rope_id": rope.id,
                    "distance": _round(rope.length_3d),
                }
                loop = game.rope_system.closed_loop_containing(rope.id)
                if loop is not None:
                    nodes, loop_ropes = loop
                    center = self._best_center_marker(game, nodes)
                    if center is not None:
                        payload, measurement = self._ring_measurement(center, nodes, loop_ropes)
                        out["ring"] = payload
                        completion = game.evaluate_ring_measurement(measurement)
                        if completion is not None:
                            out["quest_completed"] = True
                            out["quest"] = completion["quest"]
                            out["proof"] = completion["proof"]
                        else:
                            out["quest_completed"] = False
                            out["quest"] = game.quest_state()
                return out
            if len(targets) == 2:
                obstacles = self._visible_obstacles_now()
                nodes = [self._resolve_rope_node(item, obstacles) for item in targets]
                delta = [nodes[0].position_3d[i] - nodes[1].position_3d[i] for i in range(3)]
                distance = math.sqrt(sum(value * value for value in delta))
                return {
                    "ok": True,
                    "tool": "measure",
                    "mode": "ruler",
                    "kind": "node_distance",
                    "a": nodes[0].to_dict(),
                    "b": nodes[1].to_dict(),
                    "distance": _round(distance),
                }
            raise GameError("ruler mode needs one rope or two nodes")
        if mode == "angle":
            if len(targets) != 1:
                raise GameError("angle mode needs exactly one path point")
            obstacles = self._visible_obstacles_now()
            node = self._resolve_rope_node(targets[0], obstacles)
            ropes = game.rope_system.ropes_at(node)
            if len(ropes) != 2:
                raise GameError(
                    f"angle needs exactly two ropes at {node.label}; found {len(ropes)}"
                )

            def far_end(rope):
                if (rope.node_a.kind, rope.node_a.id) == (node.kind, node.id):
                    return rope.node_b
                return rope.node_a

            first = far_end(ropes[0])
            second = far_end(ropes[1])
            vec_a = [first.position_3d[i] - node.position_3d[i] for i in range(3)]
            vec_b = [second.position_3d[i] - node.position_3d[i] for i in range(3)]
            norm_a = math.sqrt(sum(value * value for value in vec_a))
            norm_b = math.sqrt(sum(value * value for value in vec_b))
            if norm_a < 1e-9 or norm_b < 1e-9:
                raise GameError("cannot measure an angle at a degenerate rope endpoint")
            cosine = sum(a * b for a, b in zip(vec_a, vec_b)) / (norm_a * norm_b)
            angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
            # One vertex only: the client collects all three vertex angles before
            # it asks for the triangle sum (Task 19 rework #4).
            return {
                "ok": True,
                "tool": "measure",
                "mode": "angle",
                "kind": "node_angle",
                "node": node.to_dict(),
                "far_nodes": [first.to_dict(), second.to_dict()],
                "ropes": [rope.id for rope in ropes],
                "angle_degrees": _round(angle, 6),
            }
        if mode == "angle_sum":
            if len(targets) != 3:
                raise GameError("angle_sum mode needs exactly three path points")
            obstacles = self._visible_obstacles_now()
            nodes = [self._resolve_rope_node(item, obstacles) for item in targets]
            surface = game.player_view.surface
            total = (
                surface.tangent_angle(nodes[0].uv, nodes[1].uv, nodes[2].uv)
                + surface.tangent_angle(nodes[1].uv, nodes[2].uv, nodes[0].uv)
                + surface.tangent_angle(nodes[2].uv, nodes[0].uv, nodes[1].uv)
            )
            excess = total - math.pi
            report = {
                "sum": total,
                "excess": excess,
                "markers": [node.label for node in nodes],
                "curvature_integral": 0.0,
            }
            return {
                "ok": True,
                "tool": "measure",
                "mode": "angle_sum",
                "kind": "rope_triangle_angle",
                "nodes": [node.to_dict() for node in nodes],
                "angle_sum_degrees": _round(math.degrees(total), 6),
                "excess_degrees": _round(math.degrees(excess), 6),
                **self._quest_tool_payload(game, report),
            }
        if mode == "protractor":
            if len(targets) == 3 and all(isinstance(item, str) for item in targets):
                names = [str(item) for item in targets]
                report = game.triangle_report(names[0], names[1], names[2])
                out = {
                    "ok": True,
                    "tool": "measure",
                    "mode": "protractor",
                    "kind": "triangle_angle_sum",
                    "markers": names,
                    "angles": [_round(value, 6) for value in report["angles"]],
                    "sum": _round(report["sum"], 6),
                    "excess": _round(report["excess"], 6),
                    "excess_degrees": _round(math.degrees(report["excess"]), 6),
                    "character": report["character"],
                }
                return {**out, **self._quest_tool_payload(game, report)}
            if len(targets) == 3 and all(
                isinstance(item, dict) and str(item.get("type", "")).lower() == "rope"
                for item in targets
            ):
                ropes = [game.rope_system.get(int(item.get("id"))) for item in targets]
                counts: Dict[Any, int] = {}
                nodes: Dict[Any, RopeNode] = {}
                for rope in ropes:
                    for node in (rope.node_a, rope.node_b):
                        key = (node.kind, node.id)
                        counts[key] = counts.get(key, 0) + 1
                        nodes[key] = node
                if len(nodes) != 3 or any(count != 2 for count in counts.values()):
                    raise GameError("three ropes must form a closed triangle over three nodes")
                ordered = list(nodes.values())
                a, b, c = ordered
                surface = game.player_view.surface
                total = (
                    surface.tangent_angle(a.uv, b.uv, c.uv)
                    + surface.tangent_angle(b.uv, c.uv, a.uv)
                    + surface.tangent_angle(c.uv, a.uv, b.uv)
                )
                excess = total - math.pi
                report = {
                    "sum": total,
                    "excess": excess,
                    "markers": [node.label for node in ordered],
                    "curvature_integral": 0.0,
                }
                return {
                    "ok": True,
                    "tool": "measure",
                    "mode": "protractor",
                    "kind": "rope_triangle_angle_sum",
                    "nodes": [node.to_dict() for node in ordered],
                    "sum": _round(total, 6),
                    "excess": _round(excess, 6),
                    "excess_degrees": _round(math.degrees(excess), 6),
                    **self._quest_tool_payload(game, report),
                }
            if len(targets) == 2:
                ropes = [
                    game.rope_system.get(int(item.get("id")))
                    for item in targets
                    if isinstance(item, dict) and str(item.get("type", "")).lower() == "rope"
                ]
                if len(ropes) != 2:
                    raise GameError("protractor with two ropes needs two rope targets")
                shared = None
                for node_a in (ropes[0].node_a, ropes[0].node_b):
                    for node_b in (ropes[1].node_a, ropes[1].node_b):
                        if node_a.kind == node_b.kind and node_a.id == node_b.id:
                            shared = node_a
                if shared is None:
                    raise GameError("the two ropes do not share a node")

                def other_end(rope, node):
                    if (rope.node_a.kind, rope.node_a.id) == (node.kind, node.id):
                        return rope.node_b
                    return rope.node_a

                first = other_end(ropes[0], shared)
                second = other_end(ropes[1], shared)
                vec_a = [first.position_3d[i] - shared.position_3d[i] for i in range(3)]
                vec_b = [second.position_3d[i] - shared.position_3d[i] for i in range(3)]
                norm_a = math.sqrt(sum(value * value for value in vec_a))
                norm_b = math.sqrt(sum(value * value for value in vec_b))
                if norm_a < 1e-9 or norm_b < 1e-9:
                    raise GameError("cannot measure an angle at a degenerate rope endpoint")
                cosine = sum(a * b for a, b in zip(vec_a, vec_b)) / (norm_a * norm_b)
                angle = math.degrees(math.acos(max(-1.0, min(1.0, cosine))))
                return {
                    "ok": True,
                    "tool": "measure",
                    "mode": "protractor",
                    "kind": "rope_angle",
                    "shared_node": shared.to_dict(),
                    "angle_degrees": _round(angle, 6),
                }
            raise GameError("protractor mode needs three markers or two ropes")
        raise GameError(f"unknown measure mode {mode!r}")

    def _quest_tool_payload(self, game: ExplorationGame, report: Dict[str, Any]) -> Dict[str, Any]:
        """Task 18: quest progress + optional completion/proof for a goniometer use."""
        completion = game.evaluate_triangle_measurement(report)
        if completion is None:
            return {
                "quest_completed": False,
                "quest": game.quest_state(),
            }
        return {
            "quest_completed": True,
            "quest": completion["quest"],
            "proof": completion["proof"],
        }

    def tool(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        tool = str(payload.get("tool", "")).strip().lower()
        game = self._game

        if tool == "scan":
            silent = self.difficulty in ("medium", "hard")
            if silent:
                game.read_detector(payload.get("note"))
                return {
                    "ok": True,
                    "tool": "scan",
                    "signal": 0.0,
                    "label": "Offline" if self.difficulty == "medium" else "Reserved",
                    "trend": "same",
                    "readings": len(game.log),
                }
            if game.detector_locked:
                # Task 19: the seal sleeps the detector until the trials are done.
                return {
                    "ok": True,
                    "tool": "scan",
                    "signal": 0.0,
                    "label": "Sealed",
                    "trend": "same",
                    "locked": True,
                    "readings": len(game.log),
                }
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
            self._require_capability("markers")
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
            self._require_capability("measurement")
            mode = str(payload.get("mode", "")).strip().lower()
            if mode == "holonomy_calibrate":
                targets = payload.get("targets", [])
                if not isinstance(targets, (list, tuple)) or not targets:
                    raise GameError("holonomy calibrate needs a marker")
                first = targets[0]
                name = str(first.get("id")) if isinstance(first, dict) else str(first)
                calibrated = game.calibrate_tangent_vector(name)
                self._holonomy_start_label = str(calibrated["marker"])
                self._holonomy_vector = (float(calibrated["vector"][0]), float(calibrated["vector"][1]))
                self._holonomy_calibrated = True
                return {
                    "ok": True,
                    "tool": "measure",
                    "mode": "holonomy_calibrate",
                    "kind": "parallel_vector_calibrated",
                    "calibrated": True,
                    "marker": self._holonomy_start_label,
                    "vector": [round(float(self._holonomy_vector[0]), 8), round(float(self._holonomy_vector[1]), 8)],
                    "heading_radians": _round(calibrated["heading_radians"]),
                    "quest": game.quest_state(),
                    "holonomy": self._holonomy_payload(),
                }
            if mode == "holonomy":
                return self._measure_holonomy(payload)
            if mode == "parabolic":
                return self._measure_parabolic(payload)
            if mode == "homotopy":
                manager = game.quest_manager
                active = manager.active_quest if manager is not None else None
                if active is None or active.id != "homotopy_loop":
                    raise GameError("homotopy measurement requires the active homotopy quest")
                completion = game.evaluate_homotopy_measurement(payload.get("origin"))
                out = {
                    "ok": True,
                    "tool": "measure",
                    "mode": "homotopy",
                    "kind": "non_contractible_homotopy",
                    "homotopy": game.homotopy_state(),
                    "quest": game.quest_state(),
                    "quest_completed": False,
                }
                if completion is not None:
                    out.update({
                        "quest": completion["quest"],
                        "proof": completion["proof"],
                        "quest_completed": True,
                    })
                return out
            if mode in ("ruler", "protractor", "angle", "angle_sum"):
                return self._measure_tool(payload)
            distance = game.distance_between_markers(str(payload.get("a", "")), str(payload.get("b", "")))
            return {
                "ok": True,
                "tool": "measure",
                "a": str(payload.get("a", "")),
                "b": str(payload.get("b", "")),
                "distance": _round(distance),
                "kind": "ambient_euclidean_3d",
            }
        if tool == "rope_connect":
            self._require_capability("ropes")
            obstacles = self._visible_obstacles_now()
            node_a = self._resolve_rope_node(
                {"type": payload.get("from_type"), "id": payload.get("from_id")}, obstacles
            )
            node_b = self._resolve_rope_node(
                {"type": payload.get("to_type"), "id": payload.get("to_id")}, obstacles
            )
            rope = game.connect_rope(node_a, node_b)
            return {"ok": True, "tool": "rope_connect", "rope": rope.to_dict(), **game.rope_state()}
        if tool == "rope_pull_circumcircle":
            self._require_capability("circumcircle")
            names = payload.get("markers")
            if not isinstance(names, (list, tuple)) or len(names) != 3:
                raise GameError("rope_pull_circumcircle requires exactly three marker names")
            nodes = [self._resolve_rope_node(
                {"type": "marker", "id": name}, self._visible_obstacles_now()
            ) for name in names]
            circle = game.pull_circumcircle(nodes[0], nodes[1], nodes[2])
            measurement = self._circumcircle_measurement(circle)
            out: Dict[str, Any] = {
                "ok": True,
                "tool": "rope_pull_circumcircle",
                "kind": "circumcircle",
                "circumcircle": circle.to_dict(),
                "quest": game.quest_state(),
                "quest_completed": False,
                **game.rope_state(),
            }
            completion = game.evaluate_ring_measurement(measurement)
            if completion is not None:
                out.update({
                    "quest": completion["quest"],
                    "proof": completion["proof"],
                    "quest_completed": True,
                })
            return out
        if tool == "rope_recover_circumcircle":
            raw_id = payload.get("circle_id")
            removed = game.recover_circumcircle(None if raw_id is None else int(raw_id))
            return {"ok": True, "tool": "rope_recover_circumcircle", "removed": removed, **game.rope_state()}
        if tool == "rope_clear":
            self._require_capability("ropes")
            raw_id = payload.get("rope_id")
            removed = game.clear_ropes(None if raw_id is None else int(raw_id))
            return {"ok": True, "tool": "rope_clear", "removed": removed, **game.rope_state()}
        if tool == "curvature":
            game.record_tool_usage("curvature")
            return {"ok": True, "tool": "curvature", "curvature": _round(game.curvature(), 8)}
        if tool == "angle_sum":
            names = payload.get("markers")
            if not isinstance(names, (list, tuple)) or len(names) != 3:
                raise GameError("angle_sum requires exactly three marker names")
            result = game.triangle_angle_sum(str(names[0]), str(names[1]), str(names[2]))
            report = {
                "ok": True,
                "tool": "angle_sum",
                "markers": [str(name) for name in names],
                "angles": [_round(value, 6) for value in result["angles"]],
                "sum": _round(result["sum"], 6),
                "excess": _round(result["excess"], 6),
                "kind": "tangent_plane_angle_sum",
            }
            return {**report, **self._quest_tool_payload(game, result)}
        if tool == "triangle":
            names = payload.get("markers")
            if not isinstance(names, (list, tuple)) or len(names) != 3:
                raise GameError("triangle requires exactly three marker names")
            report = game.triangle_report(str(names[0]), str(names[1]), str(names[2]))
            payload_out = {
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
            return {**payload_out, **self._quest_tool_payload(game, report)}
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
                    payload.get("map_id"),
                    payload.get("seed"),
                    payload.get("mode"),
                    payload.get("scale"),
                    payload.get("difficulty"),
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