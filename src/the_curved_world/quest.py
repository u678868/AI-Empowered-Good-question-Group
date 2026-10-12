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

from src.the_curved_world.scanner import (
    BDP_MAX_KR2,
    BDP_MIN_KMAX,
    ManifoldFeatures,
)


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
class RingMeasurement:
    """Player-side closed rope-ring measurement (Task 20 / game_task7)."""

    center_label: str
    vertex_labels: Tuple[str, ...]
    perimeter: float
    mean_radius: float
    radius_samples: Tuple[float, ...] = ()
    flat_perimeter: Optional[float] = None
    center_curvature: Optional[float] = None
    center: Optional[Tuple[float, float]] = None
    triangle_labels: Tuple[str, ...] = ()
    is_circumcircle: bool = False
    kind: str = "rope_ring"


@dataclass(frozen=True)
class HolonomyMeasurement:
    """Player-side result of transporting a vector around a closed loop."""

    start_label: str
    vertex_labels: Tuple[str, ...]
    angle: float
    closure_error: float = 0.0
    vector_start: Tuple[float, float] = (1.0, 0.0)
    vector_end: Tuple[float, float] = (1.0, 0.0)
    steps: int = 0
    kind: str = "levi_civita_holonomy"


@dataclass(frozen=True)
class ParabolicMeasurement:
    """Three player pegs tested against the zero-curvature band."""

    labels: Tuple[str, ...]
    curvatures: Tuple[float, ...]
    principal_curvatures: Tuple[Tuple[float, float], ...] = ()
    pairwise_distances: Tuple[float, ...] = ()
    kind: str = "parabolic_line"


@dataclass(frozen=True)
class HomotopyMeasurement:
    """Unwrapped phase accumulated by a player's closed circumnavigation."""

    origin_label: str
    phase_u: float
    phase_v: float
    closure_distance: float
    capture_radius: float
    current_label: str = ""
    kind: str = "non_contractible_homotopy"


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
    objective_unit: str = "deg"

    @abstractmethod
    def is_applicable(self, features: ManifoldFeatures) -> bool:
        """True when the manifold can physically host this quest."""

    @abstractmethod
    def target_value(self, features: ManifoldFeatures) -> float:
        """Objective threshold in radians, derived from measured extremes."""

    @abstractmethod
    def evaluate(self, features: ManifoldFeatures, measurement: TriangleMeasurement) -> QuestResult:
        """Judge one triangle measurement against the adaptive target."""

    def evaluate_ring(self, features: ManifoldFeatures, measurement: RingMeasurement) -> QuestResult:
        """Judge a closed rope-ring measurement (default: this quest does not use rings)."""
        return QuestResult(
            self.id,
            False,
            0.0,
            0.0,
            self.target_value(features),
            {"kind": self.id, "note": "this quest is not evaluated with a rope ring"},
        )


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


