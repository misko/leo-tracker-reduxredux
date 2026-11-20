import numpy as np
import pytest

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.variants import conditioned_cfo_bank, fine_batch, fine_search


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    if not fine_batch.supports_host():
        pytest.skip("requires AVX2 frame lanes")
    path, _ = fine_batch.build(tmp_path_factory.mktemp("fine-batch"))
    return path


@pytest.mark.hardware
def test_frame_batch_preserves_all_bins_for_real_geometry_and_exact_score_ties(library):
    batch = fine_batch.FineBatch(library, acquisition)
    assert batch.compatible
    assert batch.work.ctypes.data % 32 == 0
    rng = np.random.default_rng(20261119)
    random = rng.integers(-8192, 8192, (fine_search.SAMPLES, 2)).astype(float).view(complex).ravel()
    blank = np.zeros_like(random)
    for values, edge, epoch, bins, first in (
        (random, "upper", 0, 321, -790_000.125),
        (random, "lower", fine_search.EPOCHS - 1, 161, 610_000.25),
        (blank, "lower", 92, 321, -80_000.0),
        (random, "upper", 1, 320, -790_000.125),
    ):
        template = acquisition.qin_edge_pilot_frame(fine_search.RATE, edge).astype(complex)
        grid = tuple(first + 500 * bin for bin in range(bins))
        args = values, template, fine_search.RATE, epoch, grid, fine_search.SYMBOLS
        expected = batch.original(*args, transform_size=fine_search.FFT_SIZE)
        actual = batch.score(*args, transform_size=fine_search.FFT_SIZE)
        assert actual == expected
        if values is blank:
            assert actual == (0.0,) * len(grid)
    assert batch.calls == 4
    assert batch.frames == 58
    assert batch.fallbacks == 0


@pytest.mark.hardware
def test_conditioned_tie_remains_on_original_score_path(library, tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    cfo_lib = tmp_path / "cfo.so"
    conditioned_cfo_bank.compile_bank(cfo_lib)
    cfo = conditioned_cfo_bank.ConditionedBank(cfo_lib, acquisition)
    batch = fine_batch.FineBatch(library, acquisition)
    template = acquisition.qin_edge_pilot_frame(fine_search.RATE, "lower").astype(complex)
    values = np.tile(template, 16)[: fine_search.SAMPLES].copy()
    for start in fine_search.FRAME_BASE:
        values[start : start + len(template)] = template
    grid = (-1000.0, -500.0, 0.0, 500.0, 1000.0)
    geometry = values, template, fine_search.RATE, 0
    with batch.route():
        fine = acquisition._normalized_frame_scores_fft(
            *geometry, grid, fine_search.SYMBOLS, transform_size=fine_search.FFT_SIZE
        )
        assert int(np.argmax(fine)) == 2
        args = (*geometry, (-50.0, 50.0))
        assert cfo.score(*args) == cfo.original(*args)
    assert batch.calls == 1
    assert cfo.receipts[-1]["fallback"] == "overlapping_score_intervals"


def test_batch_installation_requires_avx2(tmp_path, monkeypatch):
    monkeypatch.setattr(fine_batch, "supports_host", lambda: False)
    with pytest.raises(RuntimeError, match="requires AVX2"):
        fine_batch.build(tmp_path)
