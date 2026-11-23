import ctypes as ct
import platform
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3 import short_cfo_exact_cost as trial


@pytest.fixture
def native(tmp_path):
    if platform.machine() != "x86_64":
        pytest.skip("Exact AVX2 angle-preparation qualification")
    helper = trial.ref.HERE / "short_cfo_exact_cost.inc"
    path = tmp_path / "fixture.c"
    path.write_text(f"""
#include <math.h>
#include <stdint.h>
#include <stddef.h>
enum {{ max_frames = 15, samples = 200000, first = 88, aperture = 2816, stop = first + aperture }};
static const double tau = 6.283185307179586476925286766559, rate = 10000000.0;
typedef struct {{ double r, i; }} PortableFineSample;
typedef struct {{ struct {{ PortableFineSample fine[samples]; }} iq; }} PortableVerifier;
static int portable_verifier_load(PortableVerifier *w, const int16_t *iq, unsigned lane) {{
    return w && iq && lane < 2 ? 77 : -1;
}}
#include "{helper}"
int load(PortableVerifier *w, const int16_t *iq, unsigned lane, const int32_t *starts,
         int frames, double offset, int integer) {{
    return load_frame_support(w, iq, lane, starts, frames, offset, integer);
}}
__attribute__((optimize("no-tree-vectorize")))
void angles_stock(double *array, int origin, double offset, double cfo) {{
    for (int k = 0; k < aperture; ++k) {{
        const double position = origin + first + k + offset;
        array[k] = -tau * cfo * position / rate;
    }}
}}
int angles_candidate(double *array, int origin, double offset, double cfo) {{
    if (!__builtin_cpu_supports("avx2")) return 77;
    prepare_angles(array, origin, offset, cfo);
    return 0;
}}
""")
    binary = tmp_path / "fixture.so"
    subprocess.run(["cc", "-shared", "-fPIC", "-O3", "-std=c11", "-fopenmp-simd", "-ffp-contract=off",
                    "-fno-math-errno", str(path), "-lm", "-o", str(binary)], check=True)
    lib = ct.CDLL(str(binary))
    lib.load.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_uint, ct.c_void_p, ct.c_int, ct.c_double, ct.c_int]
    lib.load.restype = ct.c_int
    for fn, returns in ((lib.angles_stock, None), (lib.angles_candidate, ct.c_int)):
        fn.argtypes, fn.restype = (ct.c_void_p, ct.c_int, ct.c_double, ct.c_double), returns
    return lib


@pytest.mark.parametrize(("offset", "integer"), [(0.375, 0), (-1.5, 0), (-1.0000000000005, 1)])
def test_loader_fills_only_literal_correlation_support(native, offset, integer):
    starts = np.array([0, 146667], dtype=np.int32)
    rng = np.random.default_rng(286)
    samples = rng.integers(-32768, 32767, (200_000, 2, 2), dtype=np.int16)
    output = np.full((200_000, 2), np.nan)
    args = output.ctypes.data, samples.ctypes.data, 1, starts.ctypes.data, len(starts), offset, integer
    assert native.load(*args) == 0
    expected = np.full_like(output, np.nan)
    for start in starts:
        first = start + 88 + (round(offset) if integer else int(np.floor(offset))-7)
        stop = first+2816+(0 if integer else 15)
        expected[first:stop] = samples[first:stop, 1]
    np.testing.assert_array_equal(output, expected)
    starts[-1] = 199_000
    output.fill(np.nan)
    assert native.load(*args) == 77
    assert np.isnan(output).all()


def test_angle_vector_matches_scalar_multiply_divide_rounding(native):
    stock, candidate = (np.empty(2816, dtype=np.float64) for _ in range(2))
    for origin, offset, cfo in ((0, -.99, -800_021.75), (166667, .19987, 663_903.11), (189955, 1.5, -0.0)):
        status = native.angles_candidate(candidate.ctypes.data, origin, offset, cfo)
        if status == 77:
            pytest.skip("AVX2 unavailable")
        assert status == 0
        native.angles_stock(stock.ctypes.data, origin, offset, cfo)
        assert candidate.tobytes() == stock.tobytes()
