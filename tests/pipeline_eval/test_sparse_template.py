from pathlib import Path
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3 import sparse_template_trial as trial


def test_top_power_selects_largest_energy_with_stable_ties():
    energy = np.array([1, 2, 0, 2, 1, 6], dtype=float)
    assert trial.upper_row(energy, 3).tolist() == [5, 1, 3]
    assert trial.minimum_subset(energy, .5) == 1
    assert trial.minimum_subset(energy, .9) == 4
    with pytest.raises(ValueError, match="nonzero"):
        trial.minimum_subset(np.zeros(12), .9)


def test_direct_bank_preserves_separate_frame_and_full_duration_cost_branches():
    numbers = trial.direct_bound()
    independent, coherent = numbers["grid"].values()
    assert independent["accumulations"] == 14
    assert coherent["accumulations"] == 1
    assert coherent["carriers"] == 32001
    assert coherent["min_one_hypothetical_operation_per_cell_ms_per_scout"] > 2
    assert numbers["rectangular_half_50_hz_bin_power"] == pytest.approx(4/np.pi**2)


def test_full_visit_comb_matches_direct_signed_numpy_spectrum_at_both_strides(tmp_path):
    source = Path(trial.__file__).with_name("sparse_template_comb.c")
    library = tmp_path / "sparse-comb.so"
    subprocess.run(["cc", "-std=c11", "-O2", "-fPIC", "-shared", str(source),
                    "-lfftw3f", "-o", str(library)], check=True)
    pilot_bins = np.array([173, -782, 1193], dtype=np.intc)
    weights = np.array([.5, .3, .2], dtype=np.float32)
    phases = np.arange(trial.POINTS) * 2j*np.pi/trial.POINTS
    iq = np.empty((trial.POINTS, 2, 2), dtype="<i2")
    for lane, carrier in enumerate((-15780, 15770)):
        wave = sum(7000 * weight * np.exp((line + carrier) * phases)
                   for line, weight in zip(pilot_bins, weights, strict=True))
        iq[:, lane, 0], iq[:, lane, 1] = np.rint(wave.real), np.rint(wave.imag)
    for stride in (1, 4):
        fft_size = trial.POINTS // stride
        lines = np.ascontiguousarray(pilot_bins % fft_size, dtype=np.intc)
        comb = trial.Comb(library, stride)
        try:
            for lane, carrier in enumerate((-15780, 15770)):
                samples = iq[::stride, lane, 0] + 1j*iq[::stride, lane, 1]
                power = abs(np.fft.fft(samples))**2
                expected = sum(weight * power[(trial.BINS + line) % fft_size]
                               for weight, line in zip(weights, lines, strict=True))
                comb.measure(iq, lane, lines, weights)
                scale = expected.max()
                np.testing.assert_allclose(comb.score/scale, expected/scale, atol=2e-6, rtol=3e-6)
                assert trial.ranked(comb.score)[0] == carrier * 50
        finally:
            comb.close()
