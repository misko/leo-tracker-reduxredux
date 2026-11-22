import ctypes as ct
from contextlib import ExitStack

import numpy as np
import pytest

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.experimental.receiver_build import build
from tools.pipeline_eval.variants.verifier_integration import FRAC_COMPLETE, Result

pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def libraries(tmp_path_factory):
    binaries = tmp_path_factory.mktemp("stencil")
    libraries = []
    for pack in (False, True):
        path = binaries / f"stencil-{pack}.so"
        build(path, fftw=False, pack_stencil=pack)
        libraries.append(ct.CDLL(str(path)))
    return tuple(libraries)


def test_each_packed_correlation_preserves_the_original_fused_terms(libraries):
    normal, packed = libraries
    original = normal.correlated_integer
    original.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, *[ct.c_void_p] * 5]
    original.restype = None
    stencil = packed.correlated_stencil
    stencil.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, *[ct.c_void_p] * 3]
    stencil.restype = None

    rng = np.random.default_rng(97105)
    iq = rng.integers(-32768, 32768, size=(30_000, 2), dtype=np.int16).astype("<f8")
    iq[618:663] = 0
    reference = rng.normal(size=(64 * 44, 2))
    angles = np.arange(len(reference)) * (-np.pi / 18.7)
    phase = np.column_stack((np.cos(angles), np.sin(angles)))
    starts = np.array([613, 1001, 27827 - len(phase)], dtype="<i4")
    indices = starts + np.arange(4, dtype="<i4")[:, None]
    rows = np.zeros(4, dtype="<i4")
    expected = np.zeros((4, len(starts), 64, 2), dtype="<f8")
    original(iq.ctypes.data, indices.ctypes.data, 4, len(starts), rows.ctypes.data,
             phase.ctypes.data, reference.ctypes.data, None, expected.ctypes.data, None)
    actual = np.zeros((4, 15, 64, 2), dtype="<f8")
    stencil(iq.ctypes.data, starts.ctypes.data, len(starts), phase.ctypes.data,
            reference.ctypes.data, actual.ctypes.data)
    assert actual[:, :len(starts)].tobytes() == expected.tobytes()


def test_fractional_result_and_flags_are_exact_across_the_stencil_boundaries(libraries):
    rate, edge = 10_000_000, "upper"
    exact = qin_edge_pilot_frame(rate, edge).astype("<c16")
    control = qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL).astype("<c16")
    synth = qin_edge_pilot_frame(3 * rate, edge)
    iq = np.random.default_rng(47).integers(-256, 257, size=(200000, 2, 2), dtype=np.int16)
    iq[:, 0] = 0
    waveform, _ = unit_wave(synth, 3 * 200 + 1, -358000, 143, False)
    iq, clips = mix(iq, 1, [(waveform, 7)])
    assert not clips
    latest_full = len(iq) - (14 * 40_000 + 1) // 3 - 66 * 44
    with ExitStack() as stack:
        receivers = []
        for library in libraries:
            library.portable_verifier_create.argtypes = [ct.c_void_p, ct.c_void_p]
            library.portable_verifier_create.restype = ct.c_void_p
            library.portable_verifier_free.argtypes = [ct.c_void_p]
            library.portable_verifier_free.restype = None
            load = library.portable_verifier_load
            load.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_uint]
            load.restype = ct.c_int
            factor = library.portable_verifier_factor
            factor.argtypes = [ct.c_void_p, ct.c_uint, ct.POINTER(Result)]
            factor.restype = ct.c_int
            context = library.portable_verifier_create(exact.ctypes.data, control.ctypes.data)
            assert context
            stack.callback(library.portable_verifier_free, context)
            receivers.append((context, load, factor))
        fractional = False
        cases = (200, 201, 0, 1, 13331, 13332, latest_full - 2, latest_full, latest_full + 2)
        for lane in (1, 0):
            for context, load, _ in receivers:
                assert load(context, iq.ctypes.data, lane) == 0
            for epoch in cases:
                for hz in (-358000., 250000.):
                    results = []
                    for context, _, factor in receivers:
                        result = Result(acquired_hz=hz)
                        assert factor(context, epoch, ct.byref(result)) == 0
                        results.append(result)
                    assert bytes(results[0]) == bytes(results[1])
                    fractional |= bool(results[0].flags & FRAC_COMPLETE)
        assert fractional
