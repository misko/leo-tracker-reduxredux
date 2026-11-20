import pytest

from tools.pipeline_eval.qualification import diagnostic_whole as trial
from tools.pipeline_eval.qualification import diagnostic_whole_results as results


def candidate(rank, epoch, gated=True):
    return dict(
        candidate_rank=rank, integer_epoch_sample=epoch, passed_fractional_margin_gate=gated
    )


def test_gate_retains_identical_stock_candidate_when_ordinal_changes():
    stock = [
        {
            "visit": 0,
            "probes": [
                {"candidates": [candidate(0, 10), candidate(1, 20, False)]},
                {"candidates": [candidate(0, 30)]},
            ],
        }
    ]
    replacement = [
        {
            "visit": 0,
            "probes": [
                {"candidates": [candidate(0, 20), candidate(1, 10)]},
                {"candidates": []},
            ],
        }
    ]
    assert list(results.retention(stock, replacement)) == [
        {"visit": 0, "retained_stock_gates": [1, 0], "new_gate_payloads": [1, 0]}
    ]


def test_gate_retention_rejects_unmatched_receiver_inventory():
    stock = [{"visit": 0, "probes": [{"candidates": []}]}]
    with pytest.raises(ValueError, match="shorter"):
        list(results.retention(stock, [{"visit": 0, "probes": []}]))


def test_pooled_scores_keep_the_failed_diagnostic_in_its_denominator():
    scored = []
    for cohort in ("development diagnostic", "manifest-selected held"):
        for method in (trial.BASELINE, trial.METHOD):
            for arm in ("c0", "fitted_c"):
                failure = cohort == "development diagnostic" and method == trial.METHOD
                scored.append(
                    dict(
                        cohort=cohort,
                        method=method,
                        arm=arm,
                        error_km=None if failure else 0.35,
                        within_5pct=not failure,
                        within_10pct=not failure,
                    )
                )
    summary = results.pooled_summary(scored)
    assert summary["all"]["c0"][trial.METHOD]["attempted"] == 2
    assert summary["all"]["c0"][trial.METHOD]["published"] == 1
    assert summary["all"]["fitted_c"][trial.BASELINE]["within_10pct"] == 2
    failed = summary["development diagnostic"]["fitted_c"][trial.METHOD]
    assert failed["attempted"] == 1
    assert failed["error_km"]["n"] == 0
