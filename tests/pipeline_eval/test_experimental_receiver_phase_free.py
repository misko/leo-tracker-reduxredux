import ctypes as ct
from contextlib import ExitStack

import numpy as np
import pytest

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.experimental.receiver_build import build
from tools.pipeline_eval.variants.experimental.receiver_phase_trial import phase_stats
from tools.pipeline_eval.variants.verifier_integration import FRAC_COMPLETE, Result


@pytest.fixture(scope="module")
def binaries(tmp_path_factory):
    work = tmp_path_factory.mktemp("frame-relative-verifier")
    paths = work / "original.so", work / "relative.so"
    for binary, alternate in zip(paths, (False, True), strict=True):
        build(binary, fftw=False, fma=False, phase_free=alternate)
    return paths


def invoke(binary, iq, lane, jobs, *, diagnostic=False):
    lib = ct.CDLL(str(binary))
    lib.portable_verifier_create.argtypes = [ct.c_void_p, ct.c_void_p]
    lib.portable_verifier_create.restype = ct.c_void_p
    lib.portable_verifier_free.argtypes = [ct.c_void_p]
    lib.portable_verifier_free.restype = None
    lib.portable_verifier_load.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_uint]
    lib.portable_verifier_load.restype = ct.c_int
    mode = lib.portable_verifier_glrt if diagnostic else lib.portable_verifier_factor
    mode.argtypes = [ct.c_void_p, ct.c_uint, ct.POINTER(Result)]
    mode.restype = ct.c_int
    templates = [qin_edge_pilot_frame(10_000_000, "upper", symbol_roll=roll).astype("<c16")
                 for roll in (0, CONTROL_SYMBOL_ROLL)]
    with ExitStack() as resources:
        w = lib.portable_verifier_create(*(template.ctypes.data for template in templates))
        assert w
        resources.callback(lib.portable_verifier_free, w)
        assert lib.portable_verifier_load(w, iq.ctypes.data, lane) == 0
        results = []
        for epoch, hz in jobs:
            result = Result(acquired_hz=hz)
            assert mode(w, epoch, ct.byref(result)) == 0
            results.append(result)
        return results


def test_frame_relative_scores_keep_fractional_phase_signed_carrier_and_gate(binaries):
    rng = np.random.default_rng(62)
    iq = rng.integers(-400, 401, (200_000, 2, 2), dtype=np.int16)
    pilot = qin_edge_pilot_frame(30_000_000, "upper")
    for lane, hz, epoch in ((0, -358000., 200), (1, 238000., 1700)):
        wave, _ = unit_wave(pilot, 3 * epoch + 1, hz, 143, False)
        planted, clipping = mix(iq, lane, [(wave, 9)])
        assert not clipping
        jobs = [(epoch, hz)]
        before, = invoke(binaries[0], planted, lane, jobs)
        phase_stats(binaries[1])
        after, = invoke(binaries[1], planted, lane, jobs)
        trace = phase_stats(binaries[1])
        assert trace == dict(attempted=1, accepted=1, fallback=0, margin_order_retries=0)
        assert before.flags == after.flags and after.flags & FRAC_COMPLETE
        assert bytes(before.exact_grid) == bytes(after.exact_grid)
        assert before.offset_samples == after.offset_samples
        assert before.fractional_residual_hz == after.fractional_residual_hz
        np.testing.assert_allclose(
            [before.fractional_exact, before.fractional_control],
            [after.fractional_exact, after.fractional_control], atol=2e-11, rtol=0.,
        )
        oracle, = invoke(binaries[0], planted, lane, jobs, diagnostic=True)
        diagnostic, = invoke(binaries[1], planted, lane, jobs, diagnostic=True)
        assert bytes(oracle) == bytes(diagnostic)


def test_low_amplitude_ambiguous_spectrum_uses_the_stock_evaluation(binaries):
    iq = np.random.default_rng(909).integers(-1, 2, (200_000, 2, 2), dtype=np.int16)
    jobs = [(epoch, 4_900_000.) for epoch in range(100, 1701, 100)]
    phase_stats(binaries[1])
    actual = invoke(binaries[1], iq, 1, jobs)
    trace = phase_stats(binaries[1])
    assert trace["fallback"] > 0 and trace["accepted"] == 0
    assert list(map(bytes, actual)) == list(map(bytes, invoke(binaries[0], iq, 1, jobs)))
