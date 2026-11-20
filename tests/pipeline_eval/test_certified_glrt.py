import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.qualification.certified_glrt_bounds import upper_bounds
from tools.pipeline_eval.variants import anchor_grid, certified_glrt, dense_q10, pilot_kernel


def test_every_partial_bound_encloses_the_coherent_score():
    rng = np.random.default_rng(8172)
    samples = rng.normal(size=(4, 12, 44)) + 1j * rng.normal(size=(4, 12, 44))
    samples[0, 1] = 0
    ref = rng.normal(size=44) + 1j * rng.normal(size=44)
    ref /= np.linalg.norm(ref)
    cfo = np.exp(1j * np.linspace(-0.4, 0.4, 7)[:, None] * np.arange(len(ref)))
    bounds = upper_bounds(samples, ref, cfo * ref)
    assert np.all(bounds[:-1] + 1e-14 >= bounds[-1])
    assert np.all(bounds[:, 0, 1, :] == 0)


@pytest.mark.hardware
def test_identical_nested_retry_reuses_work_and_clears_between_receiver_calls(tmp_path):
    reference_file = tmp_path / "tiled.so"
    dense_file = tmp_path / "dense.so"
    pilot_kernel.compile_filter(reference_file)
    dense_q10.compile_grid(dense_file)
    direct = anchor_grid.native_grid(reference_file)
    fine_inputs = []

    def fine(*args):
        fine_inputs.append(args)
        return (0.5,)

    grid = certified_glrt.ReusedGrid(dense_file, direct, fine)
    rate = 2_500_000
    epochs = round(rate / 750)
    frequencies = (-80_000.0, 0.0, 80_000.0)
    template = qin_edge_pilot_frame(rate, "upper")
    data = np.random.default_rng(19).integers(-10_000, 10_000, (2, rate // 50)).astype(float)
    values = data[0] + 1j * data[1]

    def guarded():
        peaks = []
        for iq, ref in ((values, template), (values.copy(), template.copy())):
            rows = grid.score_grid(iq, ref, rate, frequencies, (2, 28, 54), epochs)
            peaks.append(grid.retain_peaks(frequencies, rows, 8, 20, 80_000, epochs))
            assert grid.fine_scores(iq, ref, rate, peaks[-1][0][1], frequencies, (2,)) == (0.5,)
        return peaks

    run = grid.guarded_acquisition(guarded)
    for i in range(2):
        first, retry = run()
        assert first == retry
        assert len(fine_inputs) == i + 1
        assert grid.reuse[-1] == {"coarse_hits": 1, "fine_hits": 1}


def test_equal_values_with_different_float_bits_do_not_authorize_reuse():
    assert not certified_glrt.same_bytes(np.array([-0.0]), np.array([0.0]))
