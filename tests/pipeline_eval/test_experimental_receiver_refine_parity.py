import ctypes as ct
import platform
from pathlib import Path

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental.receiver_build import build


pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(platform.machine() != "x86_64", reason="x86 refinement bank build"),
]


class RefineRequest(ct.Structure):
    _fields_ = [("epoch", ct.c_int), ("hz", ct.c_double)]


RESULT = ct.c_double * 4
BAND = (-800000., 800000.)


@pytest.fixture(scope="module")
def refine(tmp_path_factory):
    binary = tmp_path_factory.mktemp("refine-parity") / "receiver.so"
    build(binary, fftw=False, fma=False, batch_refine=True, refine_parity=True)
    lib = ct.CDLL(str(binary))
    lib.delay_refine_bank.argtypes = [ct.c_void_p, ct.c_void_p, ct.POINTER(RefineRequest),
                                     ct.c_int, ct.c_double, ct.c_double, ct.POINTER(RESULT)]
    lib.delay_refine_parity.argtypes = [ct.c_void_p, ct.c_void_p, RefineRequest, ct.c_double,
                                       ct.c_double, ct.c_double, ct.POINTER(ct.c_double)]
    return lib


@pytest.fixture(scope="module")
def waveform():
    rng = np.random.default_rng(1605)
    iq = rng.integers(-32768, 32768, size=400000, dtype=np.int16).astype(np.float32)
    pilot = rng.normal(size=2 * 2816).astype(np.float32)
    return iq, pilot


def compare(refine, waveform, request, threshold):
    iq, pilot = waveform
    data = (iq.ctypes.data, pilot.ctypes.data)
    reference, candidate = RESULT(), RESULT()
    assert refine.delay_refine_bank(*data, ct.byref(request), 1, *BAND, ct.byref(reference)) == 0
    cutoff = reference[3] if threshold is None else threshold
    status = refine.delay_refine_parity(*data, request, *BAND, cutoff, candidate)
    if status == 1:
        assert reference[3] < cutoff
    else:
        assert status == 0
        assert bytes(reference) == bytes(candidate)
    return status


@pytest.mark.parametrize("epoch,hz", [(4, -795000.), (8540, 179031.), (13328, 799875.)])
def test_every_pruned_exact_score_is_below_the_incumbent(refine, waveform, epoch, hz):
    if " avx2 " not in Path("/proc/cpuinfo").read_text():
        pytest.skip("asserting exercised parity pruning requires AVX2")
    request = RefineRequest(epoch, hz)
    assert compare(refine, waveform, request, threshold=.25) == 1
    assert compare(refine, waveform, request, threshold=None) == 0


@pytest.mark.parametrize("epoch,hz,threshold", [
    (0, -600000., .25), (13332, 670000., .25), (5570, -0., 0.),
    (331, 0., float("inf")), (8867, -12000., 1e-9),
])
def test_wrapped_or_unresolved_scores_keep_reference_bytes(refine, waveform, epoch, hz, threshold):
    assert compare(refine, waveform, RefineRequest(epoch, hz), threshold) == 0
