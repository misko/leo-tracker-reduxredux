"""Visit-only selection and paired scoring boundaries."""

from dataclasses import replace

import pytest

from raw_0016_best_trial import check_extent
from raw_band_pair import BAND, select_member, selection
from raw_band_pair_score import paired_error_delta


def test_selection_uses_inclusive_counts_then_lexical_dataset_label():
    rows = [
        dict(id="DS30-0001", windows=385, archived_original=True),
        dict(id="DS30-0003", windows=384, archived_original=True),
        dict(id="DS30-0002", windows=384, archived_original=False),
        dict(id="DS30-0004", windows=511),
        dict(id="DS30-0005", windows=512),
        dict(id="DS30-0006", windows=383),
    ]
    assert [row["id"] for row in select_member(rows, 384, 511)] == [
        "DS30-0002", "DS30-0003", "DS30-0001", "DS30-0004",
    ]
    with pytest.raises(ValueError, match="Invalid visit band or cohort"):
        select_member([rows[0], rows[0]], 384, 511)
    with pytest.raises(ValueError, match="No originals"):
        select_member(rows, 100, 200)


def test_pinned_cohort_selects_one_incomplete_original_and_rejects_substitution():
    result = selection()
    assert result["cohort_size"] == 455
    assert result["eligible"] == [dict(dataset_label="DS30-0306", issued_visits=405)]
    assert result["recording_state"] == "incomplete"
    with pytest.raises(ValueError, match="differs from the visit-count selection"):
        selection(replace(BAND, inputs=replace(BAND.inputs, workload=replace(BAND.inputs.workload, id="DS30-0016"))))


def test_selected_extent_preserves_whole_recording_and_fixed_conditioning_cap():
    cache = dict(members=7, observed_members=7, unavailable={}, observed_file_pages=119_934)
    check_extent(cache, 491_238_921, BAND.inputs)
    with pytest.raises(ValueError, match="conditioning extent"):
        check_extent(cache, 520_000_001, BAND.inputs)
    with pytest.raises(ValueError, match="conditioning extent"):
        check_extent(cache | {"observed_members": 6}, 491_238_921, BAND.inputs)


def test_withheld_arm_stands_apart_from_a_zero_error_estimate():
    geo = dict(runs={
        "stock": dict(horizontal_error_km={"c0": 1.0, "fitted_c": None}),
        "candidate": dict(horizontal_error_km={"c0": 2.0, "fitted_c": 0.0}),
    })
    assert paired_error_delta(geo) == {"c0": 1000.0, "fitted_c": None}
