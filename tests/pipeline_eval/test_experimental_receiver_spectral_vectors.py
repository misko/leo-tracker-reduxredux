import ctypes as ct
import subprocess

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental.receiver_build import HERE


@pytest.fixture(scope="module")
def kernels(tmp_path_factory):
    work = tmp_path_factory.mktemp("spectral-vectors")
    source = work / "fixture.c"
    source.write_text("""
#include <math.h>
#include <string.h>
typedef struct { float re, im; } Sample;
static Sample multiply(Sample a, Sample b) {
    return (Sample){a.re*b.re-a.im*b.im, a.re*b.im+a.im*b.re};
}
static Sample conjugate(Sample a) { return (Sample){a.re, -a.im}; }
static float power(Sample a) { return a.re*a.re+a.im*a.im; }
#include "receiver_spectral_vectors.inc"

int have_avx2(void) { return __builtin_cpu_supports("avx2"); }
void lag_vectors(const Sample *a, const Sample *b, Sample *out, double *prefix,
                 int width, int lag, int fft_size, int packed) {
    if (packed) {
        spectral_lag_products(out, prefix, a, b, width, lag, fft_size);
        return;
    }
    memset(out, 0, fft_size*sizeof(*out));
    prefix[0] = 0.;
    for (int i = 0; i < width-lag; ++i) {
        Sample x = multiply(a[i+lag], conjugate(a[i])), y = multiply(b[i+lag], conjugate(b[i]));
        out[i] = (Sample){x.re+y.re, x.im+y.im};
        prefix[i+1] = prefix[i]+power(out[i]);
    }
}
void filter_vectors(Sample *in, const Sample *filter, int size, int packed) {
    if (packed) spectral_filter(in, filter, size);
    else for (int i = 0; i < size; ++i) in[i] = multiply(in[i], filter[i]);
}
void timing_scores(double *scores, double *prefix, Sample *inverse,
                  int epochs, int length, int fft_size, int packed) {
    if (packed) {
        spectral_timing_scores(scores, prefix, inverse, epochs, length, fft_size);
        return;
    }
    const float scale = 1.f / fft_size;
    for (int i = 0; i < fft_size; ++i) {
        inverse[i].re *= scale;
        inverse[i].im *= scale;
    }
    for (int i = 0; i < epochs; ++i)
        scores[i] += power(inverse[i]) / fmax(prefix[i+length]-prefix[i], 1e-20);
}
double carrier_vectors(const Sample *mode, const Sample *code, Sample *out, int length, int fft_size,
                       double energy, int packed) {
    if (packed) return spectral_carrier_input(out, mode, code, length, fft_size, energy);
    memset(out, 0, fft_size*sizeof(*out));
    for (int i = 0; i < length; ++i) {
        out[i] = multiply(mode[i], conjugate(code[i]));
        energy += power(mode[i]);
    }
    return energy;
}
void carrier_powers(const Sample *fft, double *powers, int length, int packed) {
    if (packed) spectral_carrier_power(powers, fft, length);
    else for (int i = 0; i < length; ++i) powers[i] += power(fft[i]);
}
""")
    library = source.with_suffix(".so")
    subprocess.run(
        ["cc", "-O3", "-fPIC", "-shared", "-ffp-contract=off", "-fno-strict-aliasing",
         "-I", HERE, source, "-lm", "-o", library],
        check=True,
    )
    code = ct.CDLL(str(library))
    p, i, d = ct.c_void_p, ct.c_int, ct.c_double
    for name, signature in (
        ("lag_vectors", [p, p, p, p, i, i, i, i]), ("filter_vectors", [p, p, i, i]),
        ("timing_scores", [p, p, p, i, i, i, i]), ("carrier_vectors", [p, p, p, i, i, d, i]),
        ("carrier_powers", [p, p, i, i]),
    ):
        kernel = getattr(code, name)
        kernel.argtypes = signature
        kernel.restype = d if name == "carrier_vectors" else None
    if not code.have_avx2():
        pytest.skip("The arithmetic fixture executes AVX2 directly")
    return code


@pytest.mark.hardware
@pytest.mark.parametrize(("width", "fft", "epochs", "lag"), [
    (4740, 4800, 3333, 2), (4740, 4800, 3333, 11), (4740, 4800, 3333, 74),
    (18964, 19200, 13333, 298),
])
def test_lag_products_prefixes_and_scores_are_byte_identical(kernels, width, fft, epochs, lag):
    rng = np.random.default_rng(5528 + lag)
    a, b = rng.standard_normal((2, 2 * width), dtype=np.float32)
    a[::11], b[::13] = -0., 0.
    filter_values = rng.standard_normal(2 * fft, dtype=np.float32)
    inverse = rng.standard_normal(2 * fft, dtype=np.float32)
    ref = None
    for packed in (0, 1):
        out = np.full(2 * fft, np.nan, dtype=np.float32)
        prefix = np.empty(width - lag + 1, dtype=np.float64)
        scores = np.arange(epochs, dtype=np.float64) / 37
        kernels.lag_vectors(a.ctypes.data, b.ctypes.data, out.ctypes.data, prefix.ctypes.data,
                            width, lag, fft, packed)
        first = (out.tobytes(), prefix.tobytes())
        kernels.filter_vectors(out.ctypes.data, filter_values.ctypes.data, fft, packed)
        temporary = inverse.copy()
        kernels.timing_scores(scores.ctypes.data, prefix.ctypes.data, temporary.ctypes.data,
                              epochs, width - epochs + 1 - lag, fft, packed)
        result = first + (out.tobytes(), scores.tobytes())
        if packed:
            assert result == ref
        else:
            ref = result


@pytest.mark.hardware
def test_carrier_packing_preserves_two_ordered_energies_and_bin_powers(kernels):
    rng = np.random.default_rng(43762)
    length, fft = 707, 4096
    modes = rng.standard_normal((2, 2 * length), dtype=np.float32)
    code = rng.standard_normal(2 * length, dtype=np.float32)
    transforms = rng.standard_normal((2, 2 * fft), dtype=np.float32)
    results = []
    for packed in (0, 1):
        energy = 0.
        out = np.full(2 * fft, -23, dtype=np.float32)
        powers = np.zeros(fft, dtype=np.float64)
        products = []
        for mode, transformed in zip(modes, transforms, strict=True):
            energy = kernels.carrier_vectors(mode.ctypes.data, code.ctypes.data, out.ctypes.data,
                                             length, fft, energy, packed)
            products.append(out.tobytes())
            kernels.carrier_powers(transformed.ctypes.data, powers.ctypes.data, fft, packed)
        results.append((products, energy, powers.tobytes()))
    assert results[0] == results[1]


@pytest.mark.hardware
def test_timing_scores_keep_the_denominator_floor(kernels):
    epochs, length, fft = 13, 8, 32
    prefix = np.zeros(epochs + length, dtype=np.float64)
    prefix[10] = np.nan
    prefix[16] = 1e-25
    inverse = np.linspace(-2., 2., 2 * fft, dtype=np.float32)
    arrays = []
    for packed in (0, 1):
        scores = np.zeros(epochs, dtype=np.float64)
        temporary = inverse.copy()
        kernels.timing_scores(scores.ctypes.data, prefix.ctypes.data, temporary.ctypes.data,
                              epochs, length, fft, packed)
        arrays.append(scores.tobytes())
    assert arrays[0] == arrays[1]
