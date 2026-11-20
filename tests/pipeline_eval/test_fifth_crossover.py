import pytest

from tools.pipeline_eval.qualification import fifth_crossover as study
from tools.pipeline_eval.qualification import fifth_crossover_results as results


def test_matched_fft_scout_requires_the_same_proposal_and_the_same_physical_visit():
    old = [
        {
            "status": "processed",
            "visit_metadata_sha256": "physical",
            "differential": {"hints": [8, 6], "changed": [True, False]},
        }
    ]
    new = [dict(old[0], differential={"hints": [8, 6], "changed": [True, True]})]
    assert results.compare_hints(old, new) == {
        "matched_dual_calls": 1,
        "matched_hints": 2,
        "historical_changed_receivers": 1,
        "union_changed_receivers": 2,
    }
    new[0]["differential"]["hints"][1] = 2
    with pytest.raises(ValueError, match="different FFTW hints"):
        results.compare_hints(old, new)
    new[0]["visit_metadata_sha256"] = "unmatched"
    with pytest.raises(ValueError, match="physical visit"):
        results.compare_hints(old, new)


def test_six_case_projection_omits_inapplicable_replacement_and_counts_failure():
    roles = {"control": study.CONTROL, "union": study.METHOD}
    attempts = []
    for ident in ("a", "b"):
        for method in roles.values():
            for arm in ("c0", "fitted_c"):
                failed = ident == "b" and method == study.METHOD
                attempts.append(
                    dict(
                        id=ident,
                        method=method,
                        arm=arm,
                        error_km=None if failed else 0.8,
                        within_5pct=not failed,
                        within_10pct=not failed,
                    )
                )
    summary = results.summary({"six": ["a", "b"]}, attempts, roles)
    assert set(summary["six"]["c0"]) == set(roles)
    assert summary["six"]["fitted_c"]["union"]["attempted"] == 2
    assert summary["six"]["fitted_c"]["union"]["published"] == 1
    assert summary["six"]["fitted_c"]["union"]["within_10pct"] == 1
