"""Built-in map definition managed independently."""

from __future__ import annotations

from src.the_curved_world.config import default_surface_config
from src.the_curved_world.geometry import SmoothSurface
from src.the_curved_world.manifold import (
    BottleKleinBottle,
    DeformedEllipsoid,
    DeformedTorus,
    EllipticCurveTorus,
    GenusTwoApproximation,
    KleinBottle,
    KnottedTorus,
    ProjectivePlane,
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
    placement={"min_separation": 70.0, "boundary_margin": 0.0, "detector_scale": 60.0, "obstacle_count": 30, "obstacle_radius": 4.2, "obstacle_safe_margin": 45.0},
    genus=1,
)
class TorusGenusOneMap:
    def build(self, params):
        return DeformedTorus(ring_radius=130.0, tube_radius=45.0, harmonics=default_harmonics())
