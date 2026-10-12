"""Closed two-dimensional manifolds embedded in R^3 (Task 8/Task 17).

Four adjustable closed surface models, all parameterised on the periodic
domain ``(u, v) in [-pi, pi) x [-pi, pi)``:

* :class:`DeformedTorus`         -- genus 1 (the default world)
* :class:`DeformedEllipsoid`     -- genus 0 (a doubly covered deformed ellipsoid)
* :class:`GenusTwoApproximation` -- a two-lobed torus reading as a two-hole form
* :class:`KleinBottle`           -- non-orientable, chi = 0, self-intersecting in R^3

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
* :class:`KleinBottle` is non-orientable, so it cannot be embedded in R^3 at
  all: our chart is an *immersion* that necessarily intersects itself, and the
  surface admits no globally consistent "outside" normal. Both facts are
  documented on the class and are observable in-game rather than papered over.

Chart periods
-------------
Several models identify parameter points that are not simply ``2 pi`` apart in
each coordinate. Rather than hard-coding that in the gameplay, obstacle and
front-end layers, every manifold publishes :meth:`ClosedManifold.chart_periods`
and :meth:`ClosedManifold.chart_relative`:

* torus / ellipsoid / two-hole approximation: periods ``(2 pi, 2 pi)`` -- the
  plain periodic square;
* Klein bottle: periods ``(4 pi, 2 pi)``. The chart is a *double cover* of the
  surface (the translation subgroup of its deck group has index 2), so a pure
  ``2 pi`` shift in ``u`` is **not** the identity -- it flips ``v`` instead.
  Translating by the published periods is always invisible, which is what the
  movement, collision and rendering code needs.
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


def wrap_period(value, period):
    """Normalise a coordinate into ``[-period/2, period/2)``.

    ``wrap_period(x, 2 pi)`` is exactly :func:`wrap_parameter`; the wider
    ``4 pi`` period is what the Klein-bottle chart needs (see the module
    docstring), because a ``2 pi`` shift in ``u`` there flips ``v``.
    """
    array = np.asarray(value, dtype=float)
    half = 0.5 * float(period)
    wrapped = (array + half) % float(period) - half
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
    #: Euler characteristic (Gauss-Bonnet: ``iint K dA = 2 pi chi``).
    euler_characteristic = None
    #: False for non-orientable models (the Klein bottle): no global "outside".
    orientable = True
    #: True when the chart's deck group contains a twist, i.e. a *translation*
    #: of one coordinate that mirrors the other instead of being the identity.
    twisted = False
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

    # -- chart identification ---------------------------------------------

    def chart_periods(self) -> Tuple[float, float]:
        """Translation periods ``(p_u, p_v)`` of the chart.

        Shifting a coordinate by its period is *exactly* the identity on the
        surface, for every point of the chart. For the plain periodic models
        that is ``(2 pi, 2 pi)``; the Klein-bottle chart needs ``(4 pi, 2 pi)``
        because its ``2 pi`` shift in ``u`` mirrors ``v`` instead.
        """
        return (TWO_PI, TWO_PI)

    def wrap(self, u, v):
        """Bring a parameter pair into the canonical chart window.

        Scalar in, scalar out; arrays are supported as well (the old
        ``wrap_parameter`` was vectorised and callers may still rely on that).
        """
        period_u, period_v = self.chart_periods()
        return wrap_period(u, period_u), wrap_period(v, period_v)

    def chart_copy_transforms(self):
        """Affine chart copies of one surface point, modulo :meth:`chart_periods`.

        Each entry is ``(du, dv, flip_v)``: the copy is
        ``(u + du, (-v if flip_v else v) + dv)``. The default chart is
        single-sheeted (one copy). Multi-sheeted charts list every sheet; for
        example the figure-8 Klein bottle chart is a double cover whose second
        sheet is the flipped twin ``(u + 2 pi, -v)``.

        Every generator here must be an exact symmetry of the chart, and the
        translations it spans must *include* :meth:`chart_periods`; the
        construction self-check in each model verifies the identities
        numerically rather than trusting the algebra.
        """
        return ((0.0, 0.0, False),)

    def chart_copies(self, u, v):
        """The chart points that map to the same surface point as ``(u, v)``."""
        u = float(u)
        v = float(v)
        return tuple(
            (u + float(du), (-v if flip else v) + float(dv))
            for du, dv, flip in self.chart_copy_transforms()
        )

    def chart_relative(self, u_ref, v_ref, u, v):
        """Chart coordinates of the copy of ``(u, v)`` closest to the reference.

        This is the surface-point-preserving replacement for a bare
        ``wrap_difference``: it picks the sheet *and* the period translate that
        minimises the chart displacement, so "nearby" stays nearby across the
        seam -- including across a Klein bottle's flip or a projective-plane
        antipode.
        """
        period_u, period_v = self.chart_periods()
        best = (u_ref, v_ref)
        best_cost = None
        for copy_u, copy_v in self.chart_copies(u, v):
            delta_u = float(wrap_period(copy_u - float(u_ref), period_u))
            delta_v = float(wrap_period(copy_v - float(v_ref), period_v))
            cost = delta_u * delta_u + delta_v * delta_v
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = (float(u_ref) + delta_u, float(v_ref) + delta_v)
        return best

    def orbit_positions(self, u, v):
        """Distinct *3D* realizations of one surface point (its chart copies).

        Copies that share a 3D position -- as on a Klein bottle, whose two chart
        sheets land on the very same point -- collapse to a single entry. On a
        quotient world such as the projective plane the copies land on genuinely
        different points (antipodes), and both are returned.
        """
        positions = []
        for copy_u, copy_v in self.chart_copies(u, v):
            point = np.asarray(self.position(copy_u, copy_v), dtype=float)
            if not any(float(np.max(np.abs(point - other))) < 1e-9 for other in positions):
                positions.append(point)
        return tuple(positions)

    def chart_relative(self, u_ref, v_ref, u, v):
        """Chart coordinates of the copy of ``(u, v)`` closest to the reference.

        This is the surface-point-preserving replacement for a bare
        ``wrap_difference``: it picks the sheet *and* the period translate that
        minimises the chart displacement, so "nearby" stays nearby across the
        seam -- including across the Klein bottle's flip.
        """
        period_u, period_v = self.chart_periods()
        best = (u_ref, v_ref)
        best_cost = None
        for copy_u, copy_v in self.chart_copies(u, v):
            delta_u = float(wrap_period(copy_u - float(u_ref), period_u))
            delta_v = float(wrap_period(copy_v - float(v_ref), period_v))
            cost = delta_u * delta_u + delta_v * delta_v
            if best_cost is None or cost < best_cost:
                best_cost = cost
                best = (float(u_ref) + delta_u, float(v_ref) + delta_v)
        return best

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
    euler_characteristic: int = 0

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
    # the *image* is still a torus (the chart is the periodic square), so chi = 0
    euler_characteristic: int = 0

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
    euler_characteristic: int = 2

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


@dataclass(frozen=True)
class KleinBottle(ClosedManifold):
    """Non-orientable Klein bottle, immersed in R^3 (Task 17).

    Chart (the classical figure-8 immersion, with an explicit tube scale)::

        P(u, v) = R + t (cos(u/2) sin v - sin(u/2) sin 2v)
        Q(u, v) = t (sin(u/2) sin v + cos(u/2) sin 2v)
        r(u, v) = (P cos u, P sin u, Q)

    Everything the base class needs (``r_u``, ``r_v``, ``r_uu``, ``r_uv``,
    ``r_vv``, ``E``, ``F``, ``G``, ``L``, ``M``, ``N``, ``K``) is analytic; the
    hand-derived identifications ``P_u = -Q/2`` and ``Q_uu = -Q/4`` keep the
    algebra short without any finite differences.

    Honest topological facts -- these are the point of the model, not caveats:

    * **It cannot be embedded.** The Klein bottle is non-orientable, so *no*
      embedding into R^3 exists; this chart is an immersion and therefore
      intersects itself. Two different parameter points can share the exact same
      3D position. ``E G - F^2 > 0`` still holds everywhere (it is a genuine
      immersion), so the surface is regular; the self-intersection is a
      measure-zero artefact of living in R^3.
    * **There is no global "outside".** The cross-product normal is continuous
      in the chart, but the chart is not: crossing the flip seam reverses it.
      Any statement of the form "outward normal" is therefore local-only here.
      We still return the analytic normal so that cameras, tangent frames and
      curvature keep working, and we say so instead of pretending.
    * **The chart is a double cover.** ``r(u + 2 pi, v) = r(u, -v)``, i.e. a
      ``2 pi`` shift in ``u`` is *not* the identity -- it mirrors ``v``. The
      published periods are therefore ``(4 pi, 2 pi)`` (see
      :meth:`chart_periods`), and :meth:`chart_copies` exposes both sheets.
    * **Euler characteristic 0.** Like the torus, so Gauss-Bonnet predicts
      ``iint K dA = 0`` -- and it is, numerically, on this immersion too.
    """

    ring_radius: float = 90.0
    tube_radius: float = 31.0
    name: str = "figure-8 Klein bottle (non-orientable)"
    # local-only orientation: the raw cross product points away from the tube
    # axis near the outer ring, which is the closest thing to "outward" here.
    outward_sign = 1.0
    genus = None
    euler_characteristic: int = 0
    orientable: bool = False
    twisted: bool = True

    def __post_init__(self) -> None:
        if not (self.ring_radius > 0.0 and self.tube_radius > 0.0):
            raise ConfigError("KleinBottle radii must be > 0")
        grid_u, grid_v = _periodic_grid(72, 72)
        if float(np.asarray(self.regularity(grid_u, grid_v), dtype=float).min()) <= 0.0:
            raise ConfigError("KleinBottle chart is not an immersion (E G - F^2 <= 0)")
        # Self-check of the topological identity that the whole chart API relies
        # on: a 2*pi shift in u mirrors v, so it is *not* the identity.
        sample_u = np.array([0.3, 1.7, -2.4, 2.9])
        sample_v = np.array([0.0, 0.9, -1.3, 2.5])
        shifted = np.asarray(self.position(sample_u + TWO_PI, sample_v), dtype=float)
        mirrored = np.asarray(self.position(sample_u, -sample_v), dtype=float)
        if not np.allclose(shifted, mirrored, atol=1e-9):
            raise ConfigError("KleinBottle chart failed the r(u + 2 pi, v) = r(u, -v) identity")

    def describe(self) -> Tuple:
        return (
            "klein-bottle-figure-8",
            round(self.ring_radius, 9),
            round(self.tube_radius, 9),
        )

    # -- chart identification ---------------------------------------------

    def chart_periods(self) -> Tuple[float, float]:
        # 4 pi in u: a 2 pi shift mirrors v instead of being the identity.
        return (2.0 * TWO_PI, TWO_PI)

    def chart_copy_transforms(self):
        # The chart is a double cover: its second sheet is the flipped twin.
        return ((0.0, 0.0, False), (TWO_PI, 0.0, True))

    # -- analytic chart ----------------------------------------------------

    def _chart(self, u, v):
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        half = 0.5 * u
        cos_half, sin_half = np.cos(half), np.sin(half)
        cos_v, sin_v = np.cos(v), np.sin(v)
        cos_2v, sin_2v = np.cos(2.0 * v), np.sin(2.0 * v)
        tube = float(self.tube_radius)
        radial = cos_half * sin_v - sin_half * sin_2v
        axial = sin_half * sin_v + cos_half * sin_2v
        p = float(self.ring_radius) + tube * radial
        q = tube * axial
        # hand-derived identities: P_u = -Q/2, Q_uu = -Q/4, Q_uv = P_v/2
        p_u = -0.5 * q
        q_u = 0.5 * tube * radial
        p_v = tube * (cos_half * cos_v - 2.0 * sin_half * cos_2v)
        q_v = tube * (sin_half * cos_v + 2.0 * cos_half * cos_2v)
        p_uu = -0.5 * q_u
        p_uv = -0.5 * q_v
        q_uu = -0.25 * q
        q_uv = 0.5 * p_v
        p_vv = tube * (-cos_half * sin_v + 4.0 * sin_half * sin_2v)
        q_vv = tube * (-sin_half * sin_v - 4.0 * cos_half * sin_2v)
        return p, q, p_u, p_v, p_uu, p_uv, p_vv, q_u, q_v, q_uu, q_uv, q_vv

    def position(self, u, v):
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        p, q = self._chart(u, v)[:2]
        cos_u, sin_u = np.cos(u), np.sin(u)
        return np.stack([p * cos_u, p * sin_u, q], axis=-1)

    def first_partials(self, u, v):
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        p, _q, p_u, p_v, _p_uu, _p_uv, _p_vv, q_u, q_v, _q_uu, _q_uv, _q_vv = self._chart(u, v)
        cos_u, sin_u = np.cos(u), np.sin(u)
        r_u = np.stack([p_u * cos_u - p * sin_u, p_u * sin_u + p * cos_u, q_u], axis=-1)
        r_v = np.stack([p_v * cos_u, p_v * sin_u, q_v], axis=-1)
        return r_u, r_v

    def second_partials(self, u, v):
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        p, _q, p_u, p_v, p_uu, p_uv, p_vv, _q_u, _q_v, q_uu, q_uv, q_vv = self._chart(u, v)
        cos_u, sin_u = np.cos(u), np.sin(u)
        r_uu = np.stack(
            [p_uu * cos_u - 2.0 * p_u * sin_u - p * cos_u,
             p_uu * sin_u + 2.0 * p_u * cos_u - p * sin_u,
             q_uu],
            axis=-1,
        )
        r_uv = np.stack([p_uv * cos_u - p_v * sin_u, p_uv * sin_u + p_v * cos_u, q_uv], axis=-1)
        r_vv = np.stack([p_vv * cos_u, p_vv * sin_u, q_vv], axis=-1)
        return r_uu, r_uv, r_vv

    def sample_grid(self, nu: int, nv: int):
        """Mesh of the fundamental domain ``[0, 2 pi]^2`` for the god view.

        Unlike the periodic models this grid is not sewn shut by ``linspace``
        endpoints: the ``u = 0`` and ``u = 2 pi`` edge curves are the *same*
        curve traversed with opposite ``v`` (``r(0, -v) = r(2 pi, v)``), so the
        classic self-intersecting bottle picture is drawn without duplicating a
        seam row.
        """
        if nu < 2 or nv < 2:
            raise ValueError("sample_grid requires nu >= 2 and nv >= 2")
        us = np.linspace(0.0, TWO_PI, nu)
        vs = np.linspace(0.0, TWO_PI, nv)
        grid_u, grid_v = np.meshgrid(us, vs)
        points = np.asarray(self.position(grid_u, grid_v), dtype=float)
        return points[..., 0], points[..., 1], points[..., 2]


def _torus_knot_centerline(ring, carrier, p, q, u):
    """Centre curve of the ``(p, q)`` torus knot, numpy-vectorised."""
    u = np.asarray(u, dtype=float)
    theta = p * u
    phi = q * u
    radial = ring + carrier * np.cos(phi)
    return np.stack([radial * np.cos(theta), radial * np.sin(theta), carrier * np.sin(phi)], axis=-1)


def _knot_strand_gap(ring, carrier, p, q, samples=720, refinement=60) -> float:
    """Smallest 3D distance between two points of the knot that are far apart.

    This is the radius limit of an embedded tube: a tube of radius ``rho`` stays
    self-intersection free while ``rho < gap / 2``. The coarse scan is refined by
    coordinate descent, because two strands can approach nearly tangentially and
    a grid alone would overestimate the gap -- and an overestimate would let a
    self-intersecting tube through the constructor.
    """
    u = np.linspace(0.0, TWO_PI, samples, endpoint=False)
    points = _torus_knot_centerline(ring, carrier, p, q, u)
    index = np.arange(samples)
    best = (np.inf, 0.0, 0.0)
    for i in range(samples):
        cyclic = np.minimum(np.abs(index - i), samples - np.abs(index - i))
        distance = np.linalg.norm(points - points[i], axis=1)
        distance[cyclic < samples // 8] = np.inf
        j = int(np.argmin(distance))
        if float(distance[j]) < best[0]:
            best = (float(distance[j]), float(u[i]), float(u[j]))

    def separation(a: float, b: float) -> float:
        pa = _torus_knot_centerline(ring, carrier, p, q, np.array([a]))
        pb = _torus_knot_centerline(ring, carrier, p, q, np.array([b]))
        return float(np.linalg.norm(pa - pb))

    a, b = best[1], best[2]
    coarse = best[0]
    step = TWO_PI / samples
    for _ in range(refinement):
        improved = False
        for da, db in ((step, 0.0), (-step, 0.0), (0.0, step), (0.0, -step)):
            value = separation(a + da, b + db)
            if value < best[0]:
                best = (value, a + da, b + db)
                a, b = a + da, b + db
                improved = True
        step *= 0.6
        if not improved and step < 1e-10:
            break
    # Guard: if the refinement slid into the immediate neighbourhood of the same
    # strand it would report a meaningless gap of ~0, so fall back to the scan.
    parameter_gap = abs((a - b + math.pi) % TWO_PI - math.pi)
    if parameter_gap < 0.5 * math.pi:
        return float(coarse)
    return float(best[0])


@dataclass(frozen=True)
class KnottedTorus(ClosedManifold):
    """Tube around a ``(p, q)`` torus knot -- an *embedded* genus-1 torus.

    The knot lies on a carrier torus of radii ``(ring_radius, carrier_radius)``::

        theta(u) = p u,   phi(u) = q u
        K(u)     = ((R + a cos phi) cos theta, (R + a cos phi) sin theta, a sin phi)

    and the surface is the tube around it, built from the carrier torus's own
    orthonormal frame -- ``N`` the outward normal, ``E`` the ``phi`` tangent::

        r(u, v) = K(u) + rho ( cos v N(u) + sin v E(u) )

    Both frame vectors are elementary and global (no normalisation, no
    Frenet-frame degeneration), so every first and second partial derivative is
    analytic::

        r_u  = K'  + rho ( cos v N' + sin v E')
        r_v  = rho ( -sin v N + cos v E )
        r_uu = K'' + rho ( cos v N'' + sin v E'')
        r_uv = rho ( -sin v N' + cos v E')
        r_vv = -rho ( cos v N + sin v E )

    Honest topology: the knot is a property of the *embedding*, never of the
    surface. A tube around a knot is still a plain torus -- orientable, genus 1,
    chi = 0 -- so Gauss-Bonnet still predicts ``iint K dA = 0``. What changes is
    the gameplay: strands pass close in R^3 while staying far apart along the
    surface, so the ambient-distance detector genuinely cannot tell them apart.
    ``rho`` is validated against the knot's strand gap, so the tube really is
    embedded (no self-intersection) rather than merely looking like it.
    """

    ring_radius: float = 30.0
    carrier_radius: float = 10.0
    knot_p: int = 2
    knot_q: int = 3
    tube_radius: float = 5.0
    name: str = "knotted torus ((2,3) torus knot tube)"
    outward_sign = 1.0
    genus: int = 1
    euler_characteristic: int = 0

    def __post_init__(self) -> None:
        if int(self.knot_p) < 1 or int(self.knot_q) < 1:
            raise ConfigError("KnottedTorus knot_p and knot_q must be >= 1")
        if math.gcd(int(self.knot_p), int(self.knot_q)) != 1:
            raise ConfigError(
                "KnottedTorus requires coprime (p, q); otherwise the curve is a link "
                "and the tube is not even connected"
            )
        if not (self.ring_radius > self.carrier_radius > 0.0):
            raise ConfigError("KnottedTorus requires ring_radius > carrier_radius > 0")
        if not (self.tube_radius > 0.0):
            raise ConfigError("KnottedTorus tube_radius must be > 0")
        gap = _knot_strand_gap(self.ring_radius, self.carrier_radius, int(self.knot_p), int(self.knot_q))
        if self.tube_radius >= 0.5 * gap:
            raise ConfigError(
                f"KnottedTorus tube_radius {self.tube_radius:.3f} is too large: the (p, q) "
                f"strands come within {gap:.3f} of each other, so an embedded tube needs "
                f"tube_radius < {0.5 * gap:.3f}"
            )
        grid_u, grid_v = _periodic_grid(64, 64)
        if float(np.asarray(self.regularity(grid_u, grid_v), dtype=float).min()) <= 0.0:
            raise ConfigError("KnottedTorus parameterisation is not regular")

    def describe(self) -> Tuple:
        return (
            "knotted-torus",
            round(self.ring_radius, 9),
            round(self.carrier_radius, 9),
            int(self.knot_p),
            int(self.knot_q),
            round(self.tube_radius, 9),
        )

    # -- analytic chart ----------------------------------------------------

    def _chart(self, u, v):
        u = np.asarray(u, dtype=float)
        v = np.asarray(v, dtype=float)
        p = float(self.knot_p)
        q = float(self.knot_q)
        ring = float(self.ring_radius)
        carrier = float(self.carrier_radius)
        rho = float(self.tube_radius)

        theta, phi = p * u, q * u
        ct, st = np.cos(theta), np.sin(theta)
        cf, sf = np.cos(phi), np.sin(phi)
        radial = ring + carrier * cf                 # distance from the axis

        centre = np.stack([radial * ct, radial * st, carrier * sf], axis=-1)
        centre_u = np.stack(
            [-carrier * q * sf * ct - radial * p * st,
             -carrier * q * sf * st + radial * p * ct,
             carrier * q * cf],
            axis=-1,
        )
        centre_uu = np.stack(
            [-carrier * q * q * cf * ct + 2.0 * carrier * p * q * sf * st - radial * p * p * ct,
             -carrier * q * q * cf * st - 2.0 * carrier * p * q * sf * ct - radial * p * p * st,
             -carrier * q * q * sf],
            axis=-1,
        )

        normal = np.stack([cf * ct, cf * st, sf], axis=-1)
        normal_u = np.stack([-q * sf * ct - p * cf * st, -q * sf * st + p * cf * ct, q * cf], axis=-1)
        normal_uu = np.stack(
            [-(p * p + q * q) * cf * ct + 2.0 * p * q * sf * st,
             -(p * p + q * q) * cf * st - 2.0 * p * q * sf * ct,
             -q * q * sf],
            axis=-1,
        )

        tangent = np.stack([-sf * ct, -sf * st, cf], axis=-1)
        tangent_u = np.stack([-q * cf * ct + p * sf * st, -q * cf * st - p * sf * ct, -q * sf], axis=-1)
        tangent_uu = np.stack(
            [(p * p + q * q) * sf * ct + 2.0 * p * q * cf * st,
             (p * p + q * q) * sf * st - 2.0 * p * q * cf * ct,
             -q * q * cf],
            axis=-1,
        )

        cv, sv = np.cos(v), np.sin(v)
        cv = cv[..., None] if np.ndim(cv) else float(cv)
        sv = sv[..., None] if np.ndim(sv) else float(sv)

        position = centre + rho * (cv * normal + sv * tangent)
        r_u = centre_u + rho * (cv * normal_u + sv * tangent_u)
        r_v = rho * (-sv * normal + cv * tangent)
        r_uu = centre_uu + rho * (cv * normal_uu + sv * tangent_uu)
        r_uv = rho * (-sv * normal_u + cv * tangent_u)
        r_vv = -rho * (cv * normal + sv * tangent)
        return position, r_u, r_v, r_uu, r_uv, r_vv

    def position(self, u, v):
        return self._chart(u, v)[0]

    def first_partials(self, u, v):
        chart = self._chart(u, v)
        return chart[1], chart[2]

    def second_partials(self, u, v):
        chart = self._chart(u, v)
        return chart[3], chart[4], chart[5]


@dataclass(frozen=True)
class EllipticCurveTorus(DeformedTorus):
    """The square-lattice elliptic curve ``C / (Z + i Z)`` as a surface in R^3.

    This is the torus of revolution whose ring:tube ratio is exactly
    ``sqrt(2) : 1`` -- the stereographic image of the Clifford torus in S^3.
    Stereographic projection is conformal, so this is a *conformal model* of the
    square-lattice flat torus, i.e. of the elliptic curve ``C / <1, i>``:

    * the chart ``(u, v) -> ((R + r cos v) cos u, (R + r cos v) sin u, r sin v)``
      is locally conformal after the substitution
      ``w(v) = integral r dv / (R + r cos v)``, whose period is
      ``W = 2 pi r / sqrt(R^2 - r^2)``;
    * the conformal lattice is therefore generated by ``(2 pi, 0)`` and
      ``(0, W)``, i.e. the modulus is ``tau = i * r / sqrt(R^2 - r^2)``;
    * at ``R / r = sqrt(2)`` this gives ``tau = i`` exactly: the square lattice.

    Honest limits, stated rather than glossed over:

    * This is a *conformal* model, never an isometric one. A flat (``K = 0``)
      closed surface cannot be embedded in R^3 at all (Hilbert); the ambient
      curvature here is the ordinary torus curvature, positive outside and
      negative inside, and Gauss-Bonnet still gives ``iint K dA = 0``.
    * The complex structure is invisible to the game's detector, which measures
      ambient Euclidean distance. The level's gameplay difference is geometric:
      ``r = R / sqrt(2)`` makes the tube fat and the hole narrow
      (``R - r ~ 0.293 R``), so points across the hole are close in R^3 while a
      walk between them goes half-way around the ring.
    """

    ring_radius: float = 61.0
    tube_radius: float = 61.0 / math.sqrt(2.0)
    harmonics: Tuple[RadialHarmonic, ...] = ()
    name: str = "elliptic curve C/(Z + iZ) (square-lattice conformal model)"
    outward_sign = -1.0
    genus: int = 1
    euler_characteristic: int = 0
    #: The chart used here is the plain periodic square.
    require_square_lattice: bool = True

    def __post_init__(self) -> None:
        if self.require_square_lattice and self.harmonics:
            raise ConfigError(
                "EllipticCurveTorus must stay undeformed: any radial harmonic changes the "
                "conformal modulus away from the square lattice it claims to model"
            )
        super().__post_init__()
        if self.require_square_lattice:
            ratio = self.ring_radius / self.tube_radius
            if abs(ratio - math.sqrt(2.0)) > 1e-9:
                raise ConfigError(
                    "EllipticCurveTorus requires ring_radius / tube_radius = sqrt(2) for the "
                    f"square lattice (tau = i); got ratio {ratio:.6f}"
                )

    @property
    def conformal_period(self) -> float:
        """Period ``W = 2 pi r / sqrt(R^2 - r^2)`` of the conformal coordinate."""
        return 2.0 * math.pi * self.tube_radius / math.sqrt(
            self.ring_radius ** 2 - self.tube_radius ** 2
        )

    @property
    def conformal_modulus(self) -> complex:
        """``tau = i * r / sqrt(R^2 - r^2)``; equals ``i`` on the square lattice."""
        return 1j * self.tube_radius / math.sqrt(self.ring_radius ** 2 - self.tube_radius ** 2)

    def describe(self) -> Tuple:
        return (
            "elliptic-curve-torus",
            round(self.ring_radius, 9),
            round(self.tube_radius, 9),
            round(self.conformal_modulus.imag, 9),
        )


@dataclass(frozen=True)
class ProjectivePlane(DeformedEllipsoid):
    """The real projective plane ``RP^2``: the ellipsoid chart modulo antipodes.

    ``RP^2`` is the sphere with antipodal points identified. The ellipsoid chart
    already double-covers the sphere (``r(u + pi, -v) = r(u, v)``), so quotienting
    by the *second* involution is all that is needed::

        r(u + pi, pi - v) = -r(u, v)        (the antipodal map, in chart terms)

    Both identifications are exact symmetries provided the radial modulation is
    even in ``v`` *and* symmetric about ``pi/2`` -- i.e. a function of ``cos(2k v)``
    (harmonics with even order and phase ``pi/2``). Anything else would break the
    quotient, so such deformations are rejected at construction time instead of
    quietly producing a sphere.

    Consequences, all of them checkable and all of them honest:

    * The chart has **four** sheets over the world: ``(u, v)``, ``(u+pi, -v)``
      (the same 3D point), ``(u+pi, pi-v)`` (its antipode) and ``(u, v+pi)``
      (again the antipode). :meth:`orbit_positions` therefore returns *two*
      distinct 3D realizations that are **the same world point**.
    * ``RP^2`` cannot be embedded in R^3. Here it is not even a self-intersecting
      image: the map is 2-to-1 onto the ellipsoid, i.e. a covering map, and it is
      non-orientable, so no global "outside" normal exists.
    * ``chi = 1``, so Gauss-Bonnet gives ``iint K dA = 2 pi`` for the world. The
      chart integrates over the double-covered sphere instead, so the raw number
      is ``8 pi`` -- four world-copies, documented and tested rather than implied.
    * Distances must respect the quotient: two antipodal realizations are one
      point, so the world distance is the *minimum* over the copies. That is what
      the ``orbit_min`` distance policy (``WorldConfig.distance_mode``) provides;
      every other map keeps the plain Euclidean policy.
    """

    semi_x: float = 40.0
    semi_y: float = 40.0
    semi_z: float = 40.0
    harmonics: Tuple[RadialHarmonic, ...] = (
        RadialHarmonic(amplitude=0.10, order=2, phase=math.pi / 2, axis="v"),
        RadialHarmonic(amplitude=0.06, order=4, phase=math.pi / 2, axis="v"),
        RadialHarmonic(amplitude=0.04, order=6, phase=math.pi / 2, axis="v"),
    )
    name: str = "real projective plane (non-orientable)"
    center = (0.0, 0.0, 0.0)
    genus: int = 1                     # non-orientable genus: one cross-cap
    orientable = False
    twisted = True
    euler_characteristic: int = 1

    def __post_init__(self) -> None:
        super().__post_init__()
        for term in self.harmonics:
            if term.axis != "v":
                raise ConfigError("ProjectivePlane supports radial (axis='v') modulation only")
            if int(term.order) % 2 != 0 or abs(math.sin(float(term.phase))) < 1e-9:
                raise ConfigError(
                    "ProjectivePlane modulation must be even in v and symmetric about pi/2 "
                    "(harmonics with even order and phase = pi/2), otherwise the antipodal "
                    "quotient is not a symmetry of the chart"
                )
        # Self-check both identifications the quotient relies on.
        probe_u = np.array([0.3, 1.7, -2.4, 2.9])
        probe_v = np.array([0.0, 0.9, -1.3, 2.5])
        sheet = np.asarray(self.position(probe_u + math.pi, -probe_v), dtype=float)
        if not np.allclose(sheet, np.asarray(self.position(probe_u, probe_v), dtype=float), atol=1e-9):
            raise ConfigError("ProjectivePlane failed the chart double-cover identity")
        antipode = np.asarray(self.position(probe_u + math.pi, math.pi - probe_v), dtype=float)
        if not np.allclose(antipode, -np.asarray(self.position(probe_u, probe_v), dtype=float), atol=1e-9):
            raise ConfigError("ProjectivePlane failed the antipodal identity r(u+pi, pi-v) = -r(u,v)")

    def describe(self) -> Tuple:
        return (
            "projective-plane",
            round(self.semi_x, 9),
            round(self.semi_y, 9),
            round(self.semi_z, 9),
            tuple((int(t.order), round(t.amplitude, 9), round(t.phase, 9)) for t in self.harmonics),
        )

    def chart_copy_transforms(self):
        """Four chart sheets: two name each of the two antipodal realizations."""
        return (
            (0.0, 0.0, False),                      # (u, v)
            (math.pi, 0.0, True),                   # (u+pi, -v)   same 3D point
            (math.pi, math.pi, True),               # (u+pi, pi-v) the antipode
            (0.0, math.pi, False),                  # (u, v+pi)    the antipode
        )


def _poly(terms):
    """Evaluate a polynomial ``sum coef * C^i S^j`` (C = cos u, S = sin u)."""
    def evaluate(u):
        c, s = np.cos(u), np.sin(u)
        total = None
        for (i, j), coef in terms.items():
            term = coef * c ** i * s ** j
            total = term if total is None else total + term
        return total
    return evaluate


def _poly_derivative(terms):
    """Exact ``d/du`` of a polynomial in ``(cos u, sin u)``.

    Uses ``d/du (C^i S^j) = -i C^(i-1) S^(j+1) + j C^(i+1) S^(j-1)`` -- symbolic
    differentiation of a known polynomial, never a finite difference.
    """
    out = {}
    for (i, j), coef in terms.items():
        if i:
            key = (i - 1, j + 1)
            out[key] = out.get(key, 0.0) - coef * i
        if j:
            key = (i + 1, j - 1)
            out[key] = out.get(key, 0.0) + coef * j
    return {key: value for key, value in out.items() if value != 0.0}


# Profile of the classical bottle immersion, split as
#   x = A1(u) cos v + A0(u),  y = B1(u) cos v + B0(u),  z = C1(u) sin v
# with C = cos u, S = sin u. Written as exponent dictionaries so the exact
# derivatives come from _poly_derivative instead of hand algebra.
_BOTTLE_A0 = {(1, 1): 4.0, (5, 1): -12.0, (7, 1): 8.0}
_BOTTLE_A1 = {(1, 0): -2.0 / 5.0, (2, 1): -2.0 / 3.0}
_BOTTLE_B0 = {(0, 2): 4.0}
_BOTTLE_B1 = {
    (0, 1): -1.0 / 5.0, (2, 1): 1.0 / 5.0, (4, 1): 16.0 / 5.0, (6, 1): -16.0 / 5.0,
    (1, 2): -1.0 / 3.0, (3, 2): 1.0 / 3.0, (5, 2): 16.0 / 3.0, (7, 2): -16.0 / 3.0,
}
_BOTTLE_C1 = {(0, 0): 2.0 / 5.0, (1, 1): 2.0 / 3.0}


@dataclass(frozen=True)
class BottleKleinBottle(ClosedManifold):
    """Bottle-shaped Klein bottle: the classical self-intersecting immersion.

    Uses the standard parametrisation of the "traditional" Klein bottle (the
    one everybody pictures: neck diving through the body), with the chart
    re-parameterised so that the model fits this engine's chart contract.

    The published formula, for ``0 <= u, v < 2 pi``::

        x = -(2/15) cos u (3 cos v - 30 sin u + 90 cos^4 u sin u
                          - 60 cos^6 u sin u + 5 cos u cos v sin u)
        y = -(1/15) sin u (3 cos v - 3 cos^2 u cos v - 48 cos^4 u cos v
                          + 48 cos^6 u cos v - 60 sin u + 5 cos u cos v sin u
                          - 5 cos^3 u cos v sin u - 80 cos^5 u cos v sin u
                          + 80 cos^7 u cos v sin u)
        z = (2/15) (3 + 5 cos u sin u) sin v

    Facts this class pins down rather than assumes:

    * **The formula is 2 pi-periodic in both variables, yet its image is a Klein
      bottle.** The identification is *not* a translation: ``r(u + pi, v) =
      r(u, pi - v)``. The chart therefore splits as
      ``x = A1(u) cos v + A0(u)``, ``y = B1(u) cos v + B0(u)``,
      ``z = C1(u) sin v`` with ``A1, B1`` odd and ``A0, B0, C1`` even in
      ``u -> u + pi`` -- verified numerically in ``__post_init__``.
    * **Chart contract.** Writing ``U = 2u`` and ``w = v - pi/2`` turns the
      identification into ``(U + 2 pi, -w)``, i.e. exactly the twisted shape the
      base class supports, with periods ``(4 pi, 2 pi)`` and two chart sheets.
    * **Topology.** Non-orientable, no boundary, ``chi = 0``, so Gauss-Bonnet
      still predicts ``iint K dA = 0``. The immersion necessarily intersects
      itself (the neck passes through the body); the chart is regular
      (``E G - F^2 > 0``) even where the image crosses itself.
    * Together with :class:`KleinBottle` (the figure-8 immersion) this level
      covers two of the three regular homotopy classes of Klein bottle
      immersions in R^3; the figure-8 one is chiral, this one is its mirror
      class.
    """

    scale: float = 30.0
    name: str = "bottle-shaped Klein bottle (non-orientable)"
    outward_sign = 1.0
    genus = None
    euler_characteristic: int = 0
    orientable: bool = False
    twisted: bool = True

    def __post_init__(self) -> None:
        if not np.isfinite(self.scale) or self.scale <= 0.0:
            raise ConfigError("BottleKleinBottle scale must be finite and > 0")
        grid_u, grid_v = _periodic_grid(96, 96)
        if float(np.asarray(self.regularity(grid_u, grid_v), dtype=float).min()) <= 0.0:
            raise ConfigError("BottleKleinBottle chart is not an immersion (E G - F^2 <= 0)")
        # Self-checks of the identification the whole chart API relies on.
        probe_u = np.array([0.3, 1.7, -2.4, 2.9])
        probe_w = np.array([0.0, 0.9, -1.3, 2.5])
        twisted = np.asarray(self.position(probe_u + TWO_PI, probe_w), dtype=float)
        mirrored = np.asarray(self.position(probe_u, -probe_w), dtype=float)
        if not np.allclose(twisted, mirrored, atol=1e-9):
            raise ConfigError("BottleKleinBottle failed r(U + 2 pi, w) = r(U, -w)")
        for shifted in (self.position(probe_u + 2.0 * TWO_PI, probe_w),
                        self.position(probe_u, probe_w + TWO_PI)):
            if not np.allclose(np.asarray(shifted, dtype=float),
                               np.asarray(self.position(probe_u, probe_w), dtype=float), atol=1e-9):
                raise ConfigError("BottleKleinBottle failed a pure translation period")

    def describe(self) -> Tuple:
        return ("klein-bottle-traditional", round(self.scale, 9))

    # -- chart identification ---------------------------------------------

    def chart_periods(self) -> Tuple[float, float]:
        # U has period 4 pi: shifting it by 2 pi mirrors w instead.
        return (2.0 * TWO_PI, TWO_PI)

    def chart_copy_transforms(self):
        return ((0.0, 0.0, False), (TWO_PI, 0.0, True))

    # -- analytic chart ----------------------------------------------------

    def _chart(self, u, v):
        U = np.asarray(u, dtype=float)
        w = np.asarray(v, dtype=float)
        half = 0.5 * U                       # the published variable u = U/2
        vv = w + 0.5 * math.pi               # the published variable v
        cos_v, sin_v = np.cos(vv), np.sin(vv)

        profiles = (
            _BOTTLE_A1, _BOTTLE_A0, _BOTTLE_B1, _BOTTLE_B0, _BOTTLE_C1,
        )
        values = []
        for terms in profiles:
            first = _poly_derivative(terms)
            second = _poly_derivative(first)
            # d/dU = (1/2) d/du, d^2/dU^2 = (1/4) d^2/du^2
            values.append((_poly(terms)(half), 0.5 * _poly(first)(half), 0.25 * _poly(second)(half)))
        (a1, a1u, a1uu), (a0, a0u, a0uu), (b1, b1u, b1uu), (b0, b0u, b0uu), (c1, c1u, c1uu) = values

        scale = float(self.scale)
        position = scale * np.stack([a1 * cos_v + a0, b1 * cos_v + b0, c1 * sin_v], axis=-1)
        r_u = scale * np.stack([a1u * cos_v + a0u, b1u * cos_v + b0u, c1u * sin_v], axis=-1)
        r_v = scale * np.stack([-a1 * sin_v, -b1 * sin_v, c1 * cos_v], axis=-1)
        r_uu = scale * np.stack([a1uu * cos_v + a0uu, b1uu * cos_v + b0uu, c1uu * sin_v], axis=-1)
        r_uv = scale * np.stack([-a1u * sin_v, -b1u * sin_v, c1u * cos_v], axis=-1)
        r_vv = scale * np.stack([-a1 * cos_v, -b1 * cos_v, -c1 * sin_v], axis=-1)
        return position, r_u, r_v, r_uu, r_uv, r_vv

    def position(self, u, v):
        return self._chart(u, v)[0]

    def first_partials(self, u, v):
        chart = self._chart(u, v)
        return chart[1], chart[2]

    def second_partials(self, u, v):
        chart = self._chart(u, v)
        return chart[3], chart[4], chart[5]

    def sample_grid(self, nu: int, nv: int):
        """Classic bottle mesh: the published domain drawn exactly once.

        ``u in [0, pi]`` already covers the whole image (the rest is its mirror
        sheet), and the two ``u``-edges are the same curve traversed backwards,
        so the picture closes up without a duplicated seam row.
        """
        if nu < 2 or nv < 2:
            raise ValueError("sample_grid requires nu >= 2 and nv >= 2")
        us = np.linspace(0.0, TWO_PI, nu)             # U = 2u, so u in [0, pi]
        vs = np.linspace(-0.5 * math.pi, 1.5 * math.pi, nv)   # v in [0, 2 pi]
        grid_u, grid_v = np.meshgrid(us, vs)
        points = np.asarray(self.position(grid_u, grid_v), dtype=float)
        return points[..., 0], points[..., 1], points[..., 2]


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