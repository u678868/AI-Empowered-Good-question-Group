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
    map_id="projective_plane",
    name="Real Projective Plane RP^2 (antipodal)",
    description=(
        "The sphere with antipodal points identified: your antipode IS you. Non-orientable, "
        "chi = 1, so Gauss-Bonnet gives iint K dA = 2 pi for the world (the chart integrates "
        "over the double-covered sphere, hence 8 pi -- four world-copies). RP^2 cannot be "
        "embedded in R^3; here the chart map is 2-to-1 onto an ellipsoid rather than "
        "self-intersecting. This is the only map that uses the 'orbit_min' distance policy, so a "
        "reading is the nearest of the two antipodal realizations -- as it must be, since they "
        "are one place."
    ),
    topology=CLOSED_PERIODIC,
    non_orientable=True,
    placement={"min_separation": 45.0, "boundary_margin": 0.0, "detector_scale": 22.0, "obstacle_count": 20, "obstacle_radius": 3.0, "obstacle_safe_margin": 16.0, "distance_mode": "orbit_min"},
)
class ProjectivePlaneMap:
    def build(self, params):
        return ProjectivePlane()
