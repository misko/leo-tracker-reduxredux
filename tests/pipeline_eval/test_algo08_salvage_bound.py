from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3.conservative_recovery import selected_supports
from leo.analysis.research.polynomial_satellite_diagnostics import batch_noise_screen
from leo.analysis.research.retained_track_likelihood import PERIOD, profile
from tools.pipeline_eval.variants import algo08_salvage_bound as pruning, v5_tiled_salvage


def test_reprofiling_an_alias_on_a_prefix_is_not_a_lower_bound():
    residual = PERIOD / 2 + np.array([100., -120., 300.])
    noise = np.array([40., 300., 400.])
    full = profile(residual, np.zeros(3), np.diag(1 / noise))
    prefix = profile(residual[:2], np.zeros(2), np.diag(1 / noise[:2]))
    assert prefix["alias"][0] == 0 and full["alias"][0] == -1
    assert prefix["cost"][0] > full["cost"][0]
    pair_bound = (residual[0] - residual[1]) ** 2 / (noise[0]**2 + noise[1]**2)
    normalization = np.log1p(1000.**2 * np.sum(1 / noise**2))
    assert pair_bound + normalization < full["cost"][0]


def test_gating_one_phase_cannot_promote_a_different_winner():
    a = np.r_[280., np.zeros(11)]
    b = np.array([110., 110., -110., -110., 110., -110., 110., -110., -110., 110., 110., -110.])
    terms = profile(np.zeros(12), -np.stack((a, b)), np.diag(np.full(12, 1 / 40.)))
    assert np.argmin(terms["cost"]) == 0
    np.testing.assert_array_equal(np.max(abs(terms["residual"]) / 40, axis=1) <= 6, [False, True])


@pytest.mark.parametrize("distance", [0., 480., 480.0001, 520.])
def test_outward_endpoint_witness_keeps_ties(distance):
    y = np.array([0., distance])
    noise = np.full(2, 40.)
    f = np.zeros((3, 2))
    e = np.ones_like(f)
    witness = pruning.EndpointWitness.prepare(y, noise, f, e, 1., np.array([0., 20.]))
    assert witness.rejects(0, 2) == (distance > 480.)
    f[0, -1] = 1.
    witness = pruning.EndpointWitness.prepare(y, noise, f, e, 1., np.array([0., 20.]))
    if distance <= 481.:
        assert not witness.rejects(0, 2)
    if distance == 480.0001:
        e[0, 0] = -1.
        assert witness.rejects(0, 2)


def test_safe_early_exits_preserve_every_returned_support_and_phase_order():
    n = 16
    t = np.arange(n, dtype=float) * 3
    y = np.zeros(n)
    noise = np.full(n, 100.)
    sky = dict(time_s=t, position_km=np.array([[[0., 0., 0.]], [[1., 0., 0.]], [[2., 0., 0.]]]),
               velocity_km_s=np.zeros((3, 1, 3)))
    scan = SimpleNamespace(sky=sky, norads=[42, 24, 17])

    def project(bank, dates, labels, phases, *point):
        key = bank["position_km"][0, 0, 0]
        f = key * (300. * dates + PERIOD)
        return f, np.ones_like(f)

    kernel = SimpleNamespace(selected_supports=selected_supports, raw_curvature=lambda _: True,
                             paired_phase_frequency=project, profile=profile,
                             batch_noise_screen=batch_noise_screen)
    original = v5_tiled_salvage.fine_alternatives
    args = kernel, scan, dict(times=t, values=y), y, noise, 1., {0, 1, 2}, (0., 0.)
    expected = original(*args)
    assert len(expected[0]) == 5
    control, gate, proof = [Counter() for _ in range(3)]
    for mode, counter in zip(("control", "gate", "bound"), (control, gate, proof), strict=True):
        assert pruning.instrument(original, mode, counter)(*args) == expected
    assert 0 < gate["noise_calls"] < control["noise_calls"]
    assert gate["profile_calls"] == control["profile_calls"]
    assert proof["rejected_by_bound"] > 0
    assert proof["profile_calls"] < control["profile_calls"]


def test_uncertified_arithmetic_falls_back_to_original_validation():
    t = np.arange(14, dtype=float) * 3
    residual = np.full_like(t, np.nan)
    f = np.zeros((2, len(t)))
    assert pruning.EndpointWitness.prepare(residual, np.ones_like(t), f, f, 1., t) is None
    assert not pruning.defer_noise(residual, t, 1000., 0., 0., 0.)
