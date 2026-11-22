import ctypes as ct
import subprocess
from pathlib import Path

import numpy as np
import pytest

pytestmark = pytest.mark.hardware
NATIVE = Path(__file__).resolve().parents[2] / "tools/pipeline_eval/variants/experimental"
COUNT = 2816


@pytest.fixture(scope="module")
def oscillator(tmp_path_factory):
    work = tmp_path_factory.mktemp("absolute-oscillator")
    source, binary = work / "probe.c", work / "probe.so"
    source.write_text('''
#include <math.h>
#include "receiver_absolute_phase_avx.inc"

__attribute__((target("avx2,fma")))
static void quotients(const double *x, double *y, int count) {
    for (int k = 0; k < count; k += 4)
        _mm256_storeu_pd(y + k, divide_sample_rate(_mm256_loadu_pd(x + k)));
}

int divide(const double *x, double *actual, double *reference, int count) {
    if (!absolute_phase_batch_supported(100.)) return 0;
    quotients(x, actual, count);
    for (int k = 0; k < count; ++k) reference[k] = x[k] / 10000000.;
    return 1;
}

int tensor(int mode, int begin, int count, double cfo, double offset,
            double *actual, double *reference, double *rotation, double *stock_rotation) {
    static const int modes[] = {FE_TONEAREST, FE_DOWNWARD, FE_UPWARD, FE_TOWARDZERO};
    int previous = fegetround();
    if (fesetround(modes[mode])) return -1;
    const double tau = 6.283185307179586476925286766559;
    const double omega = -tau * cfo;
    const int batch = absolute_phase_batch_supported(cfo);
    if (batch) absolute_phase_batch(actual, begin, count, omega, offset);
    for (int k = 0; k < count; ++k) {
        const double position = begin + k + offset;
        reference[k] = -tau * cfo * position / 10000000.;
        if (!batch) actual[k] = omega * position / 10000000.;
        rotation[2*k] = cos(actual[k]);
        rotation[2*k + 1] = sin(actual[k]);
        stock_rotation[2*k] = cos(reference[k]);
        stock_rotation[2*k + 1] = sin(reference[k]);
    }
    if (fegetround() != modes[mode] || fesetround(previous)) return -1;
    return batch;
}

int guarded_control(int kind) {
    const unsigned previous = _mm_getcsr();
    const unsigned masks[] = {_MM_FLUSH_ZERO_MASK, _MM_DENORMALS_ZERO_MASK,
                              _MM_ROUND_DOWN, _MM_MASK_OVERFLOW};
    _mm_setcsr(previous ^ masks[kind]);
    const int route = absolute_phase_batch_supported(500.);
    _mm_setcsr(previous);
    return route;
}
''')
    subprocess.run([
        "cc", "-O3", "-std=c11", "-Wall", "-Wextra", "-Werror", "-ffp-contract=off",
        "-frounding-math", "-fPIC", "-shared", "-I", NATIVE, source, "-lm", "-o", binary,
    ], check=True)
    library = ct.CDLL(str(binary))
    library.divide.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_int]
    library.divide.restype = ct.c_int
    library.tensor.argtypes = [
        ct.c_int, ct.c_int, ct.c_int, ct.c_double, ct.c_double, *[ct.c_void_p] * 4,
    ]
    library.tensor.restype = ct.c_int
    library.guarded_control.argtypes = [ct.c_int]
    library.guarded_control.restype = ct.c_int
    return library


def test_reciprocal_residual_restores_division_rounding(oscillator):
    rng = np.random.default_rng(84019)
    mantissas = rng.integers(2**52, 2**53, 200_000, dtype=np.int64).astype(np.float64)
    exponents = rng.integers(-750, 0, size=mantissas.size)
    signs = np.where(np.arange(mantissas.size) % 2, -1., 1.)
    numerators = np.ldexp(mantissas * signs, exponents)
    # Force the minimum midpoint gap on both sides. For these mantissas,
    # the exact quotient in local ulps is mantissa * 2**16 / 78125.
    divisor = 78_125
    inverse = pow(2**16, -1, divisor)
    begin = 10_000_000 * 2**29
    near = [begin + (remainder * inverse - begin) % divisor
            for remainder in ((divisor - 1) // 2, (divisor + 1) // 2)]
    difficult = np.array([*near, *(-number for number in near)], dtype=np.float64)
    numerators = np.concatenate((numerators, difficult))
    actual = np.empty_like(numerators)
    reference = np.empty_like(numerators)
    assert oscillator.divide(numerators.ctypes.data, actual.ctypes.data, reference.ctypes.data,
                             len(numerators)) == 1, "AVX2/FMA is required for the packed witness"
    assert np.count_nonzero(numerators * 1e-7 != reference) > 10_000
    assert actual.tobytes() == reference.tobytes()


@pytest.mark.parametrize("mode", range(4))
def test_signed_phase_tensor_and_rounding_fallback(oscillator, mode):
    arguments = [np.empty(COUNT, dtype=np.float64) for _ in range(2)]
    values = [np.empty(2 * COUNT, dtype=np.float64) for _ in range(2)]
    norms = (2.**-700, -1.0, 19624.304, -65873.01387, 5_000_000., -5_000_000.)
    fallback = (0., -0., np.nextafter(0., 1.), 2.**-701)
    for cfo in (*norms, *fallback):
        for base, offset in ((88, -1.5), (510, np.nextafter(-.5, 0.)),
                             (65_001, np.nextafter(.25, 0.)), (197_182, .991)):
            route = oscillator.tensor(mode, base, COUNT, cfo, offset,
                                      *(x.ctypes.data for x in (*arguments, *values)))
            assert route == (mode == 0 and cfo in norms)
            assert arguments[0].tobytes() == arguments[1].tobytes()
            assert values[0].tobytes() == values[1].tobytes()


def test_raw_sse_rounding_denormal_and_exception_controls_select_scalar(oscillator):
    assert [oscillator.guarded_control(kind) for kind in range(4)] == [0, 0, 0, 0]
