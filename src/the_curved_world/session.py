"""Blocking interactive terminal session for The Curved World (Task 5).

The session owns the REPL: it prints a compact status line before each prompt,
reads a command, delegates it to :class:`~src.the_curved_world.cli.GameCLI` and
echoes the result. All input errors are handled by the CLI, so the loop never
raises on bad input or a missing argument. When the game is won the loop stops
and (optionally) holds the render window open instead of closing it.
"""

from __future__ import annotations

from typing import Callable, Optional

from src.the_curved_world.cli import GameCLI

PROMPT = "[CurvedWorld]> "


def run_interactive_session(
    cli: GameCLI,
    *,
    input_func: Callable[[str], str] = input,
    echo: Optional[Callable[[str], None]] = None,
    show_status: bool = True,
    hold_window_on_victory: bool = True,
) -> None:
    """Run the blocking interactive play loop for ``cli``.

    ``input_func`` and ``echo`` can be replaced in tests to simulate an input
    stream and capture the transcript without a terminal or a GUI.
    """
    write = cli.echo if echo is None else echo

    write("The Curved World - interactive session")
    write("type 'help' for commands, 'quit' to exit")

    while cli.running:
        if show_status:
            write(cli.status_line())
        try:
            line = input_func(PROMPT)
        except (EOFError, KeyboardInterrupt):
            write("")
            break

        output = cli.handle(line)
        if output:
            write(output)

        if cli.game.won:
            write("Exit found - session complete.")
            if hold_window_on_victory:
                cli.hold_window()
            break

    cli.close_window()