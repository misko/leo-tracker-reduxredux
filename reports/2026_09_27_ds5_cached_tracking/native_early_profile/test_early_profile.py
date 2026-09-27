from pathlib import Path
import sys

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from early_profile import NativeEarly, base
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from leo.analysis.starlink.templates import qin_edge_pilot_frame
import leo.analysis.starlink.pilot_methods as application


def test_oracle_is_current_checkout():
    assert Path(application.__file__).resolve() == HERE.parents[2] / 'src/leo/analysis/starlink/pilot_methods.py'


@pytest.mark.parametrize('rate', [2500000, 5000000])
@pytest.mark.parametrize('edge', ['lower', 'upper'])
@pytest.mark.parametrize('region', ['noise', 'early', 'late'])
@pytest.mark.parametrize('cfo', [-400000., 0., 400000.])
def test_integer_raw_guided_matches_application(rate, edge, region, cfo):
    raw = np.random.default_rng(92741).integers(-200, 201, (rate * 120 // 1000, 2, 2), dtype=np.int16)
    epoch = 317
    window = rate // 50
    if region != 'noise':
        template = np.asarray(qin_edge_pilot_frame(rate, edge)).copy()
        # Restrict the injected pilot to one known 64-symbol region.
        symbol = 2 if region == 'early' else 152
        lo, hi = round(symbol * 4.4e-6 * rate), round((symbol + 64) * 4.4e-6 * rate)
        template[:lo] = 0
        template[hi:] = 0
        for frame in range(16):
            start = len(raw) - window + epoch + round(frame * rate / 750)
            stop = min(len(raw), start + len(template))
            if stop > start:
                values = 3000 * template[:stop-start]
                raw[start:stop, 1, 0] += np.rint(values.real).astype(np.int16)
                raw[start:stop, 1, 1] += np.rint(values.imag).astype(np.int16)
    before = raw.copy()
    samples = raw[-window:, 1, 0].astype(float) + 1j * raw[-window:, 1, 1]
    expected = conditioned_glrt64_score(samples, rate, epoch_sample=epoch, acquired_cfo_hz=cfo, edge=edge)
    with NativeEarly(rate, edge) as engine:
        actual = engine.guided(raw, receiver=1, probe_index=10,
            predicted_local_epoch_sample=float(epoch), scoring_cfo_hz=cfo, expected_physical_cfo_hz=cfo)
    assert actual is not None
    assert actual.exact_score == pytest.approx(expected.exact_score, abs=1e-5)
    assert actual.control_score == pytest.approx(expected.control_score, abs=1e-5)
    assert actual.tracking_cfo_hz == pytest.approx(expected.tracking_cfo_hz, abs=1.)
    if region == 'late' and cfo == 0.:
        with base.NativeGuidedBoundary(rate, edge) as original:
            diverse = original.guided(raw, receiver=1, probe_index=10,
                predicted_local_epoch_sample=float(epoch), scoring_cfo_hz=0., expected_physical_cfo_hz=0.)
        assert diverse is not None
        assert actual.margin < .025 < diverse.margin
    np.testing.assert_array_equal(raw, before)
