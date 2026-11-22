import ctypes as ct
import subprocess

import numpy as np
import pytest

from tools.pipeline_eval.variants.experimental.receiver_build import HERE


@pytest.fixture(scope="module")
def sweep(tmp_path_factory):
    work = tmp_path_factory.mktemp("sparse-carriers")
    source = work / "fixture.c"
    source.write_text("""
#include <stdint.h>
#include <math.h>
#include <string.h>
#include <stdlib.h>
enum { bins = 4096 };
typedef struct { float re, im; } Sample;
static Sample multiply(Sample a, Sample b) {
    return (Sample){a.re*b.re-a.im*b.im, a.re*b.im+a.im*b.re};
}
static Sample conjugate(Sample a) { return (Sample){a.re, -a.im}; }
static float power(Sample a) { return a.re*a.re+a.im*a.im; }
#include "receiver_spectral_vectors.inc"
#include "receiver_sparse_carriers.inc"

int have_avx2(void) { return __builtin_cpu_supports("avx2"); }
int evaluate(const Sample *a, const Sample *b, const uint16_t *eligible, int count,
             int gap, double *powers, int result[2], int packed) {
    SparseCarrierSweep sweep;
    if (packed && sparse_carrier_setup(&sweep, eligible, count)) {
        sparse_carrier_power(&sweep, powers, a, 1);
        sparse_carrier_power(&sweep, powers, b, 0);
        sparse_carrier_peaks(&sweep, powers, gap, result);
        return 1;
    }
    memset(powers, 0, bins*sizeof(*powers));
    spectral_carrier_power(powers, a, bins);
    spectral_carrier_power(powers, b, bins);
    result[0] = result[1] = -1;
    int prev = -1;
    for (int rep = 0; rep < 2; ++rep) {
        int best = -1;
        for (int q = 0; q < count; ++q) {
            int j = eligible[q], distance = abs(j - prev);
            if (prev >= 0 && (distance < gap || bins - distance < gap)) continue;
            if (best < 0 || powers[j] > powers[best]) best = j;
        }
        if (best < 0) break;
        result[rep] = prev = best;
    }
    return 0;
}
""")
    binary = source.with_suffix(".so")
    subprocess.run(["cc", "-O3", "-fPIC", "-shared", "-ffp-contract=off",
                    "-fno-strict-aliasing", "-I", HERE, source, "-lm", "-o", binary],
                   check=True)
    library = ct.CDLL(str(binary))
    pointer, integer = ct.c_void_p, ct.c_int
    library.evaluate.argtypes = [pointer, pointer, pointer, integer, integer, pointer, pointer, integer]
    library.evaluate.restype = integer
    if not library.have_avx2():
        pytest.skip("The fixture executes AVX2 directly")
    return library.evaluate


def compare(sweep, inputs, eligible, gap, *, regular=True):
    eligible = np.asarray(eligible, dtype=np.uint16)
    findings = []
    for packed in (0, 1):
        powers = np.full(4096, 12345.25)
        result = np.empty(2, dtype=np.int32)
        chosen = sweep(inputs[0].ctypes.data, inputs[1].ctypes.data, eligible.ctypes.data,
                       len(eligible), gap, powers.ctypes.data, result.ctypes.data, packed)
        assert chosen == bool(packed and regular)
        if packed and regular:
            unvisited = np.ones(4096, dtype=bool)
            unvisited[eligible] = False
            assert np.all(powers[unvisited] == 12345.25)
        findings.append((powers[eligible].tobytes(), result.tolist()))
    assert findings[0] == findings[1]
    return findings[0][1]


@pytest.mark.hardware
@pytest.mark.parametrize("gap", [0, 1, 5, 17, 2048, 2049])
def test_sparse_runs_match_every_eligible_power_and_both_peaks(sweep, gap):
    rng = np.random.default_rng(8799)
    samples = rng.standard_normal((2, 4096, 2), dtype=np.float32)
    for spans in ([], [17], range(101, 1911), (*range(913), *range(2213, 4096)), range(4096)):
        compare(sweep, samples, spans, gap)


@pytest.mark.hardware
def test_circular_exclusion_and_equal_maxima(sweep):
    samples = np.zeros((2, 4096, 2), dtype=np.float32)
    for index, value in ((1, 5), (4, 5), (17, 4), (18, 4), (4080, 4), (4081, 5)):
        samples[0, index, 0] = value
    bins = (*range(32), *range(4049, 4096))
    assert compare(sweep, samples, bins, 17) == [1, 18]
    samples.fill(0.)
    assert compare(sweep, samples, bins, 17) == [0, 17]


@pytest.mark.hardware
def test_nan_initial_or_outside_winner_has_scalar_order(sweep):
    samples = np.zeros((2, 4096, 2), dtype=np.float32)
    samples[0, [0, 17, 40, 4095], 1] = np.nan
    samples[1, [32, 37], 0] = np.inf
    assert compare(sweep, samples, range(4096), 17) == [0, 17]
    samples[0, 17, 1] = 0.
    assert compare(sweep, samples, range(4096), 17) == [0, 32]


@pytest.mark.hardware
def test_more_than_two_disjoint_runs_use_complete_scalar_path(sweep):
    samples = np.ones((2, 4096, 2), dtype=np.float32)
    assert compare(sweep, samples, [2, 17, 38, 123, 4071], 17, regular=False) == [2, 38]
