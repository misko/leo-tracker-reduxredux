from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from signed_factor_roof import price, report


def test_paid_roof_tracks_scope_and_excludes_an_already_addressed_summary():
    scores = dict(exact_original_readouts=True, observed_pair_cpu_ns=dict(c0=900_000_000, fitted_c=700_000_000),
                  archived_signed_refit=dict(cpu_s=1.5), exact_owner_role_count=20, exact_readout={}, stages={
                      "paid_full_objective": dict(calls=50, cpu_ns=1_000_000_000),
                      "curved_posterior": dict(calls=52, cpu_ns=300_000_000,
                                               same_refresh=dict(calls=2, cpu_ns=10_000_000)),
                      "predictive_covariance": dict(calls=50, cpu_ns=400_000_000),
                  })
    result = price(scores)
    assert result["factor_and_all_curved_adapter_roof_ns"] == 300_000_000
    assert result["factor_roof_after_existing_summary_idea_ns"] == 290_000_000
    assert result["required_net_cpu_ns_per_predictive_call"] == 10_000_000
    assert result["signed_pair_after_free_curved_adapter_ns"] == 1_300_000_000
    assert not result["meets_factor_floor"]
    scores["stages"]["curved_posterior"]["calls"] += 1
    with pytest.raises(ValueError, match="cross the original scope"):
        price(scores)


def test_archive_bindings_reproduce_the_two_price_decisions():
    receipt = report()
    assert {case: value["curved_adapter_calls"] for case, value in receipt["current"].items()} == {"0008": 80, "0402": 72}
    assert all(not value["meets_factor_floor"] for value in receipt["current"].values())
    assert receipt["earlier_hard_native_state"]["updates"] == 5256
    assert receipt["earlier_dense_native_state"]["exact_factor_delta_rank"] == [134, 134]
    assert receipt["separate_signed_predictive_gram"]["grid_dense_calls"] == 356
