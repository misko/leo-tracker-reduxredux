from importlib import import_module

import numpy as np
import pytest

study = import_module("reports.ALGO08.single-core-2x.full_arc_code_affine_trial")


def test_affine_phase_removes_full_arc_delay_trends_and_retains_curvature():
    t = np.arange(19) * 2.
    rate = 10_000_000
    period = rate / 750
    delays = [20_000. + 95. * t + .34 * t**2, 35_000. - 163. * t + .42 * t**2]
    nuisance = [300. + 8.2 * t, -600. - 4.5 * t]
    arcs = [
        study.trial.code.Arc(owner, 11e9, "test", t,
                             study.trial.code.wrap(delay + phase, period),
                             np.zeros_like(t), t < 24.)
        for owner, (delay, phase) in enumerate(zip(delays, nuisance, strict=True), 1)
    ]
    fit = study.fit(arcs, delays, rate)
    assert fit["held_rms_samples"] < 1e-8
    assert fit["slopes_samples_per_s"] == pytest.approx([8.2, -4.5], abs=1e-10)
    linear = [delay + .024 * t + 6. for delay in delays]
    assert study.fit(arcs, linear, rate)["held_rms_samples"] < 1e-8
    curved = [delay + .0008 * t**2 for delay in linear]
    assert study.fit(arcs, curved, rate)["held_rms_samples"] > .1


def test_leave_satellite_out_preserves_equal_mass_of_the_remaining_radios():
    rows = {"A": {"orbit_mse": {1: 2., 2: 4., 3: 6.}}}
    assert study.remove_orbit(rows, 2)["A"]["held_rms_samples"] == 2.
