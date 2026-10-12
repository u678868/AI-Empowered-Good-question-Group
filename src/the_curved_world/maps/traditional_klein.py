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
    map_id="klein_bottle_traditional",
    name="Traditional Klein Bottle (bottle shape)",
    description=(
        "The classical bottle-shaped immersion of the Klein bottle: the neck dives through the "
        "body. Non-orientable, chi = 0, iint K dA = 0, and it cannot be embedded in R^3 -- the "
        "self-intersection is unavoidable. Together with the figure-8 Klein bottle this level "
        "covers two of the three regular homotopy classes of Klein immersions; the figure-8 one "
        "is chiral, this traditional one is achiral."
    ),
    topology=CLOSED_PERIODIC,
    non_orientable=True,
    placement={"min_separation": 55.0, "boundary_margin": 0.0, "detector_scale": 28.0, "obstacle_count": 26, "obstacle_radius": 3.2, "obstacle_safe_margin": 22.0},
)
class TraditionalKleinMap:
    def build(self, params):
        return BottleKleinBottle(scale=30.0)
