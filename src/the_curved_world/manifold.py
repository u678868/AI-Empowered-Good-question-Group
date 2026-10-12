"""Closed two-dimensional manifolds embedded in R^3 (Task 8).

Three adjustable closed surface models, all parameterised on the periodic
domain ``(u, v) in [-pi, pi) x [-pi, pi)``:

* :class:`DeformedTorus`         -- genus 1 (the default world)
* :class:`DeformedEllipsoid`     -- genus 0 (a doubly covered deformed ellipsoid)
* :class:`GenusTwoApproximation` -- a two-lobed torus reading as a two-hole form

Every first and second partial derivative is analytic; the first fundamental
form (E, F, G), the second fundamental form (L, M, N) and the Gaussian curvature
``K = (L N - M^2) / (E G - F^2)`` are derived in the base class. No finite
differences are used at runtime.

Honest topological note
-----------------------
A *regular* parameterisation over ``[-pi, pi)^2`` identifies the parameter
square with a torus, so its image is necessarily genus 1. Consequences, stated
rather than hidden:

* :class:`DeformedTorus` and :class:`GenusTwoApproximation` are regular
  everywhere (``E G - F^2 > 0``).
* :class:`DeformedEllipsoid` is genus 0, so it *must* have degenerate parameter
  points -- its two poles. The determinant is positive everywhere except those
  two points and the curvature formula floors the denominator so nothing divides
  by zero.
* A true genus-2 surface needs a genus-2 parameter domain; model C is therefore
  a two-hole *approximation*, exactly as its name says.
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Tuple

import numpy as np

from src.the_curved_world.config import ConfigError, Domain

TWO_PI = 2.0 * math.pi
PARAM_MIN = -math.pi
PARAM_MAX = math.pi
DEGENERATE_EPS = 1e-12


def wrap_parameter(value):
    """Normalise parameters to ``[-pi, pi)`` (periodic wrap-around, no boundary)."""
    array = np.asarray(value, dtype=float)
    wrapped = (array + math.pi) % TWO_PI - math.pi
    return float(wrapped) if np.ndim(wrapped) == 0 else wrapped


def parameter_domain() -> Domain:
    """The shared periodic parameter domain ``[-pi, pi) x [-pi, pi)``."""
    return Domain(PARAM_MIN, PARAM_MAX, PARAM_MIN, PARAM_MAX)


def _scalarize(value):
    array = np.asarray(value)
    return float(array) if array.ndim == 0 else array


def _periodic_grid(nu: int, nv: int):
    us = np.linspace(PARAM_MIN, PARAM_MAX, max(2, int(nu)), endpoint=False)
    vs = np.linspace(PARAM_MIN, PARAM_MAX, max(2, int(nv)), endpoint=False)
    return np.meshgrid(us, vs)


@dataclass(frozen=True)
class RadialHarmonic:
    """One smooth radius perturbation term.

    ``axis='u'`` contributes ``amplitude * cos(order * u + phase)``; ``axis='v'``
    contributes ``amplitude * sin(order * v + phase)``. Both are 2pi-periodic and
    C-infinity, so the perturbed surface stays smooth.
    """

    amplitude: float
    order: int = 1
    phase: float = 0.0
    axis: str = "u"

    def __post_init__(self) -> None:
        if self.axis not in ("u", "v"):
            raise ConfigError("RadialHarmonic.axis must be 'u' or 'v'")
        if int(self.order) < 0:
            raise ConfigError("RadialHarmonic.order must be >= 0")
        if not np.isfinite(self.amplitude) or not np.isfinite(self.phase):
            raise ConfigError("RadialHarmonic amplitude/phase must be finite")


def _harmonic_value_and_partials(u, v, harmonics, base: float = 0.0):
    """Value and analytic partials of a sum of radial harmonics."""
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    shape = np.broadcast(u, v).shape
    value = np.full(shape, float(base))
    d_u = np.zeros(shape)
    d_v = np.zeros(shape)
    d_uu = np.zeros(shape)
    d_uv = np.zeros(shape)
    d_vv = np.zeros(shape)
    for term in harmonics:
        order = int(term.order)
        if term.axis == "u":
            angle = order * u + term.phase
            value = value + term.amplitude * np.cos(angle)
            d_u = d_u - term.amplitude * order * np.sin(angle)
            d_uu = d_uu - term.amplitude * order * order * np.cos(angle)
        else:
            angle = order * v + term.phase
            value = value + term.amplitude * np.sin(angle)
            d_v = d_v + term.amplitude * order * np.cos(angle)
            d_vv = d_vv - term.amplitude * order * order * np.sin(angle)
    return value, d_u, d_v, d_uu, d_uv, d_vv


def _torus_family(u, v, ring, rho, ring_u, ring_v, ring_uu, ring_uv, ring_vv,
                  rho_u, rho_v, rho_uu, rho_uv, rho_vv):
    """Position and analytic partials for the torus-like chart.

    ``r = (ring cos v, ring sin v, rho sin u)`` where ``ring`` and ``rho`` may
    both depend on ``(u, v)``.
    """
    u = np.asarray(u, dtype=float)
    v = np.asarray(v, dtype=float)
    cos_u, sin_u, cos_v, sin_v = np.cos(u), np.sin(u), np.cos(v), np.sin(v)
    position = np.stack([ring * cos_v, ring * sin_v, rho * sin_u], axis=-1)
    r_u = np.stack([ring_u * cos_v, ring_u * sin_v, rho_u * sin_u + rho * cos_u], axis=-1)
    r_v = np.stack([ring_v * cos_v - ring * sin_v, ring_v * sin_v + ring * cos_v, rho_v * sin_u], axis=-1)
    r_uu = np.stack(
        [ring_uu * cos_v, ring_uu * sin_v, rho_uu * sin_u + 2.0 * rho_u * cos_u - rho * sin_u],
        axis=-1,
    )
    r_uv = np.stack(
        [ring_uv * cos_v - ring_u * sin_v, ring_uv * sin_v + ring_u * cos_v,
         rho_uv * sin_u + rho_v * cos_u],
        axis=-1,
    )
    r_vv = np.stack(
        [ring_vv * cos_v - 2.0 * ring_v * sin_v - ring * cos_v,
         ring_vv * sin_v + 2.0 * ring_v * cos_v - ring * sin_v,
         rho_vv * sin_u],
        axis=-1,
    )
    return position, r_u, r_v, r_uu, r_uv, r_vv


class ClosedManifold(ABC):
    """A closed regular surface parameterised on ``[-pi, pi) x [-pi, pi)``."""

    name = "closed manifold"
    genus = None
    periodic = True
    # Orientation of the raw cross product so the reported normal points OUTWARD.
    # ``center`` (optional) flips any residual per-point sign, which the doubly
    # covered genus-0 chart needs.
    outward_sign = 1.0
    center = None

    @property
    def domain(self) -> Domain:
        return parameter_domain()

    @property
    def config(self):
        """Self-reference so graph-surface code reading ``surface.config`` still works."""
        return self

    @property
    def cache_key(self):
        return (self.name, self.describe())

    # -- to implement ------------------------------------------------------

    @abstractmethod
    def describe(self) -> Tuple:
        """Hashable description of the surface parameters."""

    @abstractmethod
    def position(self, u, v):
        """Embedded 3D point(s), trailing axis of size 3."""

    @abstractmethod
    def first_partials(self, u, v):
        """Analytic ``(r_u, r_v)``."""

    @abstractmethod
    def second_partials(self, u, v):
        """Analytic ``(r_uu, r_uv, r_vv)``."""

    # -- derived quantities ------------------------------------------------

    def height(self, u, v):
        """Third coordinate of the embedded point (graph-surface analogue)."""
        return _scalarize(self.position(u, v)[..., 2])

    def normal(self, u, v):
        """Unit OUTWARD normal: the up direction of the player."""
        r_u, r_v = self.first_partials(u, v)
        cross = np.cross(r_u, r_v) * self.outward_sign
        length = np.linalg.norm(cross, axis=-1, keepdims=True)
        if np.asarray(length).size == 1 and float(np.max(length)) < 1e-9:
            # measure-zero degenerate chart point (the genus-0 poles): nudge and retry
            return self.normal(u, v + 1e-4)
        unit = cross / np.where(length > 0.0, length, 1.0)
        if self.center is not None:
            point = np.asarray(self.position(u, v), dtype=float)
            offset = point - np.asarray(self.center, dtype=float)
            flip = np.sum(unit * offset, axis=-1, keepdims=True) < 0.0
            unit = np.where(flip, -unit, unit)
        return unit

    def first_fundamental_form(self, u, v):
        r_u, r_v = self.first_partials(u, v)
        return (
            _scalarize(np.sum(r_u * r_u, axis=-1)),
            _scalarize(np.sum(r_u * r_v, axis=-1)),
            _scalarize(np.sum(r_v * r_v, axis=-1)),
        )

    def second_fundamental_form(self, u, v):
        r_uu, r_uv, r_vv = self.second_partials(u, v)
        normal = self.normal(u, v)
        return (
            _scalarize(np.sum(r_uu * normal, axis=-1)),
            _scalarize(np.sum(r_uv * normal, axis=-1)),
            _scalarize(np.sum(r_vv * normal, axis=-1)),
        )

    def regularity(self, u, v):
        """Metric determinant ``E G - F^2``; zero exactly where the chart degenerates."""
        e, f, g = self.first_fundamental_form(u, v)
        return _scalarize(np.asarray(e) * np.asarray(g) - np.asarray(f) ** 2)

    def area_element(self, u, v):
        """``sqrt(E G - F^2)``: how much a parameter cell is stretched."""
        return _scalarize(np.sqrt(np.maximum(np.asarray(self.regularity(u, v)), 0.0)))

    def gaussian_curvature(self, u, v):
        """``K = (L N - M^2) / (E G - F^2)`` (denominator floored at the poles)."""
        e, f, g = self.first_fundamental_form(u, v)
        l, m, n = self.second_fundamental_form(u, v)
        determinant = np.asarray(e) * np.asarray(g) - np.asarray(f) ** 2
        numerator = np.asarray(l) * np.asarray(n) - np.asarray(m) ** 2
        return _scalarize(numerator / np.maximum(determinant, DEGENERATE_EPS))

    def mean_curvature(self, u, v):
        e, f, g = self.first_fundamental_form(u, v)
        l, m, n = self.second_fundamental_form(u, v)
        determinant = np.asarray(e) * np.asarray(g) - np.asarray(f) ** 2
        numerator = (
            np.asarray(e) * np.asarray(n)
            - 2.0 * np.asarray(f) * np.asarray(m)
            + np.asarray(g) * np.asarray(l)
        )
        return _scalarize(numerator / (2.0 * np.maximum(determinant, DEGENERATE_EPS)))

    def contains(self, u, v, *, margin: float = 0.0):
        """Always true: the parameter domain is periodic and boundaryless."""
        shape = np.broadcast(np.asarray(u, dtype=float), np.asarray(v, dtype=float)).shape
        return True if shape == () else np.ones(shape, dtype=bool)

    def wrap(self, u, v):
        return wrap_parameter(u), wrap_parameter(v)

    def sample_grid(self, nu: int, nv: int):
        """Closed mesh as 3D coordinate grids ``(X, Y, Z)``."""
        if nu < 2 or nv < 2:
            raise ValueError("sample_grid requires nu >= 2 and nv >= 2")
        us = np.linspace(PARAM_MIN, PARAM_MAX, nu)
        vs = np.linspace(PARAM_MIN, PARAM_MAX, nv)
        grid_u, grid_v = np.meshgrid(us, vs)
        points = np.asarray(self.position(grid_u, grid_v), dtype=float)
        return points[..., 0], points[..., 1], points[..., 2]

    def tangent_angle(self, vertex, point_a, point_b) -> float:
        """Tangent-plane angle at ``vertex`` between directions to two points."""
        base = np.asarray(self.position(*vertex), dtype=float)
        normal = np.asarray(self.normal(*vertex), dtype=float)
        edge_a = np.asarray(self.position(*point_a), dtype=float) - base
        edge_b = np.asarray(self.position(*point_b), dtype=float) - base
        tangent_a = edge_a - float(edge_a @ normal) * normal
        tangent_b = edge_b - float(edge_b @ normal) * normal
        length_a = float(np.linalg.norm(tangent_a))
        length_b = float(np.linalg.norm(tangent_b))
        if length_a < 1e-12 or length_b < 1e-12:
            raise ValueError("tangent_angle requires three distinct surface points")
        cosine = float(np.clip(tangent_a @ tangent_b / (length_a * length_b), -1.0, 1.0))
        return float(np.arccos(cosine))

    def surface_area(self, nu: int = 240, nv: int = 240) -> float:
        """Numerical total area ``iint sqrt(E G - F^2) du dv``."""
        grid_u, grid_v = _periodic_grid(nu, nv)
        element = np.asarray(self.area_element(grid_u, grid_v), dtype=float)
        return float(element.mean()) * TWO_PI * TWO_PI

    def curvature_integral(self, nu: int = 240, nv: int = 240) -> float:
        """Numerical ``iint K dA``; Gauss-Bonnet predicts ``2 pi * chi``."""
        grid_u, grid_v = _periodic_grid(nu, nv)
        curvature = np.asarray(self.gaussian_curvature(grid_u, grid_v), dtype=float)
        element = np.asarray(self.area_element(grid_u, grid_v), dtype=float)
        return float((curvature * element).mean()) * TWO_PI * TWO_PI

    def regularity_report(self, nu: int = 120, nv: int = 120):
        grid_u, grid_v = _periodic_grid(nu, nv)
        determinant = np.asarray(self.regularity(grid_u, grid_v), dtype=float)
        return {
            "min": float(determinant.min()),
            "max": float(determinant.max()),
            "degenerate_fraction": float((determinant <= DEGENERATE_EPS).mean()),
        }


@dataclass(frozen=True)
class DeformedTorus(ClosedManifold):
    """Genus-1 torus with a smooth radius perturbation.

    ``r(u, v) = ((R + rho cos u) cos v, (R + rho cos u) sin v, rho sin u)`` with
    ``rho(u, v) = r0 + sum A_k cos(k u + phi_k) + sum B_l sin(l v + psi_l)``.
    ``R > max|rho| > 0`` guarantees ``E G - F^2 > 0`` everywhere.
    """

    ring_radius: float = 20.0
    tube_radius: float = 7.0
    harmonics: Tuple[RadialHarmonic, ...] = ()
    name: str = "deformed torus (genus 1)"
    outward_sign = -1.0
    genus: int = 1

    def __post_init__(self) -> None:
        if not (self.ring_radius > 0.0 and self.tube_radius > 0.0):
            raise ConfigError("DeformedTorus radii must be > 0")
        grid_u, grid_v = _periodic_grid(72, 72)
        rho = np.asarray(self._rho(grid_u, grid_v)[0], dtype=float)
        if not (self.ring_radius > float(np.max(np.abs(rho))) > 0.0):
            raise ConfigError("DeformedTorus requires ring_radius > max|rho| > 0")
        if float(np.asarray(self.regularity(grid_u, grid_v), dtype=float).min()) <= 0.0:
            raise ConfigError("DeformedTorus parameterisation is not regular")

    def describe(self) -> Tuple:
        return (
            "torus",
            round(self.ring_radius, 9),
            round(self.tube_radius, 9),
            tuple((t.axis, int(t.order), round(t.amplitude, 9), round(t.phase, 9)) for t in self.harmonics),
        )

    def _rho(self, u, v):
        return _harmonic_value_and_partials(u, v, self.harmonics, self.tube_radius)

    def _ring_terms(self, u, v):
        rho, rho_u, rho_v, rho_uu, rho_uv, rho_vv = self._rho(u, v)
        cos_u, sin_u = np.cos(u), np.sin(u)
        ring = self.ring_radius + rho * cos_u
        ring_u = rho_u * cos_u - rho * sin_u
        ring_v = rho_v * cos_u
        ring_uu = rho_uu * cos_u - 2.0 * rho_u * sin_u - rho * cos_u
        ring_uv = rho_uv * cos_u - rho_v * sin_u
        ring_vv = rho_vv * cos_u
        return rho, ring, ring_u, ring_v, ring_uu, ring_uv, ring_vv, rho_u, rho_v, rho_uu, rho_uv, rho_vv

    def position(self, u, v):
        rho, ring, *rest = self._ring_terms(u, v)
        return _torus_family(u, v, ring, rho, *rest)[0]

    def first_partials(self, u, v):
        rho, ring, *rest = self._ring_terms(u, v)
        return _torus_family(u, v, ring, rho, *rest)[1:3]

    def second_partials(self, u, v):
        rho, ring, *rest = self._ring_terms(u, v)
        return _torus_family(u, v, ring, rho, *rest)[3:6]


@dataclass(frozen=True)
class GenusTwoApproximation(ClosedManifold):
    """Two-hole silhouette approximation (genus-1 image, honestly labelled).

    The ring radius is modulated as ``R(u) = R0 + R1 cos(2u)`` and the tube
    radius carries its own harmonics, so the surface reads as a two-lobed
    "pretzel". A genuine genus-2 closed surface cannot be regularly
    parameterised by ``[-pi, pi)^2`` (that would force genus 1), so this model is
    an approximation rather than a true genus-2 surface.
    """

    ring_radius: float = 18.0
    ring_modulation: float = 6.0
    tube_radius: float = 5.0
    harmonics: Tuple[RadialHarmonic, ...] = ()
    name: str = "two-hole torus approximation (genus-2 look)"
    outward_sign = -1.0
    genus: int = 2

    def __post_init__(self) -> None:
        if not (self.ring_radius > 0.0 and self.tube_radius > 0.0):
            raise ConfigError("GenusTwoApproximation radii must be > 0")
        if abs(self.ring_modulation) >= self.ring_radius:
            raise ConfigError("ring_modulation must satisfy |R1| < R0")
        grid_u, grid_v = _periodic_grid(72, 72)
        rho, _, _, _, _, _ = self._rho(grid_u, grid_v)
        ring = self._ring(grid_u, grid_v)[0]
        if float(np.min(ring)) <= 0.0:
            raise ConfigError("GenusTwoApproximation ring radius became non-positive")
        if float(np.asarray(self.regularity(grid_u, grid_v), dtype=float).min()) <= 0.0:
            raise ConfigError("GenusTwoApproximation parameterisation is not regular")

    def describe(self) -> Tuple:
        return (
            "genus-two-approx",
            round(self.ring_radius, 9),
            round(self.ring_modulation, 9),
            round(self.tube_radius, 9),
            tuple((t.axis, int(t.order), round(t.amplitude, 9), round(t.phase, 9)) for t in self.harmonics),
        )

    def _rho(self, u, v):
        return _harmonic_value_and_partials(u, v, self.harmonics, self.tube_radius)

    def _ring(self, u, v):
        base = self.ring_radius + self.ring_modulation * np.cos(2.0 * u)
        base_u = -2.0 * self.ring_modulation * np.sin(2.0 * u)
        base_uu = -4.0 * self.ring_modulation * np.cos(2.0 * u)
        return base, base_u, base_uu

    def _ring_terms(self, u, v):
        rho, rho_u, rho_v, rho_uu, rho_uv, rho_vv = self._rho(u, v)
        base, base_u, base_uu = self._ring(u, v)
        cos_u, sin_u = np.cos(u), np.sin(u)
        ring = base + rho * cos_u
        ring_u = base_u + rho_u * cos_u - rho * sin_u
        ring_v = rho_v * cos_u
        ring_uu = base_uu + rho_uu * cos_u - 2.0 * rho_u * sin_u - rho * cos_u
        ring_uv = rho_uv * cos_u - rho_v * sin_u
        ring_vv = rho_vv * cos_u
        return rho, ring, ring_u, ring_v, ring_uu, ring_uv, ring_vv, rho_u, rho_v, rho_uu, rho_uv, rho_vv

    def position(self, u, v):
        rho, ring, *rest = self._ring_terms(u, v)
        return _torus_family(u, v, ring, rho, *rest)[0]

    def first_partials(self, u, v):
        rho, ring, *rest = self._ring_terms(u, v)
        return _torus_family(u, v, ring, rho, *rest)[1:3]

    def second_partials(self, u, v):
        rho, ring, *rest = self._ring_terms(u, v)
        return _torus_family(u, v, ring, rho, *rest)[3:6]


@dataclass(frozen=True)
class DeformedEllipsoid(ClosedManifold):
    """Genus-0 deformed ellipsoid, doubly covered by the torus chart.

    ``r(u, v) = (a m sin v cos u, b m sin v sin u, c m cos v)`` with a smooth
    radial modulation ``m(u, v)``. ``v`` runs all the way around, so the sphere
    is traversed twice; the two poles (``v = 0`` and ``v = pi``) are the
    unavoidable degenerate points of any genus-0 torus chart and are handled
    with a metric floor rather than hidden.
    """

    semi_x: float = 18.0
    semi_y: float = 18.0
    semi_z: float = 13.0
    harmonics: Tuple[RadialHarmonic, ...] = ()
    name: str = "deformed ellipsoid (genus 0)"
    center = (0.0, 0.0, 0.0)
    genus: int = 0

    def __post_init__(self) -> None:
        if min(self.semi_x, self.semi_y, self.semi_z) <= 0.0:
            raise ConfigError("DeformedEllipsoid semi-axes must be > 0")
        for term in self.harmonics:
            if term.axis != "v":
                raise ConfigError(
                    "DeformedEllipsoid supports radial (axis='v') modulation only: a "
                    "u-dependent modulation would destroy the two degenerate poles that a "
                    "genus-0 chart necessarily has"
                )
        grid_u, grid_v = _periodic_grid(96, 96)
        modulation = np.asarray(self._modulation(grid_u, grid_v)[0], dtype=float)
        if float(np.min(modulation)) <= 0.0:
            raise ConfigError("DeformedEllipsoid modulation must stay positive")

    def describe(self) -> Tuple:
        return (
            "ellipsoid",
            round(self.semi_x, 9),
            round(self.semi_y, 9),
            round(self.semi_z, 9),
            tuple((t.axis, int(t.order), round(t.amplitude, 9), round(t.phase, 9)) for t in self.harmonics),
        )

    def _modulation(self, u, v):
        return _harmonic_value_and_partials(u, v, self.harmonics, 1.0)

    def _chart(self, u, v):
        m, m_u, m_v, m_uu, m_uv, m_vv = self._modulation(u, v)
        cos_v, sin_v = np.cos(v), np.sin(v)
        p = m * sin_v
        q = m * cos_v
        p_u = m_u * sin_v
        p_v = m_v * sin_v + m * cos_v
        p_uu = m_uu * sin_v
        p_uv = m_uv * sin_v + m_u * cos_v
        p_vv = m_vv * sin_v + 2.0 * m_v * cos_v - m * sin_v
        q_u = m_u * cos_v
        q_v = m_v * cos_v - m * sin_v
        q_uu = m_uu * cos_v
        q_uv = m_uv * cos_v - m_u * sin_v
        q_vv = m_vv * cos_v - 2.0 * m_v * sin_v - m * cos_v
        return p, q, p_u, p_v, p_uu, p_uv, p_vv, q_u, q_v, q_uu, q_uv, q_vv

    def position(self, u, v):
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        p, q = self._chart(u, v)[:2]
        cos_u, sin_u = np.cos(u), np.sin(u)
        return np.stack(
            [self.semi_x * p * cos_u, self.semi_y * p * sin_u, self.semi_z * q], axis=-1
        )

    def first_partials(self, u, v):
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        p, q, p_u, p_v, _p_uu, _p_uv, _p_vv, q_u, q_v, _q_uu, _q_uv, _q_vv = self._chart(u, v)
        cos_u, sin_u = np.cos(u), np.sin(u)
        r_u = np.stack(
            [self.semi_x * (p_u * cos_u - p * sin_u),
             self.semi_y * (p_u * sin_u + p * cos_u),
             self.semi_z * q_u],
            axis=-1,
        )
        r_v = np.stack(
            [self.semi_x * p_v * cos_u, self.semi_y * p_v * sin_u, self.semi_z * q_v],
            axis=-1,
        )
        return r_u, r_v

    def second_partials(self, u, v):
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        p, q, p_u, p_v, p_uu, p_uv, p_vv, q_u, q_v, q_uu, q_uv, q_vv = self._chart(u, v)
        cos_u, sin_u = np.cos(u), np.sin(u)
        r_uu = np.stack(
            [self.semi_x * (p_uu * cos_u - 2.0 * p_u * sin_u - p * cos_u),
             self.semi_y * (p_uu * sin_u + 2.0 * p_u * cos_u - p * sin_u),
             self.semi_z * q_uu],
            axis=-1,
        )
        r_uv = np.stack(
            [self.semi_x * (p_uv * cos_u - p_v * sin_u),
             self.semi_y * (p_uv * sin_u + p_v * cos_u),
             self.semi_z * q_uv],
            axis=-1,
        )
        r_vv = np.stack(
            [self.semi_x * p_vv * cos_u, self.semi_y * p_vv * sin_u, self.semi_z * q_vv],
            axis=-1,
        )
        return r_uu, r_uv, r_vv


def default_harmonics() -> Tuple[RadialHarmonic, ...]:
    """The default smooth radius perturbation used by the torus world."""
    return (
        # gently smoothed high-order perturbation: shallower, more continuous slopes
        # macro scale: low frequency, small amplitude -> very gentle rolling ground
        RadialHarmonic(amplitude=0.45, order=1, phase=0.35, axis="u"),
        RadialHarmonic(amplitude=0.35, order=2, phase=1.10, axis="v"),
        RadialHarmonic(amplitude=0.20, order=2, phase=2.20, axis="u"),
    )


def default_ellipsoid_harmonics() -> Tuple[RadialHarmonic, ...]:
    """Small positive-preserving modulation for the genus-0 model."""
    return (
        RadialHarmonic(amplitude=0.16, order=2, phase=0.4, axis="v"),
        RadialHarmonic(amplitude=0.10, order=3, phase=1.3, axis="v"),
        RadialHarmonic(amplitude=0.06, order=5, phase=2.1, axis="v"),
    )


def default_genus_two_harmonics() -> Tuple[RadialHarmonic, ...]:
    """Lobed modulation that gives model C its two-hole silhouette."""
    return (
        RadialHarmonic(amplitude=1.6, order=2, phase=0.0, axis="u"),
        RadialHarmonic(amplitude=0.8, order=4, phase=0.9, axis="v"),
    )

def default_manifold() -> ClosedManifold:
    """The default world surface: a deformed torus (genus 1)."""
    return DeformedTorus(ring_radius=20.0, tube_radius=7.0, harmonics=default_harmonics())