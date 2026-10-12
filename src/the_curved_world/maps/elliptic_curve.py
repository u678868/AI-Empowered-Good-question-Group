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
    map_id="elliptic_curve",
    name="Elliptic Curve C/(Z + iZ)",
    description=(
        "The square-lattice elliptic curve as a conformal model: the stereographic image of the "
        "Clifford torus, i.e. the torus of revolution with ring:tube = sqrt(2):1. Its conformal "
        "modulus is exactly tau = i. Honest limit: this is a CONFORMAL model, never isometric -- "
        "a flat (K = 0) closed surface cannot be embedded in R^3 at all (Hilbert). Gameplay-wise "
        "the fat tube and the narrow hole put many near-strands close together in R^3."
    ),
    topology=CLOSED_PERIODIC,
    genus=1,
    placement={"min_separation": 60.0, "boundary_margin": 0.0, "detector_scale": 45.0, "obstacle_count": 28, "obstacle_radius": 4.0, "obstacle_safe_margin": 30.0},
)
class EllipticCurveMap:
    def build(self, params):
        return EllipticCurveTorus()
