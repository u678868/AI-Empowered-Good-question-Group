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

    @property
    def positive_peak(self) -> bool:
        return self.k_max > 0.0

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


_SCAN_CACHE: Dict[Tuple[object, int, Optional[int]], ManifoldFeatures] = {}

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


def _reference_triangle(manifold, peak: Tuple[float, float], base_radius: float):
    """Best reachable triangle around the positive peak (largest excess)."""
    best = None
    angles = (
        math.pi / 2.0,
        math.pi / 2.0 + 2.0 * math.pi / 3.0,
        math.pi / 2.0 + 4.0 * math.pi / 3.0,
    )
    for factor in (1.0, 1.5, 2.0):
        radius = base_radius * factor
        vertices = [
            _wrap_or_clamp(manifold, peak[0] + radius * math.cos(angle), peak[1] + radius * math.sin(angle))
            for angle in angles
        ]
        try:
            total = _tangent_angle_sum(manifold, vertices)
        except ValueError:
            continue
        excess = total - math.pi
        if best is None or excess > best[0]:
            best = (excess, total, radius)
    if best is None:
        return 0.0, 0.0, base_radius
    excess, total, radius = best
    return float(excess), float(total), float(radius)


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
) -> ManifoldFeatures:
    """Coarsely scan ``manifold`` and cache its geometric extremes."""
    if samples < 5:
        raise ValueError("samples must be >= 5 for a meaningful scan")
    key = (getattr(manifold, "cache_key", None) or id(manifold), int(samples), genus_hint)
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
    excess, angle_sum, radius = _reference_triangle(manifold, peak, base_radius)

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
    )
    _SCAN_CACHE[key] = features
    return features


def clear_scan_cache() -> None:
    """Testing helper: drop cached scans."""
    _SCAN_CACHE.clear()