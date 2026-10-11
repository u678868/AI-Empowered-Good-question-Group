"""Tests for the smooth surface geometry."""

from __future__ import annotations

import numpy as np
import pytest

from src.the_curved_world.config import (
    Domain,
    GaussianHill,
    SurfaceConfig,
    WaveComponent,
    default_surface_config,
)
from src.the_curved_world.geometry import SmoothSurface, ambient_distance


@pytest.fixture()
def surface() -> SmoothSurface:
    domain = Domain(-2.0, 2.0, -3.0, 1.0)
    config = SurfaceConfig(
        domain=domain,
        wave=WaveComponent(amplitude=0.5, kx=1.3, ky=0.7),
        hills=(
            GaussianHill(amplitude=0.8, center_x=0.5, center_y=-0.5, scale=1.1),
            GaussianHill(amplitude=-0.6, center_x=-1.0, center_y=0.5, scale=0.9),
        ),
    )
    return SmoothSurface(config)


def test_height_is_finite_and_inside_domain(surface: SmoothSurface) -> None:
    for x, y in [(0.0, 0.0), (1.9, -2.9), (-2.0, 1.0)]:
        z = surface.height(x, y)
        assert np.isfinite(z)
        assert surface.contains(x, y)


def test_contains_rejects_outside_points(surface: SmoothSurface) -> None:
    assert not surface.contains(2.5, 0.0)
    assert not surface.contains(0.0, 5.0)
    # margin shrinks the domain
    assert surface.contains(1.9, 0.0)
    assert not surface.contains(1.9, 0.0, margin=0.5)


def test_positions_satisfy_z_equals_f(surface: SmoothSurface) -> None:
    rng = np.random.default_rng(0)
    xs = rng.uniform(-2.0, 2.0, 25)
    ys = rng.uniform(-3.0, 1.0, 25)
    points = surface.position(xs, ys)
    assert points.shape == (25, 3)
    assert np.allclose(points[:, 0], xs)
    assert np.allclose(points[:, 1], ys)
    assert np.allclose(points[:, 2], surface.height(xs, ys))


def test_gradient_matches_central_difference(surface: SmoothSurface) -> None:
    x, y = 0.3, -0.7
    gx, gy = surface.gradient(x, y)
    h = 1e-6
    fdx = (surface.height(x + h, y) - surface.height(x - h, y)) / (2 * h)
    fdy = (surface.height(x, y + h) - surface.height(x, y - h)) / (2 * h)
    assert gx == pytest.approx(fdx, abs=1e-4)
    assert gy == pytest.approx(fdy, abs=1e-4)


def test_normals_are_unit_length_and_finite(surface: SmoothSurface) -> None:
    rng = np.random.default_rng(1)
    xs = rng.uniform(-2.0, 2.0, 40)
    ys = rng.uniform(-3.0, 1.0, 40)
    normals = surface.normal(xs, ys)
    assert normals.shape == (40, 3)
    assert np.all(np.isfinite(normals))
    assert np.allclose(np.linalg.norm(normals, axis=1), 1.0, atol=1e-12)


def test_sample_grid_shapes_and_consistency(surface: SmoothSurface) -> None:
    grid_x, grid_y, grid_z = surface.sample_grid(6, 4)
    assert grid_x.shape == (4, 6)
    assert grid_y.shape == (4, 6)
    assert np.allclose(grid_z, surface.height(grid_x, grid_y))
    assert np.all(surface.contains(grid_x, grid_y))


def test_ambient_distance_is_symmetric_and_nonnegative() -> None:
    p = np.array([0.0, 0.0, 1.0])
    q = np.array([1.0, 2.0, 2.0])
    expected = np.sqrt(1.0 + 4.0 + 1.0)
    assert ambient_distance(p, q) == pytest.approx(expected)
    assert ambient_distance(p, q) == ambient_distance(q, p)
    assert ambient_distance(p, p) == 0.0
    assert ambient_distance(p, q) >= 0.0


def test_sample_grid_rejects_too_small_resolution(surface: SmoothSurface) -> None:
    with pytest.raises(ValueError):
        surface.sample_grid(1, 5)
def test_gaussian_curvature_is_zero_for_a_plane() -> None:
    surface = SmoothSurface(
        SurfaceConfig(domain=Domain(-2.0, 2.0, -2.0, 2.0), wave=WaveComponent(0.0, 1.0, 1.0))
    )
    assert surface.gaussian_curvature(0.3, -0.4) == pytest.approx(0.0, abs=1e-12)


def test_gaussian_curvature_of_a_gaussian_bump_at_its_peak() -> None:
    surface = SmoothSurface(
        SurfaceConfig(
            domain=Domain(-2.0, 2.0, -2.0, 2.0),
            wave=WaveComponent(0.0, 1.0, 1.0),
            hills=(GaussianHill(1.0, 0.0, 0.0, 1.0),),
        )
    )
    # K(peak) = (2h/s^2)^2 = 4 for h = 1, s = 1
    assert surface.gaussian_curvature(0.0, 0.0) == pytest.approx(4.0)


def test_gaussian_curvature_matches_finite_difference_hessian() -> None:
    surface = SmoothSurface(default_surface_config())
    rng = np.random.default_rng(3)
    xs = rng.uniform(-2.5, 2.5, 15)
    ys = rng.uniform(-2.5, 2.5, 15)
    step = 1e-4
    fx, fy = surface.gradient(xs, ys)
    fxx = (surface.height(xs + step, ys) - 2.0 * surface.height(xs, ys) + surface.height(xs - step, ys)) / step ** 2
    fyy = (surface.height(xs, ys + step) - 2.0 * surface.height(xs, ys) + surface.height(xs, ys - step)) / step ** 2
    fxy = (
        surface.height(xs + step, ys + step)
        - surface.height(xs + step, ys - step)
        - surface.height(xs - step, ys + step)
        + surface.height(xs - step, ys - step)
    ) / (4.0 * step ** 2)
    expected = (fxx * fyy - fxy ** 2) / (1.0 + fx ** 2 + fy ** 2) ** 2
    assert np.allclose(surface.gaussian_curvature(xs, ys), expected, atol=1e-3)