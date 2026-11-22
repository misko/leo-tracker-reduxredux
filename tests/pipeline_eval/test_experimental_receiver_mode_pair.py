import ctypes as ct
from pathlib import Path
import platform

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental import receiver_build, receiver_mode_pair_build


pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(platform.machine() != "x86_64", reason="paired generic x86-64 covariance"),
]


@pytest.fixture(scope="module")
def dots(tmp_path_factory):
    if " avx2 " not in Path("/proc/cpuinfo").read_text():
        pytest.skip("exercising the paired covariance products requires AVX2")
    binary = tmp_path_factory.mktemp("mode-pair") / "receiver.so"
    receiver_mode_pair_build.overlay(receiver_build.build)(binary, fftw=False, fma=False)
    lib = ct.CDLL(str(binary))
    function = lib.experimental_covariance_dots
    function.argtypes = [ct.c_void_p] * 3 + [ct.c_int, ct.c_int, ct.c_void_p]
    function.restype = None
    return function


@pytest.mark.parametrize("width", [0, 1, 3, 4, 17, 4740, 18964])
def test_paired_covariance_preserves_four_chain_sums_and_scalar_tail(dots, width):
    rng = np.random.default_rng(411)
    rows = [rng.normal(size=(width + 1, 2)).astype("<f4")[1:] for _ in range(3)]
    rows[0][::5] *= np.float32(1024.)
    rows[1][1::7] *= np.float32(1e-6)
    rows[2][1::3, 1] = -0.
    expected, actual = [np.empty((2, 2), dtype="<f4") for _ in range(2)]
    for partners in (rows[1:], (rows[0], rows[1]), (rows[1], rows[1])):
        args = [row.ctypes.data for row in (rows[0], *partners)]
        dots(*args, width, 0, expected.ctypes.data)
        dots(*args, width, 1, actual.ctypes.data)
        assert actual.tobytes() == expected.tobytes()
