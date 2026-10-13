"""Interface-independent exploration mechanics for The Curved World.

This module contains the game logic only: movement, detector readings, the
exploration log, markers, the measurement probe and the victory condition. It
never prints or plots -- user interfaces (the CLI in :mod:`cli`, or a future
Matplotlib/3D renderer) drive it and read its state.

Movement happens in *parameter space* and the surface height is recomputed after
every step, so the player always stays on the surface. This is deliberately not
a geodesic walk and not a physically realistic simulation.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.the_curved_world.config import ConfigError, hard_mode_time_limit
from src.the_curved_world.geometry import ambient_distance
from src.the_curved_world.manifold import wrap_parameter
from src.the_curved_world.quest import (
    HolonomyMeasurement,
    HomotopyMeasurement,
    ParabolicMeasurement,
    QuestManager,
    RingMeasurement,
    TriangleMeasurement,
    empty_quest_state,
)
from src.the_curved_world.ropes import Rope, RopeError, RopeNode, RopeSystem
from src.the_curved_world.observations import (
    ObservationConfig,
    PlayerObservation,
    PlayerObserver,
    PlayerView,
)
from src.the_curved_world.world import DebugView, WorldState

ParameterPosition = Tuple[float, float]


def _wrap_angle(value: float) -> float:
    """Normalise an angle to ``[-pi, pi)``."""
    return (float(value) + math.pi) % (2.0 * math.pi) - math.pi


def _tangent_vectors(surface, u: float, v: float):
    """Analytic ``(r_u, r_v)`` for either a graph surface or a closed manifold."""
    partials = getattr(surface, "first_partials", None)
    if callable(partials):
        r_u, r_v = partials(u, v)
        return np.asarray(r_u, dtype=float), np.asarray(r_v, dtype=float)
    grad_x, grad_y = surface.gradient(u, v)
    return (
        np.array([1.0, 0.0, float(grad_x)]),
        np.array([0.0, 1.0, float(grad_y)]),
    )

class GameError(ValueError):
    """Raised for invalid gameplay actions (bad names, unknown markers, ...)."""


@dataclass(frozen=True)
class GameplayConfig:
    """Tunable exploration parameters.

    ``move_speed`` (parameter units per second) times ``time_step`` (seconds per
    move) gives the fixed step length. ``capture_radius`` is the ambient
    Euclidean victory radius and must be at least the step length so the exit
    cannot be stepped straight over.
    """

    move_speed: float = 1.0
    time_step: float = 0.25
    capture_radius: float = 12.0
    max_pointer_uses: int = 3
    pointer_sectors: int = 16
    player_radius: float = 0.6
    eye_height: float = 2.0
    slope_damping: float = 3.0
    # Task 17: geometric scale S and difficulty tier (easy / medium / hard).
    scale_factor: float = 1.0
    difficulty: str = "easy"
    max_rope_pool: float = 1_000_000.0
    max_markers: int = 0

    def __post_init__(self) -> None:
        for name, value in (
            ("move_speed", self.move_speed),
            ("time_step", self.time_step),
            ("capture_radius", self.capture_radius),
        ):
            if not np.isfinite(value) or value <= 0.0:
                raise ConfigError(f"GameplayConfig.{name} must be finite and > 0")
        if self.effective_capture_radius < self.step_length:
            raise ConfigError(
                "GameplayConfig.capture_radius must be >= move_speed * time_step "
                f"({self.step_length}), got {self.capture_radius}"
            )
        if not np.isfinite(self.eye_height) or float(self.eye_height) <= 0.0:
            raise ConfigError("GameplayConfig.eye_height must be > 0")
        if not np.isfinite(self.slope_damping) or float(self.slope_damping) < 0.0:
            raise ConfigError("GameplayConfig.slope_damping must be >= 0")
        if not np.isfinite(float(self.scale_factor)) or not (0.2 <= float(self.scale_factor) <= 10.0):
            raise ConfigError("GameplayConfig.scale_factor must be within [0.2, 10.0]")
        if str(self.difficulty).strip().lower() not in ("easy", "medium", "hard"):
            raise ConfigError("GameplayConfig.difficulty must be one of easy/medium/hard")
        if not np.isfinite(float(self.max_rope_pool)) or float(self.max_rope_pool) <= 0.0:
            raise ConfigError("GameplayConfig.max_rope_pool must be finite and > 0")
        if int(self.max_markers) < 0:
            raise ConfigError("GameplayConfig.max_markers must be >= 0")
        if str(self.difficulty).strip().lower() == "hard":
            object.__setattr__(self, "max_rope_pool", min(float(self.max_rope_pool), 500.0))
            object.__setattr__(self, "max_markers", min(int(self.max_markers) or 8, 8))
        if int(self.max_pointer_uses) < 0:
            raise ConfigError("GameplayConfig.max_pointer_uses must be >= 0")
        if int(self.pointer_sectors) < 1:
            raise ConfigError("GameplayConfig.pointer_sectors must be >= 1")

    @property
    def step_length(self) -> float:
        return self.move_speed * self.time_step / float(self.scale_factor)

    @property
    def effective_capture_radius(self) -> float:
        return float(self.capture_radius) / float(self.scale_factor)

    @property
    def effective_player_radius(self) -> float:
        return float(self.player_radius) / float(self.scale_factor)

    @property
    def effective_eye_height(self) -> float:
        return float(self.eye_height) / float(self.scale_factor)


@dataclass(frozen=True)
class Marker:
    """A player-placed marker. It is never the hidden exit."""

    name: str
    position: ParameterPosition
    signal: float
    label: str


@dataclass(frozen=True)
class LogEntry:
    """One player-visible exploration log record (no hidden state)."""

    index: int
    position: ParameterPosition
    signal: float
    label: str
    trend: str
    note: Optional[str] = None


@dataclass(frozen=True)
class MoveResult:
    """Outcome of a single movement step."""

    position: ParameterPosition
    moved: bool
    clamped: bool
    won: bool
    collided: bool = False


@dataclass(frozen=True)
class GameSummary:
    """Completion summary shown on victory."""

    seed: int
    observations: int
    markers: int
    steps: int
    elapsed_time: float


class ExplorationGame:
    """Interface-independent exploration game engine."""

    def __init__(
        self,
        world: WorldState,
        gameplay_config: GameplayConfig | None = None,
        observation_config: ObservationConfig | None = None,
        quest_manager: QuestManager | None = None,
    ) -> None:
        if not isinstance(world, WorldState):
            raise TypeError("ExplorationGame requires a WorldState")
        self._world = world
        self._player: PlayerView = world.player_view()
        self._observer: PlayerObserver = world.player_observer(observation_config)
        self._config = GameplayConfig() if gameplay_config is None else gameplay_config
        self._pointer_uses_remaining = int(self._config.max_pointer_uses)
        self._obstacles = getattr(world, "obstacles", None)
        self._player_radius = float(getattr(self._config, "effective_player_radius", self._config.player_radius))
        self._yaw = 0.0
        self._last_slope = {"slope": 0.0, "speed_scale": 1.0}
        self._effective_steps = 0.0
        self._tool_usages: Dict[str, int] = {
            "detector": 0,
            "pointer": 0,
            "curvature": 0,
            "triangle": 0,
            "marker": 0,
        }
        self._quest_manager = quest_manager
        rope_pool = float(getattr(self._config, "max_rope_pool", 1_000_000.0))
        self._ropes = RopeSystem(total_pool=rope_pool)
        self._quest_time_limit: Optional[float] = None
        self._quest_time_started: Optional[float] = None
        self._quest_timer_id: Optional[str] = None
        self._time_expired = False
        self._defeated = False
        self._position: ParameterPosition = (float(world.start[0]), float(world.start[1]))
        self._last_client_sync = time.monotonic()
        self._steps = 0
        self._elapsed = 0.0
        self._log: List[LogEntry] = []
        self._markers: Dict[str, Marker] = {}
        self._trajectory: List[ParameterPosition] = [self._position]
        self._homotopy_origin_label: Optional[str] = None
        self._homotopy_phase_u = 0.0
        self._homotopy_phase_v = 0.0
        self._won = False
        self._sync_quest_timer()
        self._update_victory()

    # -- read-only player state -------------------------------------------

    @property
    def player_view(self) -> PlayerView:
        return self._player

    @property
    def position(self) -> ParameterPosition:
        return self._position

    @property
    def steps(self) -> int:
        return self._steps

    @property
    def elapsed_time(self) -> float:
        return self._elapsed

    @property
    def won(self) -> bool:
        return self._won

    @property
    def config(self) -> GameplayConfig:
        return self._config

    @property
    def step_length(self) -> float:
        return self._config.step_length

    @property
    def detector_locked(self) -> bool:
        """Task 19: the exit detector sleeps until every geometric seal is claimed."""
        return self._quest_manager is not None and not self._quest_manager.exit_unlocked

    @property
    def rope_system(self) -> RopeSystem:
        return self._ropes

    @property
    def rope_remaining(self) -> float:
        return self._ropes.remaining

    def _sync_quest_timer(self) -> None:
        tier = str(getattr(self._config, "difficulty", "easy")).strip().lower()
        quest = self._quest_manager.active_quest if self._quest_manager is not None else None
        if tier != "hard" or quest is None:
            self._quest_time_limit = None
            self._quest_time_started = None
            self._quest_timer_id = None
            self._time_expired = False
            return
        if self._quest_timer_id != quest.id:
            self._quest_timer_id = quest.id
            self._quest_time_limit = hard_mode_time_limit(self._config.scale_factor)
            self._quest_time_started = time.monotonic()
            self._time_expired = False
        if self._quest_time_started is not None and not self._time_expired:
            remaining = self._quest_time_limit - (time.monotonic() - self._quest_time_started)
            if remaining <= 0.0:
                self._time_expired = True
                self._defeated = True
                self._won = False

    @property
    def quest_time_limit(self) -> Optional[float]:
        self._sync_quest_timer()
        return self._quest_time_limit

    @property
    def quest_time_remaining(self) -> Optional[float]:
        self._sync_quest_timer()
        if self._quest_time_limit is None or self._quest_time_started is None:
            return None
        return max(0.0, self._quest_time_limit - (time.monotonic() - self._quest_time_started))

    @property
    def is_time_expired(self) -> bool:
        self._sync_quest_timer()
        return bool(self._time_expired)

    @property
    def defeated(self) -> bool:
        return bool(self._defeated)

    @property
    def max_markers_allowed(self) -> int:
        return int(getattr(self._config, "max_markers", 0) or 0)

    def advance_quest_timer(self, seconds: float) -> None:
        """Advance Hard-mode time for deterministic tests and UI integration."""
        self._sync_quest_timer()
        if self._quest_time_started is None:
            return
        self._quest_time_started -= max(0.0, float(seconds))
        self._sync_quest_timer()
        self._update_victory()
    def connect_rope(self, node_a: RopeNode, node_b: RopeNode) -> Rope:
        try:
            return self._ropes.connect(node_a, node_b)
        except RopeError as exc:
            raise GameError(str(exc)) from exc

    def clear_ropes(self, rope_id: int | None = None) -> int:
        try:
            return self._ropes.clear(rope_id)
        except RopeError as exc:
            raise GameError(str(exc)) from exc

    def pull_circumcircle(self, marker_a: RopeNode, marker_b: RopeNode, marker_c: RopeNode):
        """Pull three connected marker pegs into a circumscribed geodesic circle."""
        try:
            return self._ropes.pull_circumcircle(
                marker_a, marker_b, marker_c, surface=self._player.surface
            )
        except RopeError as exc:
            raise GameError(str(exc)) from exc

    def recover_circumcircle(self, circle_id: int | None = None) -> int:
        try:
            return self._ropes.recover_circumcircle(circle_id)
        except RopeError as exc:
            raise GameError(str(exc)) from exc

    def rope_state(self) -> Dict[str, object]:
        return self._ropes.state_payload()

    @property
    def quest_manager(self) -> QuestManager | None:
        return self._quest_manager

    def quest_state(self) -> Dict[str, object]:
        """Task 18: current quest / relic / seal state for the player payload."""
        if self._quest_manager is None:
            return empty_quest_state()
        return self._quest_manager.state_payload()

    def evaluate_triangle_measurement(self, report: Dict[str, object]) -> Dict[str, object] | None:
        """Feed a goniometer report into the active quest (Task 18)."""
        if self._quest_manager is None:
            return None
        quest = self._quest_manager.active_quest
        if quest is None:
            return None
        measurement = TriangleMeasurement(
            angle_sum=float(report.get("sum", 0.0)),
            markers=tuple(str(name) for name in report.get("markers", ())),
            excess=float(report.get("excess", 0.0)),
            curvature_integral=float(report.get("curvature_integral", 0.0)),
        )
        result = self._quest_manager.evaluate_measurement(measurement)
        if result is None or not result.completed:
            return None
        # A completed seal may open the exit while the player is already standing on it.
        self._update_victory()
        return {
            "quest_id": quest.id,
            "quest": self._quest_manager.state_payload(),
            "proof": self._quest_manager.completion_payload(quest, result),
        }

    def evaluate_ring_measurement(self, measurement: RingMeasurement) -> Dict[str, object] | None:
        """Feed a closed rope-ring measurement into the active quest (Task 20)."""
        if self._quest_manager is None:
            return None
        quest = self._quest_manager.active_quest
        if quest is None:
            return None
        result = self._quest_manager.evaluate_ring_measurement(measurement)
        if result is None or not result.completed:
            return None
        self._update_victory()
        return {
            "quest_id": quest.id,
            "quest": self._quest_manager.state_payload(),
            "proof": self._quest_manager.completion_payload(quest, result),
        }

    def evaluate_holonomy_measurement(self, measurement: HolonomyMeasurement) -> Dict[str, object] | None:
        """Feed a parallel-transport result into Quest 3 (Task 21)."""
        if self._quest_manager is None:
            return None
        quest = self._quest_manager.active_quest
        if quest is None:
            return None
        result = self._quest_manager.evaluate_holonomy_measurement(measurement)
        if result is None or not result.completed:
            return None
        self._update_victory()
        return {
            "quest_id": quest.id,
            "quest": self._quest_manager.state_payload(),
            "proof": self._quest_manager.completion_payload(quest, result),
        }

    def evaluate_parabolic_measurement(self, measurement: ParabolicMeasurement) -> Dict[str, object] | None:
        """Feed three parabolic pegs into Quest 4 (Task 22)."""
        if self._quest_manager is None:
            return None
        quest = self._quest_manager.active_quest
        if quest is None:
            return None
        result = self._quest_manager.evaluate_parabolic_measurement(measurement)
        if result is None or not result.completed:
            return None
        self._update_victory()
        return {
            "quest_id": quest.id,
            "quest": self._quest_manager.state_payload(),
            "proof": self._quest_manager.completion_payload(quest, result),
        }

    def evaluate_homotopy_measurement(self, origin_label: Optional[str] = None) -> Dict[str, object] | None:
        """Close the origin beacon and evaluate the unwrapped phase (Task 23)."""
        if self._quest_manager is None:
            return None
        quest = self._quest_manager.active_quest
        if quest is None or quest.id != "homotopy_loop":
            return None
        label = str(origin_label or self._homotopy_origin_label or "")
        if not label or label not in self._markers:
            raise GameError("homotopy loop needs an origin marker named O")
        origin = self._markers[label]
        surface = self._player.surface
        current = self._player.position(self._position)
        origin_point = self._player.position(origin.position)
        closure_distance = ambient_distance(current, origin_point)
        measurement = HomotopyMeasurement(
            origin_label=label,
            phase_u=float(self._homotopy_phase_u),
            phase_v=float(self._homotopy_phase_v),
            closure_distance=float(closure_distance),
            capture_radius=float(self._quest_manager.features.homotopy_capture_radius),
            current_label=label,
        )
        result = self._quest_manager.evaluate_homotopy_measurement(measurement)
        if result is None or not result.completed:
            return None
        self._homotopy_origin_label = None
        self._homotopy_phase_u = 0.0
        self._homotopy_phase_v = 0.0
        self._update_victory()
        return {
            "quest_id": quest.id,
            "quest": self._quest_manager.state_payload(),
            "proof": self._quest_manager.completion_payload(quest, result),
        }

    def homotopy_state(self) -> Dict[str, object]:
        """Player-visible phase tracking for Quest 5, if it is active."""
        if self._quest_manager is None:
            return {}
        quest = self._quest_manager.active_quest
        if quest is None or quest.id != "homotopy_loop":
            return {}
        label = self._homotopy_origin_label
        payload: Dict[str, object] = {
            "origin_label": label,
            "phase_u": float(self._homotopy_phase_u),
            "phase_v": float(self._homotopy_phase_v),
            "phase_max_pi": max(abs(self._homotopy_phase_u), abs(self._homotopy_phase_v)) / math.pi,
            "winding_u": self._homotopy_phase_u / (2.0 * math.pi),
            "winding_v": self._homotopy_phase_v / (2.0 * math.pi),
            "capture_radius": float(self._quest_manager.features.homotopy_capture_radius),
            "closure_distance": None,
        }
        if label and label in self._markers:
            marker = self._markers[label]
            payload["origin_position"] = [
                float(marker.position[0]),
                float(marker.position[1]),
            ]
            payload["closure_distance"] = float(
                ambient_distance(
                    self._player.position(self._position),
                    self._player.position(marker.position),
                )
            )
        return payload

    def calibrate_tangent_vector(self, marker_name: str) -> Dict[str, object]:
        """Anchor a unit tangent vector at a player marker (Task 21)."""
        name = str(marker_name).strip()
        marker = self._markers.get(name)
        if marker is None:
            raise GameError(f"unknown marker {name!r}")
        surface = self._player.surface
        u, v = (float(marker.position[0]), float(marker.position[1]))
        normal = np.asarray(surface.normal(u, v), dtype=float)
        r_u, r_v = _tangent_vectors(surface, u, v)
        tangent_one = r_u - float(r_u @ normal) * normal
        if float(np.linalg.norm(tangent_one)) < 1e-12:
            tangent_one = r_v - float(r_v @ normal) * normal
        tangent_one = tangent_one / max(float(np.linalg.norm(tangent_one)), 1e-15)
        tangent_two = np.cross(normal, tangent_one)
        forward = math.cos(self._yaw) * tangent_one + math.sin(self._yaw) * tangent_two
        e, f, g = surface.first_fundamental_form(u, v)
        b1 = float(forward @ r_u)
        b2 = float(forward @ r_v)
        determinant = float(e) * float(g) - float(f) * float(f)
        if abs(determinant) < 1e-12:
            raise GameError("cannot calibrate a tangent vector at a degenerate chart point")
        du = (float(g) * b1 - float(f) * b2) / determinant
        dv = (float(e) * b2 - float(f) * b1) / determinant
        norm = math.hypot(du, dv)
        if norm < 1e-12:
            raise GameError("calibration direction is degenerate")
        vector = (du / norm, dv / norm)
        return {
            "marker": name,
            "position": [u, v],
            "vector": [float(vector[0]), float(vector[1])],
            "heading_radians": float(self._yaw),
        }

    @property
    def effective_steps(self) -> float:
        """Task 17: uphill-weighted movement cost (sum of 1 / speed_scale)."""
        return float(self._effective_steps)

    @property
    def tool_usages(self) -> Dict[str, int]:
        return dict(self._tool_usages)

    @property
    def score(self) -> float:
        return float(self.calculate_score()["total_score"])

    def calculate_score(self) -> Dict[str, object]:
        """Task 27: structured metric score, rank and breakdown ledger."""
        completed = len(self._quest_manager.completed_quests) if self._quest_manager is not None else 0
        base = 2000.0 if self._won else 0.0
        scale = float(self._config.scale_factor)
        target_time = max(1e-9, 240.0 * scale)
        time_bonus = max(0.0, 3000.0 * (1.0 - self._elapsed / (2.0 * target_time)))

        marker_count = len(self._markers)
        marker_bonus = max(0.0, 1000.0 - 80.0 * max(0, marker_count - 3 * completed))

        rope_total = max(1e-9, float(self._ropes.total_pool))
        rope_bonus = max(0.0, 1000.0 * float(self._ropes.remaining) / rope_total)

        measure_calls = int(self._tool_usages.get("triangle", 0)) + int(self._tool_usages.get("curvature", 0))
        allowed_calls = 4 * completed
        tool_bonus = max(0.0, 1000.0 - 40.0 * max(0, measure_calls - allowed_calls))

        step_penalty = min(1000.0, float(self._effective_steps) * 0.2)
        difficulty = str(self._config.difficulty).strip().lower()
        difficulty_mult = {"easy": 1.0, "medium": 1.5, "hard": 2.2}.get(difficulty, 1.0)
        if abs(scale - 0.5) < 1e-9:
            scale_mult = 0.8
        elif abs(scale - 1.0) < 1e-9:
            scale_mult = 1.0
        elif abs(scale - 2.0) < 1e-9:
            scale_mult = 1.25
        elif abs(scale - 4.0) < 1e-9:
            scale_mult = 1.5
        else:
            scale_mult = min(2.0, max(0.6, 0.8 * math.sqrt(max(scale, 1e-9))))
        combined_mult = float(difficulty_mult) * float(scale_mult)

        subtotal = base + time_bonus + marker_bonus + rope_bonus + tool_bonus - step_penalty
        final_score = int(math.floor(max(100.0, subtotal * combined_mult)))
        if final_score >= 8000:
            rank = "S"
        elif final_score >= 5500:
            rank = "A"
        elif final_score >= 3500:
            rank = "B"
        else:
            rank = "C"
        return {
            "total_score": final_score,
            "rank": rank,
            "breakdown": {
                "base": round(base, 2),
                "time_bonus": round(time_bonus, 2),
                "marker_bonus": round(marker_bonus, 2),
                "rope_bonus": round(rope_bonus, 2),
                "tool_bonus": round(tool_bonus, 2),
                "step_penalty": round(step_penalty, 2),
                "marker_count": int(marker_count),
                "rope_remaining": round(float(self._ropes.remaining), 2),
                "rope_total": round(rope_total, 2),
                "effective_steps": round(float(self._effective_steps), 2),
                "measure_calls": int(measure_calls),
                "completed_quests": int(completed),
                "multipliers": {
                    "difficulty": difficulty,
                    "difficulty_mult": float(difficulty_mult),
                    "scale": float(scale),
                    "scale_mult": float(scale_mult),
                    "combined": combined_mult,
                },
            },
        }

    def record_tool_usage(self, name: str) -> None:
        key = str(name).strip().lower()
        if key in self._tool_usages:
            self._tool_usages[key] += 1

    @property
    def log(self) -> Tuple[LogEntry, ...]:
        return tuple(self._log)

    @property
    def markers(self) -> Tuple[Marker, ...]:
        return tuple(self._markers.values())

    @property
    def trajectory(self) -> Tuple[ParameterPosition, ...]:
        return tuple(self._trajectory)

    # -- actions -----------------------------------------------------------

    # -- first-person frame ------------------------------------------------

    @property
    def yaw(self) -> float:
        return self._yaw

    def turn(self, delta: float) -> float:
        """Rotate the first-person heading inside the tangent plane (radians)."""
        delta = float(delta)
        if not math.isfinite(delta):
            raise GameError("turn angle must be finite")
        self._yaw = _wrap_angle(self._yaw + delta)
        return self._yaw

    def tangent_basis(self):
        """Orthonormal tangent basis ``(t1, t2, up)`` at the current position."""
        surface = self._player.surface
        u, v = self._position
        up = np.asarray(surface.normal(u, v), dtype=float)
        r_u, r_v = _tangent_vectors(surface, u, v)
        tangent_one = r_u - float(r_u @ up) * up
        if float(np.linalg.norm(tangent_one)) < 1e-12:
            tangent_one = r_v - float(r_v @ up) * up
        tangent_one = tangent_one / float(np.linalg.norm(tangent_one))
        tangent_two = np.cross(up, tangent_one)
        return tangent_one, tangent_two, up

    def frame(self) -> Dict[str, Tuple[float, float, float]]:
        """First-person orthonormal frame ``{forward, right, up}`` in R^3."""
        tangent_one, tangent_two, up = self.tangent_basis()
        forward = math.cos(self._yaw) * tangent_one + math.sin(self._yaw) * tangent_two
        right = np.cross(forward, up)
        return {
            "forward": (float(forward[0]), float(forward[1]), float(forward[2])),
            "right": (float(right[0]), float(right[1]), float(right[2])),
            "up": (float(up[0]), float(up[1]), float(up[2])),
        }

    def move_relative(self, direction: str, steps: int = 1) -> MoveResult:
        """Step along the current heading.

        ``direction`` is one of ``forward`` / ``backward`` / ``strafe_left`` /
        ``strafe_right``; the heading itself is changed with :meth:`turn`.
        """
        frame = self.frame()
        forward = np.asarray(frame["forward"], dtype=float)
        right = np.asarray(frame["right"], dtype=float)
        options = {
            "forward": forward,
            "backward": -forward,
            "strafe_right": right,
            "strafe_left": -right,
        }
        if direction not in options:
            raise GameError(f"unknown direction {direction!r}")
        target = options[direction]

        surface = self._player.surface
        u, v = self._position
        r_u, r_v = _tangent_vectors(surface, u, v)
        e = float(r_u @ r_u)
        f = float(r_u @ r_v)
        g = float(r_v @ r_v)
        determinant = e * g - f * f
        if determinant < 1e-12:
            raise GameError("degenerate metric; cannot move here")
        b1 = float(target @ r_u)
        b2 = float(target @ r_v)
        du = (g * b1 - f * b2) / determinant
        dv = (e * b2 - f * b1) / determinant
        norm = math.hypot(du, dv)
        if norm < 1e-12:
            return MoveResult(self._position, moved=False, clamped=False, won=self._won)

        result = MoveResult(self._position, moved=False, clamped=False, won=self._won)
        for _ in range(max(1, int(steps))):
            result = self.move(du / norm, dv / norm)
            if not result.moved:
                break
        return result

    def _blocked(self, position: ParameterPosition) -> bool:
        if self._obstacles is None:
            return False
        return bool(self._obstacles.check_collision(position[0], position[1], self._player_radius))
    # -- camera / slope ----------------------------------------------------

    @property
    def eye_height(self) -> float:
        return float(getattr(self._config, "effective_eye_height", self._config.eye_height))

    def camera_position(self) -> np.ndarray:
        """First-person camera point: lifted off the surface along the normal.

        ``P_camera = r(u, v) + h_eye * n(u, v)`` with ``h_eye > 0``, so the eye is
        strictly outside the solid surface and never clips into the mesh.
        """
        surface = self._player.surface
        u, v = self._position
        point = np.asarray(surface.position(u, v), dtype=float)
        normal = np.asarray(surface.normal(u, v), dtype=float)
        return point + self.eye_height * normal

    def project_to_tangent(self, vector) -> np.ndarray:
        """Remove the surface-normal component (keep the player on the outer shell)."""
        surface = self._player.surface
        normal = np.asarray(surface.normal(*self._position), dtype=float)
        vec = np.asarray(vector, dtype=float)
        return vec - float(vec @ normal) * normal

    def calculate_slope_penalty(self, u: float, v: float, du: float, dv: float) -> Dict[str, float]:
        """Uphill damping for a parameter step.

        ``slope = dz / ||dr_tangent||`` using the global z axis as the height
        reference (as specified). ``speed_scale = 1 / (1 + k * slope^2)`` uphill,
        and exactly ``1`` downhill or on the flat.
        """
        surface = self._player.surface
        base = np.asarray(surface.position(u, v), dtype=float)
        target = np.asarray(surface.position(u + du, v + dv), dtype=float)
        delta = target - base
        normal = np.asarray(surface.normal(u, v), dtype=float)
        tangent = delta - float(delta @ normal) * normal
        length = float(np.linalg.norm(tangent))
        slope = float(delta[2] / length) if length > 1e-12 else 0.0
        if slope > 0.0:
            scale = 1.0 / (1.0 + float(self._config.slope_damping) * slope * slope)
        else:
            scale = 1.0
        return {"slope": slope, "speed_scale": scale}

    @property
    def last_slope(self) -> Dict[str, float]:
        return dict(self._last_slope)
    def move(self, dx: float, dy: float) -> MoveResult:
        """Move one fixed-length step in the direction ``(dx, dy)``.

        The direction is normalised so diagonal movement is not faster than
        axis-aligned movement. Parameter coordinates are clamped to the domain,
        so the player never leaves the valid region (``clamped`` reports this).
        """
        dx = float(dx)
        dy = float(dy)
        if not (np.isfinite(dx) and np.isfinite(dy)):
            raise GameError("movement direction must be finite numbers")
        norm = math.hypot(dx, dy)
        if norm == 0.0:
            return MoveResult(self._position, moved=False, clamped=False, won=self._won)

        step = self._config.step_length
        unit_x, unit_y = dx / norm, dy / norm
        # Uphill damping: the effective step shrinks as the slope steepens.
        penalty = self.calculate_slope_penalty(self._position[0], self._position[1],
                                               unit_x * step, unit_y * step)
        self._last_slope = penalty
        effective = step * float(penalty["speed_scale"])
        if effective <= 1e-9:
            return MoveResult(self._position, moved=False, clamped=False, won=self._won)
        target = (self._position[0] + unit_x * effective, self._position[1] + unit_y * effective)
        candidate, clamped = self._clamp(target)
        if self._blocked(candidate):
            # Tangent sliding: remove the radial penetration and keep the rest.
            resolved = None
            if self._obstacles is not None and hasattr(self._obstacles, "resolve_collision"):
                resolved = self._obstacles.resolve_collision(
                    self._position, candidate, self._player_radius
                )
            if resolved is not None and not self._blocked(resolved):
                previous = self._position
                self._position = resolved
                self._record_homotopy_delta(self._position[0] - previous[0], self._position[1] - previous[1])
                self._trajectory.append(self._position)
                self._steps += 1
                self._effective_steps += 1.0 / max(float(penalty["speed_scale"]), 1e-9)
                self._elapsed += self._config.time_step
                self._update_victory()
                return MoveResult(self._position, moved=True, clamped=clamped,
                                  won=self._won, collided=True)
            return MoveResult(self._position, moved=False, clamped=clamped,
                              won=self._won, collided=True)
        previous = self._position
        self._position = candidate
        self._record_homotopy_delta(self._position[0] - previous[0], self._position[1] - previous[1])
        self._trajectory.append(self._position)
        self._steps += 1
        self._effective_steps += 1.0 / max(float(penalty["speed_scale"]), 1e-9)
        self._elapsed += self._config.time_step
        self._update_victory()
        return MoveResult(self._position, moved=True, clamped=clamped, won=self._won)

    def sync_position(self, u: float, v: float) -> MoveResult:
        """Adopt a client-computed position (client physics, server audit).

        The client integrates its own 60 fps locomotion; this entry point lets it
        hand the resulting parameter position back. The server still owns world
        state, collision audit and the victory decision.
        """
        previous = self._position
        wrapped, _ = self._clamp((float(u), float(v)))
        du = wrapped[0] - previous[0]
        dv = wrapped[1] - previous[1]
        surface = self._player.surface
        if getattr(surface, "periodic", False):
            relative = getattr(surface, "chart_relative", None)
            if callable(relative):
                near = relative(previous[0], previous[1], wrapped[0], wrapped[1])
                du = near[0] - previous[0]
                dv = near[1] - previous[1]
            else:  # pragma: no cover - duck-typed periodic surfaces
                du = wrap_parameter(du)
                dv = wrap_parameter(dv)
        if math.hypot(du, dv) > 1e-12:
            penalty = self.calculate_slope_penalty(previous[0], previous[1], du, dv)
            self._last_slope = penalty
            self._effective_steps += 1.0 / max(float(penalty["speed_scale"]), 1e-9)
        now = time.monotonic()
        dt = min(1.0, max(0.0, now - self._last_client_sync))
        self._last_client_sync = now
        if math.hypot(du, dv) > 1e-12:
            self._elapsed += dt
        self._position = wrapped
        self._record_homotopy_delta(du, dv)
        self._trajectory.append(self._position)
        self._update_victory()
        return MoveResult(self._position, moved=True, clamped=False, won=self._won)
    def _detector_silent(self) -> bool:
        """Task 17/19: the seal and the medium / hard tiers hide every distance cue."""
        if self.detector_locked:
            return True
        tier = str(getattr(self._config, "difficulty", "easy")).strip().lower()
        return tier in ("medium", "hard")

    def _neutral_observation(self) -> PlayerObservation:
        # PlayerObservation only accepts Weak/Moderate/Strong; the web layer
        # relabels this placeholder as Offline / Reserved for the player.
        return PlayerObservation(signal=0.0, label="Weak", trend="same")

    def read_detector(self, note: str | None = None) -> PlayerObservation:
        """Take a detector reading, append it to the log and return it."""
        self._tool_usages["detector"] += 1
        observation = (
            self._neutral_observation()
            if self._detector_silent()
            else self._observer.observe(self._position)
        )
        self._log.append(
            LogEntry(
                index=len(self._log) + 1,
                position=self._position,
                signal=observation.signal,
                label=observation.label,
                trend=observation.trend,
                note=note,
            )
        )
        return observation

    def place_marker(self, name: str) -> Marker:
        """Place a named marker at the current position (does not move)."""
        cleaned = (name or "").strip()
        if not cleaned:
            raise GameError("marker name must be non-empty")
        if cleaned in self._markers:
            raise GameError(f"marker {cleaned!r} already exists")
        limit = int(getattr(self._config, "max_markers", 0) or 0)
        if limit > 0 and len(self._markers) >= limit:
            raise GameError(
                f"Hard mode limit: Maximum {limit} marker pegs reached. "
                "Remove existing pegs to proceed."
            )
        self._tool_usages["marker"] += 1
        observation = self.peek_detector()
        marker = Marker(
            name=cleaned,
            position=self._position,
            signal=observation.signal,
            label=observation.label,
        )
        self._markers[cleaned] = marker
        active = self._quest_manager.active_quest if self._quest_manager is not None else None
        if active is not None and active.id == "homotopy_loop" and self._homotopy_origin_label is None:
            self._homotopy_origin_label = cleaned
            self._homotopy_phase_u = 0.0
            self._homotopy_phase_v = 0.0
        return marker

    def triangle_angle_sum(self, name_a: str, name_b: str, name_c: str) -> Dict[str, object]:
        """Tangent-plane angle sum of the triangle formed by three markers.

        Returns the three angles (radians), their sum and the excess over pi.
        Honest scope: these are tangent-plane angles, an approximation to the
        angle sum of a geodesic triangle -- not an exact geodesic computation.
        """
        self._tool_usages["triangle"] += 1
        positions = []
        for name in (name_a, name_b, name_c):
            marker = self._markers.get(name)
            if marker is None:
                raise GameError(f"unknown marker {name!r}")
            positions.append(marker.position)
        surface = self._player.surface
        try:
            angle_a = surface.tangent_angle(positions[0], positions[1], positions[2])
            angle_b = surface.tangent_angle(positions[1], positions[2], positions[0])
            angle_c = surface.tangent_angle(positions[2], positions[0], positions[1])
        except ValueError as exc:
            raise GameError(f"triangle requires three distinct markers: {exc}") from exc
        total = angle_a + angle_b + angle_c
        return {
            "markers": (name_a, name_b, name_c),
            "angles": (angle_a, angle_b, angle_c),
            "sum": total,
            "excess": total - math.pi,
        }
    def distance_between_markers(self, name_a: str, name_b: str) -> float:
        """Ambient (straight-line 3D) distance between two player-known markers.

        The hidden exit is never a valid endpoint because endpoints are marker
        names only. This is the documented Euclidean distance, never a path
        length along the surface.
        """
        marker_a = self._markers.get(name_a)
        marker_b = self._markers.get(name_b)
        if marker_a is None:
            raise GameError(f"unknown marker {name_a!r}")
        if marker_b is None:
            raise GameError(f"unknown marker {name_b!r}")
        return self._world.ambient_distance(marker_a.position, marker_b.position)

    def summary(self) -> GameSummary:
        """Victory summary; contains the seed so the world can be replayed."""
        return GameSummary(
            seed=self._world.seed,
            observations=len(self._log),
            markers=len(self._markers),
            steps=self._steps,
            elapsed_time=self._elapsed,
        )

    def peek_detector(self) -> PlayerObservation:
        """Player-facing reading at the current position.

        Does not append to the log and does not change the trend baseline; used
        by the visualiser to show the current signal without side effects.
        """
        if self._detector_silent():
            return self._neutral_observation()
        return self._observer.peek(self._position)

    @property
    def pointer_uses_remaining(self) -> int:
        return self._pointer_uses_remaining

    def curvature_area_integral(self, name_a: str, name_b: str, name_c: str, subdivisions: int = 64) -> Dict[str, float]:
        """Numerical ``iint_T K dA`` over the parameter triangle of three markers.

        The surface area element is ``dA = sqrt(1 + f_x^2 + f_y^2) dx dy``; the
        integral is a midpoint average over a uniform grid clipped to the
        parameter triangle.
        """
        positions = []
        for name in (name_a, name_b, name_c):
            marker = self._markers.get(name)
            if marker is None:
                raise GameError(f"unknown marker {name!r}")
            positions.append(np.asarray(marker.position, dtype=float))
        point_a, point_b, point_c = positions
        edge_b = point_b - point_a
        edge_c = point_c - point_a
        determinant = edge_b[0] * edge_c[1] - edge_b[1] * edge_c[0]
        parameter_area = abs(float(determinant)) / 2.0
        if parameter_area <= 1e-9:
            raise GameError("triangle requires three non-collinear markers")

        surface = self._player.surface
        count = max(8, int(subdivisions))
        coord_x = np.linspace(min(point_a[0], point_b[0], point_c[0]), max(point_a[0], point_b[0], point_c[0]), count)
        coord_y = np.linspace(min(point_a[1], point_b[1], point_c[1]), max(point_a[1], point_b[1], point_c[1]), count)
        grid_x, grid_y = np.meshgrid(coord_x, coord_y)
        rel_x = grid_x - point_a[0]
        rel_y = grid_y - point_a[1]
        u = (rel_x * edge_c[1] - rel_y * edge_c[0]) / determinant
        v = (edge_b[0] * rel_y - edge_b[1] * rel_x) / determinant
        inside = (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0)
        if not bool(inside.any()):
            raise GameError("triangle sampling failed; markers may be degenerate")
        sample_x = grid_x[inside]
        sample_y = grid_y[inside]
        curvature = np.asarray(surface.gaussian_curvature(sample_x, sample_y), dtype=float)
        stretch = np.asarray(surface.area_element(sample_x, sample_y), dtype=float)
        return {
            "parameter_area": parameter_area,
            "curvature_integral": float(np.mean(curvature * stretch)) * parameter_area,
            "samples": int(inside.sum()),
        }

    def triangle_report(self, name_a: str, name_b: str, name_c: str, subdivisions: int = 64) -> Dict[str, object]:
        """Gauss-Bonnet report for the triangle formed by three markers.

        Returns the tangent-plane angle sum and its excess over pi, together with
        the numerical curvature area integral ``iint_T K dA``.

        Honest scope: Gauss-Bonnet ``iint_T K dA = sum(theta) - pi`` is exact for a
        *geodesic* triangle. Our angles live in tangent planes, so the residual is
        reported rather than claimed to be zero.
        """
        angle_report = self.triangle_angle_sum(name_a, name_b, name_c)
        integral = self.curvature_area_integral(name_a, name_b, name_c, subdivisions)
        excess = float(angle_report["excess"])
        curvature_integral = float(integral["curvature_integral"])
        if excess > 1e-6:
            character = "positive curvature (bulge)"
        elif excess < -1e-6:
            character = "negative curvature (saddle)"
        else:
            character = "flat"
        return {
            "markers": angle_report["markers"],
            "angles": angle_report["angles"],
            "sum": angle_report["sum"],
            "excess": excess,
            "curvature_integral": curvature_integral,
            "gauss_bonnet_residual": excess - curvature_integral,
            "parameter_area": integral["parameter_area"],
            "samples": integral["samples"],
            "character": character,
            "kind": "gauss_bonnet_tangent_plane",
        }

    def release_pointer(self) -> Dict[str, object]:
        """Spend one limited-use pointer: a coarse tangent-plane heading hint.

        This is an intentional, *limited* gameplay affordance (an "Eye of Ender
        lite"). It returns only a quantised bearing inside the tangent plane and a
        quantised pitch angle -- never the exit coordinates, the exact distance or
        the true 3D offset. The number of uses is capped by the configuration.
        """
        if self._pointer_uses_remaining <= 0:
            raise GameError("no pointer uses remaining")
        self._tool_usages["pointer"] += 1

        surface = self._player.surface
        x, y = self._position
        delta = 1e-3
        player_point = np.asarray(surface.position(x, y), dtype=float)
        exit_point = np.asarray(self._world.exit_position(), dtype=float)
        direction = exit_point - player_point
        length = float(np.linalg.norm(direction))
        if length < 1e-9:
            raise GameError("pointer is undefined at the exit")

        normal = np.asarray(surface.normal(x, y), dtype=float)
        # tangent-plane axes in parameter space: dP/dx and dP/dy, which map
        # directly onto the 2D player view (x to the right, y upwards).
        axis_x = np.asarray(surface.position(x + delta, y), dtype=float) - np.asarray(surface.position(x - delta, y), dtype=float)
        axis_y = np.asarray(surface.position(x, y + delta), dtype=float) - np.asarray(surface.position(x, y - delta), dtype=float)
        component_x = float(direction @ axis_x)
        component_y = float(direction @ axis_y)
        normal_component = float(direction @ normal)

        # bearing of the tangent-plane projection, in the parameter tangent basis
        bearing = math.degrees(math.atan2(component_y, component_x))
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, normal_component / length))))
        sectors = max(1, int(self._config.pointer_sectors))
        sector_width = 360.0 / sectors
        bearing_quantised = round(bearing / sector_width) * sector_width
        bearing_quantised = (bearing_quantised + 180.0) % 360.0 - 180.0
        pitch_quantised = round(pitch / 15.0) * 15.0
        radians = math.radians(bearing_quantised)

        self._pointer_uses_remaining -= 1
        return {
            "bearing_degrees": bearing_quantised,
            "pitch_degrees": pitch_quantised,
            "tangent_direction": [math.cos(radians), math.sin(radians)],
            "sector_width_degrees": sector_width,
            "uses_remaining": self._pointer_uses_remaining,
            "kind": "quantised_tangent_plane_hint",
        }
    def curvature(self) -> float:
        """Analytic Gaussian curvature of the surface at the current position.

        A local geometric reading; it does not expose any hidden world state.
        """
        return float(self._player.surface.gaussian_curvature(self._position[0], self._position[1]))
    def debug_view(self) -> DebugView:
        """PRIVILEGED: developer interface. Must be requested explicitly."""
        return self._world.debug_view()

    # -- internals ---------------------------------------------------------

    def _clamp(self, position: ParameterPosition) -> Tuple[ParameterPosition, bool]:
        surface = self._player.surface
        if getattr(surface, "periodic", False):
            # Closed manifold: wrap through the surface itself. Some charts
            # (Klein bottle / projective plane) use non-(2*pi, 2*pi) periods.
            wrap = getattr(surface, "wrap", None)
            if callable(wrap):
                wrapped = wrap(position[0], position[1])
                return (float(wrapped[0]), float(wrapped[1])), False
            return (wrap_parameter(position[0]), wrap_parameter(position[1])), False
        domain = surface.domain
        x = min(max(position[0], domain.x_min), domain.x_max)
        y = min(max(position[1], domain.y_min), domain.y_max)
        return (x, y), (x != position[0] or y != position[1])

    def _record_homotopy_delta(self, du: float, dv: float) -> None:
        if self._quest_manager is None:
            return
        quest = self._quest_manager.active_quest
        if quest is None or quest.id != "homotopy_loop" or self._homotopy_origin_label is None:
            return
        if getattr(self._player.surface, "periodic", False):
            du = wrap_parameter(du)
            dv = wrap_parameter(dv)
        self._homotopy_phase_u += float(du)
        self._homotopy_phase_v += float(dv)

    def _update_victory(self) -> None:
        if self._won:
            return
        if self._defeated:
            self._won = False
            return
        distance = self._world.ambient_distance(self._position, self._world.exit)
        sealed = self._quest_manager is not None and not self._quest_manager.exit_unlocked
        capture = float(getattr(self._config, "effective_capture_radius", self._config.capture_radius))
        if distance <= capture:
            if sealed:
                # Task 18: the exit stays sealed until every geometric relic is claimed.
                self._quest_manager.mark_seal_contact(True)
                return
            self._won = True
        elif sealed:
            self._quest_manager.mark_seal_contact(False)
