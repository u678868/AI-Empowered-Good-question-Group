"""Command-line entry point for The Curved World."""

from __future__ import annotations

import argparse
from typing import Sequence

from src.the_curved_world.cli import GameCLI
from src.the_curved_world.config import default_config
from src.the_curved_world.maps import DEFAULT_MAP_ID, MapRegistry, world_config_for
from src.the_curved_world.world import WorldGenerator


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="the-curved-world",
        description="The Curved World - exploration prototype.",
    )
    parser.add_argument("--seed", type=int, default=12345, help="world seed (default: 12345)")
    parser.add_argument(
        "--map",
        choices=MapRegistry.ids(),
        default=DEFAULT_MAP_ID,
        help="registered map to build (default: %(default)s)",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="print a developer summary and exit instead of playing interactively",
    )
    parser.add_argument(
        "--demo-scenario",
        action="store_true",
        help="run the reproducible demo scenario (default seed 12345) and exit",
    )
    parser.add_argument(
        "--serve",
        action="store_true",
        help="serve the web UI and local JSON API (Task 6)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="web server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="web server port (default: 8000)")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable the privileged /api/state/debug endpoint (web)",
    )
    parser.add_argument(
        "--play",
        action="store_true",
        help="start the interactive play session with a live 3D view",
    )
    parser.add_argument(
        "--render",
        action="store_true",
        help="open a Matplotlib 3D view that updates after each command",
    )
    parser.add_argument(
        "--view",
        choices=["player", "debug"],
        default="player",
        help="view shown by the renderer (default: player)",
    )
    args = parser.parse_args(argv)
    world_config = world_config_for(args.map)

    if args.demo:
        world = WorldGenerator(world_config).generate(args.seed)
        debug = world.debug_view()
        print(f"[curved-world] seed = {debug.seed}")
        print(f"  start (x, y)          = ({debug.start[0]:.4f}, {debug.start[1]:.4f})")
        print(f"  exit  (x, y)          = ({debug.exit[0]:.4f}, {debug.exit[1]:.4f})  (developer view only)")
        print(f"  true distance s->exit = {debug.distance_to_exit(debug.start):.4f}")
        print("NOTE: the detector reports only the signal; distance and exit are developer-only.")
        return 0

    if args.serve:
        from src.the_curved_world.server import serve

        serve(seed=args.seed, host=args.host, port=args.port, debug=args.debug, map_id=args.map)
        return 0

    if args.demo_scenario:
        from src.the_curved_world.demo import run_demo

        result = run_demo(args.seed, world_config=world_config)
        return 0 if result["won"] else 1

    cli = GameCLI(world_config, seed=args.seed)
    if args.render or args.play:
        from src.the_curved_world.render import MatplotlibRenderer

        cli.attach_renderer(MatplotlibRenderer(), mode=args.view)
    cli.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())