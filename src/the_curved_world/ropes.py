"""Task 19: finite surveyor rope system.

A rope connects two *player-known* nodes: a marker peg or an obstacle that is
currently inside the player's view. The system enforces a single-segment limit
and a total length pool, and it only ever stores player-visible endpoints, so it
cannot be used to probe unexplored regions or the hidden exit.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

DEFAULT_MAX_SEGMENT = 100.0
DEFAULT_TOTAL_POOL = 300.0

VALID_NODE_KINDS = ("marker", "obstacle")


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
        self._next_id = 0
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

    def ropes_at(self, node: RopeNode) -> Tuple[Rope, ...]:
        """Every rope bound to ``node`` (Task 19: at most two per path point)."""
        key = node_key(node)
        return tuple(
            rope
            for rope in self._ropes
            if node_key(rope.node_a) == key or node_key(rope.node_b) == key
        )

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
            self._used = 0.0
            return removed
        target = int(rope_id)
        for index, rope in enumerate(self._ropes):
            if rope.id == target:
                self._ropes.pop(index)
                self._used = max(0.0, self._used - rope.length_3d)
                return 1
        raise RopeError(f"unknown rope id {rope_id!r}")

    # -- payloads ----------------------------------------------------------

    def to_list(self) -> List[Dict[str, object]]:
        return [rope.to_dict() for rope in self._ropes]

    def state_payload(self) -> Dict[str, object]:
        return {
            "ropes": self.to_list(),
            "rope_remaining": round(self.remaining, 6),
            "rope_used": round(self.used, 6),
            "rope_total": round(self._total_pool, 6),
            "rope_max_segment": round(self._max_segment, 6),
        }