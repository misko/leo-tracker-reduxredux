import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from local_future_0057 import changes
from local_future_witness import census
from local_future_transfer_figure import necessary_fraction


def test_owner_audit_counts_displaced_rows_and_rejects_ambiguous_labels():
    old = [["one", 1, "conditional"], ["two", 2, "predictive"]]
    new = [["one", 1, "predictive"], ["three", 2, "conditional"]]
    assert changes(old, new) == dict(before=2, after=2, lost=1, added=1, changed=1)
    with pytest.raises(ValueError):
        changes(old, new + [new[0]])


def test_full_receiver_silence_and_disagreement_are_counted_separately():
    factor = dict(candidate_rank=0, integer_epoch_sample=12, fractional_epoch_offset_samples=0.,
                  fractional_tracking_cfo_hz=100.)
    evidence = census({"a": (1, "conditional"), "b": (2, "predictive")}, {"a": 4},
                      {"a": (factor, factor), "b": (factor, None)})
    assert evidence["stock_other_satellite"] == evidence["stock_unassigned"] == 1
    assert evidence["full_selected"] == evidence["rank_zero_time_cfo_match"] == 1


def test_geodesic_fraction_must_satisfy_bounds_from_both_ends():
    assert necessary_fraction(2, 1, 1, 1.5) == (.5, 1.)
    assert necessary_fraction(1, 2, 1, 1.5) == (0., .5)
    assert necessary_fraction(2, 2, 0, 1.5) is None
    assert necessary_fraction(1, 1, 0, 1.5) == (0., 1.)
