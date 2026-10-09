"""Synthetic full148 coverage and descriptive summary qualification."""

import copy

import numpy as np
import pytest
from report import compact_arm, render, summarize


def arm_fixture(scale=1):
    pairs = [
        dict(
            satellite=s,
            channel=0,
            tick_ms=i * 1000,
            rx0_indices=[i * 2],
            rx1_indices=[i * 2 + 1],
            difference_hz=scale * (s + i),
        )
        for s in [1, 2]
        for i in range(10)
    ]
    common = dict(
        satellite_ids=[1, 2],
        eligible_satellite_ids=[1, 2],
        contrasts_hz=[-2 * scale, 2 * scale],
        no_op=False,
    )
    y = np.array([p["difference_hz"] for p in pairs])
    delta = np.repeat([-2 * scale, 2 * scale], 10)
    projected = dict(
        common,
        data_rank=1,
        regularized_rank=1,
        background_rank=2,
        residual_hz=(y - delta - 5 * scale).tolist(),
    )
    smooth = dict(
        common,
        contrasts_hz=[0, 0],
        data_rank=0,
        regularized_rank=1,
        background_rank=3,
        no_op=True,
        residual_hz=[0] * 20,
    )
    return dict(
        pair_count=20,
        paired_rows=pairs,
        raw_pair_mean_hz=float(y.mean()),
        raw_pair_rms_hz=float(np.sqrt(np.mean(y**2))),
        unadjusted_shrinkage=common,
        background_projected=projected,
        smooth_clock_projected=smooth,
    )


def fixture():
    bindings, receipts = [], {}
    for dataset, count in [("DS16", 63), ("DS17", 51), ("DS18", 34)]:
        for i in range(count):
            member = dict(
                inventory_label=f"{dataset}-{i + 1:03d}",
                dataset=dataset,
                session_id=f"synthetic-{dataset}-{i}",
                exposure="previously_evaluated_consumed"
                if dataset == "DS18" and i < 24
                else "consumed",
            )
            kind = "legacy_ds16" if dataset == "DS16" and i < 48 else "catalog"
            bindings.append(dict(member=member, loader_binding=dict(kind=kind)))
            receipts[member["inventory_label"]] = dict(
                member=member,
                status="complete",
                protocol_sha256="synthetic",
                sigma_hz=30,
                pair_variance_hz2=31250,
                objective_checks={arm: dict(delta=0) for arm in ("fitted-c", "zero-c")},
                arms={"fitted-c": arm_fixture(), "zero-c": arm_fixture(2)},
            )
    return dict(members=bindings, contrast_sigma_hz=30, pair_variance_hz2=31250), receipts


def test_full_membership_both_arms_and_exposure_accounting():
    plan, receipts = fixture()
    summary = summarize(plan, receipts, "synthetic")
    assert summary["complete"] and summary["membership"] == 148
    assert summary["groups"]["DS16-original48"]["membership"] == 48
    assert summary["groups"]["DS16-added15"]["membership"] == 15
    assert summary["groups"]["DS18-prior24"]["membership"] == 24
    assert summary["groups"]["DS18-other10-consumed"]["membership"] == 10
    for arm, expected in [("fitted-c", 2), ("zero-c", 4)]:
        pooled = summary["groups"]["Pooled"]["arms"][arm]
        assert pooled["total_pairs"] == 2960
        assert (
            pooled["methods"]["background_projected"]["per_recording_mean_abs_hz"]["median"]
            == expected
        )
        assert pooled["methods"]["smooth_clock_projected"]["no_identified_modes_count"] == 148
        assert pooled["methods"]["smooth_clock_projected"]["rank_fraction"]["median"] == 0


def test_failed_and_missing_members_remain_explicit_not_dropped():
    plan, receipts = fixture()
    del receipts["DS16-001"]
    receipts["DS17-001"].update(status="failed", error="synthetic input failure")
    summary = summarize(plan, receipts, "synthetic")
    assert not summary["complete"]
    assert summary["statuses"] == dict(missing=1, failed=1, complete=146)
    assert len(summary["cases"]) == 148
    assert summary["groups"]["Pooled"]["membership"] == 148
    assert summary["groups"]["Pooled"]["arms"]["fitted-c"]["available_recordings"] == 146


def test_rms_common_background_and_remaining_contrast_are_known():
    compact = compact_arm(arm_fixture())
    rms = compact["methods"]["background_projected"]["fit_rms"]
    assert rms["fitted_common_background_rms_hz"] == pytest.approx(5)
    y = np.array([s + i for s in [1, 2] for i in range(10)])
    assert rms["after_background_rms_hz"] == pytest.approx(np.sqrt(np.mean((y - 5) ** 2)))
    assert rms["contrast_rms_hz"] == pytest.approx(2)
    assert "paired_rows" not in compact


@pytest.mark.parametrize("change", ["digest", "pair_membership", "objective", "unexpected"])
def test_invalid_authority_is_rejected(change):
    plan, receipts = fixture()
    first = receipts["DS16-001"]
    if change == "digest":
        first["protocol_sha256"] = "wrong"
    elif change == "pair_membership":
        first["arms"]["zero-c"]["paired_rows"][0]["rx0_indices"] = [999]
    elif change == "objective":
        first["objective_checks"]["fitted-c"]["delta"] = 0.1
    else:
        receipts["unexpected"] = copy.deepcopy(first)
    with pytest.raises(AssertionError):
        summarize(plan, receipts, "synthetic")


def test_render_synthetic_plots_and_report_without_accuracy_claim(tmp_path):
    plan, receipts = fixture()
    summary = summarize(plan, receipts, "synthetic")
    render(summary, tmp_path)
    for name in ["contrast-comparison.png", "contrast-distributions.png"]:
        assert (tmp_path / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    text = (tmp_path / "RESULTS.md").read_text()
    assert "No new position" in text
    assert "DS18-034" in text and "DS16-063" in text
