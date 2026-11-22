import ctypes as ct
from pathlib import Path

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental.receiver_build import build


pytestmark = pytest.mark.hardware


@pytest.fixture(scope="module")
def fir(tmp_path_factory):
    path = tmp_path_factory.mktemp("integer-fir") / "receiver.so"
    build(path, fftw=False, integer_fir=True)
    library = ct.CDLL(str(path))
    reference = library.delay_decimate
    reference.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p]
    reference.restype = ct.c_int
    integer = library.delay_decimate_integer
    integer.argtypes = [*reference.argtypes[:-1], ct.c_int, ct.c_void_p]
    integer.restype = ct.c_int

    def run(iq, coeff, mixed=False, stride=4):
        original, quantized = [np.empty((len(iq) // stride, 2), dtype="<f4") for _ in range(2)]
        args = (iq.ctypes.data, coeff.ctypes.data, len(coeff), stride)
        assert reference(*args, original.ctypes.data) == 0
        assert integer(*args, mixed, quantized.ctypes.data) == 0
        return original, quantized

    return run


@pytest.mark.parametrize("mixed", [False, True])
def test_integer_fir_matches_signed_dot_products_and_exact_edges(fir, mixed):
    cpuinfo = Path("/proc/cpuinfo").read_text().splitlines()
    if not any(line.startswith("flags") and "avx_vnni" in line.split() for line in cpuinfo):
        pytest.skip("the packed Q15 assertions require AVX-VNNI")
    rng = np.random.default_rng(489)
    iq = rng.integers(-32768, 32768, (200000, 2), dtype="<i2").astype("<f4")
    iq[45:166] = -32768
    if mixed:
        iq = np.column_stack((iq[:, 0] + iq[:, 1], iq[:, 1] - iq[:, 0])) * np.float32(0.5**0.5)
    half = rng.uniform(-0.02, 0.02, 40).astype("<f4")
    coeff = np.r_[half, np.float32(0.25701), half[::-1]]
    original, calculated = fir(iq, coeff, mixed)
    weights = np.copysign(np.floor(np.abs(coeff * 32768) + 0.5), coeff).astype(np.int64)
    scale = 2 if mixed else 1
    packed = np.rint(iq / scale).astype(np.int64)
    indices = np.r_[10:45, 49950:49990, 101:49900:37]
    centers = packed[4 * indices[:, None] + np.arange(-40, 41)]
    expected = np.sum(centers * weights[None, :, None], axis=1).astype(np.float32) * (scale / 32768)
    assert calculated[indices].tobytes() == expected.tobytes()
    assert calculated[:10].tobytes() == original[:10].tobytes()
    assert calculated[-10:].tobytes() == original[-10:].tobytes()
    assert np.any(calculated[indices] != original[indices])


@pytest.mark.parametrize("fallback", ["unsafe_sum", "asymmetric", "other_stride"])
def test_integer_fir_falls_back_to_original_samples(fir, fallback):
    iq = np.arange(400000, dtype=np.int16).reshape(-1, 2).astype("<f4")
    coeff = np.zeros(81, dtype="<f4")
    coeff[40] = 0.2
    stride = 4
    if fallback == "unsafe_sum":
        coeff[:] = 0.5
    elif fallback == "asymmetric":
        coeff[31] = 0.083
    else:
        stride = 3
    original, calculated = fir(iq, coeff, stride=stride)
    assert calculated.tobytes() == original.tobytes()