class BertrandDiquetPuisseuxQuest(GeometricQuest):
    """Quest 2: verify geodesic circle shrinkage on a positive curvature dome."""

    id = "bdp_circle_deficit"
    title = "Bertrand-Diquet-Puisseux Circle Deficit"
    relic_name = "Metric Seal"
    description = (
        "Form a triangle on a positive curvature dome and pull it into a circumscribed "
        "geodesic circle. Measure its perimeter to verify geodesic shrinkage."
    )
    hint = (
        "In flat space, a circle circumscribing three pegs spans exactly 2*pi*R. On an "
        "outward bulging dome, the boundary shrinks inward. Pull your rope into a circle "
        "at the peak to cinch the perimeter."
    )
    objective_label = "Perimeter Ratio"
    objective_unit = "ratio"
    min_vertices = 12

    def is_applicable(self, features: ManifoldFeatures) -> bool:
        radius = float(features.bdp_reference_radius_world)
        return bool(
            features.k_max > BDP_MIN_KMAX
            and features.k_max * radius * radius <= BDP_MAX_KR2
            and features.bdp_deficit_peak > 0.002
        )

    def target_value(self, features: ManifoldFeatures) -> float:
        return float(features.bdp_ratio_target)

    def evaluate(self, features: ManifoldFeatures, measurement: TriangleMeasurement) -> QuestResult:
        return QuestResult(
            self.id,
            False,
            0.0,
            0.0,
            self.target_value(features),
            {"kind": self.id, "note": "needs a closed rope ring"},
        )

    def evaluate_ring(self, features: ManifoldFeatures, measurement: RingMeasurement) -> QuestResult:
        target = self.target_value(features)
        count = len(measurement.vertex_labels)
        radius = max(1e-9, float(measurement.mean_radius))
        perimeter = float(measurement.perimeter)
        circumcircle = bool(measurement.is_circumcircle)
        if measurement.flat_perimeter is not None:
            flat_reference = max(1e-9, float(measurement.flat_perimeter))
            ratio = perimeter / flat_reference
            flat_polygon = flat_reference
        else:
            circle = 2.0 * math.pi * radius
            flat_polygon = count * 2.0 * radius * math.sin(math.pi / count) if count >= 3 else circle
            flat_reference = flat_polygon
            ratio = perimeter / flat_polygon if flat_polygon > 0 else 1.0
        circle = 2.0 * math.pi * radius
        ratio_circle = perimeter / circle if circle > 0 else 1.0
        span = max(1e-9, 1.0 - target)
        progress = _clamp((1.0 - ratio) / span, 0.0, 1.0)
        enough_vertices = circumcircle or count >= self.min_vertices
        completed = bool(enough_vertices and ratio <= target)
        deficit = max(0.0, 1.0 - ratio)
        k_estimate = (3.0 / (math.pi * radius ** 3)) * (flat_reference - perimeter)
        analytic_k = float(measurement.center_curvature) if measurement.center_curvature is not None else features.k_max
        labels = measurement.triangle_labels or measurement.vertex_labels
        steps = [
            "Bertrand-Diquet-Puisseux: a geodesic circle of radius r obeys C(r) = 2*pi*r - (pi/3) K r^3 + O(r^4).",
            "Pegs %s define flat circumradius R = %.3f m from a*b*c/(4*Area)." % (
                ", ".join(str(label) for label in labels[:3]) or "A, B, C",
                radius,
            ),
            "Flat reference circumference: C_flat = 2*pi*R = %.2f m." % flat_reference,
            "Measured surface circumference: C_real = %.2f m; deficit = %.2f%%; target ratio <= %.4f." % (
                perimeter,
                deficit * 100.0,
                target,
            ),
            "Inverse estimate K_est = 3(C_flat - C_real)/(pi*R^3) = %.6g vs analytic K = %.6g." % (
                k_estimate,
                analytic_k,
            ),
        ]
        detail = {
            "kind": self.id,
            "steps": steps,
            "vertex_count": count,
            "center": measurement.center_label,
            "vertices": list(measurement.vertex_labels),
            "triangle_labels": list(labels),
            "perimeter": perimeter,
            "mean_radius": radius,
            "circle_perimeter": circle,
            "flat_perimeter": flat_reference,
            "flat_polygon_perimeter": flat_polygon,
            "ratio": ratio,
            "ratio_circle": ratio_circle,
            "target_ratio": target,
            "deficit": deficit,
            "k_estimate": k_estimate,
            "k_analytic": analytic_k,
            "center_curvature": measurement.center_curvature,
            "is_circumcircle": circumcircle,
            "relic": self.relic_name,
        }
        return QuestResult(self.id, completed, progress, ratio, target, detail)


