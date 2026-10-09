import pytest
from report import render, summarize


def fixture():
    members = [
        dict(
            dataset=dataset,
            inventory_label=f"{dataset}-{i:03d}",
            session_id=f"synthetic-{dataset}-{i}",
        )
        for dataset, count in [("DS16", 63), ("DS17", 51), ("DS18", 34)]
        for i in range(1, count + 1)
    ]
    stats = dict(
        counts=dict(total=20, assigned=20, eligible_assignment=20, noise=0, nonfinite=0),
        receiver_pairs=dict(
            pairs_total=10,
            eligible_satellite_count=1,
            no_op=True,
            satellites=[dict(eligible=True, mean_hz=3, pair_count=10)],
        ),
        serial_groups=[dict(eligible=True, correlation=0.5)],
        margin=dict(correlation_residual=None, correlation_abs_residual=None),
    )
    receipts = {
        m["inventory_label"]: dict(
            member=m,
            protocol_sha256="frozen",
            status="complete",
            arms={"fitted-c": stats, "zero-c": stats},
        )
        for m in members
    }
    return dict(members=members), receipts


def test_full_membership_and_both_arms():
    plan, receipts = fixture()
    summary = summarize(plan, receipts, "frozen")
    assert summary["complete"]
    assert summary["groups"]["Pooled"]["membership"] == 148
    assert set(summary["groups"]["DS18"]["arms"]) == {"fitted-c", "zero-c"}
    paired = summary["groups"]["Pooled"]["arms"]["fitted-c"]["paired_receiver"]
    assert paired["eligible_satellite_recording_groups"] == 148
    assert paired["eligible_pair_count"] == 1480
    assert paired["per_scan_median_abs_group_mean_hz"]["median"] == 3


def test_failed_and_missing_withhold_all_aggregates():
    plan, receipts = fixture()
    del receipts["DS16-001"]
    receipts["DS18-034"].update(status="failed", error="synthetic input failure")
    summary = summarize(plan, receipts, "frozen")
    assert not summary["complete"]
    assert summary["groups"]["DS16"]["statuses"]["missing"] == 1
    assert summary["groups"]["DS18"]["statuses"]["failed"] == 1
    assert all(g["arms"] is None for g in summary["groups"].values())
    assert len(summary["cases"]) == 148


def test_wrong_protocol_and_unexpected_members_rejected():
    plan, receipts = fixture()
    receipts["DS16-001"]["protocol_sha256"] = "wrong"
    with pytest.raises(AssertionError):
        summarize(plan, receipts, "frozen")


def test_synthetic_figures_and_membership_table(tmp_path):
    plan, receipts = fixture()
    render(summarize(plan, receipts, "frozen"), tmp_path)
    assert (tmp_path / "paired-per-scan.png").read_bytes().startswith(b"\x89PNG")
    assert (tmp_path / "paired-group-bias.png").read_bytes().startswith(b"\x89PNG")
    assert "DS18-034" in (tmp_path / "RESULTS.md").read_text()
    plan, receipts = fixture()
    receipts["extra"] = {}
    with pytest.raises(AssertionError):
        summarize(plan, receipts, "frozen")
