"""Check calibrated mixture arithmetic and relative pilot-match semantics."""

import numpy as np
import pytest

from tools.pipeline_eval.qualification import austin_timing_transfer as trial


def test_mix_leaves_uninjected_lane_and_donor_control_byte_exact():
    rng = np.random.default_rng(251)
    donor = np.rint(rng.normal(0, 160, (20_000, 2, 2))).astype("<i2")
    emission = rng.normal(0, 250, 20_000) + 1j * rng.normal(0, 250, 20_000)
    mixed, gain = trial.mix(donor, emission, 1, -12)
    no_plant, _ = trial.mix(donor, None, 0, None)
    np.testing.assert_array_equal(donor, no_plant)
    np.testing.assert_array_equal(mixed[:, 0, :], donor[:, 0, :])
    signal = np.column_stack((emission.real, emission.imag)) * gain
    reference = donor[:, 1, :].astype(float)
    observed = 10 * np.log10(np.mean(signal**2) / np.mean(reference**2))
    assert observed == pytest.approx(-12.0)
    clean, _ = trial.mix(donor, emission, 1, -12, clean=True)
    np.testing.assert_array_equal(mixed[:, 1, :] - donor[:, 1, :], clean[:, 1, :])


def test_timing_schedule_advances_by_known_translation_and_rotates_lanes():
    events = trial.schedule()
    assert events == trial.schedule() and len(events) == 4
    assert {e["origin_ms"] for e in events} == {0, 20}
    assert sum(e["rx"] for e in events) == 2
    values = np.arange(1000).astype(np.complex64)
    e = dict(events[0], cfo_shift_hz=0)
    np.testing.assert_array_equal(trial.moved(values, e), np.roll(values, e["epoch_shift_samples"]))


def test_phase_match_tracks_folded_frequency_and_rejects_wrong_code_epoch():
    candidate = dict(
        epoch=11001,
        fractional_epoch=dict(
            status="complete",
            margin=0.05,
            offset_samples=0.2,
            tracking_cfo_hz=56_000 - trial.wave.ALIAS_HZ + 90,
        ),
    )
    assert trial.complete([candidate]) == [candidate]
    assert trial.identify(candidate, 11000, 56000) == (True, True)
    assert trial.identify(candidate, 11005, 54000) == (False, False)