class HolonomyQuest(GeometricQuest):
    """Quest 3: measure the Levi-Civita rotation around a closed circuit."""

    id = "holonomy_loop"
    title = "Levi-Civita Holonomy Loop"
    relic_name = "Connection Seal"
    description = (
        "Carry a parallel-transported tangent vector around a closed circuit encircling "
        "curved terrain. Measure the final rotation angle upon return."
    )
    hint = (
        "In flat space, a spear carried around any loop returns pointing true. On curved soil, "
        "the connection twists its tip. Encircle the heights to turn your compass needle."
    )
    objective_label = "Holonomy Angle"
    objective_unit = "deg"

    def is_applicable(self, features: ManifoldFeatures) -> bool:
        return bool(
            features.closed
            and features.curvature_abs_integral > 0.05
            and features.holonomy_reference_angle > 1e-6
            and features.holonomy_target_angle > 1e-6
        )

    def target_value(self, features: ManifoldFeatures) -> float:
        return float(features.holonomy_target_angle)

    def evaluate(self, features: ManifoldFeatures, measurement: HolonomyMeasurement) -> QuestResult:
        if not isinstance(measurement, HolonomyMeasurement):
            return QuestResult(self.id, False, 0.0, 0.0, self.target_value(features), {
                "kind": self.id,
                "note": "this quest needs a parallel-transport loop measurement",
            })
        achieved = abs(float(measurement.angle))
        target = self.target_value(features)
        closure_tolerance = max(0.10, 1e-4 * max(1.0, features.reference_radius_world))
        closed = float(measurement.closure_error) <= closure_tolerance
        progress = _clamp(achieved / max(target, 1e-12), 0.0, 1.0)
        completed = bool(closed and len(measurement.vertex_labels) >= 3 and achieved >= target)
        steps = [
            "The Levi-Civita transport equation is dv^k/dt + Gamma^k_ij (dx^i/dt) v^j = 0.",
            "The reference loop around the positive peak encloses a curvature flux of |K| dA and yields a target holonomy of %.2f deg." % math.degrees(target),
            "The player loop is closed within %.3f m (tolerance %.3f m) with %d path points." % (
                float(measurement.closure_error),
                closure_tolerance,
                len(measurement.vertex_labels),
            ),
            "Numerical transport produced v_start = (%.6f, %.6f) and v_end = (%.6f, %.6f) in the (u,v) chart." % (
                measurement.vector_start[0],
                measurement.vector_start[1],
                measurement.vector_end[0],
                measurement.vector_end[1],
            ),
            "Metric angle between the start and end vectors: Delta alpha = %.2f deg; relic awarded: %s." % (
                math.degrees(achieved),
                self.relic_name,
            ),
        ]
        detail = {
            "kind": self.id,
            "steps": steps,
            "theorem": "Ambrose-Singer: parallel transport around a closed loop rotates by integral K dA modulo 2*pi.",
            "holonomy_angle": achieved,
            "holonomy_degrees": math.degrees(achieved),
            "target_angle": target,
            "target_degrees": math.degrees(target),
            "closure_error": float(measurement.closure_error),
            "closure_tolerance": closure_tolerance,
            "vertex_labels": list(measurement.vertex_labels),
            "vector_start": list(measurement.vector_start),
            "vector_end": list(measurement.vector_end),
            "transport_steps": int(measurement.steps),
            "relic": self.relic_name,
        }
        return QuestResult(self.id, completed, progress, achieved, target, detail)


class ParabolicLineQuest(GeometricQuest):
    """Quest 4: mark three separated points on the K = 0 parabolic seam."""

    id = "parabolic_line"
    title = "Parabolic Curve Tracing"
    relic_name = "Singularity Seal"
    description = (
        "Locate the borderland where the surface transitions from bulge to saddle. "
        "Plant 3 pegs along the silent zero-curvature parabolic boundary."
    )
    hint = (
        "Between the outward domes (K > 0) and the twisting saddles (K < 0) lies a border "
        "of zero curvature. Find where the world flattens along one direction and mark the seam."
    )
    objective_label = "Parabolic Pegs"
    objective_unit = "count"

    def is_applicable(self, features: ManifoldFeatures) -> bool:
        if features.genus is None or int(features.genus) < 1:
            return False
        peak_abs = max(abs(features.k_max), abs(features.k_min), 1e-12)
        threshold = max(1e-6, 0.02 * peak_abs)
        return bool(features.k_min < -threshold and features.k_max > threshold)

    def target_value(self, features: ManifoldFeatures) -> float:
        return 3.0

    def evaluate(self, features: ManifoldFeatures, measurement: ParabolicMeasurement) -> QuestResult:
        if not isinstance(measurement, ParabolicMeasurement):
            return QuestResult(self.id, False, 0.0, 0.0, self.target_value(features), {
                "kind": self.id,
                "note": "this quest needs three parabolic peg measurements",
            })
        labels = tuple(str(label) for label in measurement.labels)
        curvatures = tuple(float(value) for value in measurement.curvatures)
        distances = tuple(float(value) for value in measurement.pairwise_distances)
        tolerance = float(features.parabolic_tolerance)
        d_min = float(features.parabolic_min_distance)
        valid_count = sum(1 for value in curvatures if abs(value) <= tolerance)
        spacing_ok = bool(len(distances) >= 3 and min(distances) >= d_min)
        distinct = len(set(labels)) == 3
        completed = bool(valid_count == 3 and spacing_ok and distinct)
        progress = _clamp(valid_count / 3.0, 0.0, 1.0)
        if valid_count == 3 and not spacing_ok:
            progress = 0.9
        principal = [
            [float(pair[0]), float(pair[1])]
            for pair in measurement.principal_curvatures
            if isinstance(pair, (tuple, list)) and len(pair) >= 2
        ]
        steps = [
            "At a parabolic point K = kappa_1 * kappa_2 = 0, so at least one principal curvature vanishes.",
            "The scanner chose a broad band |K| <= %.6f, not an exact floating-point zero." % tolerance,
            "Peg readings: %s; valid peg count = %d / 3." % (
                ", ".join("%s: %.3g" % (label, value) for label, value in zip(labels, curvatures)),
                valid_count,
            ),
            "Pairwise surface separations: %s m; required minimum d_min = %.3f m." % (
                ", ".join("%.3f" % value for value in distances) or "none",
                d_min,
            ),
            "Principal-curvature polynomial det(II - kappa I) has roots %s; relic awarded: %s." % (
                principal or "not sampled",
                self.relic_name,
            ),
        ]
        detail = {
            "kind": self.id,
            "steps": steps,
            "theorem": "K = det(I^-1 II) = kappa_1 * kappa_2; a parabolic point has a zero principal curvature.",
            "labels": list(labels),
            "curvatures": list(curvatures),
            "principal_curvatures": principal,
            "pairwise_distances": list(distances),
            "valid_pegs": int(valid_count),
            "target_pegs": 3,
            "tolerance": tolerance,
            "min_distance": d_min,
            "spacing_ok": spacing_ok,
            "relic": self.relic_name,
        }
        return QuestResult(self.id, completed, progress, float(valid_count), 3.0, detail)


