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
    map_id="knot_garden",
    name="Knotted Torus (trefoil knot tube)",
    description=(
        "A tube of constant radius around a (2,3) torus knot. Topologically this is still an "
        "ordinary torus -- orientable, genus 1, chi = 0, iint K dA = 0 -- but the knot lives in "
        "the EMBEDDING, so the strands pass within a few units of each other in R^3 while "
        "staying far apart along the surface. The ambient detector genuinely cannot tell two "
        "strands apart, which is the whole puzzle."
    ),
    topology=CLOSED_PERIODIC,
    genus=1,
    placement={"min_separation": 60.0, "boundary_margin": 0.0, "detector_scale": 30.0, "obstacle_count": 24, "obstacle_radius": 3.0, "obstacle_safe_margin": 20.0},
)
class KnotGardenMap:
    def build(self, params):
        return KnottedTorus(
            ring_radius=30.0, carrier_radius=10.0, knot_p=2, knot_q=3, tube_radius=8.0
        )
