"""Promotion gates retain failures and test accuracy independently of fit scores."""

import copy

import pytest

from leo.qualification.algo03_promotion import PROVENANCE_FLAGS, qualify


def trial():
    cohort = [
        dict(job_id=str(i), dataset=dataset, acquisition_mode=mode)
        for i, (dataset, mode) in enumerate(
            (
                ("DS23", "fast"),
                ("DS23", "adaptive"),
                ("DS24", "fast"),
                ("DS24", "adaptive"),
                ("DS26", "fast"),
            )
        )
    ]
    rows = [
        dict(
            **job,
            arm=arm,
            **dict.fromkeys(PROVENANCE_FLAGS, True),
            baseline=dict(state="complete", error_km=1.0, total_seconds=100.0),
            candidate=dict(state="complete", error_km=0.9, total_seconds=120.0, added_seconds=20.0),
        )
        for job in cohort
        for arm in ("c0", "fitted_c")
    ]
    return cohort, rows


def test_matched_improvement_passes_with_tail_and_stratum_summaries():
    cohort, rows = trial()
    result = qualify(cohort, rows, fast_only=False)
    assert result["passed"]
    assert result["summaries"]["dataset:DS24/adaptive"]["c0"]["candidate"]["p95_km"] == 0.9
    assert result["runtime"]["candidate_seconds"] == 600.0
    assert result["runtime"]["recovery_p95_seconds"] == 20.0


@pytest.mark.parametrize(
    "mutation,needle",
    [
        (lambda r: r.pop(), "missing result"),
        (lambda r: r[0]["candidate"].update(state="failed", error_km=None), "lost baseline"),
        (lambda r: r[0]["candidate"].update(error_km=float("nan")), "invalid candidate"),
        (lambda r: r[0].update(no_GPS_inference=False), "no_GPS_inference"),
        (lambda r: r[0]["candidate"].update(total_seconds=2401.0), "runtime budget"),
        (lambda r: r[0]["candidate"].update(error_km=1.2), "regression"),
    ],
)
def test_unfavorable_or_incomplete_evidence_cannot_disappear(mutation, needle):
    cohort, rows = trial()
    mutation(rows)
    result = qualify(cohort, rows, fast_only=False)
    assert not result["passed"]
    assert any(needle in failure for failure in result["failures"])
    assert result["cohort_count"] == 5


def test_better_frequency_objective_does_not_establish_accuracy_gain():
    cohort, rows = trial()
    for row in rows:
        row["candidate"].update(error_km=1.0, negative_twice_elbo=-1e6)
    result = qualify(cohort, rows, fast_only=False)
    assert not result["passed"]
    assert "all/fitted_c: mean error does not improve" in result["failures"]


def test_fitted_c_gain_cannot_hide_c0_or_acquisition_stratum_regression():
    cohort, rows = trial()
    for row in rows:
        if row["arm"] == "c0" or row["acquisition_mode"] == "adaptive":
            row["candidate"]["error_km"] = 1.2
    result = qualify(cohort, rows, fast_only=False)
    assert not result["passed"]
    assert any("all/c0" in failure for failure in result["failures"])
    assert any("acquisition_mode:adaptive" in failure for failure in result["failures"])


def test_full_runtime_and_exact_frozen_identity_are_required():
    cohort, rows = trial()
    for row in rows:
        row["candidate"].update(total_seconds=261.0, added_seconds=161.0)
    assert not qualify(cohort, rows)["passed"]
    rows = copy.deepcopy(rows)
    rows[0]["dataset"] = "DS26"
    with pytest.raises(ValueError, match="provenance"):
        qualify(cohort, rows)


def test_duplicate_and_absent_dataset_rejected():
    cohort, rows = trial()
    with pytest.raises(ValueError, match="Duplicate result"):
        qualify(cohort, [*rows, rows[0]])
    result = qualify(cohort[:-1], rows[:-2])
    assert "DS26: absent from frozen cohort" in result["failures"]


def test_shared_unavailable_input_remains_in_denominator_without_inventing_audit():
    cohort, rows = trial()
    cohort.append(dict(job_id="unavailable", dataset="DS26", acquisition_mode="fast"))
    for arm in ("c0", "fitted_c"):
        rows.append(
            dict(
                **cohort[-1],
                arm=arm,
                baseline=dict(state="unavailable", error_km=None, total_seconds=0.0),
                candidate=dict(
                    state="unavailable", error_km=None, total_seconds=0.0, added_seconds=0.0
                ),
            )
        )
    result = qualify(cohort, rows, fast_only=False)
    assert result["passed"]
    assert result["cohort_count"] == 6
    assert result["summaries"]["all"]["fitted_c"]["baseline_complete"] == 5


def test_current_user_scope_rejects_adaptive_even_when_its_results_improve():
    cohort, rows = trial()
    result = qualify(cohort, rows)
    assert not result["passed"]
    assert any("fast-only scope" in failure for failure in result["failures"])
    assert result["scope_amendment_id"] == "algo03-fast-only-user-scope-2026-10-30-v1"
