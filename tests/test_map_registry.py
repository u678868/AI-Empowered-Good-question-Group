"""Tests for the extensible map registry (Task 9)."""

from __future__ import annotations

import json

import pytest

from src.the_curved_world.config import ConfigError, WorldConfig
from src.the_curved_world.gameplay import ExplorationGame
from src.the_curved_world.geometry import SmoothSurface
from src.the_curved_world.maps import (
    BOUNDED_PLANE,
    CLOSED_PERIODIC,
    DEFAULT_MAP_ID,
    MapMetadata,
    MapNotFound,
    MapRegistry,
    map_id_for,
    register_map,
    world_config_for,
)
from src.the_curved_world.world import WorldGenerator

BUILTIN_IDS = ["double_torus", "ellipsoid_genus0", "planar_landscape", "torus_genus1"]


def test_builtin_maps_are_registered() -> None:
    assert MapRegistry.ids() == BUILTIN_IDS
    assert DEFAULT_MAP_ID in MapRegistry.ids()


def test_every_map_has_complete_metadata() -> None:
    for entry in MapRegistry.list_maps():
        assert {"id", "name", "description", "topology", "periodic"} <= set(entry)
        assert entry["name"]
        assert entry["description"]
        assert entry["topology"] in (CLOSED_PERIODIC, BOUNDED_PLANE)
        assert entry["periodic"] == (entry["topology"] == CLOSED_PERIODIC)
        json.dumps(entry)  # must be JSON serialisable for the /api/maps endpoint


def test_create_builds_a_surface_per_id() -> None:
    seen = set()
    for map_id in BUILTIN_IDS:
        surface = MapRegistry.create(map_id)
        assert hasattr(surface, "position") and hasattr(surface, "domain")
        assert surface.domain == world_config_for(map_id).domain
        seen.add(type(surface).__name__)
    assert len(seen) == 4  # four distinct surface classes


def test_unknown_map_id_is_rejected() -> None:
    with pytest.raises(MapNotFound):
        MapRegistry.get("no_such_map")
    with pytest.raises(MapNotFound):
        MapRegistry.create("no_such_map")
    with pytest.raises(MapNotFound):
        world_config_for("no_such_map")


def test_every_map_builds_a_playable_world() -> None:
    for map_id in BUILTIN_IDS:
        config = world_config_for(map_id)
        assert isinstance(config, WorldConfig)
        world = WorldGenerator(config).generate(11)
        game = ExplorationGame(world)
        assert 0.0 <= game.read_detector().signal <= 1.0
        for _ in range(30):
            game.move(1.0, 0.3)
        assert game.steps == 30


def test_map_id_round_trips() -> None:
    for map_id in BUILTIN_IDS:
        assert map_id_for(world_config_for(map_id)) == map_id

    from src.the_curved_world.manifold import DeformedTorus

    custom_surface = DeformedTorus(ring_radius=9.0)
    custom = WorldConfig(
        domain=custom_surface.domain,
        surface=custom_surface,
        min_separation=5.0,
        boundary_margin=0.0,
        detector_scale=5.0,
    )
    assert map_id_for(custom) == "custom"


def test_register_map_decorator_extends_the_registry() -> None:
    @register_map(
        map_id="test_small_plane",
        name="Test plane",
        description="unit-test map",
        topology=BOUNDED_PLANE,
        placement={"min_separation": 4.0, "boundary_margin": 1.0, "detector_scale": 4.0},
    )
    class SmallPlaneMap:
        def build(self, params):
            from src.the_curved_world.config import default_surface_config

            return SmoothSurface(default_surface_config())

    try:
        assert "test_small_plane" in MapRegistry.ids()
        surface = MapRegistry.create("test_small_plane")
        assert isinstance(surface, SmoothSurface)
        config = world_config_for("test_small_plane")
        assert config.min_separation == pytest.approx(4.0)
        assert config.detector_scale == pytest.approx(4.0)
    finally:
        MapRegistry.unregister("test_small_plane")

    assert "test_small_plane" not in MapRegistry.ids()


def test_registry_rejects_bad_metadata() -> None:
    with pytest.raises(ConfigError):
        MapRegistry.register(
            MapMetadata(id="", name="x", description="x", topology=CLOSED_PERIODIC, factory=lambda params: None)
        )
    with pytest.raises(ConfigError):
        MapRegistry.register(
            MapMetadata(id="bad_topology", name="x", description="x", topology="mobius", factory=lambda params: None)
        )
    with pytest.raises(ConfigError):
        MapRegistry.register(
            MapMetadata(id="bad_factory", name="x", description="x", topology=CLOSED_PERIODIC, factory="nope")
        )