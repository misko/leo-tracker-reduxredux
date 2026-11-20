import numpy as np

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.variants import anchor_grid, prepared_hotpath_peaks
from tools.pipeline_eval.variants.prepared_hotpath import FFT_SIZE, SYMBOLS, FineWorkspace
from tools.pipeline_eval.variants.refine_bank import RATE, SAMPLES


def test_fine_fft_reuses_only_geometry_and_keeps_every_score_exact():
    rng = np.random.default_rng(19718)
    values = rng.integers(-2048, 2048, (2, SAMPLES, 2)).astype(np.float64).view(np.complex128)
    grid = tuple(-768_750.125 + 500 * i for i in range(321))
    backing = FineWorkspace(acquisition)
    check = backing.original
    data = ((0, "lower", 10), (1, "upper", 13_332), (0, "upper", 9), (1, "lower", 13_000))
    for index, edge, epoch in data:
        template = np.asarray(acquisition.qin_edge_pilot_frame(RATE, edge), dtype=np.complex128)
        args = values[index, :, 0], template, RATE, epoch, grid, SYMBOLS
        assert check(*args, transform_size=FFT_SIZE) == backing.score(
            *args, transform_size=FFT_SIZE
        )
    assert backing.applied == len(data)
    assert backing.fallbacks == 0

    template = np.asarray(acquisition.qin_edge_pilot_frame(RATE, "lower"), dtype=np.complex128)
    args = np.zeros(SAMPLES, dtype=np.complex128), template, RATE, 111, grid, SYMBOLS[1:]
    assert check(*args, transform_size=FFT_SIZE) == backing.score(*args, transform_size=FFT_SIZE)
    assert backing.fallbacks == 1


def test_routed_selector_preserves_discovery_order_at_a_one_ulp_tie():
    peaks = np.zeros((4, 64))
    peaks[0, [1, 56]] = 1.0
    peaks[1, [1, 10]] = 1.0
    peaks[2, [16, 60]] = np.nextafter(1.0, np.inf)
    peaks[3, [0, 40]] = 1.0
    args = (80_000.0, -80_000.0, 160_000.0, 0.0), tuple(peaks), 8, 9, 80_000.0, 64
    original = acquisition._retain_score_map_peaks
    assert prepared_hotpath_peaks.retained_peaks(*args) == original(*args)
    with FineWorkspace(acquisition).route(selector=anchor_grid.retained_peaks):
        assert acquisition._retain_score_map_peaks(*args) == original(*args)
    assert acquisition._retain_score_map_peaks is original


def test_first_peak_per_lane_matches_heap_on_repeated_scores():
    rng = np.random.default_rng(9153)
    for epochs in (1, 2, 64, 13333):
        scores = rng.integers(0, 13, size=(7, epochs)).astype(float)
        grid = (0.0, -80_000.0, 80_000.0, -160_000.0, 160_000.0, 240_000.0, 0.0)
        args = grid, tuple(scores), 8, 20, 80_000.0, epochs
        assert prepared_hotpath_peaks.retained_peaks(*args) == acquisition._retain_score_map_peaks(
            *args
        )
