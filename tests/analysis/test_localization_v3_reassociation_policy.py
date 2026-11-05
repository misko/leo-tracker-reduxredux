from copy import deepcopy

import pytest

from leo.analysis.localization_v3 import reassociation_policy as policy


def fixture():
    baseline = {
        a: dict(x=[0.0, 0.0], error_m=None, objective=100.0, rms_hz=None, associated=40)
        for a in policy.ARMS
    }
    row = dict(
        qualified=True,
        all_gates_pass=True,
        phase_closed=True,
        optimizer_success=True,
        mixture_phase_interior=True,
        native_ids_sha256="ids",
        x=[1.0, 2.0],
        error_m=None,
        objective=90.0,
        rms_hz=20.0,
    )
    candidate = dict(
        name="replacement",
        accepted=True,
        gains={a: 5.0 for a in policy.ARMS},
        pair={a: deepcopy(row) for a in policy.ARMS},
        control={a: dict(native_ids_sha256="ids") for a in policy.ARMS},
    )
    guard = dict(
        passed=True, model="receiver_offset", unique_folds=5, missing=[], minimum_margin=0.01
    )
    return baseline, [candidate], {"replacement": guard}


def test_accepted_repair_preserves_point_count_and_does_not_use_evaluation_error():
    base, records, guards = fixture()
    before = policy.select(base, records, guards)
    records[0]["pair"]["c0"]["error_m"] = 1e20
    base["fitted_c"]["error_m"] = 0.0
    after = policy.select(base, records, guards)
    assert before["selected"] == after["selected"] == "replacement"
    assert before["review"] == after["review"]
    assert all(row["associated"] == 40 for row in after["final"].values())


@pytest.mark.parametrize(
    "fault",
    [
        "physical",
        "folds",
        "margin",
        "receiver",
        "missing",
        "gain",
        "phase",
        "mixture",
        "lost",
        "remapped",
        "evidence",
    ],
)
def test_each_admission_guard_can_retain_exact_baseline(fault):
    base, records, guards = fixture()
    row, guard = records[0], guards["replacement"]
    if fault == "physical":
        row["accepted"] = False
    elif fault == "folds":
        guard["unique_folds"] = 4
    elif fault == "margin":
        guard["minimum_margin"] = 0.0
    elif fault == "receiver":
        guard["model"] = "independent_offset"
    elif fault == "missing":
        guard["missing"] = ["fold"]
    elif fault == "gain":
        row["gains"]["c0"] = float("nan")
    elif fault == "phase":
        row["pair"]["fitted_c"]["phase_closed"] = False
    elif fault == "mixture":
        row["pair"]["c0"]["mixture_phase_interior"] = False
    elif fault == "lost":
        row["pair"]["c0"]["lost_ids"] = ["a"]
    elif fault == "remapped":
        row["pair"]["fitted_c"]["unexpected_reassigned_ids_count"] = 1
    else:
        row["control"]["c0"]["native_ids_sha256"] = "different"
    result = policy.select(base, records, guards)
    assert result["selected"] is None and result["final"] == base
    result["final"]["c0"]["x"][0] = 3.0
    assert base["c0"]["x"][0] == 0.0


def test_complete_search_requires_every_arm_and_start_without_duplicates():
    rows = [
        dict(arm=a, start=s, status="complete")
        for a in policy.ARMS
        for s in ("published", "family_omitted")
    ]
    assert policy.fit_rows_complete(rows)
    assert not policy.fit_rows_complete(rows[:-1])
    assert not policy.fit_rows_complete(rows[:-1] + [rows[0]])
    rows[-1]["status"] = "incomplete"
    assert not policy.fit_rows_complete(rows)


def test_gain_uses_penalized_matched_bounds_in_both_arms():
    h = dict(name="r", penalty=3.0)
    pair = {a: dict(objective=9.0) for a in policy.ARMS}
    control = {a: {} for a in policy.ARMS}
    result = policy.score_record(h, pair, control, dict(c0=12.0, fitted_c=20.0))
    assert result["gains"] == dict(c0=0.0, fitted_c=8.0) and not result["accepted"]
    assert policy.destination_owned(dict(c0={"x": 1}, fitted_c={"y": 2}), 2)


def test_propagation_exclusion_is_exact_and_never_allows_partial_failures():
    receipt = dict(
        nominal_causality_verified=True,
        partial_or_unknown_blocks=False,
        failures=[dict(norad=1, classification="exclude_consistent_model_invalid_all_grid")],
    )
    assert policy.propagation_eligible(receipt, [1])
    assert not policy.propagation_eligible(receipt, [2])
    receipt["partial_or_unknown_blocks"] = True
    assert not policy.propagation_eligible(receipt, [1])
