"""Task 18: geometric quest engine scaffolding.

The engine is deliberately *data first*: a quest declares the manifold
conditions it needs (``is_applicable``), an objective value derived from the
scanner (``target_value``) and how to judge a measurement (``evaluate``).
``QuestManager`` keeps the deterministic chain, the collected relics and the
exit-seal state that the game/session expose to the player.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.the_curved_world.scanner import ManifoldFeatures


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class TriangleMeasurement:
    """Player-side goniometer output fed into a quest evaluation."""

    angle_sum: float
    markers: Tuple[str, ...] = ()
    excess: float = 0.0
    curvature_integral: float = 0.0


@dataclass(frozen=True)
class QuestResult:
    """Outcome of evaluating one measurement for the active quest."""

    quest_id: str
    completed: bool
    progress: float
    achieved: float
    target: float
    detail: Dict[str, Any] = field(default_factory=dict)


class GeometricQuest(ABC):
    """Base class for one geometric imprint task."""

    id: str = "geometric_quest"
    title: str = "Geometric Quest"
    description: str = ""
    hint: str = ""
    relic_name: str = "Geometric Seal"
    objective_label: str = "Angle Sum"

    @abstractmethod
    def is_applicable(self, features: ManifoldFeatures) -> bool:
        """True when the manifold can physically host this quest."""

    @abstractmethod
    def target_value(self, features: ManifoldFeatures) -> float:
        """Objective threshold in radians, derived from measured extremes."""

    @abstractmethod
    def evaluate(self, features: ManifoldFeatures, measurement: TriangleMeasurement) -> QuestResult:
        """Judge one measurement against the adaptive target."""


class GaussBonnetQuest(GeometricQuest):
    """Quest 1: enclose enough positive curvature to beat an angle-sum target."""

    id = "gauss_bonnet_excess"
    title = "Gauss-Bonnet Angle Excess"
    description = (
        "Find a positive-curvature ridge, place three beacons and use the goniometer "
        "to enclose a triangle whose interior angle sum beats the adaptive target."
    )
    hint = (
        "For a small triangle, (sum of angles - 180 deg) equals the integral of K dA. "
        "Stay near a convex bump and widen the triangle if the measured excess is short."
    )
    relic_name = "Curvature Seal"
    objective_label = "Angle Sum"

    def is_applicable(self, features: ManifoldFeatures) -> bool:
        return bool(features.k_max > 0.0 and features.reference_excess > 1e-6)

    def target_value(self, features: ManifoldFeatures) -> float:
        """Adaptive angle-sum target in radians.

        The reference excess is what a reachable triangle on the positive peak
        already achieves, so the target is always strictly above 180 deg and
        strictly below the measured physical maximum (never unwinnable).
        """
        reference = max(float(features.reference_excess), 1e-9)
        desired = 0.60 * reference
        window_low = min(math.radians(20.0), 0.50 * reference)
        window_high = min(math.radians(80.0), 0.85 * reference)
        excess_target = _clamp(desired, window_low, window_high)
        excess_target = min(excess_target, 0.95 * reference)
        return math.pi + max(0.0, excess_target)

    def evaluate(self, features: ManifoldFeatures, measurement: TriangleMeasurement) -> QuestResult:
        target = self.target_value(features)
        achieved = float(measurement.angle_sum)
        span = max(target - math.pi, 1e-9)
        progress = _clamp((achieved - math.pi) / span, 0.0, 1.0)
        completed = bool(achieved >= target)
        detail = {
            "theorem": "Gauss-Bonnet: sum(theta_i) - pi = integral_T K dA (geodesic triangle)",
            "angle_sum_degrees": math.degrees(achieved),
            "target_degrees": math.degrees(target),
            "excess_degrees": math.degrees(achieved - math.pi),
            "target_excess_degrees": math.degrees(target - math.pi),
            "reference_excess_degrees": math.degrees(features.reference_excess),
            "k_max": features.k_max,
            "genus": features.genus,
            "markers": list(measurement.markers),
            "relic": self.relic_name,
        }
        return QuestResult(self.id, completed, progress, achieved, target, detail)


class QuestManager:
    """Deterministic quest chain + relic ledger + exit seal state."""

    def __init__(
        self,
        features: ManifoldFeatures,
        seed: int,
        quests: Optional[Sequence[GeometricQuest]] = None,
    ) -> None:
        self._features = features
        pool: List[GeometricQuest] = list(quests) if quests is not None else [GaussBonnetQuest()]
        applicable = [quest for quest in pool if quest.is_applicable(features)]
        rng = np.random.default_rng(abs(int(seed)) % (2 ** 63))
        order = rng.permutation(len(applicable)) if applicable else []
        self._chain: List[GeometricQuest] = [applicable[int(index)] for index in order]
        self._index = 0
        self._completed: List[str] = []
        self._relics: List[str] = []
        self._last_measurement: Optional[TriangleMeasurement] = None
        self._last_result: Optional[QuestResult] = None
        self._seal_contact = False
        self._last_proof: Optional[Dict[str, Any]] = None
        self._features_payload = features.to_dict()

    # -- read-only state ---------------------------------------------------

    @property
    def features(self) -> ManifoldFeatures:
        return self._features

    @property
    def active_quest(self) -> Optional[GeometricQuest]:
        if 0 <= self._index < len(self._chain):
            return self._chain[self._index]
        return None

    @property
    def chain(self) -> Tuple[str, ...]:
        """Deterministic quest id order for this manager (Task 18)."""
        return tuple(quest.id for quest in self._chain)

    @property
    def completed_quests(self) -> Tuple[str, ...]:
        return tuple(self._completed)

    @property
    def relics(self) -> Tuple[str, ...]:
        return tuple(self._relics)

    @property
    def exit_unlocked(self) -> bool:
        return self.active_quest is None

    @property
    def exit_sealed(self) -> bool:
        return not self.exit_unlocked

    @property
    def seal_contact(self) -> bool:
        return self._seal_contact

    def mark_seal_contact(self, value: bool = True) -> None:
        self._seal_contact = bool(value)

    def target_value(self) -> Optional[float]:
        quest = self.active_quest
        return None if quest is None else float(quest.target_value(self._features))

    # -- evaluation --------------------------------------------------------

    def evaluate_measurement(self, measurement: TriangleMeasurement) -> Optional[QuestResult]:
        quest = self.active_quest
        if quest is None:
            return None
        result = quest.evaluate(self._features, measurement)
        self._last_measurement = measurement
        self._last_result = result
        if result.completed:
            self._last_proof = self.completion_payload(quest, result)
            self._completed.append(quest.id)
            self._relics.append(quest.relic_name)
            self._index += 1
            self._seal_contact = False
            self._last_measurement = None
            self._last_result = None
        return result

    def completion_payload(self, quest: GeometricQuest, result: QuestResult) -> Dict[str, Any]:
        detail = result.detail
        steps = [
            "A geodesic triangle on a curved surface obeys the Gauss-Bonnet relation:",
            "sum(theta_i) - pi = integral over the triangle of K dA.",
            "Measured interior angle sum: %.2f deg (excess %.2f deg)." % (
                detail.get("angle_sum_degrees", 0.0),
                detail.get("excess_degrees", 0.0),
            ),
            "Adaptive target: %.2f deg (reference peak excess %.2f deg, safety-clamped)." % (
                detail.get("target_degrees", 0.0),
                detail.get("reference_excess_degrees", 0.0),
            ),
            "Relic awarded: %s." % quest.relic_name,
        ]
        return {
            "quest_id": quest.id,
            "title": quest.title,
            "theorem": detail.get("theorem", ""),
            "steps": steps,
            "angle_sum_degrees": detail.get("angle_sum_degrees"),
            "target_degrees": detail.get("target_degrees"),
            "excess_degrees": detail.get("excess_degrees"),
            "reference_excess_degrees": detail.get("reference_excess_degrees"),
            "relic": quest.relic_name,
            "detail": dict(detail),
        }

    # -- payloads ----------------------------------------------------------

    def state_payload(self) -> Dict[str, Any]:
        quest = self.active_quest
        target = self.target_value()
        achieved = None if self._last_measurement is None else float(self._last_measurement.angle_sum)
        progress = 0.0 if self._last_result is None else float(self._last_result.progress)
        return {
            "id": None if quest is None else quest.id,
            "title": quest.title if quest is not None else "All geometric seals claimed",
            "description": quest.description if quest is not None else "The exit seal is open.",
            "hint": quest.hint if quest is not None else "",
            "relic_name": None if quest is None else quest.relic_name,
            "objective": None if quest is None else quest.objective_label,
            "target_angle_sum_degrees": None if target is None else math.degrees(target),
            "current_angle_sum_degrees": None if achieved is None else math.degrees(achieved),
            "progress": progress,
            "completed": self.exit_unlocked,
            "completed_quests": list(self._completed),
            "relics": list(self._relics),
            "exit_sealed": self.exit_sealed,
            "seal_contact": self._seal_contact,
            "required_remaining": 1 if quest is not None else 0,
            "last_proof": None if self._last_proof is None else dict(self._last_proof),
            "features": dict(self._features_payload),
        }


def empty_quest_state() -> Dict[str, Any]:
    """Payload when a session deliberately runs without a quest manager."""
    return {
        "id": None,
        "title": "No active quest",
        "description": "",
        "hint": "",
        "relic_name": None,
        "objective": None,
        "target_angle_sum_degrees": None,
        "current_angle_sum_degrees": None,
        "progress": 0.0,
        "completed": True,
        "completed_quests": [],
        "relics": [],
        "exit_sealed": False,
        "seal_contact": False,
        "required_remaining": 0,
        "last_proof": None,
        "features": {},
    }