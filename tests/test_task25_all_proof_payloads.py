"""Task 25: structured proof payloads for quests 3, 4, and 5."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from src.the_curved_world.quest import (
    HolonomyMeasurement,
    HolonomyQuest,
    HomotopyLoopQuest,
    HomotopyMeasurement,
    ParabolicLineQuest,
    ParabolicMeasurement,
)


def _assert_no_none(value) -> None:
    if value is None:
        raise AssertionError("proof payload contains None")
    if isinstance(value, dict):
        for item in value.values():
            _assert_no_none(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_no_none(item)


def test_holonomy_proof_payload_has_structured_vectors_and_flux() -> None:
    features = SimpleNamespace(
        closed=True,
        curvature_abs_integral=0.10,
        holonomy_reference_angle=math.radians(45.0),
        holonomy_target_angle=math.radians(30.0),
        reference_radius_world=8.0,
    )
    result = HolonomyQuest().evaluate(
        features,
        HolonomyMeasurement(
            start_label="A",
            vertex_labels=("A", "B", "C"),
            angle=math.radians(60.0),
            closure_error=0.0,
            vector_start=(1.0, 0.0),
            vector_end=(0.5, math.sqrt(3.0) / 2.0),
            steps=24,
        ),
    )
    detail = result.detail
    for key in (
        "start_vector",
        "end_vector",
        "holonomy_angle_deg",
        "holonomy_angle_rad",
        "target_angle_deg",
        "area_flux_rad",
        "area_flux_deg",
        "relative_error",
    ):
        assert key in detail
    assert len(detail["start_vector"]) == 2
    assert len(detail["end_vector"]) == 2
    assert detail["holonomy_angle_deg"] == pytest.approx(60.0)
    assert detail["area_flux_deg"] == pytest.approx(45.0)
    assert detail["relative_error"] == pytest.approx((60.0 - 45.0) / 45.0)
    _assert_no_none(detail)


def test_parabolic_proof_payload_has_pegs_and_asymptotic_direction() -> None:
    features = SimpleNamespace(parabolic_tolerance=0.004, parabolic_min_distance=2.0)
    result = ParabolicLineQuest().evaluate(
        features,
        ParabolicMeasurement(
            labels=("P1", "P2", "P3"),
            curvatures=(0.0, 0.0, 0.0),
            principal_curvatures=((0.0, -0.20), (0.0, 0.12), (0.0, -0.18)),
            asymptotic_directions=((1.0, 0.0), (0.8, 0.6), (1.0, 0.0)),
            pairwise_distances=(3.0, 3.0, 3.0),
        ),
    )
    detail = result.detail
    assert detail["pegs"] == [
        {"k": 0.0, "kappa1": 0.0, "kappa2": -0.20},
        {"k": 0.0, "kappa1": 0.0, "kappa2": 0.12},
        {"k": 0.0, "kappa1": 0.0, "kappa2": -0.18},
    ]
    assert detail["tolerance_k"] == 0.004
    assert detail["asymptotic_direction"] == [1.0, 0.0]
    assert len(detail["asymptotic_directions"]) == 3
    assert detail["is_parabolic_verified"] is True
    _assert_no_none(detail)


def test_homotopy_proof_payload_has_universal_cover_fields() -> None:
    features = SimpleNamespace(genus=1)
    result = HomotopyLoopQuest().evaluate(
        features,
        HomotopyMeasurement(
            origin_label="O",
            phase_u=2.0 * math.pi,
            phase_v=0.0,
            closure_distance=0.0,
            capture_radius=3.0,
        ),
    )
    detail = result.detail
    for key in (
        "u_start",
        "u_end",
        "delta_u",
        "winding_u",
        "winding_v",
        "genus",
        "fundamental_group",
    ):
        assert key in detail
    assert detail["u_start"] == 0.0
    assert detail["u_end"] == 2.0 * math.pi
    assert detail["delta_u"] == 2.0 * math.pi
    assert detail["winding_u"] == 1.0
    assert detail["winding_v"] == 0.0
    assert detail["genus"] == 1
    assert detail["fundamental_group"] == "Z + Z"
    _assert_no_none(detail)


def test_new_proof_payloads_do_not_leak_exit_or_true_distance() -> None:
    features = SimpleNamespace(
        closed=True,
        curvature_abs_integral=0.10,
        holonomy_reference_angle=math.radians(45.0),
        holonomy_target_angle=math.radians(30.0),
        reference_radius_world=8.0,
    )
    detail = HolonomyQuest().evaluate(
        features,
        HolonomyMeasurement(
            start_label="A",
            vertex_labels=("A", "B", "C"),
            angle=math.radians(60.0),
            vector_start=(1.0, 0.0),
            vector_end=(0.5, math.sqrt(3.0) / 2.0),
            steps=24,
        ),
    ).detail
    text = json.dumps(detail, sort_keys=True)
    assert "exit_position" not in text
    assert "true_distance" not in text
