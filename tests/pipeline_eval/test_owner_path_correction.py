"""Unit coverage for the saved signed-path diagnostic."""

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from owner_path_correction import CFO, MEASUREMENTS, SAMPLE_RATE, exact_changes, geographic_score, group_readout, pieces, proposals


def lane(t, cfo, *, short=True, radio=0, epoch=0):
    factor = {CFO: cfo, "integer_epoch_sample": epoch, "fractional_epoch_offset_samples": 0}
    return dict(counter=t*SAMPLE_RATE, radio=radio, short=short, factor=factor,
                row=dict(edge="lower", channel=2, actual_rf_hz=11_000_000_000))


def test_proposal_uses_two_anchors_but_leaves_middle_anchor_out():
    b = {"a": lane(0, -800., short=False), "b": lane(2, -600., short=False),
         "c": lane(4, -400., short=False), "target": lane(3, -570.),
         "too_far": lane(4.1, -750.), "too_late": lane(15, 10.)}
    assert list(pieces(b, b)) == [["a", "b", "target", "c", "too_far"], ["too_late"]]
    assert proposals({"track": list(b)}, b) == {"b": 0., "target": 35.}


def test_correction_scores_same_support_and_distinguishes_unmatched_owner():
    a = {"start": lane(0, 0, short=False), "end": lane(4, 40, short=False),
         "one": lane(1, 10), "two": lane(2, 20), "three": lane(3, 30), "other": lane(3.5, 35, epoch=3)}
    b = dict(a, one=lane(1, 110), two=lane(2, -80), three=lane(3, 130), other=lane(3.5, 25))
    owners = {key: (42, "conditional") for key in a}
    result = group_readout(owners, owners, a, b)
    assert result["counts"]["strict_short"] == 3
    assert result["counts"]["short_disagree"] == 1
    assert result["outside_strict_shared_short"] == 1
    assert result["correction"]["centered_loss_gain"] == pytest.approx(.75)
    assert result["correction"]["corrected_centered_rms_hz"] == pytest.approx(
        result["correction"]["centered_rms_hz"] / 2)
    assert not result["correction"]["qualifies"]  # Three favorable points never clear enrollment.


def test_changed_role_contributes_time_union_instead_of_false_overlap():
    a = {"start": lane(0, 4), "middle": lane(1, 25), "end": lane(2, 79)}
    left = {key: (42, "conditional") for key in a}
    right = dict(left, end=(42, "predictive"))
    result = group_readout(left, right, a, a)
    assert result["counts"]["shared_changed_role"] == 1
    assert result["counts"]["strict_short"] == 2
    assert result["interval_seconds"] == [2., 1., 1.]
    assert result["interval_jaccard_loss"] == .5


def test_intervention_counts_a_restored_owner_only_if_exact_row_matches():
    before = {"a": lane(0, 4), "b": lane(1, 2)}
    sparse = dict(before, a=lane(0, 5))
    masked = dict(sparse, a=lane(0, 4))
    old = {"a": (42, "conditional"), "b": (42, "conditional")}
    mixed = {"b": (42, "conditional")}
    assert exact_changes(before, sparse, masked, old, mixed, old) == dict(
        changed_winners=1, changed_now_owned=1, restored_stock_owner=1, restored_with_exact_stock_tuple=1)


def test_archived_geography_join_refuses_unsealed_receiver_features(tmp_path):
    feature = MEASUREMENTS / "owner-path-correction-features.json"
    archived = geographic_score(feature)
    assert not archived["advances"]
    assert archived["receiver_effect_m"]["DS30-0220"]["fitted_c"]["charted"] > 1_000
    unsealed = tmp_path / feature.name
    unsealed.write_bytes(feature.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="Sealed input differs"):
        geographic_score(unsealed)