class HomotopyLoopQuest(GeometricQuest):
    """Quest 5: wind once around a handle and return to the origin beacon."""

    id = "homotopy_loop"
    title = "Non-Contractible Homotopy Loop"
    relic_name = "Topology Seal"
    description = (
        "Embark on a grand circumnavigation. Run continuously along a coordinate meridian "
        "until you meet your origin peg from the other side of space."
    )
    hint = (
        "On a flat plane, every tied loop shrinks to a point. On an academy torus, some paths "
        "wind around the abyss of high dimensions. Run until you face your past self."
    )
    objective_label = "Circumnavigation Phase"
    objective_unit = "pi"

    def is_applicable(self, features: ManifoldFeatures) -> bool:
        return bool(features.genus is not None and int(features.genus) >= 1 and features.closed)

    def target_value(self, features: ManifoldFeatures) -> float:
        return 1.8

    def evaluate(self, features: ManifoldFeatures, measurement: HomotopyMeasurement) -> QuestResult:
        if not isinstance(measurement, HomotopyMeasurement):
            return QuestResult(self.id, False, 0.0, 0.0, self.target_value(features), {
                "kind": self.id,
                "note": "this quest needs a closed homotopy-loop measurement",
            })
        phase_u = float(measurement.phase_u)
        phase_v = float(measurement.phase_v)
        phase_max = max(abs(phase_u), abs(phase_v))
        winding_max = phase_max / (2.0 * math.pi)
        target = self.target_value(features)
        capture = max(float(measurement.capture_radius), 1e-9)
        closed = float(measurement.closure_distance) <= capture
        completed = bool(closed and phase_max >= 1.8 * math.pi)
        progress = _clamp(phase_max / (1.8 * math.pi), 0.0, 1.0)
        steps = [
            "The universal cover unwraps a periodic path into (u_0 + Delta u, v_0 + Delta v).",
            "Winding numbers are n_u = Delta u / (2*pi) = %.4f and n_v = Delta v / (2*pi) = %.4f." % (
                phase_u / (2.0 * math.pi),
                phase_v / (2.0 * math.pi),
            ),
            "The path returns to the origin beacon within %.3f m (capture radius %.3f m)." % (
                float(measurement.closure_distance),
                capture,
            ),
            "A non-contractible class requires |n_u| >= 1 or |n_v| >= 1; current max winding = %.4f." % winding_max,
            "The first fundamental group of a genus-%s surface is non-trivial; relic awarded: %s." % (
                features.genus,
                self.relic_name,
            ),
        ]
        detail = {
            "kind": self.id,
            "steps": steps,
            "theorem": "On a genus-g >= 1 closed surface, pi_1 is non-trivial and a coordinate loop has non-zero winding.",
            "phase_u": phase_u,
            "phase_v": phase_v,
            "phase_max_pi": phase_max / math.pi,
            "winding_u": phase_u / (2.0 * math.pi),
            "winding_v": phase_v / (2.0 * math.pi),
            "winding_max": winding_max,
            "closure_distance": float(measurement.closure_distance),
            "capture_radius": capture,
            "origin_label": measurement.origin_label,
            "current_label": measurement.current_label,
            "target_phase_pi": target,
            "relic": self.relic_name,
        }
        return QuestResult(self.id, completed, progress, phase_max / math.pi, target, detail)


