import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.variants import anchor_grid, dense_q10, pilot_kernel

FREQUENCIES = (-717_709.0, -317_709.0, 2_291.0)


@pytest.fixture(scope="module")
def kernels(tmp_path_factory):
    folder = tmp_path_factory.mktemp("dense-q10")
    tiled, dense = folder / "tiled.so", folder / "dense.so"
    pilot_kernel.compile_filter(tiled)
    dense_q10.compile_grid(dense)
    control = anchor_grid.native_grid(tiled)
    return control, dense_q10.DenseQ10Grid(dense, control)


@pytest.mark.hardware
@pytest.mark.parametrize("rate,edge", [(2_500_000, "lower"), (10_000_000, "upper")])
@pytest.mark.parametrize("pattern", ["full", "near_zero", "wrapping"])
def test_dense_bound_and_original_rank(kernels, rate, edge, pattern):
    direct, bank = kernels
    values = np.random.default_rng(233).integers(-32768, 32768, (2, rate // 50))
    if pattern == "near_zero":
        values[:, 50:] %= 2
        values[:, 19::59] = 0
    if pattern == "wrapping":
        t = np.arange(values.shape[1])
        phase = 2j * np.pi * ((FREQUENCIES[1] + 117187.5) / rate) * t
        signal = 32767 * np.exp(phase)
        values = np.rint(np.vstack([signal.real, signal.imag]))
    epochs = round(rate / 750)
    args = (
        values[0] + 1j * values[1],
        qin_edge_pilot_frame(rate, edge),
        rate,
        FREQUENCIES,
        (2, 28, 77, 101, 301),
        epochs,
    )
    expected = np.asarray(direct(*args))
    scores = bank.score_grid(*args)
    assert np.max(abs(np.asarray(scores) - expected)) <= bank.receipts[-1]["error_bound"]
    actual = bank.retain_peaks(FREQUENCIES, scores, 8, 20, 80_000, epochs)
    assert actual == anchor_grid.retained_peaks(FREQUENCIES, expected, 8, 20, 80_000, epochs)
    for _, epoch, cfo in actual:
        row = FREQUENCIES.index(cfo)
        sl = slice(max(0, epoch - 1), min(epochs, epoch + 2))
        np.testing.assert_array_equal(scores[row][sl], expected[row, sl])
