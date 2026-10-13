"""Task 18: coarse manifold feasibility scanner.

``scan_manifold`` samples the *existing* manifold (no re-sampling of the world
itself) on a coarse parameter grid and caches the geometric facts a quest engine
needs before it dares to dispatch a task:

* ``k_max`` / ``k_min``  - Gaussian curvature extremes;
* ``has_parabolic_line`` - is there a sign flip (``k_min < 0 < k_max``)?
* ``genus``               - topological genus (metadata hint or numeric
  Gauss-Bonnet total curvature);
* ``reference_excess``    - the tangent-plane angle excess of a *reachable*
  reference triangle placed on the positive curvature peak.

The reference excess is measured with the same ``tangent_angle`` routine the
in-game goniometer uses, so a quest target derived from it is achievable by
construction (the "never make it unwinnable" rule).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np

from src.the_curved_world.differential import loop_polygon, parallel_transport_polyline


@dataclass(frozen=True)
class ManifoldFeatures:
    """Cached geometric summary of one manifold."""

    samples: int
    k_max: float
    k_min: float
    k_mean: float
    has_parabolic_line: bool
    genus: Optional[int]
    closed: bool
    euler_characteristic: Optional[float]
    peak: Tuple[float, float]
    metric_scale: float
    reference_radius: float
    reference_radius_world: float
    reference_angle_sum: float
    reference_excess: float
    domain_width: float
    domain_height: float
    bdp_reference_radius: float
    bdp_reference_radius_world: float
    bdp_deficit_peak: float
    bdp_ratio_target: float
    curvature_abs_integral: float = 0.0
    holonomy_reference_radius: float = 0.0
    holonomy_reference_radius_world: float = 0.0
    holonomy_reference_angle: float = 0.0
    holonomy_target_angle: float = 0.0
    parabolic_tolerance: float = 0.004
    parabolic_min_distance: float = 2.0
    homotopy_capture_radius: float = 3.0
    saddle: Tuple[float, float] = (0.0, 0.0)
    reference_deficit: float = 0.0
    reference_deficit_angle_sum: float = math.pi
    reference_deficit_radius: float = 0.0
    excess_target_easy: float = math.pi
    excess_target_medium: float = math.pi
    excess_target_hard: float = math.pi
    deficit_target_easy: float = math.pi
    deficit_target_medium: float = math.pi
    deficit_target_hard: float = math.pi

    @property
    def positive_peak(self) -> bool:
        return self.k_max > 0.0

    @property
    def negative_saddle(self) -> bool:
        # Closed manifolds use curvature scales from ~1e-4 to ~1; the
        # deficit magnitude is the physical gate, while this relative floor
        # avoids treating numerical noise as a saddle.
        return self.reference_deficit > 1e-6 and self.k_min < -1e-5

    def to_dict(self) -> Dict[str, object]:
        """Player-safe summary: extremes and topology only, never coordinates."""
        return {
            "k_max": self.k_max,
            "k_min": self.k_min,
            "k_mean": self.k_mean,
            "has_parabolic_line": self.has_parabolic_line,
            "genus": self.genus,
            "closed": self.closed,
            "has_positive_peak": self.positive_peak,

            "bdp_ratio_target": self.bdp_ratio_target,
            "has_holonomy_flux": self.curvature_abs_integral > 0.05,
            "holonomy_target_angle_degrees": math.degrees(self.holonomy_target_angle),
            "parabolic_tolerance": self.parabolic_tolerance,
            "parabolic_min_distance": self.parabolic_min_distance,
            "homotopy_capture_radius": self.homotopy_capture_radius,
        }


_SCAN_CACHE: Dict[Tuple[object, ...], ManifoldFeatures] = {}

# "A moderate triangle" for the reference measurement: about 8 world units of
# radius, but never more than 15% of the parameter domain.
REFERENCE_RADIUS_WORLD = 8.0
REFERENCE_RADIUS_MIN_FRACTION = 0.03
REFERENCE_RADIUS_MAX_FRACTION = 0.15

# Task 20: Bertrand-Diquet-Puisseux reference ring radius (fits the 100 m rope).
BDP_REFERENCE_RADIUS_WORLD = 20.0
BDP_RADIUS_MIN_FRACTION = 0.02
BDP_RADIUS_MAX_FRACTION = 0.20
BDP_MIN_KMAX = 0.00005
BDP_MAX_KR2 = 2.0
BDP_MAX_DEFICIT = 0.9

# Task 21-23: broad, scale-aware feature bands.  The closed-manifold models
# span very different curvature scales (the large torus has K ~ 1e-4), so a
# literal fixed threshold would make some otherwise valid tasks unreachable.
HOLONOMY_MIN_FLUX = 0.05
PARABOLIC_MIN_SIGN_RATIO = 0.02
PARABOLIC_MIN_TOLERANCE = 5e-6
PARABOLIC_MAX_TOLERANCE = 0.004

# Task 26: triangle target tightness and the local precheck search.  The
# fractions are relative to the strongest reachable sampling triangle, not to
# an abstract curvature bound, so a target remains physically meaningful.
TRIANGLE_DIFFICULTY_FRACTIONS = {
    "easy": 0.55,
    "medium": 0.82,
    "hard": 0.92,
}
TRIANGLE_FEASIBILITY_FACTORS = (1.0, 1.50, 2.0)
TRIANGLE_FEASIBILITY_OFFSETS = (0.0, math.pi / 6.0)


class TriangleFeasibilityReport(dict):
    """Boolean-compatible report returned by the local feasibility precheck."""

    def __bool__(self) -> bool:
        return bool(self.get("feasible", False))


def _is_periodic(manifold) -> bool:
    return bool(getattr(manifold, "periodic", False))


def _sample_axes(domain, samples: int, periodic: bool):
    if periodic:
        xs = np.linspace(domain.x_min, domain.x_max, samples, endpoint=False)
        ys = np.linspace(domain.y_min, domain.y_max, samples, endpoint=False)
        dx = domain.width / float(samples)
        dy = domain.height / float(samples)
    else:
        xs = np.linspace(domain.x_min, domain.x_max, samples)
        ys = np.linspace(domain.y_min, domain.y_max, samples)
        dx = domain.width / float(max(1, samples - 1))
        dy = domain.height / float(max(1, samples - 1))
    return xs, ys, dx, dy


def _wrap_or_clamp(manifold, u: float, v: float) -> Tuple[float, float]:
    domain = manifold.domain
    if _is_periodic(manifold):
        if hasattr(manifold, "wrap"):
            return manifold.wrap(u, v)
        return (
            domain.x_min + (u - domain.x_min) % domain.width,
            domain.y_min + (v - domain.y_min) % domain.height,
        )
    return (
        min(max(u, domain.x_min), domain.x_max),
        min(max(v, domain.y_min), domain.y_max),
    )


def _tangent_angle_sum(manifold, vertices) -> float:
    a, b, c = vertices
    return float(
        manifold.tangent_angle(a, b, c)
        + manifold.tangent_angle(b, c, a)
        + manifold.tangent_angle(c, a, b)
    )


def _reference_triangle(
    manifold,
    center: Tuple[float, float],
    base_radius: float,
    *,
    mode: str = "excess",
):
    """Best reachable triangle around a curvature extreme.

    ``mode="excess"`` maximises the angle excess around a positive peak;
    ``mode="deficit"`` minimises the angle sum around a negative saddle.
    """
    if mode not in ("excess", "deficit"):
        raise ValueError("mode must be 'excess' or 'deficit'")
    best = None
    angles = (
        math.pi / 2.0,
        math.pi / 2.0 + 2.0 * math.pi / 3.0,
        math.pi / 2.0 + 4.0 * math.pi / 3.0,
    )
    for factor in (1.0, 1.5, 2.0):
        radius = base_radius * factor
        vertices = [
            _wrap_or_clamp(
                manifold,
                center[0] + radius * math.cos(angle),
                center[1] + radius * math.sin(angle),
            )
            for angle in angles
        ]
        try:
            total = _tangent_angle_sum(manifold, vertices)
        except (ValueError, FloatingPointError, np.linalg.LinAlgError):
            continue
        excess = total - math.pi
        better = (
            best is None
            or (mode == "excess" and excess > best[0])
            or (mode == "deficit" and excess < best[0])
        )
        if better:
            best = (excess, total, radius)
    if best is None:
        return 0.0, 0.0, base_radius
    excess, total, radius = best
    return float(excess), float(total), float(radius)


def _extreme_center(manifold, mode: str, samples: int = 17) -> Tuple[float, float]:
    """Locate the sampled positive peak or negative saddle without exposing it."""
    if mode not in ("excess", "deficit"):
        raise ValueError("mode must be 'excess' or 'deficit'")
    domain = manifold.domain
    periodic = _is_periodic(manifold)
    xs, ys, _dx, _dy = _sample_axes(domain, max(5, int(samples)), periodic)
    best_center = (float(xs[0]), float(ys[0]))
    best_value = -float("inf") if mode == "excess" else float("inf")
    for v in ys:
        for u in xs:
            curvature = float(manifold.gaussian_curvature(float(u), float(v)))
            better = (
                (mode == "excess" and curvature > best_value)
                or (mode == "deficit" and curvature < best_value)
            )
            if better:
                best_value = curvature
                best_center = (float(u), float(v))
    return best_center


def _base_reference_radius(manifold, center: Tuple[float, float]) -> float:
    domain = manifold.domain
    e, _f, g = manifold.first_fundamental_form(float(center[0]), float(center[1]))
    metric_scale = max(1e-9, 0.5 * (math.sqrt(float(e)) + math.sqrt(float(g))))
    min_side = min(domain.width, domain.height)
    return float(
        min(
            max(
                REFERENCE_RADIUS_WORLD / metric_scale,
                REFERENCE_RADIUS_MIN_FRACTION * min_side,
            ),
            REFERENCE_RADIUS_MAX_FRACTION * min_side,
        )
    )


def verify_triangle_feasibility(
    manifold,
    mode: str,
    target_sum: float,
    difficulty: str = "easy",
    *,
    center: Optional[Tuple[float, float]] = None,
    blocked=None,
    samples: int = 17,
) -> Dict[str, object]:
    """Run a lightweight local triangle search before dispatching a target.

    The search tries several radii and angular offsets around the positive peak
    or negative saddle and optionally rejects candidate vertices through the
    supplied ``blocked(u, v)`` callback.  If the requested target is not
    reachable in this local neighbourhood, the returned adjusted target is
    pulled back to the chosen difficulty fraction of the best sampled triangle.
    """
    normalized_mode = str(mode).strip().lower()
    normalized_difficulty = str(difficulty).strip().lower()
    if normalized_mode not in ("excess", "deficit"):
        raise ValueError("mode must be 'excess' or 'deficit'")
    if normalized_difficulty not in TRIANGLE_DIFFICULTY_FRACTIONS:
        raise ValueError("difficulty must be one of easy/medium/hard")
    target = float(target_sum)
    if not math.isfinite(target):
        raise ValueError("target_sum must be finite")

    search_center = _extreme_center(manifold, normalized_mode, samples) if center is None else (float(center[0]), float(center[1]))
    base_radius = _base_reference_radius(manifold, search_center)
    angles = (
        math.pi / 2.0,
        math.pi / 2.0 + 2.0 * math.pi / 3.0,
        math.pi / 2.0 + 4.0 * math.pi / 3.0,
    )
    best_total = None
    attempts = 0
    for factor in TRIANGLE_FEASIBILITY_FACTORS:
        radius = base_radius * factor
        for offset in TRIANGLE_FEASIBILITY_OFFSETS:
            vertices = [
                _wrap_or_clamp(
                    manifold,
                    search_center[0] + radius * math.cos(angle + offset),
                    search_center[1] + radius * math.sin(angle + offset),
                )
                for angle in angles
            ]
            if blocked is not None and any(bool(blocked(u, v)) for u, v in vertices):
                continue
            try:
                total = _tangent_angle_sum(manifold, vertices)
            except (ValueError, FloatingPointError, np.linalg.LinAlgError):
                continue
            attempts += 1
            if best_total is None:
                best_total = total
            elif normalized_mode == "excess" and total > best_total:
                best_total = total
            elif normalized_mode == "deficit" and total < best_total:
                best_total = total

    if best_total is None:
        return TriangleFeasibilityReport({
            "feasible": False,
            "mode": normalized_mode,
            "difficulty": normalized_difficulty,
            "target_sum": float(target),
            "adjusted_target_sum": float(target),
            "best_sum": math.pi,
            "best_excess": 0.0,
            "attempts": 0,
            "adjusted": False,
            "center": [float(search_center[0]), float(search_center[1])],
        })

    best = float(best_total)
    feasible = best >= target if normalized_mode == "excess" else best <= target
    extreme = max(0.0, best - math.pi) if normalized_mode == "excess" else max(0.0, math.pi - best)
    adjusted = False
    adjusted_target = float(target)
    if not feasible:
        fraction = TRIANGLE_DIFFICULTY_FRACTIONS[normalized_difficulty]
        if normalized_mode == "excess":
            adjusted_target = math.pi + max(1e-6, fraction * extreme)
        else:
            adjusted_target = math.pi - max(1e-6, fraction * extreme)
        adjusted = True
        feasible = extreme > 1e-9
    return TriangleFeasibilityReport({
        "feasible": bool(feasible),
        "mode": normalized_mode,
        "difficulty": normalized_difficulty,
        "target_sum": float(target),
        "adjusted_target_sum": float(adjusted_target),
        "best_sum": best,
        "best_excess": float(best - math.pi),
        "attempts": int(attempts),
        "adjusted": bool(adjusted),
        "center": [float(search_center[0]), float(search_center[1])],
    })


def metric_length(surface, start, end, samples: int = 24) -> float:
    """Geodesic-ish length of the parameter segment start -> end (Task 20).

    Integrates ``sqrt(E du^2 + 2F du dv + G dv^2)`` with a midpoint rule, which
    is the Riemannian length of the surface path traced by the straight
    parameter segment. This is far more faithful than the ambient chord length
    for the tiny Bertrand-Diquet-Puisseux signal.
    """
    steps = max(2, int(samples))
    du = float(end[0]) - float(start[0])
    dv = float(end[1]) - float(start[1])
    total = 0.0
    for index in range(steps):
        t = (index + 0.5) / steps
        u = float(start[0]) + du * t
        v = float(start[1]) + dv * t
        e, f, g = surface.first_fundamental_form(u, v)
        total += math.sqrt(max(1e-12, float(e) * du * du + 2.0 * float(f) * du * dv + float(g) * dv * dv))
    return total / steps


def scan_manifold(
    manifold,
    samples: int = 31,
    *,
    genus_hint: Optional[int] = None,
    blocked=None,
    blocked_key=None,
) -> ManifoldFeatures:
    """Coarsely scan ``manifold`` and cache its geometric extremes."""
    if samples < 5:
        raise ValueError("samples must be >= 5 for a meaningful scan")
    key = (getattr(manifold, "cache_key", None) or id(manifold), int(samples), genus_hint)
    if blocked is not None:
        key = key + (blocked_key if blocked_key is not None else id(blocked),)
    cached = _SCAN_CACHE.get(key)
    if cached is not None:
        return cached

    domain = manifold.domain
    periodic = _is_periodic(manifold)
    xs, ys, dx, dy = _sample_axes(domain, int(samples), periodic)

    curvatures = np.empty((len(ys), len(xs)), dtype=float)
    total_curvature = 0.0
    for j, v in enumerate(ys):
        for i, u in enumerate(xs):
            k = float(manifold.gaussian_curvature(float(u), float(v)))
            curvatures[j, i] = k
            total_curvature += k * float(manifold.area_element(float(u), float(v))) * dx * dy

    k_max = float(np.max(curvatures))
    k_min = float(np.min(curvatures))
    k_mean = float(np.mean(curvatures))
    curvature_abs_integral = 0.0
    if samples > 0:
        for j, v in enumerate(ys):
            for i, u in enumerate(xs):
                curvature_abs_integral += abs(float(curvatures[j, i])) * float(
                    manifold.area_element(float(u), float(v))
                ) * dx * dy
    span = max(abs(k_max), abs(k_min), 1e-12)
    tolerance = 1e-4 * span
    has_parabolic_line = bool(k_min < -tolerance and k_max > tolerance)

    peak_index = np.unravel_index(int(np.argmax(curvatures)), curvatures.shape)
    peak = (float(xs[peak_index[1]]), float(ys[peak_index[0]]))
    saddle_index = np.unravel_index(int(np.argmin(curvatures)), curvatures.shape)
    saddle = (float(xs[saddle_index[1]]), float(ys[saddle_index[0]]))

    if periodic:
        euler_characteristic = float(total_curvature / (2.0 * math.pi))
    else:
        euler_characteristic = None

    if genus_hint is not None:
        genus: Optional[int] = int(genus_hint)
    elif euler_characteristic is not None:
        chi_round = int(round(euler_characteristic))
        genus = max(0, int(round((2 - chi_round) / 2.0)))
    else:
        genus = None

    E, _F, G = manifold.first_fundamental_form(peak[0], peak[1])
    metric_scale = max(1e-9, 0.5 * (math.sqrt(float(E)) + math.sqrt(float(G))))
    min_side = min(domain.width, domain.height)
    base_radius = min(
        max(REFERENCE_RADIUS_WORLD / metric_scale, REFERENCE_RADIUS_MIN_FRACTION * min_side),
        REFERENCE_RADIUS_MAX_FRACTION * min_side,
    )
    excess, angle_sum, radius = _reference_triangle(manifold, peak, base_radius, mode="excess")
    saddle_radius = _base_reference_radius(manifold, saddle)
    deficit_excess, deficit_angle_sum, deficit_radius = _reference_triangle(
        manifold,
        saddle,
        saddle_radius,
        mode="deficit",
    )
    reference_deficit = max(0.0, -float(deficit_excess))

    # Task 26: precheck both directions and materialise a target for every
    # difficulty.  A failed local target is pulled back to a point that the
    # precheck itself certifies as reachable.
    excess_limit = max(0.0, float(excess))
    medium_excess_target = math.pi + TRIANGLE_DIFFICULTY_FRACTIONS["medium"] * excess_limit
    excess_check = verify_triangle_feasibility(
        manifold,
        "excess",
        medium_excess_target,
        "medium",
        center=peak,
        blocked=blocked,
    )
    excess_extreme = (
        max(0.0, float(excess_check["best_sum"]) - math.pi)
        if int(excess_check["attempts"]) > 0
        else 0.0
    )
    if blocked is None:
        excess_extreme = excess_limit
    else:
        excess_extreme = min(excess_limit, excess_extreme)

    medium_deficit_target = math.pi - TRIANGLE_DIFFICULTY_FRACTIONS["medium"] * reference_deficit
    deficit_check = verify_triangle_feasibility(
        manifold,
        "deficit",
        medium_deficit_target,
        "medium",
        center=saddle,
        blocked=blocked,
    )
    deficit_extreme = (
        max(0.0, math.pi - float(deficit_check["best_sum"]))
        if int(deficit_check["attempts"]) > 0
        else 0.0
    )
    if blocked is None:
        deficit_extreme = reference_deficit
    else:
        deficit_extreme = min(reference_deficit, deficit_extreme)

    triangle_targets: Dict[str, float] = {}
    for difficulty, fraction in TRIANGLE_DIFFICULTY_FRACTIONS.items():
        triangle_targets[f"excess_target_{difficulty}"] = math.pi + fraction * excess_extreme
        triangle_targets[f"deficit_target_{difficulty}"] = math.pi - fraction * deficit_extreme

    # Task 20: Bertrand-Diquet-Puisseux ring reference.
    # Adapt the ring radius so the BDP expansion stays in its perturbative
    # regime (K r^2 <= BDP_MAX_KR2) while never exceeding the 100 m ropes.
    bdp_world_limit = min(
        BDP_REFERENCE_RADIUS_WORLD,
        (BDP_MAX_KR2 / max(k_max, 1e-12)) ** 0.5 if k_max > 1e-12 else BDP_REFERENCE_RADIUS_WORLD,
    )
    bdp_base_radius = min(
        max(
            bdp_world_limit / metric_scale,
            BDP_RADIUS_MIN_FRACTION * min_side,
        ),
        BDP_RADIUS_MAX_FRACTION * min_side,
    )
    bdp_radius_world = bdp_base_radius * metric_scale
    bdp_deficit_peak = max(0.0, k_max / 6.0 * bdp_radius_world * bdp_radius_world)
    bdp_deficit_peak = min(BDP_MAX_DEFICIT, bdp_deficit_peak)
    # Task 20 rework (game_task7): deliberately loose target.  The player
    # should only need to pull a reasonable circle around a positive peak, not
    # reproduce the theoretical maximum deficit exactly.
    deficit_target = max(0.015, 0.60 * bdp_deficit_peak)
    deficit_target = min(BDP_MAX_DEFICIT, deficit_target)
    bdp_ratio_target = 1.0 - max(0.0, deficit_target)

    # Task 21: choose a reference closed loop near the positive peak.  A small
    # search over scale factors keeps the reference holonomy in a useful band
    # (roughly 25-60 degrees) instead of silently using a nearly flat loop.
    holonomy_radius = float(radius)
    holonomy_angle = 0.0
    holonomy_best_error = float("inf")
    for factor in (0.35, 0.50, 0.65, 0.80, 1.00, 1.20, 1.50):
        candidate_radius = float(radius) * factor
        try:
            result = parallel_transport_polyline(
                manifold,
                loop_polygon(manifold, peak, candidate_radius, 12),
                (1.0, 0.0),
                samples_per_segment=20,
            )
        except (ValueError, np.linalg.LinAlgError, FloatingPointError):
            continue
        candidate_angle = float(result["abs_angle"])
        error = abs(candidate_angle - math.radians(40.0))
        if error < holonomy_best_error:
            holonomy_best_error = error
            holonomy_radius = candidate_radius
            holonomy_angle = candidate_angle
    if holonomy_angle < math.radians(25.0):
        holonomy_target = max(0.0, 0.60 * holonomy_angle)
    else:
        holonomy_target = min(max(math.radians(20.0), 0.60 * holonomy_angle), math.radians(65.0))
        holonomy_target = min(holonomy_target, 0.88 * holonomy_angle)

    # Task 22/23: conservative playable bands.
    peak_abs = max(abs(k_max), abs(k_min), 1e-12)
    sign_threshold = max(1e-6, PARABOLIC_MIN_SIGN_RATIO * peak_abs)
    parabolic_tolerance = max(
        PARABOLIC_MIN_TOLERANCE,
        min(PARABOLIC_MAX_TOLERANCE, 0.05 * peak_abs),
    )
    parabolic_min_distance = max(2.0, 0.015 * metric_scale * min_side)
    homotopy_capture_radius = max(3.0, 0.015 * metric_scale * min_side)
    features = ManifoldFeatures(
        samples=int(samples),
        k_max=k_max,
        k_min=k_min,
        k_mean=k_mean,
        has_parabolic_line=has_parabolic_line,
        genus=genus,
        closed=bool(periodic),
        euler_characteristic=euler_characteristic,
        peak=peak,
        metric_scale=float(metric_scale),
        reference_radius=float(radius),
        reference_radius_world=float(radius * metric_scale),
        reference_angle_sum=float(angle_sum),
        reference_excess=float(max(0.0, excess)),
        domain_width=float(domain.width),
        domain_height=float(domain.height),
        bdp_reference_radius=float(bdp_base_radius),
        bdp_reference_radius_world=float(bdp_radius_world),
        bdp_deficit_peak=float(bdp_deficit_peak),
        bdp_ratio_target=float(bdp_ratio_target),
        curvature_abs_integral=float(curvature_abs_integral),
        holonomy_reference_radius=float(holonomy_radius),
        holonomy_reference_radius_world=float(holonomy_radius * metric_scale),
        holonomy_reference_angle=float(holonomy_angle),
        holonomy_target_angle=float(holonomy_target),
        parabolic_tolerance=float(parabolic_tolerance),
        parabolic_min_distance=float(parabolic_min_distance),
        homotopy_capture_radius=float(homotopy_capture_radius),
        saddle=saddle,
        reference_deficit=float(reference_deficit),
        reference_deficit_angle_sum=float(deficit_angle_sum),
        reference_deficit_radius=float(deficit_radius),
        excess_target_easy=float(triangle_targets["excess_target_easy"]),
        excess_target_medium=float(triangle_targets["excess_target_medium"]),
        excess_target_hard=float(triangle_targets["excess_target_hard"]),
        deficit_target_easy=float(triangle_targets["deficit_target_easy"]),
        deficit_target_medium=float(triangle_targets["deficit_target_medium"]),
        deficit_target_hard=float(triangle_targets["deficit_target_hard"]),
    )
    _SCAN_CACHE[key] = features
    return features


def clear_scan_cache() -> None:
    """Testing helper: drop cached scans."""
    _SCAN_CACHE.clear()