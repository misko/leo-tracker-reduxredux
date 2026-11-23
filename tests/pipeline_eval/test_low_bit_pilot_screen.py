import math

import numpy as np
import pytest

from reports.ALGO08.v3.low_bit_pilot_screen import (
    bank_count, geometry_counts, quantization_efficiency, quantize, sensitivity, whole_budgets,
)


def test_full_bank_counts_distinct_complex_terms_frames_and_bit_pairs():
    bank = geometry_counts()
    fine = bank["frozen_frames14_bits1"]
    assert (fine["epochs"], fine["carrier_cells"]) == (3333, 2621)
    assert fine["hypothetical_popcounts_per_scout"] == 3333 * 2621 * 14 * 3 * 4
    assert bank["frozen_frames14_bits2"]["hypothetical_popcounts_per_scout"] == (
        4 * fine["hypothetical_popcounts_per_scout"])
    tiny = bank_count(3, 7, 2, signed_bits=2)
    assert tiny["byte_expanded_vnni_dot_ops_per_scout"] == 3 * 7 * 2 * 44 * 2
    assert tiny["optional_float32_score_grid_bytes_per_sweep"] == 3 * 7 * 4


def test_whole_callback_budget_does_not_credit_install_ingress():
    receipt = dict(ordered_probes=100,
                   outside_detector_cpu_s=12.,
                   outside_detector_wall_s=40.,
                   in_process_to_solver_cpu_s=30.,
                   in_process_to_solver_wall_s=58.,
                   detector_groups={"a": {"cpu_s": 5.}, "b": {"cpu_s": 13.}})
    warm = dict(launch_to_detections_s=28., terminal_to_exit_s=2.)
    budget = whole_budgets(receipt, warm)
    assert budget["cold_cpu_callback_budget_s"] == budget["projected_warm_callback_budget_s"] == 3.
    assert budget["cold_cpu_callback_budget_ms_per_lane"] == 30.
    assert budget["measured_cold_outside_elapsed_s"] > budget["measured_cold_half_acquisition_elapsed_s"]


def test_quantizer_and_nonzero_indistinguishable_perturbation():
    before = np.tile(np.array([-3., -1., 1., 3.]), 20).reshape(-1, 2)
    after = before - .25
    for bits in (1, 2):
        output = quantize(before, bits, math.sqrt(5))
        assert np.all(np.sign(output) == np.sign(before))
        assert sensitivity(before, after)[str(bits)] == dict(changed_component_fraction=0.,
                                                             squared_change_projection=0.)
    with pytest.raises(ValueError, match="bits"):
        quantize(before, 3, 1.)


def test_gaussian_efficiency_for_sign_on_one_and_both_sides():
    sign = quantization_efficiency(1)
    two = quantization_efficiency(2)
    assert sign["one_side_efficiency"] == pytest.approx(2 / math.pi)
    assert sign["two_side_efficiency"] == pytest.approx((2 / math.pi)**2)
    assert sign["two_side_loss_db"] == pytest.approx(3.9224, abs=.0001)
    assert 1 < two["two_side_loss_db"] < 1.3
