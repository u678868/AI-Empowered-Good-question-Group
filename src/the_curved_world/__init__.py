"""The Curved World -- a mathematical exploration prototype.

Public API: smooth graph-surface geometry, deterministic world generation, a
distance-sensitive detector, a strict separation between privileged world state
and player-facing observations, the exploration game engine, a terminal
interface and a Matplotlib 3D visualisation layer.
"""

from src.the_curved_world.cli import GameCLI
from src.the_curved_world.config import (
    ConfigError,
    Domain,
    GaussianHill,
    SurfaceConfig,
    WaveComponent,
    WorldConfig,
    default_config,
    default_domain,
    default_surface_config,
)
from src.the_curved_world.detector import Detector, DetectorConfig
from src.the_curved_world.gameplay import (
    ExplorationGame,
    GameError,
    GameplayConfig,
    GameSummary,
    LogEntry,
    Marker,
    MoveResult,
)
from src.the_curved_world.geometry import SmoothSurface, ambient_distance
from src.the_curved_world.observations import (
    ObservationConfig,
    PlayerObservation,
    PlayerObserver,
    PlayerView,
)
from src.the_curved_world.render import (
    MatplotlibRenderer,
    PlotMode,
    RenderConfig,
    Scene,
    SurfaceMeshCache,
    build_scene,
)
from src.the_curved_world.world import DebugView, WorldGenerator, WorldState

__version__ = "0.1.0"

__all__ = [
    "ConfigError",
    "Domain",
    "GaussianHill",
    "SurfaceConfig",
    "WaveComponent",
    "WorldConfig",
    "default_config",
    "default_domain",
    "default_surface_config",
    "Detector",
    "DetectorConfig",
    "SmoothSurface",
    "ambient_distance",
    "ObservationConfig",
    "PlayerObservation",
    "PlayerObserver",
    "PlayerView",
    "DebugView",
    "WorldGenerator",
    "WorldState",
    "ExplorationGame",
    "GameError",
    "GameplayConfig",
    "GameSummary",
    "LogEntry",
    "Marker",
    "MoveResult",
    "GameCLI",
    "MatplotlibRenderer",
    "PlotMode",
    "RenderConfig",
    "Scene",
    "SurfaceMeshCache",
    "build_scene",
    "__version__",
]