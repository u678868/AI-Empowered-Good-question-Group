"""Differential-geometry helpers shared by scanners and quests.

The helpers are deliberately surface-agnostic: they only require the small
interface already implemented by both ``SmoothSurface`` and ``ClosedManifold``
(``first_fundamental_form``, ``second_fundamental_form`` and ``position``).
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence, Tuple

import numpy as np

from src.the_curved_world.manifold import wrap_parameter


def _clamp_parameter(surface, u: float, v: float) -> Tuple[float, float]:
    """Move a sample back into the valid chart before a finite difference."""
    domain = surface.domain
    if bool(getattr(surface, "periodic", False)):
        return wrap_parameter(u), wrap_parameter(v)
    return (
        min(max(float(u), float(domain.x_min)), float(domain.x_max)),
        min(max(float(v), float(domain.y_min)), float(domain.y_max)),
    )


def _metric(surface, u: float, v: float) -> np.ndarray:
    e, f, g = surface.first_fundamental_form(float(u), float(v))
    return np.array([[float(e), float(f)], [float(f), float(g)]], dtype=float)


def _periodic_delta(surface, delta: float) -> float:
    return wrap_parameter(delta) if bool(getattr(surface, "periodic", False)) else float(delta)


def christoffel_symbols(surface, u: float, v: float, h: float = 1e-4) -> np.ndarray:
    """Return ``Gamma[k, i, j]`` from finite differences of the metric.

    The formula is the standard Levi-Civita one::

        Gamma^k_ij = 1/2 g^kl (d_i g_jl + d_j g_il - d_l g_ij)

    Derivatives are evaluated with central differences.  The helper is used
    only for closed regular chart regions in the quest path, so the chart is
    wrapped (or clamped for a graph surface) before each evaluation.
    """
    h = max(float(h), 1e-7)
    g = _metric(surface, u, v)
    dg = np.empty((2, 2, 2), dtype=float)  # dg[direction, row, column]

    for direction, step in ((0, (h, 0.0)), (1, (0.0, h))):
        um, vm = _clamp_parameter(surface, u - step[0], v - step[1])
        up, vp = _clamp_parameter(surface, u + step[0], v + step[1])
        dg[direction] = (_metric(surface, up, vp) - _metric(surface, um, vm)) / (2.0 * h)

    inv_g = np.linalg.inv(g)
    gamma = np.zeros((2, 2, 2), dtype=float)
    for k in range(2):
        for i in range(2):
            for j in range(2):
                total = 0.0
                for ell in range(2):
                    total += 0.5 * inv_g[k, ell] * (
                        dg[i, j, ell] + dg[j, i, ell] - dg[ell, i, j]
                    )
                gamma[k, i, j] = total
    return gamma


def metric_inner(surface, u: float, v: float, first: Sequence[float], second: Sequence[float]) -> float:
    """Inner product of two tangent vectors in chart coordinates."""
    g = _metric(surface, u, v)
    a = np.asarray(first, dtype=float)
    b = np.asarray(second, dtype=float)
    return float(a @ g @ b)


def metric_norm(surface, u: float, v: float, vector: Sequence[float]) -> float:
    return math.sqrt(max(0.0, metric_inner(surface, u, v, vector, vector)))


def normalize_tangent(surface, u: float, v: float, vector: Sequence[float]) -> Tuple[float, float]:
    norm = metric_norm(surface, u, v, vector)
    if norm < 1e-12:
        raise ValueError("cannot normalize a zero tangent vector")
    return (float(vector[0]) / norm, float(vector[1]) / norm)


def _transport_step(
    surface,
    u: float,
    v: float,
    du: float,
    dv: float,
    vector: np.ndarray,
) -> np.ndarray:
    gamma = christoffel_symbols(surface, u, v)
    # d v^k / dt = -Gamma^k_ij xdot^i v^j
    connection = np.einsum("kij,i,j->k", gamma, np.array([du, dv]), vector)
    return vector - connection


def parallel_transport_polyline(
    surface,
    vertices: Sequence[Sequence[float]],
    initial_vector: Sequence[float],
    samples_per_segment: int = 24,
) -> dict:
    """Parallel transport a chart tangent vector along a closed polygon.

    ``vertices`` may include the repeated first point at the end; the helper
    also closes an open list automatically.  Each edge is integrated with a
    fourth-order Runge-Kutta step in the straight parameter segment.
    """
    if len(vertices) < 3:
        raise ValueError("parallel transport needs at least three vertices")
    points = [(float(point[0]), float(point[1])) for point in vertices]
    if math.hypot(_periodic_delta(surface, points[0][0] - points[-1][0]),
                  _periodic_delta(surface, points[0][1] - points[-1][1])) > 1e-7:
        points.append(points[0])
    start = points[0]
    start_vector = normalize_tangent(surface, start[0], start[1], initial_vector)
    vector = np.asarray(start_vector, dtype=float)
    total_steps = 0
    for index in range(len(points) - 1):
        u0, v0 = points[index]
        u1, v1 = points[index + 1]
        du = _periodic_delta(surface, u1 - u0)
        dv = _periodic_delta(surface, v1 - v0)
        steps = max(2, int(samples_per_segment))
        dt = 1.0 / float(steps)
        for step_index in range(steps):
            t = step_index * dt
            u = u0 + du * t
            v = v0 + dv * t
            k1 = _transport_step(surface, u, v, du, dv, vector)
            k2 = _transport_step(surface, u + 0.5 * du * dt, v + 0.5 * dv * dt, du, dv, vector + 0.5 * dt * k1)
            k3 = _transport_step(surface, u + 0.5 * du * dt, v + 0.5 * dv * dt, du, dv, vector + 0.5 * dt * k2)
            k4 = _transport_step(surface, u + du * dt, v + dv * dt, du, dv, vector + dt * k3)
            vector = vector + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
            total_steps += 1
    vector = np.asarray(normalize_tangent(surface, start[0], start[1], vector), dtype=float)
    first = np.asarray(start_vector, dtype=float)
    cosine = metric_inner(surface, start[0], start[1], first, vector)
    denominator = metric_norm(surface, start[0], start[1], first) * metric_norm(
        surface, start[0], start[1], vector
    )
    cosine = max(-1.0, min(1.0, cosine / max(denominator, 1e-15)))
    sine_numer = float(first[0] * vector[1] - first[1] * vector[0])
    sine_numer *= math.sqrt(max(1e-15, float(np.linalg.det(_metric(surface, *start)))))
    sine = sine_numer / max(denominator, 1e-15)
    angle = math.atan2(max(-1.0, min(1.0, sine)), cosine)
    return {
        "start": start,
        "vector_start": (float(first[0]), float(first[1])),
        "vector_end": (float(vector[0]), float(vector[1])),
        "angle": float(angle),
        "abs_angle": float(abs(angle)),
        "steps": int(total_steps),
    }


def principal_curvatures(surface, u: float, v: float) -> Tuple[float, float]:
    """Eigenvalues of the shape operator I^{-1} II, returned as (k1, k2)."""
    e, f, g = surface.first_fundamental_form(float(u), float(v))
    l, m, n = surface.second_fundamental_form(float(u), float(v))
    first = np.array([[float(e), float(f)], [float(f), float(g)]], dtype=float)
    second = np.array([[float(l), float(m)], [float(m), float(n)]], dtype=float)
    shape = np.linalg.pinv(first, rcond=1e-12) @ second
    eigenvalues = np.linalg.eigvals(shape)
    values = np.sort(np.real(eigenvalues))
    return float(values[0]), float(values[1])


def loop_polygon(surface, center: Sequence[float], radius: float, count: int = 8) -> list:
    """Return a closed parameter polygon around ``center`` (diagnostic helper)."""
    count = max(3, int(count))
    center_u, center_v = float(center[0]), float(center[1])
    points = []
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        points.append(_clamp_parameter(
            surface,
            center_u + float(radius) * math.cos(angle),
            center_v + float(radius) * math.sin(angle),
        ))
    return points


__all__ = [
    "christoffel_symbols",
    "loop_polygon",
    "metric_inner",
    "metric_norm",
    "normalize_tangent",
    "parallel_transport_polyline",
    "principal_curvatures",
]
