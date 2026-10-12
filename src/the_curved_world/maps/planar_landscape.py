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
    map_id="planar_landscape",
    name="Classic Planar Landscape",
    description=(
        "Multi-scale sines plus mixed Gaussian hills on a bounded 100x100 parameter domain. "
        "Has a boundary clamp; it is not a closed manifold."
    ),
    topology=BOUNDED_PLANE,
    placement={"min_separation": 25.0, "boundary_margin": 3.0, "detector_scale": 25.0, "obstacle_count": 18, "obstacle_radius": 4.5, "obstacle_safe_margin": 16.0},
    genus=None,
)
class PlanarLandscapeMap:
    def build(self, params):
        return SmoothSurface(default_surface_config())
