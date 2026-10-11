"""Smooth height-function geometry for The Curved World.

The world is a *graph surface* embedded in ordinary three-dimensional
Euclidean space::

    S = { (x, y, f(x, y)) : (x, y) in D }

where ``D`` is a bounded rectangle (see :class:`~src.the_curved_world.config.Domain`)
and ``f`` is C-infinity. All derivatives are computed analytically.
"""

from __future__ import annotations

from typing import Tuple

import numpy as np

from src.the_curved_world.config import SurfaceConfig


def ambient_distance(p, q) -> float:
    """Ambient Euclidean distance ``||p - q||_2`` between two 3D points.

    This is *not* the geodesic distance along the surface. For points on a
    curved surface the straight-line (ambient) distance is always less than or
    equal to the geodesic distance.
    """
    a = np.asarray(p, dtype=float).reshape(3)
    b = np.asarray(q, dtype=float).reshape(3)
    return float(np.linalg.norm(a - b))


class SmoothSurface:
    """A smooth graph surface sampleable over its rectangular parameter domain.

    The height function is the analytic sum of a smooth wave and any number of
    Gaussian hills::

        f(x, y) = A * sin(kx * x) * cos(ky * y)
                  + sum_i h_i * exp(-((x - cx_i)^2 + (y - cy_i)^2) / s_i^2)

    All methods accept scalars or NumPy arrays and broadcast accordingly.
    """

    def __init__(self, config: SurfaceConfig) -> None:
        if not isinstance(config, SurfaceConfig):
            raise TypeError("SmoothSurface requires a SurfaceConfig")
        self._config = config

    name: str = "planar landscape (bounded height field)"

    @property
    def config(self) -> SurfaceConfig:
        return self._config

    @property
    def domain(self):
        return self._config.domain

    @property
    def cache_key(self):
        return self._config

    @property
    def periodic(self) -> bool:
        return False

    def height(self, x, y):
        """Evaluate ``f(x, y)``."""
        xa = np.asarray(x, dtype=float)
        ya = np.asarray(y, dtype=float)
        z = np.zeros(np.broadcast(xa, ya).shape, dtype=float)
        for wave in self._config.wave_terms():
            z = z + wave.amplitude * np.sin(wave.kx * xa) * np.cos(wave.ky * ya)
        for hill in self._config.hills:
            d2 = (xa - hill.center_x) ** 2 + (ya - hill.center_y) ** 2
            z = z + hill.amplitude * np.exp(-d2 / (hill.scale ** 2))
        return float(z) if np.ndim(z) == 0 else z

    def position(self, x, y):
        """Embedded 3D point(s) ``(x, y, f(x, y))`` as an array with trailing axis of size 3."""
        xa = np.asarray(x, dtype=float)
        ya = np.asarray(y, dtype=float)
        z = np.asarray(self.height(xa, ya), dtype=float)
        return np.stack([np.broadcast_to(xa, z.shape), np.broadcast_to(ya, z.shape), z], axis=-1)

    def gradient(self, x, y) -> Tuple[float, float]:
        """Analytic partial derivatives ``(df/dx, df/dy)``."""
        xa = np.asarray(x, dtype=float)
        ya = np.asarray(y, dtype=float)
        dzdx = np.zeros(np.broadcast(xa, ya).shape, dtype=float)
        dzdy = np.zeros(np.broadcast(xa, ya).shape, dtype=float)
        for wave in self._config.wave_terms():
            dzdx = dzdx + wave.amplitude * wave.kx * np.cos(wave.kx * xa) * np.cos(wave.ky * ya)
            dzdy = dzdy - wave.amplitude * wave.ky * np.sin(wave.kx * xa) * np.sin(wave.ky * ya)
        for hill in self._config.hills:
            d2 = (xa - hill.center_x) ** 2 + (ya - hill.center_y) ** 2
            e = np.exp(-d2 / (hill.scale ** 2))
            factor = hill.amplitude * e * (-2.0 / (hill.scale ** 2))
            dzdx = dzdx + factor * (xa - hill.center_x)
            dzdy = dzdy + factor * (ya - hill.center_y)
        if np.ndim(dzdx) == 0:
            return float(dzdx), float(dzdy)
        return dzdx, dzdy

    def normal(self, x, y):
        """Outward unit surface normal ``normalize((-df/dx, -df/dy, 1))``."""
        dzdx, dzdy = self.gradient(x, y)
        dzdx = np.asarray(dzdx, dtype=float)
        dzdy = np.asarray(dzdy, dtype=float)
        n = np.stack([-dzdx, -dzdy, np.ones_like(dzdx)], axis=-1)
        length = np.linalg.norm(n, axis=-1, keepdims=True)
        return n / length

    def second_derivatives(self, x, y) -> Tuple[float, float, float]:
        """Analytic second partials ``(d2f/dx2, d2f/dy2, d2f/dxdy)``."""
        xa = np.asarray(x, dtype=float)
        ya = np.asarray(y, dtype=float)
        shape = np.broadcast(xa, ya).shape
        fxx = np.zeros(shape, dtype=float)
        fyy = np.zeros(shape, dtype=float)
        fxy = np.zeros(shape, dtype=float)
        for wave in self._config.wave_terms():
            base = -wave.amplitude * np.sin(wave.kx * xa) * np.cos(wave.ky * ya)
            fxx = fxx + base * wave.kx ** 2
            fyy = fyy + base * wave.ky ** 2
            fxy = fxy - wave.amplitude * wave.kx * wave.ky * np.cos(wave.kx * xa) * np.sin(wave.ky * ya)
        for hill in self._config.hills:
            scale_sq = hill.scale ** 2
            u = (xa - hill.center_x) / hill.scale
            v = (ya - hill.center_y) / hill.scale
            e = hill.amplitude * np.exp(-(u ** 2 + v ** 2))
            fxx = fxx + (2.0 * e / scale_sq) * (2.0 * u ** 2 - 1.0)
            fyy = fyy + (2.0 * e / scale_sq) * (2.0 * v ** 2 - 1.0)
            fxy = fxy + (4.0 * e * u * v / scale_sq)
        if np.ndim(fxx) == 0:
            return float(fxx), float(fyy), float(fxy)
        return fxx, fyy, fxy

    def gaussian_curvature(self, x, y):
        """Analytic Gaussian curvature of the graph surface.

        For a graph ``z = f(x, y)``::

            K = (f_xx * f_yy - f_xy^2) / (1 + f_x^2 + f_y^2)^2

        This is a local geometric property of the surface; it reveals nothing
        about the hidden exit.
        """
        grad_x, grad_y = self.gradient(x, y)
        fxx, fyy, fxy = self.second_derivatives(x, y)
        numerator = np.asarray(fxx) * np.asarray(fyy) - np.asarray(fxy) ** 2
        denominator = (1.0 + np.asarray(grad_x) ** 2 + np.asarray(grad_y) ** 2) ** 2
        curvature = numerator / denominator
        return float(curvature) if np.ndim(curvature) == 0 else curvature
    def tangent_angle(self, vertex, point_a, point_b) -> float:
        """Angle at ``vertex`` between the directions to two other surface points.

        The two edge vectors are projected into the tangent plane at ``vertex``
        and the angle between the projections is returned, in radians.

        Honest scope: this is a *tangent-plane* angle. It approximates the angle
        of a geodesic triangle; it is not an exact geodesic computation.
        """
        base = np.asarray(self.position(*vertex), dtype=float)
        normal = np.asarray(self.normal(*vertex), dtype=float)
        edge_a = np.asarray(self.position(*point_a), dtype=float) - base
        edge_b = np.asarray(self.position(*point_b), dtype=float) - base
        tangent_a = edge_a - float(edge_a @ normal) * normal
        tangent_b = edge_b - float(edge_b @ normal) * normal
        norm_a = float(np.linalg.norm(tangent_a))
        norm_b = float(np.linalg.norm(tangent_b))
        if norm_a < 1e-12 or norm_b < 1e-12:
            raise ValueError("tangent_angle requires three distinct surface points")
        cosine = float(np.clip(tangent_a @ tangent_b / (norm_a * norm_b), -1.0, 1.0))
        return float(np.arccos(cosine))
    def first_fundamental_form(self, x, y) -> Tuple[float, float, float]:
        """First fundamental form ``(E, F, G)`` of the graph surface.

        ``E = 1 + f_x^2``, ``F = f_x f_y``, ``G = 1 + f_y^2``. The area element
        is ``sqrt(E G - F^2) = sqrt(1 + f_x^2 + f_y^2)``.
        """
        grad_x, grad_y = self.gradient(x, y)
        e = 1.0 + np.asarray(grad_x) ** 2
        f = np.asarray(grad_x) * np.asarray(grad_y)
        g = 1.0 + np.asarray(grad_y) ** 2
        if np.ndim(e) == 0:
            return float(e), float(f), float(g)
        return e, f, g

    def area_element(self, x, y):
        """Area element ``sqrt(E G - F^2)``; how much the surface stretches a parameter cell."""
        grad_x, grad_y = self.gradient(x, y)
        value = np.sqrt(1.0 + np.asarray(grad_x) ** 2 + np.asarray(grad_y) ** 2)
        return float(value) if np.ndim(value) == 0 else value
    def contains(self, x, y, *, margin: float = 0.0):
        """Whether ``(x, y)`` is inside the parameter domain (optionally shrunk)."""
        return self._config.domain.contains(x, y, margin=margin)

    def sample_grid(self, nx: int, ny: int):
        """Regular sampling mesh ``(X, Y, Z)`` for plotting and diagnostics."""
        if nx < 2 or ny < 2:
            raise ValueError("sample_grid requires nx >= 2 and ny >= 2")
        dom = self._config.domain
        xs = np.linspace(dom.x_min, dom.x_max, nx)
        ys = np.linspace(dom.y_min, dom.y_max, ny)
        grid_x, grid_y = np.meshgrid(xs, ys)
        grid_z = np.asarray(self.height(grid_x, grid_y), dtype=float)
        return grid_x, grid_y, grid_z