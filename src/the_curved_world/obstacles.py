"""Surface obstacles and collision (Task 10).

Generation is deliberately **two-stage and decoupled**: the smooth closed
surface is built first (``manifold.py``), then static obstacles are scattered on
it from an explicit seed. Obstacles keep a safe margin around the start and the
exit, and never overlap each other.

Collision uses the *ambient 3D* distance, which handles the periodic seam for
free: two parameter points that are 2*pi apart map to the same 3D point.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from src.the_curved_world.config import ConfigError

OBSTACLE_KINDS = ("tree", "rock")


def wrap_parameter(value):
    """Normalise a parameter to [-pi, pi)."""
    return (float(value) + np.pi) % (2.0 * np.pi) - np.pi


def wrap_difference(value: float) -> float:
    """Smallest signed representative of ``value`` modulo 2*pi."""
    return (float(value) + np.pi) % (2.0 * np.pi) - np.pi


def periodic_parameter_distance(u1: float, v1: float, u2: float, v2: float) -> float:
    """Parameter-space distance on the torus (wraps across the seam)."""
    return float(np.hypot(wrap_difference(u1 - u2), wrap_difference(v1 - v2)))


def _wrap_point(manifold, u: float, v: float) -> Tuple[float, float]:
    """Canonical chart window of ``manifold`` (falls back to the plain torus).

    Closed manifolds publish their own periods -- the Klein bottle needs
    ``(4 pi, 2 pi)``, since a ``2 pi`` shift in ``u`` mirrors ``v`` there rather
    than returning to the same chart point.
    """
    wrap = getattr(manifold, "wrap", None)
    if callable(wrap):
        wrapped = wrap(u, v)
        return float(wrapped[0]), float(wrapped[1])
    return wrap_parameter(u), wrap_parameter(v)


def _relative_point(manifold, u_ref: float, v_ref: float, u: float, v: float) -> Tuple[float, float]:
    """Chart coordinates of ``(u, v)`` near ``(u_ref, v_ref)``.

    Uses the manifold's own sheet/period identification when available, so this
    stays correct for a twisted (non-orientable) chart.
    """
    relative = getattr(manifold, "chart_relative", None)
    if callable(relative):
        near = relative(u_ref, v_ref, u, v)
        return float(near[0]), float(near[1])
    return (u_ref + wrap_difference(u - u_ref), v_ref + wrap_difference(v - v_ref))


@dataclass(frozen=True)
class Obstacle:
    """A single static obstacle sitting on the surface."""

    id: int
    u: float
    v: float
    position_3d: Tuple[float, float, float]
    radius: float
    kind: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "u": round(self.u, 6),
            "v": round(self.v, 6),
            "position": [round(value, 6) for value in self.position_3d],
            "radius": round(self.radius, 6),
            "kind": self.kind,
        }


def _surface_tangents(surface, u: float, v: float):
    """Analytic ``(r_u, r_v)`` for a graph surface or a closed manifold."""
    partials = getattr(surface, "first_partials", None)
    if callable(partials):
        r_u, r_v = partials(u, v)
        return np.asarray(r_u, dtype=float), np.asarray(r_v, dtype=float)
    grad_x, grad_y = surface.gradient(u, v)
    return (
        np.array([1.0, 0.0, float(grad_x)]),
        np.array([0.0, 1.0, float(grad_y)]),
    )

class ObstacleField:
    """A deterministic set of obstacles bound to one manifold."""

    def __init__(self, manifold, obstacles: Iterable[Obstacle] = (), distance_mode: str = "euclidean") -> None:
        self._manifold = manifold
        self._obstacles: Tuple[Obstacle, ...] = tuple(obstacles)
        # ``orbit_min`` makes collision and vision respect a quotient world: an
        # obstacle's other realization is the same place, so it counts as near.
        self._distance_mode = distance_mode

    @property
    def manifold(self):
        return self._manifold

    @property
    def distance_mode(self) -> str:
        return self._distance_mode

    @property
    def obstacles(self) -> Tuple[Obstacle, ...]:
        return self._obstacles

    def _realizations(self, obstacle: Obstacle) -> Tuple[np.ndarray, ...]:
        """Every 3D realization of one obstacle (its antipode included on RP^2)."""
        if self._distance_mode != "orbit_min":
            return (np.asarray(obstacle.position_3d, dtype=float),)
        orbit = getattr(self._manifold, "orbit_positions", None)
        if not callable(orbit):
            return (np.asarray(obstacle.position_3d, dtype=float),)
        return tuple(np.asarray(point, dtype=float) for point in orbit(obstacle.u, obstacle.v))

    def __len__(self) -> int:
        return len(self._obstacles)

    def __iter__(self):
        return iter(self._obstacles)

    # -- generation --------------------------------------------------------

    @classmethod
    def generate(
        cls,
        manifold,
        config,
        seed: int,
        exclude_points: Sequence[Tuple[float, float]] = (),
        safe_margin: Optional[float] = None,
    ) -> "ObstacleField":
        """Scatter ``config.obstacle_count`` obstacles deterministically.

        ``exclude_points`` are parameter points (start / exit) that must stay
        clear by at least ``safe_margin`` of *ambient* distance.
        """
        count = int(getattr(config, "obstacle_count", 0))
        base_radius = float(getattr(config, "obstacle_radius", 1.0))
        margin = float(getattr(config, "obstacle_safe_margin", 0.0)) if safe_margin is None else float(safe_margin)
        mode = str(getattr(config, "distance_mode", "euclidean"))
        if count <= 0:
            return cls(manifold, (), distance_mode=mode)

        domain = manifold.domain
        rng = np.random.default_rng(int(seed) + 7919)
        orbit = getattr(manifold, "orbit_positions", None) if mode == "orbit_min" else None
        # Anchors (start / exit) and this candidate are all measured with the
        # world's own policy, so an antipodal twin counts as "right here".
        excluded = [
            tuple(np.asarray(p, dtype=float) for p in orbit(*point)) if callable(orbit)
            else (np.asarray(manifold.position(*point), dtype=float),)
            for point in exclude_points
        ]

        def _too_close(point, anchors, limit: float) -> bool:
            for anchor in anchors:
                if any(float(np.linalg.norm(point - target)) < limit for target in anchor):
                    return True
            return False

        obstacles: List[Obstacle] = []
        placed: List[Tuple[np.ndarray, ...]] = []
        attempts = 0
        max_attempts = max(2000, count * 400)
        while len(obstacles) < count and attempts < max_attempts:
            attempts += 1
            u = float(rng.uniform(domain.x_min, domain.x_max))
            v = float(rng.uniform(domain.y_min, domain.y_max))
            point = np.asarray(manifold.position(u, v), dtype=float)
            realizations = tuple(np.asarray(p, dtype=float) for p in orbit(u, v)) if callable(orbit) else (point,)
            if any(_too_close(p, excluded, margin) for p in realizations):
                continue
            if any(_too_close(p, placed, 2.5 * base_radius) for p in realizations):
                continue
            # 60% low-poly pines, 40% low-poly rocks (deterministic from the seed)
            kind = "tree" if float(rng.random()) < 0.6 else "rock"
            radius = base_radius * float(rng.uniform(0.8, 1.3))
            obstacles.append(
                Obstacle(
                    id=len(obstacles),
                    u=u,
                    v=v,
                    position_3d=(float(point[0]), float(point[1]), float(point[2])),
                    radius=radius,
                    kind=kind,
                )
            )
            placed.append(realizations)

        if len(obstacles) < count:
            raise ConfigError(
                f"could not place {count} obstacles with the requested safe margin; placed {len(obstacles)}"
            )
        return cls(manifold, obstacles, distance_mode=mode)

    # -- queries -----------------------------------------------------------

    def point_of(self, u: float, v: float) -> np.ndarray:
        return np.asarray(self._manifold.position(u, v), dtype=float)

    def nearest_realization(self, point, obstacle: Obstacle):
        """Obstacle realization nearest to ``point``, with its distance.

        For the default Euclidean policy this is just the stored 3D position, so
        every other map keeps its exact previous behaviour.
        """
        centres = self._realizations(obstacle)
        best = None
        for centre in centres:
            value = float(np.linalg.norm(np.asarray(point, dtype=float) - centre))
            if best is None or value < best[1]:
                best = (centre, value)
        return best

    def distance_to(self, u: float, v: float, obstacle: Obstacle) -> float:
        return self.nearest_realization(self.point_of(u, v), obstacle)[1]

    def check_collision(self, u: float, v: float, player_radius: float = 0.0) -> bool:
        """True when the point lies inside any obstacle's collision volume."""
        if not self._obstacles:
            return False
        point = self.point_of(u, v)
        for obstacle in self._obstacles:
            reach = obstacle.radius + player_radius
            if self.nearest_realization(point, obstacle)[1] < reach:
                return True
        return False

    def blocking_obstacle(self, u: float, v: float, player_radius: float = 0.0) -> Optional[Obstacle]:
        point = self.point_of(u, v)
        for obstacle in self._obstacles:
            if self.nearest_realization(point, obstacle)[1] < obstacle.radius + player_radius:
                return obstacle
        return None

    def resolve_collision(self, current_uv, next_uv, player_radius: float = 0.0):
        """Tangent sliding: push ``next_uv`` out of any obstacle it penetrates.

        The radial (normal-to-the-obstacle) penetration component is removed and
        the remaining motion is kept, so the player slides along the obstacle
        contour instead of sticking. Returns the wrapped parameter position, or
        ``None`` when no obstacle is involved.
        """
        manifold = self._manifold
        base = np.asarray(manifold.position(*current_uv), dtype=float)
        resolved = np.asarray(manifold.position(*next_uv), dtype=float).copy()
        touched = False
        for obstacle in self._obstacles:
            center, distance = self.nearest_realization(resolved, obstacle)
            reach = obstacle.radius + player_radius
            if distance >= reach:
                continue
            touched = True
            offset = resolved - center
            direction = offset / distance if distance > 1e-9 else (base - center)
            norm = float(np.linalg.norm(direction))
            direction = direction / norm if norm > 1e-9 else np.array([0.0, 0.0, 1.0])
            resolved = center + direction * (reach + 1e-6)
        if not touched:
            return None

        r_u, r_v = _surface_tangents(manifold, current_uv[0], current_uv[1])
        delta = resolved - base
        e = float(r_u @ r_u)
        f = float(r_u @ r_v)
        g = float(r_v @ r_v)
        determinant = e * g - f * f
        if determinant < 1e-12:
            return None
        b1 = float(delta @ r_u)
        b2 = float(delta @ r_v)
        du = (g * b1 - f * b2) / determinant
        dv = (e * b2 - f * b1) / determinant
        resolved_uv = _wrap_point(manifold, current_uv[0] + du, current_uv[1] + dv)
        # The tangent map is only first order, so back off toward the (collision-free)
        # current position until the point is genuinely outside every obstacle.
        for _ in range(10):
            if not self.check_collision(resolved_uv[0], resolved_uv[1], player_radius):
                return resolved_uv
            near = _relative_point(manifold, current_uv[0], current_uv[1], resolved_uv[0], resolved_uv[1])
            resolved_uv = _wrap_point(
                manifold,
                current_uv[0] + 0.5 * (near[0] - current_uv[0]),
                current_uv[1] + 0.5 * (near[1] - current_uv[1]),
            )
        return None
    def obstacles_near(self, u: float, v: float, radius: float) -> List[Obstacle]:
        """Obstacles within ``radius`` of the given point (used for the radar HUD)."""
        point = self.point_of(u, v)
        scored = [
            (self.nearest_realization(point, obstacle)[1], obstacle) for obstacle in self._obstacles
        ]
        return [obstacle for distance, obstacle in sorted(scored, key=lambda item: item[0]) if distance <= radius]

    def to_list(self) -> List[Dict[str, object]]:
        return [obstacle.to_dict() for obstacle in self._obstacles]


EMPTY_FIELD: Optional[ObstacleField] = None