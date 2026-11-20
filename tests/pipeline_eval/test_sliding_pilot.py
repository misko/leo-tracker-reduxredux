import numpy as np
import pytest

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.variants import fine_batch
from tools.pipeline_eval.variants import sliding_pilot as rolling


def test_physical_tones_and_boundary_tap_explain_both_template_families():
    for edge in ("lower", "upper"):
        for symbols, seam_count in ((acquisition.DEFAULT_ANCHOR_SYMBOLS, 1), (rolling.RETRY, 4)):
            model = rolling.family(edge, symbols)
            assert tuple(model.tones_hz) == tuple(117_187.5 * np.arange(-7, 8, 2))
            assert np.count_nonzero(model.seam) == seam_count
            assert 0 < model.relative_error < 3.1e-8
            assert 0 < model.tap_error < 1.0e-7


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    if not fine_batch.supports_host():
        pytest.skip("requires AVX2 rolling tone lanes")
    return rolling.build(tmp_path_factory.mktemp("sliding-pilot"))[0]


@pytest.mark.hardware
def test_rolling_bank_matches_direct_cfo_and_fold_at_real_support_boundaries(native):
    rng = np.random.default_rng(365182)
    source = rng.integers(-4096, 4096, (2, rolling.SAMPLES))
    values = source[0] + 1j * source[1]
    frequencies = tuple(np.arange(-800_000, 800_001, 80_000) + 92_315.125)
    for edge, symbols in (("upper", acquisition.DEFAULT_ANCHOR_SYMBOLS), ("lower", rolling.RETRY)):
        model = rolling.family(edge, symbols)
        template = rolling.template_for(edge)
        bank = rolling.SlidingPilotGrid(native, use_float=True, use_pairs=len(symbols) == 22)
        grid = bank.score_grid(
            acquisition,
            None,
            values,
            template,
            rolling.RATE,
            frequencies,
            symbols,
            rolling.EPOCHS,
        )
        for lane, epoch in ((0, 0), (20, 13332), (9, 37)):
            phase = np.exp(-2j * np.pi * frequencies[lane] * np.arange(rolling.TAPS) / rolling.RATE)
            correlations = []
            for start in model.starts:
                ref = template[start : start + rolling.TAPS]
                for frame in rolling.FRAME_BASE:
                    position = frame + start + epoch
                    if position + rolling.TAPS <= len(values):
                        wave = values[position : position + rolling.TAPS]
                        correlations.append(
                            abs(np.vdot(ref, wave * phase))
                            / (np.linalg.norm(wave) * np.linalg.norm(ref))
                        )
            assert len(correlations) == model.support[epoch]
            assert grid[lane][epoch] == pytest.approx(np.mean(correlations), abs=1e-6)
        assert bank.calls[0]["inverse_ffts"] == 0
        assert rolling.drift(bank.library, values, frequencies[0])["normalized_max"] <= 1e-10
