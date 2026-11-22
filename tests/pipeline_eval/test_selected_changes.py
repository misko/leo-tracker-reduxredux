from importlib import import_module

import pytest
from PIL import Image

audit = import_module("reports.ALGO08.single-core-2x.selected_changes")


def row(visit, rank=None):
    return dict(visit_index=visit, receiver_id=1, channel=3, actual_rf_hz=2,
                candidates=[] if rank is None else [dict(candidate_rank=rank, cfo=3)])


def test_classifies_lost_primary_and_rank_substitution_separately():
    left = [row(0, 0), row(1, 1), row(2), row(3, 1)]
    right = [row(0), row(1, 0), row(2, 1), row(3, 1)]
    result = audit.changes(left, right)
    assert result["transitions"] == {"primary_to_none": 1, "residual_to_primary": 1, "none_to_residual": 1}
    assert result["changed"] == 3 and result["changes_by_channel"] == {"3": 3}
    assert [r["visit"] for r in result["rows"]] == [0, 1, 2]
    with pytest.raises(ValueError, match="Different admitted RF opportunity"):
        audit.changes(left, list(reversed(right)))


def test_partial_stage_plot_handles_withholding_and_keeps_unmeasured_cases_out(tmp_path):
    plot = import_module("reports.ALGO08.single-core-2x.plot_ds30_stage").plot
    missing = dict(state="missing", case="DS30-0008")
    with pytest.raises(ValueError, match="No verified pairs"):
        plot(dict(assigned=1, cases=[missing]), tmp_path / "plot.png")
    arms = {k: dict(latlon=None) for k in ("c0", "fitted_c")}
    row = dict(case="DS30-0374", state="verified", cpu_s=dict(baseline=2, candidate=1),
               elapsed_s=dict(baseline=3, candidate=2), arms=dict(baseline=arms, candidate=arms))
    plot(dict(assigned=2, cases=[row, missing]), tmp_path / "plot.png")
    with Image.open(tmp_path / "plot.png") as image:
        assert image.format == "PNG" and image.width > 1000


def test_summary_distinguishes_missing_selections_rank_substitution_and_numerical_changes():
    left = [row(0, 0), row(1, 1), row(2), row(3, 1), row(4, 0)]
    right = [row(0), row(1, 0), row(2, 1), row(3, 1), row(4, 0)]
    left[-1]["candidates"][0].update(passed=True)
    right[-1]["candidates"][0].update(passed=False, cfo=3.125)
    result = audit.selection_summary(left, right)
    assert result["opportunities"] == 5 and result["changed"] == 4
    assert result["selections"] == {"baseline": 4, "candidate": 4}
    assert result["transitions_on_changed_rows"] == {
        "primary_to_none": 1, "residual_to_primary": 1, "none_to_residual": 1, "primary_to_primary": 1}
    assert result["same_rank_field_counts"] == {"cfo": 1, "passed": 1}
    assert result["same_rank_max_abs_delta"] == {"cfo": .125}
    right[-1]["candidates"][0].pop("passed")
    with pytest.raises(ValueError, match="different fields"):
        audit.selection_summary(left, right)


def test_crossing_scores_keeps_measured_fields_and_rejects_different_selections():
    cross = import_module("reports.ALGO08.single-core-2x.cross_factor_fields")
    left = [row(12, 1)]
    right = [row(12, 1)]
    for collection, value in ((left, 1.), (right, 2.)):
        collection[0]["candidates"][0].update(dict.fromkeys(cross.SCORES | cross.MEASURED, value))
    for fields in (cross.SCORES, cross.MEASURED):
        mixed, = cross.mix(left, right, fields)[0]["candidates"]
        assert all(mixed[key] == (2. if key in fields else 1.) for key in cross.SCORES | cross.MEASURED)
    right[0]["candidates"][0]["candidate_rank"] = 0
    with pytest.raises(ValueError, match="winning rank"):
        cross.mix(left, right, cross.SCORES)
