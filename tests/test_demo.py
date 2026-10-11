"""End-to-end demo and victory integration tests (Task 4)."""

from __future__ import annotations

import math

from src.the_curved_world.config import default_config
from src.the_curved_world.demo import run_demo
from src.the_curved_world.world import WorldGenerator


def test_demo_scenario_reaches_the_exit() -> None:
    transcript: list[str] = []
    result = run_demo(12345, echo=transcript.append)

    assert result["won"] is True
    summary = result["summary"]
    assert summary.seed == 12345
    assert summary.observations >= 1
    assert summary.markers >= 1

    text = "\n".join(transcript)
    assert "[6] victory" in text
    assert "straight-line 3D ambient Euclidean distance" in text


def test_demo_is_reproducible() -> None:
    first = run_demo(12345, echo=lambda _message: None)["summary"]
    second = run_demo(12345, echo=lambda _message: None)["summary"]
    assert first == second


def test_demo_first_reading_matches_the_detector_model() -> None:
    world = WorldGenerator(default_config()).generate(12345)
    developer = world.debug_view()
    expected = math.exp(-developer.distance_to_exit(world.start) / world.detector.config.scale)

    transcript: list[str] = []
    run_demo(12345, echo=transcript.append)

    assert f"{expected:.4f}" in "\n".join(transcript)


def test_demo_transcript_never_prints_the_true_distance_to_the_exit() -> None:
    world = WorldGenerator(default_config()).generate(12345)
    developer = world.debug_view()
    hidden = f"{developer.distance_to_exit(world.start):.4f}"

    transcript: list[str] = []
    run_demo(12345, echo=transcript.append)

    assert hidden not in "\n".join(transcript)