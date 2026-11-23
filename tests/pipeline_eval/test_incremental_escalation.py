import ctypes as ct
import platform
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3.incremental_escalation import FLAGS, HOOK, RETAINED, TILE, suffix_source


pytestmark = pytest.mark.skipif(platform.machine() != "x86_64", reason="the release FIR is x86-64 AVX2")


def library(output, *sources, defines=()):
    subprocess.run(["cc", *FLAGS, *defines, "-shared", "-Wl,--wrap=delay_decimate", "-Wl,-z,defs",
                    *sources, "-o", output], check=True)
    return ct.CDLL(str(output))


def test_native_suffix_preserves_all_outputs_and_retains_only_complete_tiles(tmp_path):
    original = TILE.read_text()
    short = tmp_path / "short.c"
    short.write_text(original.replace("input_samples = 200000", "input_samples = 120000"))
    suffix = tmp_path / "suffix.c"
    suffix.write_text(suffix_source(original))
    fallback = tmp_path / "fallback.c"
    fallback.write_text("""
int leo_pgo_delay_decimate(const float *a, const float *b, int c, int d, float *e) {
    return a && b && c && d && e ? 77 : -1;
}
""")
    full = library(tmp_path / "full.so", TILE, suffix, fallback)
    prefix = library(tmp_path / "short.so", short, fallback)
    for direct in [full.delay_decimate, prefix.delay_decimate]:
        direct.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p]
        direct.restype = ct.c_int
    full.leo_escalation_fir_suffix.argtypes = [ct.c_void_p] * 3
    full.leo_escalation_fir_suffix.restype = None
    rng = np.random.default_rng(2523)
    signal = rng.integers(-32768, 32768, size=(200_000, 2), dtype=np.int16).astype(np.float32)
    half = rng.uniform(-0.1, 0.1, 41)
    coeff = np.r_[half[1:][::-1], half].astype(np.float32)
    prior, expected, resumed = (np.zeros((n, 2), dtype=np.float32) for n in (30_000, 50_000, 50_000))
    read = signal.ctypes.data, coeff.ctypes.data
    status = prefix.delay_decimate(*read, 81, 4, prior.ctypes.data)
    if status == 77:
        pytest.skip("native AVX2 tile unavailable")
    assert status == 0 and full.delay_decimate(*read, 81, 4, expected.ctypes.data) == 0
    resumed[:RETAINED] = prior[:RETAINED]
    full.leo_escalation_fir_suffix(*read, resumed.ctypes.data)
    assert expected.tobytes() == resumed.tobytes()
    assert prior[RETAINED:].tobytes() != expected[RETAINED:len(prior)].tobytes()


def test_scoped_capture_is_single_use_and_checks_filter(tmp_path):
    stub = tmp_path / "stub.c"
    stub.write_text("""
#include <stdint.h>
enum { offset = 2 * 29990 };
int __wrap_delay_decimate(const float *, const float *, int, int, float *);

int delay_decimate(const float *in, const float *coeff, int taps, int stride, float *out) {
    if (!in || !coeff || taps != 81 || stride != 4) return -1;
    out[0] = in[0];
    return 0;
}

#ifdef SHORT_APERTURE
int short_null(void *ctx, const int16_t *iq, int lane, double lo, double hi, void *out) {
    static float cache[offset], coeff[81];
    const float input[] = {13.f};
    if (!ctx || !iq || !out || lo >= hi) return -1;
    if (__wrap_delay_decimate(input, coeff, 81, 4, cache)) return -1;
    return lane < 0 ? -1 : 0;
}
#else
void leo_escalation_fir_suffix(const float *in, const float *coeff, float *out) {
    out[offset] = in[0] + coeff[0];
}

int cancellation_factors(void *ctx, const int16_t *iq, int lane, double lo, double hi, void *out) {
    static float buffer[100000];
    const float first[] = {19.f}, second[] = {31.f};
    const float coeff[81] = {(float)lane};
    if (!ctx || !iq || !out || lo >= hi) return -1;
    if (__wrap_delay_decimate(first, coeff, 81, 4, buffer)) return -1;
    if (buffer[0] != 19.f && (buffer[0] != 13.f || buffer[offset] != 19.f)) return -1;
    if (__wrap_delay_decimate(second, coeff, 81, 4, buffer) || buffer[0] != 31.f) return -1;
    return 0;
}

int test_avx2(void) { return __builtin_cpu_supports("avx2") != 0; }
#endif
""")
    short = library(tmp_path / "short.so", HOOK, stub, defines=["-DSHORT_APERTURE"])
    full = library(tmp_path / "full.so", HOOK, stub)
    run = full.leo_escalation_run
    run.argtypes = [ct.c_void_p] * 5 + [ct.c_int, ct.c_double, ct.c_double, ct.c_int] + [ct.c_void_p] * 3
    run.restype = ct.c_int
    scratch = (ct.c_int * 20)()

    def invoke(lane, mode):
        counts = (ct.c_int * 3)()
        n = run(1, 2, short.short_null, short.leo_escalation_capture, scratch, lane, -150, 200,
                mode, scratch, scratch, counts)
        return n, tuple(counts)

    assert invoke(0, 1) == (0, (0, full.test_avx2(), 2))
    assert invoke(1, 1) == (0, (0, 0, 2))
    assert invoke(-1, 1) == (-1, (0, 0, 0))
    assert invoke(0, 2) == (0, (0, 0, 2))
    assert invoke(0, 0) == (0, (0, 0, 2))
    assert invoke(0, 1) == (0, (0, full.test_avx2(), 2))
