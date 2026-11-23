from pathlib import Path
import sys

import numpy as np


RESEARCH = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(RESEARCH))
try:
    from dense_row_repetition import audit, common_rows, group_statistics, original_statistics
finally:
    sys.path.remove(str(RESEARCH))


def test_normalized_duplicates_are_local_to_original_noise_groups():
    design = np.array([[1., 0.], [2., 0.], [1., 0.], [0., 1.], [0., 1.]])
    inputs = dict(y=np.array([1., 5., 9., 4., 7.]), u=design,
                  s=np.array([1., 2., 1., 1., 2.]), g=np.array([0, 0, 1, 1, 1]))
    result = audit(inputs, prefix=design[:, :1])
    assert result["distinct"] == 4
    assert result["distinct_static_prefix"] == 3
    assert result["products"] == dict(gram=dict(original=14, removable=1), rhs=dict(original=8, removable=1))
    assert result["original_residual_rows"] == 5
    assert result["bitwise_exact"]


def test_all_distinct_reuses_exact_stock_arrays_including_signed_zero():
    design = np.array([[1., 0.], [1., -0.], [2., -0.]])
    values = np.array([1., 2., 3.])
    assert list(common_rows(design)) == [[0], [1], [2]]
    gram, rhs = original_statistics(design, values)
    out_gram, out_rhs, unique = group_statistics(design, values, gram, rhs)
    assert out_gram is gram and out_rhs is rhs and unique == 3


def test_identical_predictors_can_still_change_rounded_rhs_and_keep_different_residuals():
    design = np.repeat([[.3]], 4, axis=0)
    values = np.array([1e16, 1., -1e16, 1.])
    gram, rhs = original_statistics(design, values)
    out_gram, out_rhs, unique = group_statistics(design, values, gram, rhs)
    assert unique == 1
    np.testing.assert_allclose(out_gram, gram)
    assert out_rhs[0] != rhs[0]
    errors = np.array([1., 5., -9., 1.]) - design[:, 0] * 2.
    assert np.count_nonzero(errors != errors[0]) == 2


def test_budget_nests_the_native_grid_inside_evidence():
    from dense_row_repetition import archived_budget

    pair = dict(runs=dict(native=dict(solve_cpu_s=26., cold_cpu_s=5., grid_cpu_s=6.)))
    cap = dict(solve_cpu_s=26., panels={"4": dict(scenarios=dict(fastest_prefix=dict(dense_solve_budget_s=14.)))})
    posterior = dict(ceiling=dict(native=dict(both_arms_cpu_s=2.)))
    result = archived_budget(pair, cap, posterior)
    assert result["needed_saving_cpu_s"] == 12.
    assert result["hypothetical_shortfall_with_free_native_grid_s"] == 10.
    assert result["hypothetical_shortfall_with_free_cold_and_evidence_s"] == 1.
