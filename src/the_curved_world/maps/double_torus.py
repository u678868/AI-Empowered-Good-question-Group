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
    map_id="double_torus",
    name="Two-hole Surface (genus-2 look)",
    description=(
        "The ring radius is modulated as R(u) = R0 + R1 cos(2u) plus tube harmonics, producing a "
        "two-lobed, two-hole silhouette. The image is still genus 1: a true genus-2 surface would "
        "need a genus-2 parameter domain."
    ),
    topology=CLOSED_PERIODIC,
    placement={"min_separation": 10.0, "boundary_margin": 0.0, "detector_scale": 11.0, "obstacle_count": 16, "obstacle_radius": 4.5, "obstacle_safe_margin": 12.0},
    genus=1,
)
class DoubleTorusMap:
    def build(self, params):
        return GenusTwoApproximation(harmonics=default_genus_two_harmonics())
