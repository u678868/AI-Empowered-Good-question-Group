"""Extensible map registry for The Curved World (Task 9/10).

This is a *package* on purpose: dropping a new ``*.py`` file into
``src/the_curved_world/maps/`` is enough to add a map -- no change to the world
generator, the server or the front-end is required.

    from src.the_curved_world.maps import register_map, CLOSED_PERIODIC

    @register_map(
        map_id="my_map",
        name="My Map",
        description="...",
        topology=CLOSED_PERIODIC,
        placement={"min_separation": 5.0, "boundary_margin": 0.0, "detector_scale": 5.0},
    )
    class MyMap:
        def build(self, params):
            return DeformedTorus(ring_radius=12.0)
"""

from __future__ import annotations

import importlib
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.the_curved_world.config import ConfigError, WorldConfig

CLOSED_PERIODIC = "closed_periodic"
BOUNDED_PLANE = "bounded_plane"
TOPOLOGIES = (CLOSED_PERIODIC, BOUNDED_PLANE)

DEFAULT_MAP_ID = "torus_genus1"


class MapNotFound(KeyError):
    """Raised when a map id is not registered."""


@dataclass(frozen=True)
class MapMetadata:
    """Everything the registry and the lobby UI need to know about a map."""

    id: str
    name: str
    description: str
    topology: str
    factory: Callable[[Dict[str, Any]], Any]
    placement: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe view (the callable factory is deliberately omitted)."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "topology": self.topology,
            "periodic": self.topology == CLOSED_PERIODIC,
            "placement": dict(self.placement),
        }


class MapRegistry:
    """Singleton registry of playable maps."""

    _maps: Dict[str, MapMetadata] = {}

    @classmethod
    def register(cls, metadata: MapMetadata) -> MapMetadata:
        if not isinstance(metadata.id, str) or not metadata.id.strip():
            raise ConfigError("MapMetadata.id must be a non-empty string")
        if metadata.topology not in TOPOLOGIES:
            raise ConfigError(f"unknown topology {metadata.topology!r}")
        if not callable(metadata.factory):
            raise ConfigError("MapMetadata.factory must be callable")
        cls._maps[metadata.id] = metadata
        return metadata

    @classmethod
    def get(cls, map_id: str) -> MapMetadata:
        try:
            return cls._maps[map_id]
        except KeyError as exc:
            raise MapNotFound(
                f"unknown map id {map_id!r}; available: {sorted(cls._maps)}"
            ) from exc

    @classmethod
    def unregister(cls, map_id: str) -> None:
        cls._maps.pop(map_id, None)

    @classmethod
    def ids(cls) -> List[str]:
        return sorted(cls._maps)

    @classmethod
    def list_maps(cls) -> List[Dict[str, Any]]:
        return [cls._maps[key].to_dict() for key in sorted(cls._maps)]

    @classmethod
    def create(cls, map_id: str, params: Optional[Dict[str, Any]] = None):
        """Instantiate a map by id. Raises :class:`MapNotFound` for unknown ids."""
        metadata = cls.get(map_id)
        surface = metadata.factory(dict(params or {}))
        if not hasattr(surface, "position") or not hasattr(surface, "domain"):
            raise ConfigError(f"map {map_id!r} factory did not return a surface")
        return surface


def register_map(
    map_id: str,
    name: str,
    description: str,
    topology: str,
    placement: Optional[Dict[str, float]] = None,
):
    """Class/function decorator that registers a map factory.

    A class is expected to expose ``build(self, params)``; a plain function is
    used directly as the factory.
    """

    def decorator(target):
        factory = target().build if inspect.isclass(target) else target
        MapRegistry.register(
            MapMetadata(
                id=map_id,
                name=name,
                description=description,
                topology=topology,
                factory=factory,
                placement=dict(placement or {}),
            )
        )
        return target

    return decorator


# -- discovery -------------------------------------------------------------

def discover() -> List[str]:
    """Import every sibling module so its ``@register_map`` decorators run.

    Returns the module names that were imported. Files whose name starts with an
    underscore are skipped, so helper modules can stay private.
    """
    package_dir = Path(__file__).resolve().parent
    imported: List[str] = []
    for path in sorted(package_dir.glob("*.py")):
        stem = path.stem
        if stem == "__init__" or stem.startswith("_"):
            continue
        module_name = f"{__name__}.{stem}"
        importlib.import_module(module_name)
        imported.append(module_name)
    return imported


# -- helpers ---------------------------------------------------------------

def world_config_for(map_id: str = DEFAULT_MAP_ID) -> WorldConfig:
    """Build a :class:`WorldConfig` for a registered map id."""
    metadata = MapRegistry.get(map_id)
    surface = MapRegistry.create(map_id)
    placement = metadata.placement
    return WorldConfig(
        domain=surface.domain,
        surface=surface,
        min_separation=float(placement.get("min_separation", 12.0)),
        boundary_margin=float(placement.get("boundary_margin", 0.0)),
        detector_scale=float(placement.get("detector_scale", 12.0)),
    )


def map_id_for(config: WorldConfig) -> str:
    """Best-effort reverse lookup of a map id for an existing config."""
    surface = config.surface
    key = getattr(surface, "cache_key", None)
    for candidate_id in MapRegistry.ids():
        try:
            candidate = MapRegistry.create(candidate_id)
        except Exception:  # pragma: no cover - defensive
            continue
        if type(candidate) is type(surface) and getattr(candidate, "cache_key", None) == key:
            return candidate_id
    return "custom"


discover()

__all__ = [
    "BOUNDED_PLANE",
    "CLOSED_PERIODIC",
    "DEFAULT_MAP_ID",
    "MapMetadata",
    "MapNotFound",
    "MapRegistry",
    "TOPOLOGIES",
    "discover",
    "map_id_for",
    "register_map",
    "world_config_for",
]