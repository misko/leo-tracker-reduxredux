"""Exact operand accounting and an intentionally generous shared-work ceiling."""

from pathlib import Path
import sys

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from grid_cross_arm_posterior import FITTED_COLUMN, FIXED_INPUTS, ceiling, compare_inputs, same_bits


def scoped_operands():
    g = np.array([1, 0, 1, 0])
    x = np.ones((4, 10))
    y = np.arange(4.)
    fixed = {name: np.array([1., 2.]) for name in FIXED_INPUTS}
    fixed.update(g=g, s=np.ones(4), counts=np.bincount(g))
    zero = dict(fixed, u=x, y=y, prior=np.full(x.shape[1], -1), coefficient=np.arange(x.shape[1], dtype=float),
                noise_precision=np.array([1., 1.]))
    augmented = np.insert(x, FITTED_COLUMN, [3., -2., 3., -2.], axis=1)
    fitted = dict(fixed, u=augmented, y=y.copy(), prior=np.full(augmented.shape[1], -1),
                  coefficient=np.insert(zero["coefficient"], FITTED_COLUMN, 10.), noise_precision=np.array([1., 1.5]))
    return zero, fitted


def test_group_operand_identity_counts_shared_gram_and_rhs_separately():
    zero, fitted = scoped_operands()
    fitted["u"][zero["g"] == 1, -1] = 2.
    fitted["y"][1] += 1.
    result = compare_inputs(zero, fitted)
    assert result["widths"] == [10, 11]
    assert result["equal_response_rows"] == 3
    assert result["equal_full_common_design_rows"] == 2
    assert result["equal_common_design_columns"] == 9
    assert result["eligible_common_gram_entries"] == 9**2 + 10**2
    assert result["total_fitted_gram_entries"] == 2*11**2
    assert result["eligible_common_rhs_entries"] == 9
    assert result["groups_with_every_common_column_equal"] == result["groups_with_all_response_equal"] == 1
    assert result["coupled_noise_groups"] == 2
    assert result["equal_precision_slots"] == 1 and result["equal_precision_vectors"] == 0


def test_distinct_extra_column_does_not_make_posteriors_reusable():
    zero, fitted = scoped_operands()
    result = compare_inputs(zero, fitted)
    assert result["eligible_common_gram_entries"] == 2*10**2
    assert result["equal_common_coefficients"] == 10
    assert result["equal_prior_indices"] and not result["full_posterior_reusable"]


def test_exact_bit_comparison_and_input_alignment():
    assert same_bits(np.array([+0.]), np.array([-0.])).tolist() == [False]
    assert same_bits(np.array([True]), np.array([True])).tolist() == [True]
    zero, fitted = scoped_operands()
    fitted["g"] = np.roll(fitted["g"], 1)
    with pytest.raises(ValueError, match="aligned noise groups"):
        compare_inputs(zero, fitted)


def test_grant_switches_orientation_per_point_and_excludes_unpaired_endpoints():
    def clock(ns):
        return {key: ns for key in ("curved", "bound", "native", "validation")}

    pairs = [dict(clocks=dict(c0=clock(150), fitted_c=clock(100))),
             dict(clocks=dict(c0=clock(50), fitted_c=clock(170)))]
    result = ceiling(pairs, [dict(arm="fitted_c", clock=clock(80))])
    assert result["native"] == dict(granted_peer_cpu_s=320/1e9, endpoint_only_cpu_s=80/1e9,
                                    both_arms_cpu_s=550/1e9)
