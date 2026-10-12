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
    map_id="ellipsoid_genus0",
    name="Wavy Ellipsoid (genus 0)",
    description=(
        "Radial modulation in spherical coordinates. chi = 2; the torus chart covers it twice, "
        "and the two poles are topologically unavoidable degenerate parameter points."
    ),
    topology=CLOSED_PERIODIC,
    placement={"min_separation": 14.0, "boundary_margin": 0.0, "detector_scale": 13.0, "obstacle_count": 8, "obstacle_radius": 2.4, "obstacle_safe_margin": 12.0},
    genus=0,
)
class EllipsoidGenusZeroMap:
    def build(self, params):
        return DeformedEllipsoid(harmonics=default_ellipsoid_harmonics())
