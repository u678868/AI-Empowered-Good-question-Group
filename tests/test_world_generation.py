"""Tests for deterministic world generation."""

from __future__ import annotations

import pytest

from src.the_curved_world.config import (
    ConfigError,
    Domain,
    GaussianHill,
    WorldConfig,
    default_config,
    default_surface_config,
)
from src.the_curved_world.geometry import ambient_distance
from src.the_curved_world.world import WorldGenerator


def test_identical_seeds_reproduce_identical_world() -> None:
    generator = WorldGenerator(default_config())
    first = generator.generate(42)
    second = generator.generate(42)

    assert first.seed == second.seed
    assert first.start == second.start
    assert first.exit == second.exit
    assert first.surface.config == second.surface.config
    assert first.surface.height(0.3, -0.4) == second.surface.height(0.3, -0.4)


def test_different_seeds_normally_differ() -> None:
    generator = WorldGenerator(default_config())
    first = generator.generate(1)
    second = generator.generate(2)
    assert (first.start != second.start) or (first.exit != second.exit)


def test_start_and_exit_inside_domain_and_separated() -> None:
    config = default_config()
    generator = WorldGenerator(config)
    for seed in range(8):
        world = generator.generate(seed)
        assert world.surface.contains(*world.start)
        assert world.surface.contains(*world.exit)
        distance = ambient_distance(world.start_position, world.exit_position())
        assert distance >= config.min_separation - 1e-9


def test_start_and_exit_respect_boundary_margin() -> None:
    config = default_config()
    generator = WorldGenerator(config)
    for seed in range(8):
        world = generator.generate(seed)
        assert config.domain.contains(*world.start, margin=config.boundary_margin * 0.99)
        assert config.domain.contains(*world.exit, margin=config.boundary_margin * 0.99)


def test_none_seed_still_reproducible() -> None:
    generator = WorldGenerator(default_config())
    world = generator.generate(None)
    replayed = generator.generate(world.seed)
    assert replayed.start == world.start
    assert replayed.exit == world.exit


def test_invalid_min_separation_raises() -> None:
    config = default_config()
    with pytest.raises(ConfigError):
        WorldConfig(domain=config.domain, surface=config.surface, min_separation=-1.0)


def test_invalid_domain_raises() -> None:
    with pytest.raises(ConfigError):
        Domain(1.0, 1.0, 0.0, 1.0)
    with pytest.raises(ConfigError):
        Domain(0.0, 1.0, 2.0, 1.0)


def test_invalid_hill_scale_raises() -> None:
    with pytest.raises(ConfigError):
        GaussianHill(amplitude=1.0, center_x=0.0, center_y=0.0, scale=0.0)


def test_surface_domain_must_match_config_domain() -> None:
    other = Domain(-1.0, 1.0, -1.0, 1.0)
    with pytest.raises(ConfigError):
        WorldConfig(domain=other, surface=default_surface_config())