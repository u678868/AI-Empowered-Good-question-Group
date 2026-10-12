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
        }


_SCAN_CACHE: Dict[Tuple[object, int, Optional[int]], ManifoldFeatures] = {}

# "A moderate triangle" for the reference measurement: about 8 world units of
# radius, but never more than 15% of the parameter domain.
REFERENCE_RADIUS_WORLD = 8.0
REFERENCE_RADIUS_MIN_FRACTION = 0.03
REFERENCE_RADIUS_MAX_FRACTION = 0.15


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
    )
    _SCAN_CACHE[key] = features
    return features


def clear_scan_cache() -> None:
    """Testing helper: drop cached scans."""
    _SCAN_CACHE.clear()