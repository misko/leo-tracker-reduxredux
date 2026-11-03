import numpy as np
import pytest

from leo.analysis.starlink.pilot_predictor import PilotPredictor, native_library_path, pilot_period
from leo.contracts.digests import sha256_digest
from leo.scanner.fast_scan_analysis import VerifiedFastWindow, production_glrt
from tests.fast_scan_support import TARGET


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_planted_pilot_passes_predictor_and_fractional_glrt_at_known_cfo(edge):
    cfo = 150000.0
    z = np.tile(np.roll(pilot_period(edge), 217), 5)
    z *= np.exp(2j * np.pi * cfo * np.arange(50000) / 2500000)
    raw = np.empty((50000, 1, 2), dtype=np.int16)
    raw[:, 0, 0] = np.rint(z.real * 3000).astype(np.int16)
    raw[:, 0, 1] = np.rint(z.imag * 3000).astype(np.int16)
    score = PilotPredictor(native_library_path(), edge, 1).score_ci16(raw)[0]
    assert score["epoch_sample"] == 217 and score["margin"] > 0.8
    window = VerifiedFastWindow(
        0,
        sha256_digest(raw.tobytes()),
        {"actual_if_center_hz": 959687500},
        {**TARGET, "edge": edge},
        raw,
    )
    candidates = production_glrt(window, (0,))[0].candidates
    best = max(
        (c for c in candidates if c.fractional_margin is not None),
        key=lambda c: c.fractional_margin,
    )
    assert best.fractional_margin > 0.5
    assert best.fractional_tracking_cfo_hz == pytest.approx(cfo, abs=500)
