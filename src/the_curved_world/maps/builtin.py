"""The four built-in maps (registered on import)."""

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
)
class TorusGenusOneMap:
    def build(self, params):
        return DeformedTorus(ring_radius=130.0, tube_radius=45.0, harmonics=default_harmonics())


@register_map(
    map_id="ellipsoid_genus0",
    name="Wavy Ellipsoid (genus 0)",
    description=(
        "Radial modulation in spherical coordinates. chi = 2; the torus chart covers it twice, "
        "and the two poles are topologically unavoidable degenerate parameter points."
    ),
    topology=CLOSED_PERIODIC,
    placement={"min_separation": 14.0, "boundary_margin": 0.0, "detector_scale": 13.0, "obstacle_count": 8, "obstacle_radius": 2.4, "obstacle_safe_margin": 12.0},
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
    placement={"min_separation": 10.0, "boundary_margin": 0.0, "detector_scale": 11.0, "obstacle_count": 16, "obstacle_radius": 4.5, "obstacle_safe_margin": 12.0},
)
class DoubleTorusMap:
    def build(self, params):
        return GenusTwoApproximation(harmonics=default_genus_two_harmonics())


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
    placement={"min_separation": 60.0, "boundary_margin": 0.0, "detector_scale": 30.0, "obstacle_count": 24, "obstacle_radius": 3.0, "obstacle_safe_margin": 20.0},
)
class KnotGardenMap:
    def build(self, params):
        return KnottedTorus(
            ring_radius=30.0, carrier_radius=10.0, knot_p=2, knot_q=3, tube_radius=8.0
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
    placement={"min_separation": 60.0, "boundary_margin": 0.0, "detector_scale": 45.0, "obstacle_count": 28, "obstacle_radius": 4.0, "obstacle_safe_margin": 30.0},
)
class EllipticCurveMap:
    def build(self, params):
        return EllipticCurveTorus()


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


@register_map(
    map_id="planar_landscape",
    name="Classic Planar Landscape",
    description=(
        "Multi-scale sines plus mixed Gaussian hills on a bounded 100x100 parameter domain. "
        "Has a boundary clamp; it is not a closed manifold."
    ),
    topology=BOUNDED_PLANE,
    placement={"min_separation": 25.0, "boundary_margin": 3.0, "detector_scale": 25.0, "obstacle_count": 18, "obstacle_radius": 4.5, "obstacle_safe_margin": 16.0},
)
class PlanarLandscapeMap:
    def build(self, params):
        return SmoothSurface(default_surface_config())
