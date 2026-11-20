import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.variants import anchor_grid, pilot_kernel, spectral_grid

pytestmark = pytest.mark.hardware  # 256-bit AVX2 support for the experimental kernel.

RATE = 2_500_000
EPOCHS = round(RATE / 750)
FREQUENCIES = (-797_709.0, -317_709.0, 2_291.0, 499_002.0, 756_322.0)


@pytest.fixture(scope="module")
def kernels(tmp_path_factory):
    directory = tmp_path_factory.mktemp("spectral-grid")
    tiled_path, spectral_path = directory / "tiled.so", directory / "spectral.so"
    pilot_kernel.compile_filter(tiled_path)
    spectral_grid.compile_filter(spectral_path)
    tiled = anchor_grid.native_grid(tiled_path)
    return tiled, spectral_grid.SpectralGrid(spectral_path, tiled)


def _iq(pattern, rate=RATE):
    rng = np.random.default_rng(727403)
    iq = rng.integers(-32768, 32768, size=(2, rate // 50))
    if pattern == "sparse":
        iq[:, 0] = (1, 0)
        iq[:, 1::2] %= 2
        iq[:, 2::13] = 0
        for offset in range(0, iq.shape[1], 64):
            iq[:, offset + 24:offset + 49] %= 2
    return iq[0] + 1j * iq[1]


def _retain(function, scores, epochs=EPOCHS):
    return function(FREQUENCIES, scores, 8, 20, 80_000, epochs)


@pytest.mark.parametrize("rate", [RATE, 10_000_000])
@pytest.mark.parametrize("edge,step,pattern", [("lower", 26, "full"), ("upper", 14, "sparse")])
def test_dense_map_guard_and_selected_tiles(kernels, rate, edge, step, pattern):
    tiled, spectral = kernels
    epochs = round(rate / 750)
    template = qin_edge_pilot_frame(rate, edge)
    args = (_iq(pattern, rate), template, rate, FREQUENCIES, tuple(range(2, 302, step)), epochs)
    direct = np.asarray(tiled(*args))
    scores = spectral.score_grid(*args)
    error = np.max(abs(np.asarray(scores) - direct))
    assert 0 < error < spectral.receipts[-1]["error_bound"]
    peaks = _retain(spectral.retain_peaks, scores, epochs)
    assert peaks == _retain(anchor_grid.retained_peaks, direct, epochs)
    assert spectral.receipts[-1]["fallback"] is None
    assert 0 < spectral.receipts[-1]["repaired_cells"] < direct.size
    for _, epoch, cfo in peaks:
        index = FREQUENCIES.index(cfo)
        nearby = slice(max(0, epoch - 1), min(epochs, epoch + 2))
        np.testing.assert_array_equal(scores[index][nearby], direct[index, nearby])


def test_zero_energy_and_unsupported_sample_representation(kernels):
    tiled, spectral = kernels
    template = qin_edge_pilot_frame(RATE, "upper")
    args = (template, RATE, FREQUENCIES, (2, 28, 54), EPOCHS)
    scores = spectral.score_grid(np.zeros(50_000), *args)
    np.testing.assert_array_equal(scores, tiled(np.zeros(50_000), *args))
    assert _retain(spectral.retain_peaks, scores) == _retain(anchor_grid.retained_peaks, scores)
    assert spectral.receipts[-1]["repair_tiles"] == 0

    fractional = _iq("full") + 0.25j
    scores = spectral.score_grid(fractional, *args)
    assert spectral.receipts[-1]["fallback"] == "unsupported_grid"
    np.testing.assert_array_equal(scores, tiled(fractional, *args))


def test_failed_selection_certificate_reruns_full_tiled_grid(kernels, monkeypatch):
    tiled, spectral = kernels
    args = (_iq("full"), qin_edge_pilot_frame(RATE, "lower"), RATE, FREQUENCIES,
            tuple(range(2, 302, 26)), EPOCHS)
    control = tiled(*args)
    scores = spectral.score_grid(*args)
    # Simulate unresolved contender intervals. The endpoint still receives the
    # complete direct map rather than accepting an unrepaired winner.
    monkeypatch.setattr(spectral, "_repair_contenders",
                        lambda grid, cutoff: np.zeros_like(grid.scores, dtype=bool))
    assert _retain(spectral.retain_peaks, scores) == _retain(anchor_grid.retained_peaks, control)
    assert spectral.receipts[-1]["fallback"] == "overlapping_selection_intervals"
    np.testing.assert_array_equal(scores, control)
