"""The four built-in maps (registered on import)."""

from __future__ import annotations

from src.the_curved_world.config import default_surface_config
from src.the_curved_world.geometry import SmoothSurface
from src.the_curved_world.manifold import (
    DeformedEllipsoid,
    DeformedTorus,
    GenusTwoApproximation,
    default_ellipsoid_harmonics,
    default_genus_two_harmonics,
    default_harmonics,
)
from src.the_curved_world.maps import (
    BOUNDED_PLANE,
    CLOSED_PERIODIC,
    register_map,
)


@register_map(
    map_id="torus_genus1",
    name="Deformed Torus (genus 1)",
    description=(
        "Euler characteristic chi = 0. The tube radius is smoothly perturbed, giving positive "
        "curvature on the outer ring and negative curvature on the inner ring; the curvature "
        "integral is iint K dA = 0. Periodically wrapped, no boundary."
    ),
    topology=CLOSED_PERIODIC,
    placement={"min_separation": 12.0, "boundary_margin": 0.0, "detector_scale": 12.0},
)
class TorusGenusOneMap:
    def build(self, params):
        return DeformedTorus(ring_radius=20.0, tube_radius=7.0, harmonics=default_harmonics())


@register_map(
    map_id="ellipsoid_genus0",
    name="Wavy Ellipsoid (genus 0)",
    description=(
        "Radial modulation in spherical coordinates. chi = 2; the torus chart covers it twice, "
        "and the two poles are topologically unavoidable degenerate parameter points."
    ),
    topology=CLOSED_PERIODIC,
    placement={"min_separation": 12.0, "boundary_margin": 0.0, "detector_scale": 12.0},
)
class EllipsoidGenusZeroMap:
    def build(self, params):
        return DeformedEllipsoid(harmonics=default_ellipsoid_harmonics())


@register_map(
    map_id="double_torus",
    name="Two-hole Surface (genus-2 look)",
    description=(
        "The ring radius is modulated as R(u) = R0 + R1 cos(2u) plus tube harmonics, producing a "
        "two-lobed, two-hole silhouette. The image is still genus 1: a true genus-2 surface would "
        "need a genus-2 parameter domain."
    ),
    topology=CLOSED_PERIODIC,
    placement={"min_separation": 8.0, "boundary_margin": 0.0, "detector_scale": 9.0},
)
class DoubleTorusMap:
    def build(self, params):
        return GenusTwoApproximation(harmonics=default_genus_two_harmonics())


@register_map(
    map_id="planar_landscape",
    name="Classic Planar Landscape",
    description=(
        "Multi-scale sines plus mixed Gaussian hills on a bounded 100x100 parameter domain. "
        "Has a boundary clamp; it is not a closed manifold."
    ),
    topology=BOUNDED_PLANE,
    placement={"min_separation": 25.0, "boundary_margin": 3.0, "detector_scale": 25.0},
)
class PlanarLandscapeMap:
    def build(self, params):
        return SmoothSurface(default_surface_config())