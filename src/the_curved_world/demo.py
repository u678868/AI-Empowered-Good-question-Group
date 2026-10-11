"""Reproducible, non-interactive demo scenario for The Curved World (Task 4).

The demo follows the ordinary gameplay rules: it starts a world from a fixed
seed, takes real detector readings, moves and compares, places markers, measures
between markers, and finally reaches the exit. The final approach is *steered*
by the developer view (a controlled test), but every detector reading printed is
a genuine reading -- nothing is faked or altered, and the detector is never made
to reveal the distance.
"""

from __future__ import annotations

from typing import Callable, Dict

from src.the_curved_world.config import default_config
from src.the_curved_world.gameplay import ExplorationGame
from src.the_curved_world.world import WorldGenerator

DEFAULT_DEMO_SEED = 12345


def _reading_text(observation) -> str:
    return f"signal={observation.signal:.4f} ({observation.label}) [{observation.trend}]"


def run_demo(
    seed: int = DEFAULT_DEMO_SEED,
    *,
    world_config=None,
    echo: Callable[[str], None] = print,
    max_approach_steps: int = 600,
) -> Dict[str, object]:
    """Run the reproducible demo and return ``{"won": bool, "summary": GameSummary}``."""
    config = default_config() if world_config is None else world_config
    world = WorldGenerator(config).generate(seed)
    game = ExplorationGame(world)
    developer = world.debug_view()

    def say(text: str = "") -> None:
        echo(text)

    say(f"=== The Curved World - reproducible demo (seed={seed}, map={world.surface.name}) ===")
    say("Rules: the player sees ONLY the detector signal; the detector uses ambient Euclidean distance.")

    say("")
    say("[1] start the world")
    say(f"    start (x, y) = ({game.position[0]:.3f}, {game.position[1]:.3f})")
    say(f"    read         -> {_reading_text(game.read_detector('initial reading'))}")

    say("")
    say("[2] move and compare the signal")
    for index, (dx, dy) in enumerate(((1.0, 0.45), (0.4, 1.0), (-0.6, 0.8)), start=1):
        game.move(dx, dy)
        reading = game.read_detector()
        say(f"    move {index}: ({game.position[0]:.3f}, {game.position[1]:.3f}) -> {_reading_text(reading)}")

    say("")
    say("[3] place markers and keep exploring")
    marker = game.place_marker("P1")
    say(f"    marker P1 at ({marker.position[0]:.3f}, {marker.position[1]:.3f}) signal={marker.signal:.4f} ({marker.label})")
    game.move(1.0, -0.7)
    marker = game.place_marker("P2")
    say(f"    marker P2 at ({marker.position[0]:.3f}, {marker.position[1]:.3f}) signal={marker.signal:.4f} ({marker.label})")

    say("")
    say("[4] measurement probe between two player-known markers")
    distance = game.distance_between_markers("P1", "P2")
    say(f"    distance(P1, P2) = {distance:.4f}  (straight-line 3D ambient Euclidean distance)")

    say("")
    say("[5] controlled approach to the exit (steered by the developer view; only real readings shown)")
    for step in range(1, max_approach_steps + 1):
        if game.won:
            break
        exit_x, exit_y = developer.exit
        player_x, player_y = game.position
        game.move(exit_x - player_x, exit_y - player_y)
        if step % 2 == 1:
            say(f"    step {step:>3}: ({game.position[0]:.3f}, {game.position[1]:.3f}) -> {_reading_text(game.read_detector())}")

    won = game.won
    summary = game.summary()

    say("")
    if won:
        say("[6] victory")
        say(f"    observations = {summary.observations}")
        say(f"    markers      = {summary.markers}")
        say(f"    steps        = {summary.steps}")
        say(f"    elapsed time = {summary.elapsed_time:.2f} s")
        say(f"    seed         = {summary.seed}")
        say(f"    replay with: python -m src.main --seed {summary.seed}")
    else:
        say("[6] FAILED to reach the exit within the step budget")

    return {"won": won, "summary": summary}