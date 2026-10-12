"""Compatibility aggregate importing every built-in map module.

Each map is implemented in its own module so it can declare its geometry and
placement independently. The registry discovers the modules automatically.
"""

from __future__ import annotations

from . import (  # noqa: F401
    double_torus,
    elliptic_curve,
    ellipsoid,
    klein_bottle,
    knot_garden,
    planar_landscape,
    projective_plane,
    torus,
    traditional_klein,
)

__all__ = [
    "torus",
    "ellipsoid",
    "double_torus",
    "klein_bottle",
    "traditional_klein",
    "knot_garden",
    "elliptic_curve",
    "projective_plane",
    "planar_landscape",
]
