"""Task 19: finite surveyor rope system.

A rope connects two *player-known* nodes: a marker peg or an obstacle that is
currently inside the player's view. The system enforces a single-segment limit
and a total length pool, and it only ever stores player-visible endpoints, so it
cannot be used to probe unexplored regions or the hidden exit.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

DEFAULT_MAX_SEGMENT = 1_000_000.0
DEFAULT_TOTAL_POOL = 1_000_000.0

VALID_NODE_KINDS = ("marker", "obstacle")


def _clamp_parameter(surface, u: float, v: float) -> Tuple[float, float]:
    """Keep a numerical circumcircle sample inside its chart."""
    domain = surface.domain
    if bool(getattr(surface, "periodic", False)):
        from src.the_curved_world.manifold import wrap_parameter
        return wrap_parameter(u), wrap_parameter(v)
    return (
        min(max(float(u), float(domain.x_min)), float(domain.x_max)),
        min(max(float(v), float(domain.y_min)), float(domain.y_max)),
    )


def _metric_length(surface, start, end, samples: int = 20) -> float:
    """Metric length of a straight parameter segment (Task 20 pull geometry)."""
    u0, v0 = float(start[0]), float(start[1])
    u1, v1 = float(end[0]), float(end[1])
    if bool(getattr(surface, "periodic", False)):
        from src.the_curved_world.manifold import wrap_parameter
        du = wrap_parameter(u1 - u0)
        dv = wrap_parameter(v1 - v0)
    else:
        du, dv = u1 - u0, v1 - v0
    steps = max(2, int(samples))
    total = 0.0
    for index in range(steps):
        t = (index + 0.5) / steps
        e, f, g = surface.first_fundamental_form(u0 + t * du, v0 + t * dv)
        total += math.sqrt(max(1e-12, e * du * du + 2.0 * f * du * dv + g * dv * dv))
    return total / steps


def circumradius_from_sides(a: float, b: float, c: float) -> float:
    """Euclidean circumradius from three side lengths; returns 0 for degenerate triangles."""
    sides = sorted((abs(float(a)), abs(float(b)), abs(float(c))))
    if sides[0] <= 1e-12 or sides[0] + sides[1] <= sides[2] + 1e-12:
        return 0.0
    s = 0.5 * (sides[0] + sides[1] + sides[2])
    area = math.sqrt(max(0.0, s * (s - sides[0]) * (s - sides[1]) * (s - sides[2])))
    if area <= 1e-12:
        return 0.0
    return (sides[0] * sides[1] * sides[2]) / (4.0 * area)


def _uv_circumcenter(points: Sequence[Sequence[float]]) -> Tuple[float, float]:
    """Parameter-space circumcenter used as the initial geodesic solver guess."""
    p0 = (float(points[0][0]), float(points[0][1]))
    p1 = (float(points[1][0]), float(points[1][1]))
    p2 = (float(points[2][0]), float(points[2][1]))
    def unwrap(point):
        from src.the_curved_world.manifold import wrap_parameter
        return (p0[0] + wrap_parameter(point[0] - p0[0]),
                p0[1] + wrap_parameter(point[1] - p0[1]))
    a = unwrap(p1)
    b = unwrap(p2)
    d = 2.0 * (p0[0] * (a[1] - b[1]) + a[0] * (b[1] - p0[1]) + b[0] * (p0[1] - a[1]))
    if abs(d) < 1e-12:
        raise RopeError("the three pegs are collinear; a circumcircle is undefined")
    aa = p0[0] * p0[0] + p0[1] * p0[1]
    bb = a[0] * a[0] + a[1] * a[1]
    cc = b[0] * b[0] + b[1] * b[1]
    return (
        (aa * (a[1] - b[1]) + bb * (b[1] - p0[1]) + cc * (p0[1] - a[1])) / d,
        (aa * (b[0] - a[0]) + bb * (p0[0] - b[0]) + cc * (a[0] - p0[0])) / d,
    )


def _geodesic_circumcenter(surface, points: Sequence[Sequence[float]]):
    """Numerically balance the three geodesic distances from a parameter center."""
    initial = _uv_circumcenter(points)
    center = list(initial)
    spread = max(1e-4, 0.25 * max(
        max(float(points[i][0]) for i in range(3)) - min(float(points[i][0]) for i in range(3)),
        max(float(points[i][1]) for i in range(3)) - min(float(points[i][1]) for i in range(3)),
    ))
    step = max(1e-4, spread)
    best = center
    best_error = float("inf")
    for _ in range(14):
        improved = False
        for du in (-1.0, 0.0, 1.0):
            for dv in (-1.0, 0.0, 1.0):
                candidate = _clamp_parameter(surface, center[0] + du * step, center[1] + dv * step)
                radii = [_metric_length(surface, candidate, point) for point in points]
                error = max(radii) - min(radii) + 0.02 * (sum(radii) / 3.0)
                if error < best_error:
                    best_error = error
                    best = [candidate[0], candidate[1]]
                    improved = True
        center = best
        if not improved:
            step *= 0.5
    radii = [_metric_length(surface, center, point) for point in points]
    radius = sum(radii) / 3.0
    return (float(center[0]), float(center[1])), float(radius), tuple(float(value) for value in radii)


def _geodesic_ring_samples(surface, center, radius: float, count: int = 32):
    """Sample a closed ring of equal metric radius around a parameter center."""
    count = max(12, int(count))
    center = (float(center[0]), float(center[1]))
    domain = surface.domain
    max_ray = 0.48 * min(float(domain.width), float(domain.height))
    points = []
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        direction = (math.cos(angle), math.sin(angle))
        low, high = 1e-5, max_ray
        high_point = _clamp_parameter(surface, center[0] + high * direction[0], center[1] + high * direction[1])
        if _metric_length(surface, center, high_point) < radius:
            points.append(high_point)
            continue
        for _ in range(55):
            mid = 0.5 * (low + high)
            point = _clamp_parameter(surface, center[0] + mid * direction[0], center[1] + mid * direction[1])
            if _metric_length(surface, center, point) < radius:
                low = mid
            else:
                high = mid
        points.append(_clamp_parameter(surface, center[0] + high * direction[0], center[1] + high * direction[1]))
    return tuple(points)


@dataclass(frozen=True)
class Circumcircle:
    """A pulled circumcircle attached to three connected marker pegs."""

    id: int
    labels: Tuple[str, str, str]
    center_label: str
    center: Tuple[float, float]
    flat_radius: float
    flat_perimeter: float
    surface_radius: float
    perimeter: float
    samples: Tuple[Tuple[float, float], ...]
    rope_ids: Tuple[int, ...] = ()
    curvature: float = 0.0
    kind: str = "circumcircle"

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "labels": list(self.labels),
            "center_label": self.center_label,
            "center": [round(float(self.center[0]), 6), round(float(self.center[1]), 6)],
            "flat_radius": round(float(self.flat_radius), 6),
            "flat_perimeter": round(float(self.flat_perimeter), 6),
            "surface_radius": round(float(self.surface_radius), 6),
            "perimeter": round(float(self.perimeter), 6),
            "samples": [[round(float(u), 6), round(float(v), 6)] for u, v in self.samples],
            "rope_ids": list(self.rope_ids),
            "curvature": round(float(self.curvature), 10),
        }


class RopeError(ValueError):
    """Raised for invalid rope endpoints, over-length spans or an empty pool."""


@dataclass(frozen=True)
class RopeNode:
    """A player-known attachment point."""

    kind: str
    id: str
    label: str
    uv: Tuple[float, float]
    position_3d: Tuple[float, float, float]

    def __post_init__(self) -> None:
        if self.kind not in VALID_NODE_KINDS:
            raise RopeError(f"unknown rope node kind {self.kind!r}")

    def to_dict(self) -> Dict[str, object]:
        return {
            "type": self.kind,
            "id": self.id,
            "label": self.label,
            "position": [round(float(self.uv[0]), 6), round(float(self.uv[1]), 6)],
        }


@dataclass(frozen=True)
class Rope:
    """One taut cable between two player-known nodes."""

    id: int
    node_a: RopeNode
    node_b: RopeNode
    length_3d: float

    @property
    def is_obstacle_a(self) -> bool:
        return self.node_a.kind == "obstacle"

    @property
    def is_obstacle_b(self) -> bool:
        return self.node_b.kind == "obstacle"

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "a": self.node_a.to_dict(),
            "b": self.node_b.to_dict(),
            "length_3d": round(float(self.length_3d), 6),
            "is_obstacle_a": self.is_obstacle_a,
            "is_obstacle_b": self.is_obstacle_b,
        }


def node_key(node: RopeNode) -> Tuple[str, str]:
    return (node.kind, str(node.id))


class RopeSystem:
    """Finite rope pool shared by every cable in one game session."""

    def __init__(
        self,
        max_segment: float = DEFAULT_MAX_SEGMENT,
        total_pool: float = DEFAULT_TOTAL_POOL,
    ) -> None:
        if max_segment <= 0.0 or total_pool <= 0.0:
            raise RopeError("rope limits must be positive")
        self._max_segment = float(max_segment)
        self._total_pool = float(total_pool)
        self._ropes: List[Rope] = []
        self._circumcircles: List[Circumcircle] = []
        self._next_id = 0
        self._next_circle_id = 0
        self._used = 0.0

    # -- read-only ---------------------------------------------------------

    @property
    def ropes(self) -> Tuple[Rope, ...]:
        return tuple(self._ropes)

    @property
    def max_segment(self) -> float:
        return self._max_segment

    @property
    def total_pool(self) -> float:
        return self._total_pool

    @property
    def used(self) -> float:
        return float(self._used)

    @property
    def remaining(self) -> float:
        return max(0.0, self._total_pool - self._used)

    @property
    def circumcircles(self) -> Tuple[Circumcircle, ...]:
        return tuple(self._circumcircles)

    def ropes_at(self, node: RopeNode) -> Tuple[Rope, ...]:
        """Every rope bound to ``node`` (Task 19: at most two per path point)."""
        key = node_key(node)
        return tuple(
            rope
            for rope in self._ropes
            if node_key(rope.node_a) == key or node_key(rope.node_b) == key
        )

    def closed_loop_containing(self, rope_id: int):
        """Return ``(nodes, ropes)`` of the rope cycle containing ``rope_id`` (Task 20).

        Every node of a ring binds exactly two ropes, so the cycle can be found by
        walking from one endpoint until it returns to the start. Returns ``None``
        when the rope is not part of a simple closed loop of >= 4 nodes.
        """
        rope = self.get(rope_id)
        start_key = node_key(rope.node_a)
        loop = [rope.node_a, rope.node_b]
        used = {rope.id}
        current = rope.node_b
        for _ in range(len(self._ropes)):
            attached = [candidate for candidate in self.ropes_at(current) if candidate.id not in used]
            if len(attached) != 1:
                return None
            nxt = attached[0]
            used.add(nxt.id)
            other = nxt.node_b if node_key(nxt.node_a) == node_key(current) else nxt.node_a
            if node_key(other) == start_key:
                if len(loop) < 4:
                    return None
                return tuple(loop), tuple(self.get(rid) for rid in used)
            loop.append(other)
            current = other
        return None

    def get(self, rope_id: int) -> Rope:
        for rope in self._ropes:
            if rope.id == int(rope_id):
                return rope
        raise RopeError(f"unknown rope id {rope_id!r}")

    # -- mutations ---------------------------------------------------------

    def connect(self, node_a: RopeNode, node_b: RopeNode) -> Rope:
        if node_key(node_a) == node_key(node_b):
            raise RopeError("a rope cannot connect a node to itself")
        pair = {node_key(node_a), node_key(node_b)}
        for existing in self._ropes:
            if {node_key(existing.node_a), node_key(existing.node_b)} == pair:
                raise RopeError("these two nodes are already connected")
        for node in (node_a, node_b):
            if len(self.ropes_at(node)) >= 2:
                raise RopeError(f"{node.label} already binds two ropes")

        delta = [
            float(node_a.position_3d[index]) - float(node_b.position_3d[index]) for index in range(3)
        ]
        length = (delta[0] ** 2 + delta[1] ** 2 + delta[2] ** 2) ** 0.5
        if length <= 1e-9:
            raise RopeError("the two nodes are at the same place")
        if length > self._max_segment + 1e-9:
            raise RopeError(
                f"rope too short: {length:.2f} m exceeds the {self._max_segment:.0f} m single-segment limit"
            )
        if length > self.remaining + 1e-9:
            raise RopeError(
                f"rope pool exhausted: need {length:.2f} m, only {self.remaining:.2f} m left"
            )

        rope = Rope(id=self._next_id, node_a=node_a, node_b=node_b, length_3d=float(length))
        self._ropes.append(rope)
        self._used += float(length)
        self._next_id += 1
        return rope

    def clear(self, rope_id: Optional[int] = None) -> int:
        """Cut one rope (recovering its length) or every rope. Returns the count."""
        if rope_id is None:
            removed = len(self._ropes)
            self._ropes = []
            self._circumcircles = []
            self._used = 0.0
            return removed
        target = int(rope_id)
        for index, rope in enumerate(self._ropes):
            if rope.id == target:
                self._ropes.pop(index)
                self._used = max(0.0, self._used - rope.length_3d)
                removed_circles = [circle for circle in self._circumcircles if target in circle.rope_ids]
                for circle in removed_circles:
                    self._circumcircles.remove(circle)
                    self._used = max(0.0, self._used - float(circle.perimeter))
                return 1
        raise RopeError(f"unknown rope id {rope_id!r}")

    def _triangle_ropes(self, nodes: Sequence[RopeNode]) -> Tuple[Rope, ...]:
        if len(nodes) != 3:
            raise RopeError("a circumcircle requires exactly three marker pegs")
        if any(node.kind != "marker" for node in nodes):
            raise RopeError("circumcircle pegs must all be marker nodes")
        keys = [node_key(node) for node in nodes]
        if len(set(keys)) != 3:
            raise RopeError("circumcircle requires three distinct marker pegs")
        found = []
        for i in range(3):
            for j in range(i + 1, 3):
                pair = {keys[i], keys[j]}
                rope = next(
                    (
                        candidate for candidate in self._ropes
                        if {node_key(candidate.node_a), node_key(candidate.node_b)} == pair
                    ),
                    None,
                )
                if rope is None:
                    raise RopeError("the three pegs must be connected by all three rope edges")
                found.append(rope)
        return tuple(found)

    def pull_circumcircle(
        self,
        marker_a: RopeNode,
        marker_b: RopeNode,
        marker_c: RopeNode,
        *,
        surface=None,
        samples: int = 32,
    ) -> Circumcircle:
        """Replace a three-rope triangle with a circumscribed geodesic circle."""
        nodes = (marker_a, marker_b, marker_c)
        triangle_ropes = self._triangle_ropes(nodes)
        delta_ab = [float(marker_a.position_3d[i]) - float(marker_b.position_3d[i]) for i in range(3)]
        delta_ac = [float(marker_a.position_3d[i]) - float(marker_c.position_3d[i]) for i in range(3)]
        delta_bc = [float(marker_b.position_3d[i]) - float(marker_c.position_3d[i]) for i in range(3)]
        side_a = math.sqrt(sum(value * value for value in delta_bc))
        side_b = math.sqrt(sum(value * value for value in delta_ac))
        side_c = math.sqrt(sum(value * value for value in delta_ab))
        flat_radius = circumradius_from_sides(side_a, side_b, side_c)
        if flat_radius <= 1e-9:
            raise RopeError("the three pegs are degenerate; a circumcircle is undefined")

        uv_points = [(float(node.uv[0]), float(node.uv[1])) for node in nodes]
        center = _uv_circumcenter(uv_points)
        uv_radius = sum(
            math.hypot(point[0] - center[0], point[1] - center[1]) for point in uv_points
        ) / 3.0
        if uv_radius <= 1e-12:
            raise RopeError("the three pegs are too close; a circumcircle is undefined")
        count = max(24, int(samples))
        ring_samples = tuple(
            _clamp_parameter(
                surface if surface is not None else nodes[0],
                center[0] + uv_radius * math.cos(2.0 * math.pi * index / count),
                center[1] + uv_radius * math.sin(2.0 * math.pi * index / count),
            )
            for index in range(count)
        )
        if surface is None:
            surface_radius = float(flat_radius)
            perimeter = 2.0 * math.pi * flat_radius
            curvature = 0.0
        else:
            radii = [_metric_length(surface, center, point) for point in uv_points]
            surface_radius = sum(radii) / len(radii)
            perimeter = sum(
                _metric_length(surface, ring_samples[index], ring_samples[(index + 1) % len(ring_samples)])
                for index in range(len(ring_samples))
            )
            curvature = float(surface.gaussian_curvature(center[0], center[1]))

        if perimeter > self.remaining + 1e-7:
            raise RopeError(
                f"rope pool exhausted: pulling this circle needs {perimeter:.2f} m, "
                f"only {self.remaining:.2f} m left"
            )

        circle = Circumcircle(
            id=self._next_circle_id,
            labels=(str(marker_a.label), str(marker_b.label), str(marker_c.label)),
            center_label="O",
            center=(float(center[0]), float(center[1])),
            flat_radius=float(flat_radius),
            flat_perimeter=float(2.0 * math.pi * flat_radius),
            surface_radius=float(surface_radius),
            perimeter=float(perimeter),
            samples=tuple((float(u), float(v)) for u, v in ring_samples),
            rope_ids=tuple(int(rope.id) for rope in triangle_ropes),
            curvature=float(curvature),
        )
        self._next_circle_id += 1
        self._circumcircles.append(circle)
        self._used += float(perimeter)
        return circle

    def recover_circumcircle(self, circle_id: Optional[int] = None) -> int:
        """Recover one pulled circle or all circles, releasing their rope cost."""
        if circle_id is None:
            removed = len(self._circumcircles)
            for circle in self._circumcircles:
                self._used = max(0.0, self._used - float(circle.perimeter))
            self._circumcircles = []
            return removed
        target = int(circle_id)
        for index, circle in enumerate(self._circumcircles):
            if circle.id == target:
                self._circumcircles.pop(index)
                self._used = max(0.0, self._used - float(circle.perimeter))
                return 1
        raise RopeError(f"unknown circumcircle id {circle_id!r}")

    # -- payloads ----------------------------------------------------------

    def to_list(self) -> List[Dict[str, object]]:
        return [rope.to_dict() for rope in self._ropes]

    def circumcircle_list(self) -> List[Dict[str, object]]:
        return [circle.to_dict() for circle in self._circumcircles]

    def state_payload(self) -> Dict[str, object]:
        return {
            "ropes": self.to_list(),
            "circumcircles": self.circumcircle_list(),
            "rope_remaining": round(self.remaining, 6),
            "rope_used": round(self.used, 6),
            "rope_total": round(self._total_pool, 6),
            "rope_max_segment": round(self._max_segment, 6),
        }