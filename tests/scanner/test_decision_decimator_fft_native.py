"""Explicit FFTW-float dependency; verify overlap-save against integer FIR."""

import ctypes as ct
import os
from pathlib import Path

import numpy as np
import pytest

from tools.native_presence import pointer
from tools.prepare_decimated_dwell_replay import build, coefficients, reference

pytestmark = pytest.mark.fftw


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    prefix = os.environ.get("FFTW_FLOAT_PREFIX")
    if not prefix:
        pytest.fail("fftw-marked decimator tests require FFTW_FLOAT_PREFIX with libfftw3f.a")
    path = build(
        tmp_path_factory.mktemp("decimator-fft") / "dsp.so",
        shared=True,
        fftw_float_prefix=Path(prefix),
    )
    lib = ct.CDLL(str(path))
    lib.leo_decimator_create.argtypes = [
        ct.c_void_p,
        ct.c_uint,
        ct.c_void_p,
        ct.c_uint,
        ct.c_size_t,
    ]
    lib.leo_decimator_create.restype = ct.c_void_p
    lib.leo_decimator_run.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_void_p]
    lib.leo_decimator_run.restype = ct.c_int
    lib.leo_decimator_destroy.argtypes = [ct.c_void_p]
    return lib


@pytest.mark.parametrize("count", [4, 860, 864, 868, 1728, 1732, 1200000])
def test_overlap_save_full_scale_boundaries_reset_and_precision(native, count):
    h1, h2 = coefficients("direct")
    rng = np.random.default_rng(929)
    impulse = np.zeros((count, 2), dtype=np.int16)
    for index in (0, 159, 160, 863, 864, 865, 1727, 1728, count - 1):
        if index < count:
            impulse[index] = [32767, -32768]
    cases = [
        rng.integers(-32768, 32768, (count, 2), dtype=np.int16),
        impulse,
        np.full((count, 2), 32767, dtype=np.int16),
        np.full((count, 2), -32768, dtype=np.int16),
        np.zeros((count, 2), dtype=np.int16),
    ]
    workspace = native.leo_decimator_create(None, 0, pointer(h2), len(h2), count)
    assert workspace
    try:
        for iq in cases:
            output = np.full((count // 4, 2), 123, dtype=np.int16)
            assert native.leo_decimator_run(workspace, pointer(iq), count, pointer(output)) == 0
            expected = reference(iq, h1, h2)
            assert np.max(np.abs(output.astype(np.int32) - expected.astype(np.int32))) <= 2
        output.fill(123)
        status = native.leo_decimator_run(workspace, pointer(cases[0]), count + 4, pointer(output))
        assert status == -1
        assert np.all(output == 123)
    finally:
        native.leo_decimator_destroy(workspace)
