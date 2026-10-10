import copy

import pytest
import report
import run
from test_run import fixture


def sample():
    model, archive, predecessor, _ = fixture()
    raw = run.analyze(model, archive, predecessor)
    raw["total_elapsed_s"] = 2
    raw["pairing"]["reason_counts"] = {}
    raw["support"]["unavailable_reasons"] = {}
    members = [dict(label=f"m{i}", dataset=f"DS{i % 3}") for i in range(12)]
    return dict(members=members), {m["label"]: copy.deepcopy(raw) for m in members}


def test_full_matched_subset_summary_and_plot(tmp_path):
    plan, receipts = sample()
    result = report.summarize(plan, receipts)
    arm = result["summaries"]["pooled"]["fitted-c"]
    assert arm["crossprediction_mass"] == 24
    assert arm["raw_matched_per_mass"] == 6
    assert arm["centered_matched_per_mass"] == 0
    assert len(result["summaries"]) == 4
    result["lineage_elapsed_s"] = 30
    assert "exactly the same eligible" in report.markdown(result)
    report.plot(result, tmp_path / "plot.png")
    assert (tmp_path / "plot.png").stat().st_size > 1000


def test_failed_member_withholds_aggregate_and_plot(tmp_path):
    plan, receipts = sample()
    receipts["m1"].update(status="failed", error="parity failure")
    result = report.summarize(plan, receipts)
    assert result["summaries"] == {}
    assert len(result["members"]) == 12
    with pytest.raises(ValueError, match="complete matched"):
        report.plot(result, tmp_path / "absent.png")


def test_mismatched_decomposition_rejected():
    plan, receipts = sample()
    receipts["m1"]["arms"]["zero-c"]["crossprediction_raw_product_sum"] += 1
    with pytest.raises(ValueError, match="receipt mismatch"):
        report.summarize(plan, receipts)


def test_missing_members_rejected():
    plan, receipts = sample()
    del receipts["m1"]
    with pytest.raises(ValueError, match="full membership"):
        report.summarize(plan, receipts)