class QuestManager:
    """Deterministic quest chain + relic ledger + exit seal state."""

    def __init__(
        self,
        features: ManifoldFeatures,
        seed: int,
        quests: Optional[Sequence[GeometricQuest]] = None,
    ) -> None:
        self._features = features
        pool: List[GeometricQuest] = (
            list(quests)
            if quests is not None
            else [
                GaussBonnetQuest(),
                BertrandDiquetPuisseuxQuest(),
                HolonomyQuest(),
                ParabolicLineQuest(),
                HomotopyLoopQuest(),
            ]
        )
        applicable = [quest for quest in pool if quest.is_applicable(features)]
        # Keep the authored curriculum order stable.  The scanner still
        # filters impossible tasks, and using a fixed order makes the result
        # reproducible across machines and teacher/student replays.
        self._chain: List[GeometricQuest] = list(applicable)
        self._index = 0
        self._completed: List[str] = []
        self._relics: List[str] = []
        self._last_measurement: Optional[TriangleMeasurement] = None
        self._last_ring: Optional[RingMeasurement] = None
        self._last_holonomy: Optional[HolonomyMeasurement] = None
        self._last_parabolic: Optional[ParabolicMeasurement] = None
        self._last_homotopy: Optional[HomotopyMeasurement] = None
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

    def _advance(self, quest: GeometricQuest, result: QuestResult) -> None:
        self._last_proof = self.completion_payload(quest, result)
        self._completed.append(quest.id)
        self._relics.append(quest.relic_name)
        self._index += 1
        self._seal_contact = False
        self._last_measurement = None
        self._last_result = None
        self._last_ring = None
        self._last_holonomy = None
        self._last_parabolic = None
        self._last_homotopy = None

    def evaluate_measurement(self, measurement: TriangleMeasurement) -> Optional[QuestResult]:
        quest = self.active_quest
        if quest is None:
            return None
        result = quest.evaluate(self._features, measurement)
        self._last_measurement = measurement
        self._last_result = result
        if result.completed:
            self._advance(quest, result)
        return result

    def evaluate_ring_measurement(self, measurement: RingMeasurement) -> Optional[QuestResult]:
        quest = self.active_quest
        if quest is None:
            return None
        result = quest.evaluate_ring(self._features, measurement)
        self._last_ring = measurement
        self._last_result = result
        if result.completed:
            self._advance(quest, result)
        return result

    def evaluate_holonomy_measurement(self, measurement: HolonomyMeasurement) -> Optional[QuestResult]:
        quest = self.active_quest
        if quest is None:
            return None
        result = quest.evaluate(self._features, measurement)
        self._last_holonomy = measurement
        self._last_result = result
        if result.completed:
            self._advance(quest, result)
        return result

    def evaluate_parabolic_measurement(self, measurement: ParabolicMeasurement) -> Optional[QuestResult]:
        quest = self.active_quest
        if quest is None:
            return None
        result = quest.evaluate(self._features, measurement)
        self._last_parabolic = measurement
        self._last_result = result
        if result.completed:
            self._advance(quest, result)
        return result

    def evaluate_homotopy_measurement(self, measurement: HomotopyMeasurement) -> Optional[QuestResult]:
        quest = self.active_quest
        if quest is None:
            return None
        result = quest.evaluate(self._features, measurement)
        self._last_homotopy = measurement
        self._last_result = result
        if result.completed:
            self._advance(quest, result)
        return result

    def completion_payload(self, quest: GeometricQuest, result: QuestResult) -> Dict[str, Any]:
        detail = result.detail
        steps = detail.get("steps")
        if not steps:
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
            "kind": detail.get("kind", quest.id),
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
            "objective_unit": None if quest is None else quest.objective_unit,
            "objective_target": None if quest is None else objective_values(quest, target, None)[1],
            "objective_current": None if quest is None else objective_values(quest, target, self._last_result)[0],
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


def objective_values(quest: GeometricQuest, target: Optional[float], result: Optional[QuestResult]):
    """Return (current, target) in the quest's display unit (Tasks 18-23)."""
    if target is None:
        return None, None
    unit = getattr(quest, "objective_unit", "deg")
    detail = {} if result is None else dict(getattr(result, "detail", {}) or {})
    if unit == "ratio":
        current = None if result is None else float(result.achieved)
        return current, float(target)
    if unit == "count":
        current = detail.get("valid_pegs")
        return (None if current is None else float(current)), float(target)
    if unit == "pi":
        current = detail.get("phase_max_pi")
        return (None if current is None else float(current)), float(target)
    current = detail.get("angle_sum_degrees", detail.get("holonomy_degrees"))
    if current is None and result is not None:
        current = float(result.achieved)
    return current, math.degrees(float(target))


def empty_quest_state() -> Dict[str, Any]:
    """Payload when a session deliberately runs without a quest manager."""
    return {
        "id": None,
        "title": "No active quest",
        "description": "",
        "hint": "",
        "relic_name": None,
        "objective": None,
        "objective_unit": None,
        "objective_target": None,
        "objective_current": None,
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