import numpy as np
import pytest

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.variants import fine_search as prefix


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    path, _ = prefix.build(tmp_path_factory.mktemp("fine-search"))
    return path


def test_prefix_keeps_all_original_scores_across_boundaries_and_scratch_reuse(library):
    fine = prefix.FineSearch(library, acquisition)
    assert fine.compatible
    rng = np.random.default_rng(50091)
    carriers = rng.integers(-2048, 2048, size=(2, prefix.SAMPLES, 2)).astype(float)
    values = carriers.view(np.complex128).reshape(2, prefix.SAMPLES)
    values[1] = 0
    work = (
        (0, "lower", 0, 321),
        (0, "upper", prefix.EPOCHS - 1, 161),
        (1, "upper", 4, 320),
        (0, "lower", 10, 160),
        (0, "upper", prefix.EPOCHS - 1, 2),
    )
    for item, (receiver, edge, epoch, count) in enumerate(work):
        center = (-1) ** item * 731_231.125
        frequencies = tuple(center + 500 * index for index in range(count))
        template = np.asarray(acquisition.qin_edge_pilot_frame(prefix.RATE, edge), np.complex128)
        args = values[receiver], template, prefix.RATE, epoch, frequencies, prefix.SYMBOLS
        expected = fine.original(*args, transform_size=prefix.FFT_SIZE)
        with fine.route():
            assert (
                acquisition._normalized_frame_scores_fft(*args, transform_size=prefix.FFT_SIZE)
                == expected
            )
        assert acquisition._normalized_frame_scores_fft is fine.original
    assert fine.calls == len(work)
    assert fine.fallbacks == 0
    assert fine.frames == 73


def test_alternate_geometry_and_failed_runtime_sentinel_keep_original_dispatch(library):
    fine = prefix.FineSearch(library, acquisition)
    values = np.zeros(prefix.SAMPLES, dtype=np.complex128)
    template = np.asarray(acquisition.qin_edge_pilot_frame(prefix.RATE, "lower"), np.complex128)
    args = values, template, prefix.RATE, 0, (0.0, 500.0)
    for symbols in (prefix.SYMBOLS[1:], prefix.SYMBOLS):
        complete = (*args, symbols)
        expected = fine.original(*complete, transform_size=prefix.FFT_SIZE)
        assert fine.score(*complete, transform_size=prefix.FFT_SIZE) == expected
        fine.compatible = False
    assert fine.calls == 0
    assert fine.fallbacks == 2
