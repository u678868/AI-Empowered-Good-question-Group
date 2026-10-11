"""Command-driven terminal interface for The Curved World.

The interface owns no game rules: it only translates typed commands into calls
on :class:`~src.the_curved_world.gameplay.ExplorationGame` and formats the
result. Keeping it thin means the same engine can later be driven by a
Matplotlib/3D renderer.
"""

from __future__ import annotations

import math
import shlex
from typing import Callable, List, Optional

from src.the_curved_world.config import ConfigError, WorldConfig, default_config
from src.the_curved_world.gameplay import ExplorationGame, GameError, GameplayConfig, MoveResult
from src.the_curved_world.observations import ObservationConfig, PlayerObservation
from src.the_curved_world.world import WorldGenerator

DEFAULT_SEED = 12345

HELP_TEXT = """The Curved World - commands
  move <dx> <dy>   Move one fixed step in direction (dx, dy); direction is normalised
  w | a | s | d    Quick move one step: w=+y  s=-y  a=-x  d=+x
  scan [note]      Take a detector reading in place (alias: read)
  mark <name>      Place a named marker at the current position
  markers          List placed markers
  log              Show the exploration log
  measure <a> <b>  Ambient (straight-line 3D) distance between two markers
  curvature        Gaussian curvature at the current position (analytic)
  status           Show position, steps and observation count
  seed <n>         Restart with the given seed
  new [seed]       Start a new world (random seed unless one is given)
  view <mode>      Switch the rendered view: player | debug
  help             Show this help
  quit | exit      Quit
"""

_TREND_TEXT = {
    "first": "first reading",
    "up": "signal increased",
    "down": "signal decreased",
    "same": "signal unchanged",
}


