from dataclasses import replace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import range_epoch_model as model
from tools.pipeline_eval.qualification import range_epoch_trial as trial

RATE = 10_000_000


def test_native_epoch_uses_positive_local_delay_and_rational_frame_cycle():
    first = 9_800_000_000_001
    period = RATE / model.FRAME_HZ
    baseline = model.native_phase(first + 751, first, 350.2, RATE)
    earlier_window = model.native_phase(first + 747, first, 354.2, RATE)
    later_physical_arrival = model.native_phase(first + 751, first, 354.2, RATE)
    repeated = model.native_phase(first + 751 + RATE, first, 350.2, RATE)
    assert model.wrap(earlier_window - baseline, period) == pytest.approx(0)
    assert model.wrap(later_physical_arrival - baseline, period) == pytest.approx(4)
    assert model.wrap(repeated - baseline, period) == pytest.approx(0)


def test_arcs_are_fixed_by_chronology_without_signals_and_hold_only_last_third():
    def row(t):
        return dict(time_s=t, v5_owner=71, rf_hz=11.5e9, component="arc", phase=t, folded_hz=0)

    arcs = list(model.split([row(x) for x in np.r_[np.arange(145) * 0.5, 74, 75, 91, 92]]))
    assert len(arcs) == 2
    assert arcs[0].time_s[-1] == 60
    for arc in arcs:
        assert (~arc.train).sum() >= 6
        assert arc.time_s[arc.train][-1] < arc.time_s[~arc.train][0]
        assert arc.train[0] and not arc.train[-1]


def test_forward_injected_frame_has_positive_range_sign_on_held_rows():
    arcs, delays = [], []
    for index, rate in enumerate((-250, -150, -100)):
        t = 13 + 70 * index + np.arange(90) * 0.5
        aligned = t - t[0]
        selected = model.Arc(
            index, 11.5e9, str(index), t, np.zeros_like(t), np.zeros_like(t), np.arange(90) < 60
        )
        delay = 45000 + rate * aligned + (4 + index) * aligned**2
        arcs.append(selected)
        delays.append(delay)
    measured = trial.injected_epochs(arcs, delays, RATE)
    right, clock = model.frame_residual(arcs, delays, RATE, observed=measured)
    wrong, _ = model.frame_residual(arcs, [-d for d in delays], RATE, observed=measured)
    assert clock[0] == pytest.approx(4.75, abs=0.03)
    assert model.held_loss(arcs, right)["arc_median_mae"] < 0.3
    assert model.held_loss(arcs, wrong)["arc_median_mae"] > 100

    changed = [
        replace(a, phase=y + np.where(a.train, 0, 2500))
        for a, y in zip(arcs, measured, strict=True)
    ]
    residual, clock_changed = model.frame_residual(changed, delays, RATE)
    assert clock_changed == clock
    assert np.array_equal(residual[0][changed[0].train], right[0][arcs[0].train])


def test_original_owner_join_keeps_native_receiver_time_rf_and_frequency_authority():
    winner = dict(rx=2, channel=1, rf_hz=11.5e9, time_s=10.0, folded_hz=1700.0, phase=8.2)
    owned = dict(winner, id="key", v5_owner=31, component="arc")
    assert trial.join_owned([owned], {"key": winner})[("arc", 31)][0]["phase"] == 8.2
    with pytest.raises(ValueError, match="native winner"):
        trial.join_owned([dict(owned, folded_hz=1701)], {"key": winner})


def test_fixed_arc_frequency_calibration_absorbs_a_constant_rf_shift():
    t = np.arange(20, dtype=float)
    predicted = 500 * t**2
    arc = model.Arc(12, 11.5e9, "arc", t, t, predicted + 30000, t < 14)
    (original,) = model.frequency_residual([arc], [predicted])
    (calibrated,) = model.frequency_residual([arc], [predicted + 25000])
    assert original == pytest.approx(np.zeros_like(t), abs=1e-10)
    assert calibrated == pytest.approx(original, abs=1e-10)
