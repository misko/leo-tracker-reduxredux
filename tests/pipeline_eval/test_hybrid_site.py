"""Check the paired use of real dual samples and the null geography contract."""

from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import hybrid_site_donor as donor
from tools.pipeline_eval.qualification import hybrid_site_model as model
from tools.pipeline_eval.qualification import hybrid_site_results as scores


def test_fixed_sparse_geometry_places_all_channels_on_exact_20ms_retunes():
    plan = model.schedule()
    assert len(plan) == 768
    assert [x["visit"] for x in plan] == list(range(768))
    assert {p["channel"] for p in plan[:8]} == set(range(1, 9))
    assert all(p["edge"] == ("lower" if p["channel"] % 2 else "upper") for p in plan)
    assert plan[8]["relative_counter"] - plan[0]["relative_counter"] == 31_250_000
    assert plan[-1]["relative_counter"] + model.SAMPLES < model.RATE * 300


def test_matched_normalization_and_exact_no_injection_control():
    rng = np.random.default_rng(84)
    distribution = rng.normal(0, 1, (model.SAMPLES, 2, 2)) * [[120, 145], [89, 215]]
    raw = np.rint(distribution + [[40, 90], [10, -180]]).astype("<i2")
    zero = np.zeros(raw.shape, dtype=np.float32)
    inactive, receipt = model.mixes(raw, zero, 31)
    np.testing.assert_array_equal(inactive["hybrid"], inactive["donor-only"])
    sigma = np.sqrt(np.mean(inactive["gaussian"].astype(np.float32) ** 2, axis=0))
    np.testing.assert_allclose(sigma, receipt["matched_component_rms"], rtol=0.01)
    assert np.sqrt(np.mean(inactive["donor-only"].astype(np.float32) ** 2)) == pytest.approx(
        530, abs=0.05
    )
    added = zero.copy()
    added[:13] = 51
    active, _ = model.mixes(raw, added, 31)
    for name in ("hybrid", "gaussian"):
        np.testing.assert_array_equal(active[name].astype(int) - inactive[name].astype(int), added)
    np.testing.assert_array_equal(active["donor-only"], inactive["donor-only"])


def test_donor_validity_and_salt_are_independent_of_power_or_detector():
    aq = dict(
        complete=True,
        sample_end=200100,
        sample_start=100,
        validity_authority="provider_attested",
        validity_includes_guard=True,
        actual_if_center_hz=10,
    )
    row = SimpleNamespace(
        sample_count=200_000, receiver_count=2, acquisition=aq, sequence=11, iq_sha256="sha256:a"
    )
    target = dict(lnb_lo_hz=20, rf_center_hz=30)
    assert donor.eligible(row, target)
    row.powers = [dict(power_dbfs=-5, decision="signal")]
    assert donor.eligible(row, target)
    assert donor.rank("x", "case", (0, row)) != donor.rank("x", "case", (1, row))
    assert donor.rank("x", "case", (0, row)) != donor.rank("y", "case", (0, row))
    aq["actual_if_center_hz"] = 11
    assert not donor.eligible(row, target)


def test_donor_peak_match_needs_both_phase_and_folded_cfo():
    historical = dict(
        integer_epoch_sample=19,
        fractional_epoch_offset_samples=0.3,
        fractional_tracking_cfo_hz=135_000,
        candidate_rank=1,
        fractional_margin=0.2,
    )
    same = dict(historical, fractional_tracking_cfo_hz=135_000 - scores.pilot.ALIAS_HZ + 30)
    assert scores.matches(same, [historical])
    assert not scores.matches(dict(same, integer_epoch_sample=29), [historical])
    assert not scores.matches(dict(same, fractional_tracking_cfo_hz=130_000), [historical])


def test_positions_keep_null_control_without_a_geographic_truth():
    truth = [5, -42]
    conditions = {"a": "containing", "b": "omitted"}
    offers = {"containing": truth, "omitted": [5 + 14 / 111, -42]}
    reqs = [
        dict(id=i, tile=offers[condition], screen_center=offers[condition])
        for i, condition in conditions.items()
    ]
    requests = {a: reqs for a in model.ARMS}
    actual = {
        (variant, req["id"], method): dict(
            result=dict(
                status="ok",
                metrics={},
                arms={a: dict(latlon=req["tile"], rf_rms_hz=10) for a in scores.ARMS},
            )
        )
        for variant in model.ARMS
        for req in reqs
        for method in scores.trial.METHODS
    }
    score, labels, _, _ = scores.positions(
        actual, requests, dict(coordinate=truth, conditions=conditions, offers=offers), "a" * 64
    )
    no_plan = [r for r in score if r["variant"] == "donor-only"]
    assert len(no_plan) == 8
    assert all(r["false_publication"] and r["geography_error_km"] is None for r in no_plan)
    assert labels["donor-only"]["a"]["truth"] is None
