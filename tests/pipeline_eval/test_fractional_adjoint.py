import numpy as np
import pytest

from leo.analysis.starlink import fast_scan_scores
from tools.pipeline_eval.variants import fractional_adjoint, refine_bank

pytestmark = pytest.mark.hardware  # The locked fused reference uses NumPy X86_V3 arithmetic.


@pytest.fixture(scope="module")
def libraries(tmp_path_factory):
    root = tmp_path_factory.mktemp("fractional-adjoint")
    fast, locked = root / "adjoint.so", root / "fused.so"
    fractional_adjoint.compile_bank(fast)
    refine_bank.compile_bank(locked)
    return fast, locked


@pytest.mark.parametrize("epoch,offset", [(0, .2315653), (13332, -.212457), (900, 1.678234)])
def test_negative_scores_and_raw_cfo_match_the_fused_reference(libraries, epoch, offset):
    fast, locked = libraries
    original = refine_bank.RefinementBank(locked, fast_scan_scores)
    adjoint = fractional_adjoint.Adjoint(fast, original)
    rng = np.random.default_rng(118)
    iq = rng.integers(-400, 400, (2, refine_bank.SAMPLES))
    samples = iq[0] + 1j * iq[1]
    args = dict(epoch_sample=epoch, acquired_cfo_hz=120332.456,
                fractional_epoch_offset_samples=offset)
    expected = original.fractional(samples, refine_bank.RATE, **args)
    actual = adjoint.score(samples, refine_bank.RATE, **args)
    assert adjoint.receipts[-1]["fallback"] is None
    assert actual.tracking_cfo_hz == expected.tracking_cfo_hz
    assert np.allclose((actual.exact_score, actual.control_score, actual.margin),
                       (expected.exact_score, expected.control_score, expected.margin),
                       rtol=0, atol=1e-9)


def test_positive_uses_original_full_score(libraries):
    fast, locked = libraries
    original = refine_bank.RefinementBank(locked, fast_scan_scores)
    adjoint = fractional_adjoint.Adjoint(fast, original)
    template = fast_scan_scores.qin_edge_pilot_frame(refine_bank.RATE, "lower")
    values = np.zeros(refine_bank.SAMPLES, dtype=np.complex128)
    for f in refine_bank.FRAME_BASE:
        start = f + 731
        n = min(len(template), len(values) - start)
        values[start:start + n] = template[:n]
    args = dict(epoch_sample=731, acquired_cfo_hz=0., fractional_epoch_offset_samples=0.125)
    expected = original.fractional(values, refine_bank.RATE, **args)
    assert expected.margin >= fractional_adjoint.GATE
    assert adjoint.score(values, refine_bank.RATE, **args) == expected
    assert adjoint.receipts[-1]["fallback"] == "positive_or_gate_overlap"


def test_certification_checks_both_bin_and_margin():
    bounds = np.array([1e-6, 2e-6])
    map_ = np.zeros((2, refine_bank.GLRT_SIZE))
    map_[0, 3:5] = .5
    map_[1, 71] = .499
    assert fractional_adjoint.rejection(map_, bounds)[0] == "unresolved_frequency_bin"
    map_[0, 4] = .45
    map_[1, 71] = .4750001
    assert fractional_adjoint.rejection(map_, bounds)[0] == "positive_or_gate_overlap"
    map_[1, 71] = .478
    assert fractional_adjoint.rejection(map_, bounds) == (None, 3)
