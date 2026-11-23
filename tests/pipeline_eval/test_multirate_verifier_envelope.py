import numpy as np
import pytest

from reports.ALGO08.v3.multirate_verifier_envelope import budget, projection


def test_ideal_lowpass_counts_weighted_energy_and_worst_symbol():
    t = np.arange(256)
    low = np.exp(2j*np.pi*8*t/len(t))
    high = np.exp(2j*np.pi*40*t/len(t))
    bands = projection([low, high], 10_000_000, len(t), (0,))[0]
    assert bands[2_500_000]["weighted"] == pytest.approx(0.5)
    assert bands[2_500_000]["minimum"] == pytest.approx(0)
    assert bands[5_000_000]["minimum"] == pytest.approx(1)


def test_frozen_four_gate_preserves_observed_clock_and_distinguishes_prefix():
    out = budget()
    assert out["cases"] == ["DS30-0374", "DS30-0008", "DS30-0155", "DS30-0001"]
    complete = out["complete"]["scenarios"]
    prefix = out["fastest_prefix"]["scenarios"]
    assert complete["observed"]["elapsed_gates"] == pytest.approx([0.832896508, 0.807510842])
    assert complete["free_all_native"]["elapsed_gates"] == pytest.approx([0.6606852, 0.63078], abs=0.0001)
    assert complete["free_all_acquisition_cpu"]["elapsed_gates"][0] > 0.5
    assert prefix["entire_short_twice_as_fast"]["elapsed_gates"][0] > 0.5
    assert max(prefix["entire_short_four_times_as_fast"]["elapsed_gates"]) < 0.5
