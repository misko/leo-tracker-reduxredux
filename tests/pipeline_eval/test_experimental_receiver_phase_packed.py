import ctypes as ct
from pathlib import Path
import platform

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental import receiver_build, receiver_phase_packed_build


pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(platform.machine() != "x86_64", reason="x86 packed fractional kernel"),
]


@pytest.fixture(scope="module")
def library(tmp_path_factory):
    file = tmp_path_factory.mktemp("phase-packed") / "receiver.so"
    receiver_phase_packed_build.overlay(receiver_build.build)(file, fftw=False, pack_stencil=True)
    lib = ct.CDLL(str(file))
    for name in ("correlated_fractional_mixed_reference", "correlated_fractional_mixed"):
        function = getattr(lib, name)
        function.argtypes, function.restype = [ct.c_void_p] * 8, None
    return lib


@pytest.mark.parametrize("zero", [False, True])
def test_packed_frame_relative_kernel_preserves_scalar_correlation_bytes(library, zero):
    cpuinfo = Path("/proc/cpuinfo").read_text()
    if " avx2 " not in cpuinfo or " fma " not in cpuinfo:
        pytest.skip("packed frame-relative correlation requires AVX2 and FMA")
    rng = np.random.default_rng(613)
    aperture = 64 * 44
    starts = np.arange(aperture, dtype="<i4") + 11
    starts[9:21] += 1
    iq = rng.integers(-32768, 32768, (aperture + 30, 2), dtype="<i2").astype("<f8")
    if zero:
        iq[:, 0] = -0.
        iq[:, 1] = 0.
    row = np.repeat(np.arange(3, dtype="<i4"), (19, aperture - 36, 17))
    weights = rng.normal(size=(3, 16))
    exact, rolled = rng.normal(size=(2, aperture, 2))
    computed = []
    for name in ("correlated_fractional_mixed_reference", "correlated_fractional_mixed"):
        a, b = np.empty((64, 2), dtype="<f8"), np.empty((64, 2), dtype="<f8")
        getattr(library, name)(*(array.ctypes.data for array in (iq, starts, row, weights, exact, rolled, a, b)))
        computed.append((a.tobytes(), b.tobytes()))
    assert computed[0] == computed[1]
