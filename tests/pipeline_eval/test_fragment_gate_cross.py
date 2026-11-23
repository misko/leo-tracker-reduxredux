from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from fragment_gate_cross import install_weights, local_gate, mask_influence, peak_step, scope, state_terms, transport_phase
from fragment_gate_cross_0402 import comparable_support, isolated_slope_gate
from leo.analysis.localization_v3.acceptance import conditional_gate
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_phase_references_join_by_norad_and_keep_recipient_only_prior_coordinate():
    donor = dict(norads=[3, 1, 4], phase=[.3, .1, .4])
    phase, known = transport_phase([1, 2, 3], [.6, .7, .8], donor)
    assert phase.tolist() == [.1, .7, .3] and known == 2


def test_point_sigma_and_power_transfers_respect_active_identity_and_alias():
    points = ["a", "b", "c", "d", "e"]
    p = SimpleNamespace(
        rows=[dict(candidate_norad=12), dict(candidate_norad=13)], members=[0, 1],
        slices=[slice(0, 3), slice(3, 5)], alias=[1, -1],
        scan=SimpleNamespace(tracks=[dict(key="T1", observation_ids=points[:3]),
                                     dict(key="T2", observation_ids=points[3:])]),
        point_noise=np.full(5, 90.), keep=np.array([True, False, True, True, True]),
    )
    donor = {("T1", 12, 1): (.5, {"a": 80., "b": 70.}), ("T2", 13, 1): (.7, {"d": 70., "e": 60.})}
    power, noise, seen = install_weights(p, np.ones(2), donor)
    assert power.tolist() == [.5, 1.]
    assert noise.tolist() == [80., 90., 90., 90., 90.]
    assert seen == dict(active_rows=2, active_points=4, donor_power_rows=1, donor_noise_points=1)


def fragment(residual):
    values = np.asarray(residual, float)
    n = len(values)
    return dict(ids=np.array([str(i) for i in range(n)]), times=np.arange(n, dtype=float), raw_hz=values.copy(),
                orbit_hz=np.zeros(n), hardware_hz=np.zeros(n), smooth_hz=np.zeros(n), constant_hz=0.,
                elevation=np.full(n, 45.), alias=0, norad=123, residual_hz=values)


def test_gate_only_mask_keeps_signed_alias_and_reuses_original_split_statistic():
    f = fragment(np.r_[np.full(7, -95.), np.full(6, 95.)])
    full = f["ids"].tolist()
    points = [value for value in full if value != "2"]
    assert comparable_support(full, points) == "2"
    selected = scope(f, points)
    gate = local_gate(f, points)
    assert gate["profile_alias"] == 0 and gate["points"] == 12
    expected = conditional_gate(f["residual_hz"][selected], f["times"][selected])
    assert gate["conditional_residual_gate"] == expected
    split, score = peak_step(f["residual_hz"][selected])
    assert split == 6
    assert score == pytest.approx(expected["diagnostics"]["maximum_step_z"])
    influence = [row for row in mask_influence(f, full) if row["removed"] == "2"]
    assert influence[0]["step_z"] == pytest.approx(score)
    with pytest.raises(ValueError, match="chronological"):
        scope(f, points[::-1])


def test_fixed_state_decomposition_accounts_for_lifted_alias_and_original_nuisance():
    values = np.linspace(-100, 150, 12)
    left = fragment(values)
    orbit, hardware, smooth, constant = np.arange(12), np.full(12, 4.), np.arange(12)*.5, 1.
    right = dict(left, orbit_hz=orbit, hardware_hz=hardware, smooth_hz=smooth, constant_hz=constant, alias=1,
                 residual_hz=values + PERIOD - orbit - hardware - smooth - constant)
    readout = state_terms(left, right, left["ids"].tolist())
    assert readout["signed_alias_hz"]["mean_hz"] == PERIOD
    assert readout["hardware_hz"]["centered_rms_hz"] == 0
    assert readout["orbit_hz"]["centered_rms_hz"] == pytest.approx(np.std(orbit))
    right["times"] = right["times"] + .1
    with pytest.raises(ValueError, match="clocks"):
        state_terms(left, right, left["ids"].tolist())


def test_slope_only_triage_preserves_original_step_and_autocorrelation_limits():
    observed = dict(compatible=False, profile_bias_hz=110., profile_rms_hz=80., aliases_changed=0, points=48,
                    conditional_residual_gate=dict(
                        rms_hz=100., diagnostics=dict(slope_z=3.5, mean_z=.1, quadratic_bic_gain=3.,
                                                       maximum_step_z=3.9, lag1_acf=.12)))
    assert isolated_slope_gate(observed)
    observed["conditional_residual_gate"]["diagnostics"]["maximum_step_z"] = 4.01
    assert not isolated_slope_gate(observed)
    observed["conditional_residual_gate"]["diagnostics"]["maximum_step_z"] = 4.
    observed["conditional_residual_gate"]["diagnostics"]["lag1_acf"] = .58
    assert not isolated_slope_gate(observed)
