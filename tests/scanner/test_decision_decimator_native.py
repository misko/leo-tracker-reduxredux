"""Fixed-point DSP parity, full-scale safety, filter response and history reset."""

import ctypes as ct

import numpy as np
import pytest

from tools.native_presence import pointer
from tools.prepare_decimated_dwell_replay import (
    build,
    coefficients,
    recursive_denominator,
    reference,
)


@pytest.fixture(scope="module")
def native(tmp_path_factory):
    lib = ct.CDLL(str(build(tmp_path_factory.mktemp("decimator") / "dsp.so", shared=True)))
    lib.leo_decimator_create.argtypes = [
        ct.c_void_p,
        ct.c_uint,
        ct.c_void_p,
        ct.c_uint,
        ct.c_size_t,
    ]
    lib.leo_decimator_create.restype = ct.c_void_p
    lib.leo_decimator_create_recursive.argtypes = [
        ct.c_void_p,
        ct.c_uint,
        ct.c_void_p,
        ct.c_uint,
        ct.c_void_p,
        ct.c_size_t,
    ]
    lib.leo_decimator_create_recursive.restype = ct.c_void_p
    lib.leo_decimator_destroy.argtypes = [ct.c_void_p]
    lib.leo_decimator_run.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_size_t, ct.c_void_p]
    lib.leo_decimator_run.restype = ct.c_int
    return lib


@pytest.mark.parametrize("kind", ["cascade", "direct", "compact"])
def test_full_scale_bit_exact_and_history_reset(native, kind):
    h1, h2 = coefficients(kind)
    w = native.leo_decimator_create(pointer(h1), len(h1), pointer(h2), len(h2), 4096)
    assert w
    try:
        rng = np.random.default_rng(91)
        cases = [
            rng.integers(-32768, 32768, (4096, 2), dtype="int16"),
            np.full((4096, 2), 32767, dtype="int16"),
            np.full((4096, 2), -32768, dtype="int16"),
            np.zeros((4096, 2), dtype="int16"),
        ]
        for iq in cases:
            output = np.empty((1024, 2), dtype="int16")
            assert native.leo_decimator_run(w, pointer(iq), len(iq), pointer(output)) == 0
            np.testing.assert_array_equal(output, reference(iq, h1, h2))
        output.fill(123)
        assert native.leo_decimator_run(w, pointer(cases[0]), 4092, pointer(output)) == -1
        assert np.all(output == 123)
    finally:
        native.leo_decimator_destroy(w)


@pytest.mark.parametrize("kind", ["cascade", "direct", "compact"])
def test_frozen_filter_response(kind):
    h1, h2 = coefficients(kind)
    f = np.linspace(0, 5000000, 50001)
    h = abs(np.fft.fft(h2 / 32768, 100000))
    if len(h1):
        h = h[(2 * np.arange(50001)) % 100000] * abs(np.fft.rfft(h1 / 32768, 100000))
    else:
        h = h[:50001]
    assert np.max(np.abs(20 * np.log10(h[f <= 800000]))) < 0.01
    assert np.max(h[f >= 1250000]) < 10 ** (-65 / 20)


def test_invalid_coefficients_rejected(native):
    _, h = coefficients("direct")
    h[0] += 1
    assert not native.leo_decimator_create(None, 0, pointer(h), len(h), 4096)
    assert not native.leo_decimator_create(None, 0, pointer(h), len(h), 4095)


@pytest.mark.parametrize("count", [4, 1020, 1028, 2052, 1200000])
def test_causal_impulses_across_tiles_and_final_partial_tile(native, count):
    h1, h2 = coefficients("compact")
    iq = np.zeros((count, 2), dtype="int16")
    for index in (0, count - 1, 1023, 1024, 2047, 2048):
        if index < count:
            iq[index] = [32767, -32768]
    expected = reference(iq, h1, h2)
    output = np.empty_like(expected)
    w = native.leo_decimator_create(pointer(h1), len(h1), pointer(h2), len(h2), count)
    assert w
    try:
        assert native.leo_decimator_run(w, pointer(iq), count, pointer(output)) == 0
        np.testing.assert_array_equal(output, expected)
    finally:
        native.leo_decimator_destroy(w)


def test_recursive_response_with_quantized_numerator_and_denominator():
    h1, numerator = coefficients("recursive")
    f = np.linspace(0, 5000000, 100001)
    z = np.exp(-2j * np.pi * f / 5000000)
    h = np.polynomial.polynomial.polyval(z, numerator / 16384)
    for a, b in recursive_denominator().astype(np.float64):
        h /= 1 + a * z**2 + b * z**4
    h *= np.polynomial.polynomial.polyval(np.exp(-2j * np.pi * f / 10000000), h1 / 32768)
    assert np.max(np.abs(20 * np.log10(np.abs(h[f <= 800000])))) < 0.01
    assert np.max(np.abs(h[f >= 1250000])) < 10 ** (-65 / 20)


def test_recursive_full_scale_impulse_parity_and_state_reset(native):
    h1, h2 = coefficients("recursive")
    den = recursive_denominator()
    w = native.leo_decimator_create_recursive(
        pointer(h1), len(h1), pointer(h2), len(h2), pointer(den), 8200
    )
    assert w
    try:
        rng = np.random.default_rng(77)
        iq = rng.integers(-32768, 32768, (8200, 2), dtype="int16")
        for values in (iq, np.full_like(iq, 32767), np.zeros_like(iq)):
            output = np.empty((2050, 2), dtype="int16")
            assert native.leo_decimator_run(w, pointer(values), len(values), pointer(output)) == 0
            expected = reference(values, h1, h2, recursive=True)
            assert np.max(np.abs(output.astype(int) - expected.astype(int))) <= 2
        assert not output.any()
    finally:
        native.leo_decimator_destroy(w)


@pytest.mark.parametrize("a,b", [(float("nan"), 0), (0, 1), (2, 0), (-2, 0)])
def test_recursive_rejects_nonfinite_or_unstable_sections(native, a, b):
    h1, h2 = coefficients("recursive")
    den = recursive_denominator()
    den[0] = [a, b]
    assert not native.leo_decimator_create_recursive(
        pointer(h1), len(h1), pointer(h2), len(h2), pointer(den), 4096
    )
