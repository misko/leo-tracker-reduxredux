import importlib.util
import sys
from pathlib import Path

import numpy as np
import pytest

from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction

ROOT = Path(__file__).parents[2]


def _load(name: str):
    path = ROOT / "tools" / "research" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"test_{name}", path)
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


HOLDOUT = _load("day_frozen_position_holdout")
REPLICATION = _load("day_position_replication")


def _prediction(measured, predicted, *, candidates=("10", "20"), visible=None):
    measured = np.asarray(measured, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    count = len(measured)
    return AdaptiveTrackPrediction(
        "track",
        tuple(f"observation-{index}" for index in range(count)),
        np.arange(count, dtype=float),
        measured,
        np.asarray([True, False, True, False, True, False, True, False]),
        np.asarray(candidates),
        np.asarray([-1.0, 0.0, 1.0]),
        predicted,
        np.ones(len(candidates), dtype=bool) if visible is None else np.asarray(visible),
    )


def test_training_rows_recovers_injected_candidate_tau_and_cfo():
    base = np.array([1.0, 4.0, 9.0, 16.0, 25.0, 36.0, 49.0, 64.0])
    predictions = np.empty((2, 3, len(base)))
    predictions[0] = np.stack((base[::-1] + 20, np.sqrt(base) * 30, base**1.2))
    predictions[1] = np.stack((base[::-1], base * 0.5, base))
    measured = predictions[1, 2] + 1234.5

    winner = HOLDOUT.training_rows(_prediction(measured, predictions), top_k=1)[0]

    assert winner["candidate_id"] == "20"
    assert winner["tau_s"] == 1.0
    assert winner["offset_hz"] == pytest.approx(1234.5)
    assert winner["training_rms_hz"] == pytest.approx(0.0, abs=1e-12)


def test_evaluation_frequency_perturbation_cannot_change_training_choice():
    rng = np.random.default_rng(1923)
    predictions = rng.normal(size=(3, 3, 8))
    measured = predictions[2, 1] + 77.0
    original = _prediction(measured, predictions, candidates=("10", "20", "30"))
    changed = measured.copy()
    changed[~original.training_mask] = np.array([1e9, -2e9, 3e9, -4e9])

    assert HOLDOUT.training_rows(original, 5) == HOLDOUT.training_rows(
        _prediction(changed, predictions, candidates=("10", "20", "30")), 5
    )


def test_chunked_merge_matches_one_batch_global_ranking_with_deterministic_ties():
    measured = np.arange(8, dtype=float)
    # 10 and 20 deliberately tie; candidate ID is the documented merge tie-break.
    predicted = np.stack([np.stack((measured, measured + 5, measured + 9)) for _ in range(4)])
    candidates = ("10", "20", "30", "40")
    whole = HOLDOUT.training_rows(_prediction(measured, predicted, candidates=candidates), 6)
    merged = []
    for begin, stop in ((0, 2), (2, 4)):
        chunk = _prediction(measured, predicted[begin:stop], candidates=candidates[begin:stop])
        merged = HOLDOUT._merge_top(merged, HOLDOUT.training_rows(chunk, 6), 6)

    expected = sorted(
        whole,
        key=lambda row: (row["training_rms_hz"], row["candidate_id"], row["tau_s"]),
    )[:6]
    assert merged == expected
    assert [(row["candidate_id"], row["tau_s"]) for row in merged[:3]] == [
        ("10", -1.0),
        ("10", 0.0),
        ("10", 1.0),
    ]


def test_all_invisible_candidates_produce_no_fabricated_match():
    measured = np.arange(8, dtype=float)
    predicted = np.zeros((2, 3, 8))
    assert (
        HOLDOUT.training_rows(
            _prediction(measured, predicted, visible=np.zeros((2, 3), dtype=bool)), 8
        )
        == []
    )


def test_replication_groups_accept_disjoint_groups_and_reject_duplicates():
    assert REPLICATION._groups(
        {
            "groups": [
                {"group_id": "a", "session_ids": ["s1", "s2"]},
                {"group_id": "b", "session_ids": ["s3"]},
            ]
        }
    ) == [
        {"group_id": "a", "session_ids": ["s1", "s2"]},
        {"group_id": "b", "session_ids": ["s3"]},
    ]
    with pytest.raises(ValueError, match="unique and disjoint"):
        REPLICATION._groups({"groups": [{"session_ids": ["s1", "s1"]}]})
    with pytest.raises(ValueError, match="unique and disjoint"):
        REPLICATION._groups({"groups": [{"session_ids": ["s1"]}, {"session_ids": ["s1"]}]})
