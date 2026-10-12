"""Uniform capability contract shared by every playable map.

Map modules own only their surface factory and placement metadata.  All player
features are exposed through this single capability object so the server and
frontend never have to special-case a particular map.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple


@dataclass(frozen=True)
class MapCapabilities:
    """Feature switches for one map (all standard features default to on)."""

    movement: bool = True
    markers: bool = True
    ropes: bool = True
    measurement: bool = True
    circumcircle: bool = True
    quests: bool = True

    @property
    def tools(self) -> Tuple[str, ...]:
        tools = []
        if self.movement:
            tools.append("movement")
        if self.markers:
            tools.append("markers")
        if self.ropes:
            tools.append("ropes")
        if self.measurement:
            tools.append("measurement")
        if self.circumcircle:
            tools.append("circumcircle")
        if self.quests:
            tools.append("quests")
        return tuple(tools)

    def enabled(self, capability: str) -> bool:
        key = str(capability).strip().lower()
        mapping = {
            "move": self.movement,
            "movement": self.movement,
            "mark": self.markers,
            "marker": self.markers,
            "markers": self.markers,
            "rope": self.ropes,
            "ropes": self.ropes,
            "measure": self.measurement,
            "measurement": self.measurement,
            "circumcircle": self.circumcircle,
            "quest": self.quests,
            "quests": self.quests,
        }
        if key not in mapping:
            raise KeyError(f"unknown map capability {capability!r}")
        return bool(mapping[key])

    def to_dict(self) -> Dict[str, object]:
        return {
            "movement": self.movement,
            "markers": self.markers,
            "ropes": self.ropes,
            "measurement": self.measurement,
            "circumcircle": self.circumcircle,
            "quests": self.quests,
            "tools": list(self.tools),
        }


STANDARD_CAPABILITIES = MapCapabilities()

__all__ = ["MapCapabilities", "STANDARD_CAPABILITIES"]
