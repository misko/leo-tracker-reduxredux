from struct import pack
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.starlink import acquisition
from tools.pipeline_eval.variants import fine_batch, fine_search
from tools.pipeline_eval.variants.fine_epoch_reuse import EpochBatch, GuardReuse


@pytest.mark.hardware
def test_share_aperture_but_keep_original_signed_cfo_transform(tmp_path):
    if not fine_batch.supports_host():
        pytest.skip("requires AVX2 frame lanes")
    library, _ = fine_batch.build(tmp_path)
    original = fine_batch.FineBatch(library, acquisition)
    shared = EpochBatch(library, acquisition)
    rng = np.random.default_rng(1416)
    iq = rng.integers(-8192, 8192, (fine_search.SAMPLES, 2)).astype(float).view(complex).ravel()
    for edge, signed in (("upper", -790_000.125), ("lower", 480_000.25)):
        template = acquisition.qin_edge_pilot_frame(fine_search.RATE, edge).astype(complex)
        grids = [tuple(signed + 500 * (i + offset) for i in range(161)) for offset in (0, 80)]
        blank = np.zeros_like(iq)

        def evaluate(probe, template=template, grids=grids):
            return [
                acquisition._normalized_frame_scores_fft(
                    probe,
                    template,
                    fine_search.RATE,
                    10123,
                    grid,
                    fine_search.SYMBOLS,
                    transform_size=fine_search.FFT_SIZE,
                )
                for grid in grids
            ]

        detector = SimpleNamespace(_evaluate_probe=evaluate)
        with original.route():
            control = detector._evaluate_probe(iq)
            zero = detector._evaluate_probe(blank)
        with shared.bind(detector):
            assert detector._evaluate_probe(iq) == control
            assert detector._evaluate_probe(blank) == zero
        assert not shared.apertures
        # An overlapping physical frequency is insufficient to reuse a bin verbatim.
        assert control[0][80:] != control[1][:81]
    assert shared.hits == 4


def test_recheck_guard_requires_same_wave_template_and_signed_cfo():
    bank = SimpleNamespace(_direct_only=False)
    reuse = GuardReuse(None, None, None, bank)
    wave = np.arange(5, dtype=np.complex128)
    exact = np.array([0.0, 1.0]).astype(complex)
    wrong = np.array([1.0, 0.0]).astype(complex)
    reuse.probe = wave
    zero_pos = pack("=d", 0.0)
    zero_neg = pack("=d", -0.0)
    assert reuse.record("verify", wave, exact, zero_pos, lambda: (1.0, 5)) == (1.0, 5)
    bank._direct_only = True
    assert reuse.record("verify", wave, exact.copy(), zero_pos, lambda: (2.0, 5)) == (1.0, 5)
    assert reuse.record("verify", wave, exact, zero_neg, lambda: (2.0, 5)) == (2.0, 5)
    assert reuse.record("verify", wave, wrong, zero_pos, lambda: (3.0, 5)) == (3.0, 5)
    assert reuse.record("verify", wave.copy(), exact, zero_pos, lambda: (4.0, 5)) == (4.0, 5)
    assert reuse.hits == {"verify": 1}