class GameCLI:
    """Line-oriented command interface over :class:`ExplorationGame`."""

    def __init__(
        self,
        world_config: WorldConfig | None = None,
        gameplay_config: GameplayConfig | None = None,
        observation_config: ObservationConfig | None = None,
        *,
        echo: Callable[[str], None] = print,
        seed: Optional[int] = DEFAULT_SEED,
    ) -> None:
        self._world_config = default_config() if world_config is None else world_config
        self._generator = WorldGenerator(self._world_config)
        self._gameplay_config = GameplayConfig() if gameplay_config is None else gameplay_config
        self._observation_config = ObservationConfig() if observation_config is None else observation_config
        self._echo = echo
        self._running = True
        self._renderer = None
        self._plot_mode = "player"
        self._mesh_cache = None
        self._game = self._build_game(seed)

    # -- state -------------------------------------------------------------

    @property
    def game(self) -> ExplorationGame:
        return self._game

    @property
    def running(self) -> bool:
        return self._running

    def restart(self, seed: Optional[int]) -> None:
        self._game = self._build_game(seed)

    def _build_game(self, seed: Optional[int]) -> ExplorationGame:
        world = self._generator.generate(seed)
        return ExplorationGame(world, self._gameplay_config, self._observation_config)

    # -- command handling --------------------------------------------------

    def handle(self, line: str) -> str:
        """Handle one command line and return the text to display."""
        text = (line or "").strip()
        if not text:
            return ""
        try:
            parts = shlex.split(text)
        except ValueError as exc:
            return f"error: {exc}"
        if not parts:
            return ""
        command = parts[0].lower()
        rest = text[len(parts[0]):].strip()
        try:
            output = self._dispatch(command, parts[1:], rest)
        except (GameError, ConfigError) as exc:
            return f"error: {exc}"
        self._refresh_view()
        return output

    def attach_renderer(self, renderer, mode: str = "player") -> None:
        """Attach a Matplotlib-style renderer that is refreshed after each command."""
        from src.the_curved_world.render import SurfaceMeshCache

        self._renderer = renderer
        self._plot_mode = mode
        self._mesh_cache = SurfaceMeshCache()
        self._refresh_view()

    @property
    def plot_mode(self) -> str:
        return self._plot_mode

    def _refresh_view(self) -> None:
        if self._renderer is None:
            return
        from src.the_curved_world.render import build_scene

        scene = build_scene(self._game, self._plot_mode, mesh_cache=self._mesh_cache)
        self._renderer.render(scene)
        pause = getattr(self._renderer, "pause", None)
        if callable(pause):
            pause(0.001)

    @property
    def echo(self) -> Callable[[str], None]:
        return self._echo

    def status_line(self) -> str:
        """Compact one-line status: position, latest reading/trend, step count."""
        game = self._game
        x, y = game.position
        z = game.player_view.position((x, y))[2]
        observation = game.peek_detector()
        return (
            f"[status] (x,y,z)=({x:.3f}, {y:.3f}, {z:.3f})  "
            f"signal={observation.signal:.4f} ({observation.label}, {_TREND_TEXT[observation.trend]})  "
            f"steps={game.steps}"
        )

    def hold_window(self) -> None:
        """Keep the render window open (post-victory display)."""
        hold = getattr(self._renderer, "hold", None)
        if callable(hold):
            hold()

    def close_window(self) -> None:
        """Close the render window (on quit)."""
        close = getattr(self._renderer, "close", None)
        if callable(close):
            close()

    def run(self) -> None:
        """Run the blocking interactive session (see src.the_curved_world.session)."""
        from src.the_curved_world.session import run_interactive_session

        run_interactive_session(self)

    # -- dispatch ----------------------------------------------------------

    def _dispatch(self, command: str, args: List[str], rest: str) -> str:
        game = self._game
        if command in ("help", "?"):
            return HELP_TEXT
        if command in ("quit", "exit"):
            self._running = False
            return "bye"
        if command in ("w", "up", "n", "north"):
            return self._render_move(game.move(0.0, 1.0))
        if command in ("s", "down", "south"):
            return self._render_move(game.move(0.0, -1.0))
        if command in ("d", "right", "e", "east"):
            return self._render_move(game.move(1.0, 0.0))
        if command in ("a", "left", "west"):
            return self._render_move(game.move(-1.0, 0.0))
        if command == "move":
            if len(args) != 2:
                return "usage: move <dx> <dy>"
            return self._render_move(game.move(self._float(args[0], "dx"), self._float(args[1], "dy")))
        if command in ("read", "scan"):
            return self._render_observation(game.read_detector(rest or None))
        if command == "mark":
            if len(args) != 1:
                return "usage: mark <name>"
            marker = game.place_marker(args[0])
            return (
                f"marker {marker.name!r} placed at "
                f"({marker.position[0]:.3f}, {marker.position[1]:.3f}) "
                f"signal={marker.signal:.4f} ({marker.label})"
            )
        if command in ("markers", "marker"):
            return self._render_markers()
        if command == "log":
            return self._render_log()
        if command == "measure":
            if len(args) != 2:
                return "usage: measure <marker_a> <marker_b>"
            distance = game.distance_between_markers(args[0], args[1])
            return (
                f"straight-line 3D distance between {args[0]!r} and {args[1]!r} = {distance:.4f} "
                "(ambient Euclidean distance, not a path length along the surface)"
            )
        if command == "view":
            if len(args) != 1 or args[0].lower() not in ("player", "debug"):
                return "usage: view player|debug"
            self._plot_mode = args[0].lower()
            if self._renderer is None:
                return (
                    f"view mode set to {self._plot_mode} "
                    "(no renderer attached; start with --render to see it)"
                )
            return f"view mode set to {self._plot_mode}"
        if command == "curvature":
            return f"Gaussian curvature at the current position: K = {game.curvature():.6f} (analytic)"
        if command == "status":
            return self._render_status()
        if command == "seed":
            if len(args) != 1:
                return "usage: seed <n>"
            seed = self._int(args[0], "seed")
            self.restart(seed)
            return f"restarted with seed {seed}"
        if command == "new":
            if len(args) > 1:
                return "usage: new [seed]"
            seed = self._int(args[0], "seed") if args else None
            self.restart(seed)
            return f"new world with seed {self._game.summary().seed}"
        return f"error: unknown command {command!r}; type 'help'"

    # -- rendering ---------------------------------------------------------

    def _render_move(self, result: MoveResult) -> str:
        x, y = result.position
        height = self._game.player_view.position((x, y))[2]
        flags = " [boundary: clamped to domain]" if result.clamped else ""
        line = f"moved to ({x:.3f}, {y:.3f}), z={height:.3f}{flags}"
        if result.won:
            return line + "\n" + self._render_victory()
        return line

    def _render_observation(self, observation: PlayerObservation) -> str:
        return f"detector: signal={observation.signal:.4f} ({observation.label}) - {_TREND_TEXT[observation.trend]}"

    def _render_markers(self) -> str:
        markers = self._game.markers
        if not markers:
            return "no markers placed"
        lines = ["markers:"]
        for marker in markers:
            lines.append(
                f"  {marker.name}: ({marker.position[0]:.3f}, {marker.position[1]:.3f}) "
                f"signal={marker.signal:.4f} ({marker.label})"
            )
        return "\n".join(lines)

    def _render_log(self) -> str:
        entries = self._game.log
        if not entries:
            return "log is empty"
        lines = ["#    position            signal   label      trend   note"]
        for entry in entries:
            note = entry.note or ""
            lines.append(
                f"{entry.index:<4} ({entry.position[0]:7.3f},{entry.position[1]:7.3f})  "
                f"{entry.signal:6.4f}  {entry.label:<9}  {entry.trend:<6}  {note}"
            )
        return "\n".join(lines)

    def _render_status(self) -> str:
        game = self._game
        x, y = game.position
        height = game.player_view.position((x, y))[2]
        lines = [
            f"position=({x:.3f}, {y:.3f}) z={height:.3f}  steps={game.steps}  "
            f"time={game.elapsed_time:.2f}s  markers={len(game.markers)}  observations={len(game.log)}"
        ]
        if game.won:
            lines.append(self._render_victory())
        return "\n".join(lines)

    def _render_victory(self) -> str:
        summary = self._game.summary()
        return (
            "*** EXIT FOUND ***\n"
            f"  observations: {summary.observations}\n"
            f"  markers: {summary.markers}\n"
            f"  steps: {summary.steps}\n"
            f"  elapsed time: {summary.elapsed_time:.2f} s\n"
            f"  seed: {summary.seed}   (use `seed {summary.seed}` to replay)"
        )

    # -- parsing helpers ---------------------------------------------------

    @staticmethod
    def _float(text: str, name: str) -> float:
        try:
            value = float(text)
        except (TypeError, ValueError):
            raise GameError(f"{name} must be a number, got {text!r}")
        if not math.isfinite(value):
            raise GameError(f"{name} must be finite, got {text!r}")
        return value

    @staticmethod
    def _int(text: str, name: str) -> int:
        try:
            return int(text)
        except (TypeError, ValueError):
            raise GameError(f"{name} must be an integer, got {text!r}")