import ctypes as ct
import importlib.util
from pathlib import Path

import numpy as np
import pytest

spec = importlib.util.spec_from_file_location('fft32_build', Path(__file__).with_name('build.py'))
build_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_module)


class FFT(ct.Structure):
    _fields_ = [('size', ct.c_size_t), ('roots', ct.c_void_p), ('output', ct.c_void_p),
                ('scratch', ct.c_void_p), ('backend_plan', ct.c_void_p)]


@pytest.fixture(scope='module', params=['build.py', 'build_fftw.py'])
def library(request):
    spec = importlib.util.spec_from_file_location('fft_build_test',
                                                 Path(__file__).with_name(request.param))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lib = ct.CDLL(str(module.build()))
    lib.leo_fft_init.argtypes = [ct.POINTER(FFT), ct.c_size_t]
    lib.leo_fft_init.restype = ct.c_int
    lib.leo_fft_forward.argtypes = [ct.POINTER(FFT), ct.c_void_p]
    lib.leo_fft_free.argtypes = [ct.POINTER(FFT)]
    return lib


def output(plan):
    return np.ctypeslib.as_array((ct.c_double * (2 * plan.size)).from_address(
        plan.output)).view(np.complex128).copy()


@pytest.mark.parametrize('size', [2, 5, 10, 128, 512, 1024, 2500, 5000, 10000, 32768])
def test_integer_iq_transform_error_and_aliased_reuse(library, size):
    rng = np.random.default_rng(20260927 + size)
    iq = rng.integers(-32768, 32768, (size, 2)).astype(np.float64)
    values = np.ascontiguousarray(iq[:, 0] + 1j * iq[:, 1])
    plan = FFT()
    assert library.leo_fft_init(ct.byref(plan), size) == 0
    try:
        before = values.copy()
        library.leo_fft_forward(ct.byref(plan), values.ctypes.data)
        actual = output(plan)
        expected = np.fft.fft(values)
        assert np.linalg.norm(actual - expected) / np.linalg.norm(expected) < 2e-6
        assert np.max(np.abs(actual - expected)) / np.max(np.abs(expected)) < 2e-6
        np.testing.assert_array_equal(values, before)
        library.leo_fft_forward(ct.byref(plan), plan.output)
        repeated = output(plan)
        truth = np.fft.fft(actual)
        assert np.linalg.norm(repeated - truth) / np.linalg.norm(truth) < 2e-6
    finally:
        library.leo_fft_free(ct.byref(plan))
    assert not plan.output and not plan.backend_plan


def test_zero_impulse_and_rejected_sizes(library):
    plan = FFT()
    for bad in (0, 1, 7, 32769):
        assert library.leo_fft_init(ct.byref(plan), bad) != 0
    assert library.leo_fft_init(ct.byref(plan), 512) == 0
    try:
        values = np.zeros(512, dtype=np.complex128)
        library.leo_fft_forward(ct.byref(plan), values.ctypes.data)
        assert np.all(output(plan) == 0)
        values[0] = 32767 - 32768j
        library.leo_fft_forward(ct.byref(plan), values.ctypes.data)
        np.testing.assert_array_equal(output(plan), np.full(512, values[0]))
    finally:
        library.leo_fft_free(ct.byref(plan))
