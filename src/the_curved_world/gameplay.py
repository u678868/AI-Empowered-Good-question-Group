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
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.the_curved_world.config import ConfigError
from src.the_curved_world.geometry import ambient_distance
from src.the_curved_world.manifold import wrap_parameter
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

    def __post_init__(self) -> None:
        for name, value in (
            ("move_speed", self.move_speed),
            ("time_step", self.time_step),
            ("capture_radius", self.capture_radius),
        ):
            if not np.isfinite(value) or value <= 0.0:
                raise ConfigError(f"GameplayConfig.{name} must be finite and > 0")
        if self.capture_radius < self.step_length:
            raise ConfigError(
                "GameplayConfig.capture_radius must be >= move_speed * time_step "
                f"({self.step_length}), got {self.capture_radius}"
            )
        if not np.isfinite(self.eye_height) or float(self.eye_height) <= 0.0:
            raise ConfigError("GameplayConfig.eye_height must be > 0")
        if not np.isfinite(self.slope_damping) or float(self.slope_damping) < 0.0:
            raise ConfigError("GameplayConfig.slope_damping must be >= 0")
        if int(self.max_pointer_uses) < 0:
            raise ConfigError("GameplayConfig.max_pointer_uses must be >= 0")
        if int(self.pointer_sectors) < 1:
            raise ConfigError("GameplayConfig.pointer_sectors must be >= 1")

    @property
    def step_length(self) -> float:
        return self.move_speed * self.time_step


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
    ) -> None:
        if not isinstance(world, WorldState):
            raise TypeError("ExplorationGame requires a WorldState")
        self._world = world
        self._player: PlayerView = world.player_view()
        self._observer: PlayerObserver = world.player_observer(observation_config)
        self._config = GameplayConfig() if gameplay_config is None else gameplay_config
        self._pointer_uses_remaining = int(self._config.max_pointer_uses)
        self._obstacles = getattr(world, "obstacles", None)
        self._player_radius = float(self._config.player_radius)
        self._yaw = 0.0
        self._last_slope = {"slope": 0.0, "speed_scale": 1.0}
        self._position: ParameterPosition = (float(world.start[0]), float(world.start[1]))
        self._steps = 0
        self._elapsed = 0.0
        self._log: List[LogEntry] = []
        self._markers: Dict[str, Marker] = {}
        self._trajectory: List[ParameterPosition] = [self._position]
        self._won = False
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
        return float(self._config.eye_height)

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
                self._position = resolved
                self._trajectory.append(self._position)
                self._steps += 1
                self._elapsed += self._config.time_step
                self._update_victory()
                return MoveResult(self._position, moved=True, clamped=clamped,
                                  won=self._won, collided=True)
            return MoveResult(self._position, moved=False, clamped=clamped,
                              won=self._won, collided=True)
        self._position = candidate
        self._trajectory.append(self._position)
        self._steps += 1
        self._elapsed += self._config.time_step
        self._update_victory()
        return MoveResult(self._position, moved=True, clamped=clamped, won=self._won)

    def sync_position(self, u: float, v: float) -> MoveResult:
        """Adopt a client-computed position (client physics, server audit).

        The client integrates its own 60 fps locomotion; this entry point lets it
        hand the resulting parameter position back. The server still owns world
        state, collision audit and the victory decision.
        """
        wrapped, _ = self._clamp((float(u), float(v)))
        self._position = wrapped
        self._trajectory.append(self._position)
        self._update_victory()
        return MoveResult(self._position, moved=True, clamped=False, won=self._won)
    def read_detector(self, note: str | None = None) -> PlayerObservation:
        """Take a detector reading, append it to the log and return it."""
        observation = self._observer.observe(self._position)
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
        observation = self._observer.peek(self._position)
        marker = Marker(
            name=cleaned,
            position=self._position,
            signal=observation.signal,
            label=observation.label,
        )
        self._markers[cleaned] = marker
        return marker

    def triangle_angle_sum(self, name_a: str, name_b: str, name_c: str) -> Dict[str, object]:
        """Tangent-plane angle sum of the triangle formed by three markers.

        Returns the three angles (radians), their sum and the excess over pi.
        Honest scope: these are tangent-plane angles, an approximation to the
        angle sum of a geodesic triangle -- not an exact geodesic computation.
        """
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
        return ambient_distance(
            self._player.position(marker_a.position), self._player.position(marker_b.position)
        )

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
            # Closed manifold: wrap the parameters instead of clamping. There is
            # no boundary wall, so a move never counts as clamped.
            return (wrap_parameter(position[0]), wrap_parameter(position[1])), False
        domain = surface.domain
        x = min(max(position[0], domain.x_min), domain.x_max)
        y = min(max(position[1], domain.y_min), domain.y_max)
        return (x, y), (x != position[0] or y != position[1])

    def _update_victory(self) -> None:
        if self._won:
            return
        distance = ambient_distance(self._world.position(self._position), self._world.exit_position())
        if distance <= self._config.capture_radius:
            self._won = True