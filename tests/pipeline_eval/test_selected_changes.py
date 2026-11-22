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
