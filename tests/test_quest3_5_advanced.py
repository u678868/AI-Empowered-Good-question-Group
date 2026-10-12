"""Tasks 21-23: holonomy, parabolic seam and homotopy-loop quest tests."""

from __future__ import annotations

import math

import numpy as np

from src.the_curved_world.differential import loop_polygon, parallel_transport_polyline
from src.the_curved_world.manifold import wrap_parameter
from src.the_curved_world.maps import world_config_for
from src.the_curved_world.quest import (
    HolonomyMeasurement,
    HolonomyQuest,
    HomotopyLoopQuest,
    HomotopyMeasurement,
    ParabolicLineQuest,
    ParabolicMeasurement,
    QuestManager,
)
from src.the_curved_world.scanner import metric_length, scan_manifold
from src.the_curved_world.server import GameSession


def _features():
    return scan_manifold(world_config_for("torus_genus1").surface, genus_hint=1)


def _short_metric(surface, first, second) -> float:
    first_uv = (float(first[0]), float(first[1]))
    second_uv = (float(second[0]), float(second[1]))
    du = wrap_parameter(second_uv[0] - first_uv[0])
    dv = wrap_parameter(second_uv[1] - first_uv[1])
    return metric_length(surface, first_uv, (first_uv[0] + du, first_uv[1] + dv))


def _parabolic_points(surface, features, count: int = 3):
    candidates = []
    for u in np.linspace(-math.pi, math.pi, 81, endpoint=False):
        for v in np.linspace(-math.pi, math.pi, 81, endpoint=False):
            curvature = abs(float(surface.gaussian_curvature(u, v)))
            if curvature <= features.parabolic_tolerance:
                candidates.append((curvature, float(u), float(v)))
    candidates.sort()
    selected = []
    for curvature, u, v in candidates:
        if all(_short_metric(surface, (u, v), (other_u, other_v)) >= features.parabolic_min_distance
               for _, other_u, other_v in selected):
            selected.append((curvature, u, v))
            if len(selected) == count:
                return selected
    raise AssertionError("could not construct three separated parabolic points")


def test_scanner_filters_topology_and_exposes_loose_bands() -> None:
    torus = _features()
    ellipsoid = scan_manifold(world_config_for("ellipsoid_genus0").surface, genus_hint=0)
    assert HolonomyQuest().is_applicable(torus) is True
    assert HolonomyQuest().target_value(torus) >= math.radians(20.0)
    assert ParabolicLineQuest().is_applicable(torus) is True
    assert HomotopyLoopQuest().is_applicable(torus) is True
    # genus 0 is strictly excluded even though numerical sampling shows two signs
    assert ParabolicLineQuest().is_applicable(ellipsoid) is False
    assert HomotopyLoopQuest().is_applicable(ellipsoid) is False
    assert torus.parabolic_tolerance <= 0.004
    assert torus.homotopy_capture_radius > 0.0


def test_holonomy_transport_completes_the_connection_seal() -> None:
    surface = world_config_for("torus_genus1").surface
    features = _features()
    points = loop_polygon(surface, features.peak, features.holonomy_reference_radius, 12)
    transport = parallel_transport_polyline(surface, points, (1.0, 0.0), samples_per_segment=32)
    measurement = HolonomyMeasurement(
        start_label="A",
        vertex_labels=tuple(f"P{index}" for index in range(len(points))),
        angle=float(transport["angle"]),
        closure_error=0.0,
        vector_start=tuple(transport["vector_start"]),
        vector_end=tuple(transport["vector_end"]),
        steps=int(transport["steps"]),
    )
    result = HolonomyQuest().evaluate(features, measurement)
    assert result.completed is True
    assert result.detail["relic"] == "Connection Seal"
    assert len(result.detail["steps"]) == 5
    assert result.detail["holonomy_degrees"] >= math.degrees(features.holonomy_target_angle)


def test_holonomy_server_flow_calibrates_and_awards_connection_seal() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    features = _features()
    session._game._quest_manager = QuestManager(features, seed=1, quests=[HolonomyQuest()])
    surface = session.game.player_view.surface
    points = loop_polygon(surface, features.peak, features.holonomy_reference_radius, 12)
    names = []
    for index, (u, v) in enumerate(points):
        session.game.sync_position(u, v)
        name = chr(ord("A") + index)
        names.append(name)
        session.tool({"tool": "mark", "name": name})
    calibration = session.tool({"tool": "measure", "mode": "holonomy_calibrate", "targets": [names[0]]})
    assert calibration["calibrated"] is True
    result = session.tool({"tool": "measure", "mode": "holonomy", "targets": names})
    assert result["quest_completed"] is True
    assert result["proof"]["relic"] == "Connection Seal"
    assert session.player_state()["detector_locked"] is False


def test_parabolic_three_pegs_complete_the_singularity_seal() -> None:
    surface = world_config_for("torus_genus1").surface
    features = _features()
    selected = _parabolic_points(surface, features)
    labels = ("P1", "P2", "P3")
    curvatures = tuple(value for value, _u, _v in selected)
    points = [(u, v) for _value, u, v in selected]
    distances = tuple(
        _short_metric(surface, points[i], points[j])
        for i in range(3) for j in range(i + 1, 3)
    )
    result = ParabolicLineQuest().evaluate(
        features,
        ParabolicMeasurement(labels=labels, curvatures=curvatures, pairwise_distances=distances),
    )
    assert result.completed is True
    assert result.detail["valid_pegs"] == 3
    assert result.detail["relic"] == "Singularity Seal"
    assert len(result.detail["steps"]) == 5


def test_homotopy_requires_a_wind_and_a_closed_origin() -> None:
    features = _features()
    quest = HomotopyLoopQuest()
    short = quest.evaluate(
        features,
        HomotopyMeasurement("O", phase_u=math.pi, phase_v=0.0, closure_distance=0.0,
                            capture_radius=features.homotopy_capture_radius),
    )
    assert short.completed is False
    completed = quest.evaluate(
        features,
        HomotopyMeasurement("O", phase_u=2.0 * math.pi, phase_v=0.0, closure_distance=0.0,
                            capture_radius=features.homotopy_capture_radius),
    )
    assert completed.completed is True
    assert completed.detail["relic"] == "Topology Seal"
    assert completed.detail["winding_u"] == 1.0
    assert len(completed.detail["steps"]) == 5


def test_homotopy_wrap_around_through_server_awards_topology_seal() -> None:
    session = GameSession(seed=12345, map_id="torus_genus1", mode="player")
    features = _features()
    session._game._quest_manager = QuestManager(features, seed=1, quests=[HomotopyLoopQuest()])
    session.game.sync_position(0.0, 0.0)
    session.tool({"tool": "mark", "name": "O"})
    for index in range(1, 25):
        session.game.sync_position(wrap_parameter(2.0 * math.pi * index / 24.0), 0.0)
    tracking = session.game.homotopy_state()
    assert tracking["origin_label"] == "O"
    assert abs(tracking["winding_u"]) >= 1.0
    result = session.tool({"tool": "measure", "mode": "homotopy", "origin": "O"})
    assert result["quest_completed"] is True
    assert result["proof"]["relic"] == "Topology Seal"
