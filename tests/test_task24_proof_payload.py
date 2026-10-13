"""Task 24: structured proof payloads for the interactive proof stage."""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

from src.the_curved_world.quest import (
    BertrandDiquetPuisseuxQuest,
    GaussBonnetQuest,
    RingMeasurement,
    TriangleMeasurement,
)


def test_gauss_bonnet_proof_payload_has_structured_scalars() -> None:
    quest = GaussBonnetQuest()
    features = SimpleNamespace(k_max=0.25, reference_excess=0.40, genus=0)
    result = quest.evaluate(
        features,
        TriangleMeasurement(angle_sum=math.pi + 0.30, markers=("A", "B", "C")),
    )
    detail = result.detail

    assert detail["measured_sum"] == result.achieved
    assert detail["target_sum"] == result.target
    assert detail["excess_rad"] == result.achieved - math.pi
    assert detail["target_excess_rad"] == result.target - math.pi
    assert detail["reference_excess_rad"] == features.reference_excess
    assert detail["relic"] == "Curvature Seal"


def test_bdp_proof_payload_has_structured_scalars() -> None:
    quest = BertrandDiquetPuisseuxQuest()
    features = SimpleNamespace(bdp_ratio_target=0.95, k_max=0.10)
    radius = 2.0
    flat = 2.0 * math.pi * radius
    measurement = RingMeasurement(
        center_label="O",
        vertex_labels=tuple(f"P{index}" for index in range(12)),
        perimeter=0.90 * flat,
        mean_radius=radius,
        flat_perimeter=flat,
        center_curvature=0.125,
        triangle_labels=("A", "B", "C"),
        is_circumcircle=True,
    )
    result = quest.evaluate_ring(features, measurement)
    detail = result.detail

    assert detail["radius"] == radius
    assert detail["flat_perimeter"] == flat
    assert detail["real_perimeter"] == measurement.perimeter
    assert detail["deficit_ratio"] == pytest.approx(0.10)
    assert detail["k_est"] == detail["k_estimate"]
    assert detail["k_exact"] == 0.125
    assert detail["relative_error"] >= 0.0
    assert detail["relic"] == "Metric Seal"