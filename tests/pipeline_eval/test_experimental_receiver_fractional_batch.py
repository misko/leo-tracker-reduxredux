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
    root = tmp_path_factory.mktemp("fractional-batch")
    arms = []
    for packed in (False, True):
        binary = root / f"fractional-{packed}.so"
        build(binary, fftw=False, pack_stencil=True, batch_refine=True, fractional_batch=packed)
        arms.append(ct.CDLL(str(binary)))
    return tuple(arms)


def test_packed_interpolation_preserves_symbol_bytes_across_weight_rows(libraries):
    rng = np.random.default_rng(230)
    aperture = 64 * 44
    starts = np.arange(2 * aperture, dtype="<i4") + 11
    starts[6:8] += 1
    iq = rng.integers(-32768, 32768, size=(int(starts[-1]) + 16, 2), dtype=np.int16).astype("<f8")
    iq[11:30] = 0
    weights = rng.normal(size=(3, 16))
    rows = np.repeat(np.arange(3, dtype="<i4"), (73, aperture - 71, aperture - 2))
    angles = np.arange(len(starts)) * -np.pi / 8.3
    rotation = np.column_stack((np.cos(angles), np.sin(angles)))
    exact, control = rng.normal(size=(2, aperture, 2))
    results = []
    for library in libraries:
        correlate = library.correlated_fractional
        correlate.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, *[ct.c_void_p] * 7]
        correlate.restype = None
        out_exact = np.zeros((2, 64, 2), dtype="<f8")
        out_control = np.zeros_like(out_exact)
        remaining = rows, weights, rotation, exact, control, out_exact, out_control
        correlate(iq.ctypes.data, starts.ctypes.data, 2, *(a.ctypes.data for a in remaining))
        results.append((out_exact.tobytes(), out_control.tobytes()))
    assert results[0] == results[1]


@pytest.mark.parametrize("edge,hz", [("lower", 231000.), ("upper", -358000.)])
def test_complete_fractional_scores_and_gates_keep_their_exact_bytes(libraries, edge, hz):
    rate, epoch = 10_000_000, 200
    exact = qin_edge_pilot_frame(rate, edge).astype("<c16")
    control = qin_edge_pilot_frame(rate, edge, symbol_roll=CONTROL_SYMBOL_ROLL).astype("<c16")
    wave, _ = unit_wave(qin_edge_pilot_frame(3 * rate, edge), 3 * epoch + 1, hz, 143, False)
    iq = np.random.default_rng(62).integers(-300, 301, size=(200_000, 2, 2), dtype=np.int16)
    iq[:, 0] = 0
    iq, clips = mix(iq, 1, [(wave, 9)])
    assert not clips
    outputs = []
    with ExitStack() as stack:
        for library in libraries:
            create = library.portable_verifier_create
            create.argtypes = [ct.c_void_p, ct.c_void_p]
            create.restype = ct.c_void_p
            library.portable_verifier_free.argtypes = [ct.c_void_p]
            library.portable_verifier_free.restype = None
            load = library.portable_verifier_load
            load.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_uint]
            factor = library.portable_verifier_factor
            factor.argtypes = [ct.c_void_p, ct.c_uint, ct.POINTER(Result)]
            verifier = create(exact.ctypes.data, control.ctypes.data)
            assert verifier
            stack.callback(library.portable_verifier_free, verifier)
            results = []
            for lane in (0, 1):
                assert load(verifier, iq.ctypes.data, lane) == 0
                result = Result(acquired_hz=hz)
                assert factor(verifier, epoch, ct.byref(result)) == 0
                assert bool(result.flags & FRAC_COMPLETE) == bool(lane)
                results.append(bytes(result))
            outputs.append(results)
    assert outputs[0] == outputs[1]
