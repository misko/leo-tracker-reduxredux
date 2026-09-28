from copy import deepcopy
from pathlib import Path
import importlib.util
import sys

import numpy as np
import pytest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("confirmation_reception_sensitivity", HERE / "reception_sensitivity.py")
SENSITIVITY = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = SENSITIVITY
SPEC.loader.exec_module(SENSITIVITY)

ROBUST_SPEC = importlib.util.spec_from_file_location(
    "confirmation_robust_core", HERE.parent / "2026_09_27_roof_location_geometry/robust_core.py"
)
ROBUST = importlib.util.module_from_spec(ROBUST_SPEC)
assert ROBUST_SPEC.loader
sys.modules[ROBUST_SPEC.name] = ROBUST
ROBUST_SPEC.loader.exec_module(ROBUST)


def row(anchor, pair, matched, observation):
    return {"anchor_key": anchor, "physical_pair_key": pair, "matched": matched,
            "observation_index": observation, "detection_logit_east0": 0.,
            "detection_east_slope": 1., "ratio_mean_east0": 0.,
            "ratio_east_slope": 1.,
            "log_margin_ratio_rx1_rx0": 0. if matched else None}


def receipt(track, anchor, pair, receiver, matched):
    return {"track_id": track, "observation_id": anchor, "anchor_key": anchor,
            "physical_pair_key": pair, "receiver_id": receiver, "matched": matched}


def test_dedup_prefers_rx0_then_lexical_and_preserves_unmatched_and_tracks():
    reception = {
        "a": [row("z-rx1", "pair", True, 1), row("unmatched", None, False, 2)],
        "b": [row("b-rx0", "pair", True, 1)],
        "empty": [],
    }
    receipts = [receipt("a", "z-rx1", "pair", "rx1", True),
                receipt("a", "unmatched", None, "rx0", False),
                receipt("b", "b-rx0", "pair", "rx0", True)]
    original = deepcopy(reception)
    result, accounting = SENSITIVITY.deduplicate_matched_physical_pairs(reception, receipts)
    assert reception == original
    assert [item["anchor_key"] for item in result["a"]] == ["unmatched"]
    assert [item["anchor_key"] for item in result["b"]] == ["b-rx0"]
    assert result["empty"] == []
    assert accounting["removed_duplicate_matched_rows"] == 1
    assert accounting["unmatched_rows_preserved"] == 1
    assert accounting["tracks_empty_after_deduplication"] == ["empty"]


def test_same_receiver_tie_break_is_lexical():
    reception = {"t": [row("z", "p", True, 1), row("a", "p", True, 2)]}
    receipts = [receipt("t", "z", "p", "rx1", True),
                receipt("t", "a", "p", "rx1", True)]
    result, _ = SENSITIVITY.deduplicate_matched_physical_pairs(reception, receipts)
    assert [item["anchor_key"] for item in result["t"]] == ["a"]


def joint_inputs():
    predicted = np.array([[0., 0., 0.], [0., 10., 10.]])
    east = np.array([[-1., -1., -1.], [1., 1., 1.]])
    measured = np.zeros(3)
    train = np.array([True, False, False])
    shortlist = {"candidate_indices": [0, 1], "profiled_cfo_hz": [0., 0.],
                 "log_weights": [-np.log(2), -np.log(2)],
                 "scale_hz": 100., "degrees_of_freedom": 2.}
    return predicted, east, measured, train, shortlist


def test_zero_reception_recovers_d_and_keeps_full_reserve_denominator():
    args = joint_inputs()
    result = ROBUST.joint_heldout_score(*args, [], ratio_variance=1.)
    assert result["reserve_observations"] == 2
    assert result["reception_observations"] == 0
    assert result["scores"]["D_plus_detection"] == pytest.approx(result["scores"]["D"])
    assert result["scores"]["D_plus_geometry"] == pytest.approx(result["scores"]["D"])


def test_removing_duplicate_changes_only_rx_evidence_not_frequency_data():
    args = joint_inputs()
    rows = [row("rx0", "pair", True, 1), row("rx1", "pair", True, 2)]
    receipts = [receipt("t", "rx0", "pair", "rx0", True),
                receipt("t", "rx1", "pair", "rx1", True)]
    deduplicated, accounting = SENSITIVITY.deduplicate_matched_physical_pairs(
        {"t": rows}, receipts
    )
    full = ROBUST.joint_heldout_score(*args, rows, ratio_variance=1.)
    reduced = ROBUST.joint_heldout_score(*args, deduplicated["t"], ratio_variance=1.)
    assert accounting["removed_duplicate_matched_rows"] == 1
    assert reduced["reserve_observations"] == full["reserve_observations"] == 2
    assert reduced["scores"]["D"] == pytest.approx(full["scores"]["D"])
    assert reduced["candidate_frequency_log_likelihood"] == pytest.approx(
        full["candidate_frequency_log_likelihood"]
    )
    assert reduced["map_heldout_rms_hz"] == pytest.approx(full["map_heldout_rms_hz"])


def test_bad_receipt_fails_closed():
    with pytest.raises(ValueError, match="matching endpoint"):
        SENSITIVITY.deduplicate_matched_physical_pairs(
            {"t": [row("missing", None, False, 1)]}, []
        )
