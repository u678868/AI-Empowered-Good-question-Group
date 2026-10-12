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
    map_id="klein_bottle",
    name="Klein Bottle (non-orientable)",
    description=(
        "The classical figure-8 immersion of the Klein bottle. It has no boundary and no "
        "clamping, but it is NOT embeddable in R^3: the surface must pass through itself, so "
        "two distinct parameter points can share one 3D position (and the detector then reads "
        "maximum signal there). It is non-orientable -- there is no global outside, and the "
        "local chart flips handedness along one loop. Euler characteristic chi = 0, so "
        "Gauss-Bonnet still gives iint K dA = 0, exactly as measured."
    ),
    topology=CLOSED_PERIODIC,
    non_orientable=True,
    placement={"min_separation": 60.0, "boundary_margin": 0.0, "detector_scale": 45.0, "obstacle_count": 26, "obstacle_radius": 4.5, "obstacle_safe_margin": 40.0},
)
class KleinBottleMap:
    def build(self, params):
        return KleinBottle(ring_radius=90.0, tube_radius=31.0)
