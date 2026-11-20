from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink.templates import qin_edge_pilot_frame
from tools.pipeline_eval.qualification.sparse_epoch_eval import _audit, matches
from tools.pipeline_eval.variants import anchor_grid, pilot_kernel, sparse_epoch

RATE = 10_000_000
EPOCHS = round(RATE / 750)
FREQUENCIES = (-717_709.0, -317_709.0, 2_291.0)


@pytest.fixture(scope="module")
def kernels(tmp_path_factory):
    folder = tmp_path_factory.mktemp("sparse-epoch")
    full, sparse = folder / "full.so", folder / "sparse.so"
    pilot_kernel.compile_filter(full)
    sparse_epoch.compile_grid(sparse)
    tiled = anchor_grid.native_grid(full)
    return tiled, sparse_epoch.SparseEpochGrid(sparse, tiled)


@pytest.mark.hardware  # The experimental SIMD kernels use AVX2.
@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_same_raw_taps_at_sampled_epochs_and_exact_neighbors_for_selected_peaks(kernels, edge):
    full, sparse = kernels
    iq = np.random.default_rng(778431).integers(-32768, 32768, (2, RATE // 50))
    args = (iq[0] + 1j * iq[1], qin_edge_pilot_frame(RATE, edge), RATE, FREQUENCIES,
            (2, 18, 44, 210, 301), EPOCHS)
    direct = np.asarray(full(*args))
    scores = sparse.score_grid(*args)
    _, scout = sparse._sparse
    np.testing.assert_allclose(scout, direct[:, ::sparse_epoch.STRIDE], atol=1e-7, rtol=0)
    peaks = sparse.retain_peaks(FREQUENCIES, scores, 8, 20, 80_000, EPOCHS)
    assert len(peaks) == 8
    assert sparse.receipts[-1]["scout_cells"] == len(FREQUENCIES) * 2223
    assert sparse.receipts[-1]["verified_cells"] <= len(FREQUENCIES) * 8 * 9
    for score, epoch, cfo in peaks:
        row = FREQUENCIES.index(cfo)
        neighbors = slice(max(0, epoch - 1), min(EPOCHS, epoch + 2))
        assert score == direct[row, epoch]
        np.testing.assert_array_equal(scores[row][neighbors], direct[row, neighbors])


@pytest.mark.hardware
def test_empty_and_non_adc_input_follow_reference_selection(kernels):
    full, sparse = kernels
    geometry = qin_edge_pilot_frame(RATE, "lower"), RATE, FREQUENCIES, (2, 28), EPOCHS
    for values, expected_fallback in ((np.zeros(RATE // 50), None),
                                      (np.full(RATE // 50, 0.25j), "unsupported_grid")):
        direct = full(values, *geometry)
        scores = sparse.score_grid(values, *geometry)
        assert sparse.retain_peaks(FREQUENCIES, scores, 8, 20, 80_000, EPOCHS) == (
            anchor_grid.retained_peaks(FREQUENCIES, direct, 8, 20, 80_000, EPOCHS))
        assert sparse.receipts[-1]["fallback"] == expected_fallback


def test_candidate_matching_uses_fractional_epoch_and_raw_cfo():
    left = dict(epoch=EPOCHS - 1, offset=-0.4, cfo=30_000)
    right = dict(epoch=0, offset=0.4, cfo=31_000)
    assert matches(left, right, EPOCHS)
    assert not matches(left, dict(right, offset=0.7), EPOCHS)
    assert not matches(left, dict(right, cfo=31_001), EPOCHS)
    assert not matches(dict(left, offset=2), dict(right, offset=-2), EPOCHS)


def test_candidate_matching_does_not_count_one_trial_candidate_twice():
    first = SimpleNamespace(candidate_rank=0, epoch_sample=700, fractional_epoch_offset_samples=0,
                            tracking_cfo_hz=48000, fractional_tracking_cfo_hz=48000,
                            margin=0.25, fractional_margin=0.25)
    alternate = SimpleNamespace(**dict(vars(first), candidate_rank=1, fractional_margin=0.35))
    control = SimpleNamespace(
        receivers=[SimpleNamespace(receiver_id=0, candidates=[first, alternate])]
    )
    result = SimpleNamespace(receivers=[SimpleNamespace(receiver_id=0, candidates=[alternate])])
    for receiver in (part[0] for part in _audit(control, result, EPOCHS).values()):
        assert len(receiver["missed_positive"]) == 1
        assert not receiver["new_positive"]
