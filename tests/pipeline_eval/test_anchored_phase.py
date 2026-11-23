import ctypes as ct
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3 import anchored_phase as trial


def test_native_block_keeps_exact_anchors_and_bounded_absolute_phase(tmp_path):
    source = tmp_path / "rotation.c"
    source.write_text("""
#include <math.h>
#include <stdint.h>
#include <string.h>
enum { anchor_stride = 32, aperture = 2816, first = 88, rounded_weight_rows = 64 };
static const double tau = 6.283185307179586476925286766559, rate = 10000000.0;
typedef struct {double r, i;} PortableFineComplex;
typedef struct {double re, im;} GlrtComplex;
typedef struct {
    struct { const void *glrt; } iq;
    double integer_hz, weights[rounded_weight_rows][16];
    int32_t indices[aperture], weight_row[aperture];
    GlrtComplex glrt_rotation[aperture], glrt_exact[aperture], glrt_control[aperture], correlations[2][64];
} PortableVerifier;
static double sinc(double x) { return x ? sin(x)/x : 1.; }
static PortableFineComplex rotate(double a) { return (PortableFineComplex){cos(a), sin(a)}; }
static PortableFineComplex multiply(PortableFineComplex a, PortableFineComplex b) {
    return (PortableFineComplex){a.r*b.r-a.i*b.i, a.r*b.i+a.i*b.r};
}
#define correlated_fractional(...) ((void)0)
""" + trial.recurrence() + """
int compare(int32_t start, double offset, double cfo, GlrtComplex *fast, GlrtComplex *stock) {
    PortableVerifier w = {0};
    double mass;
    if (anchored_correlations(&w, 1, &start, cfo, offset, &mass)) return -1;
    memcpy(fast, w.glrt_rotation, sizeof(w.glrt_rotation));
    for (int k = 0; k < aperture; ++k) {
        double position = start + first + k + offset;
        PortableFineComplex z = rotate(-tau * cfo * position / rate);
        stock[k] = (GlrtComplex){z.r, z.i};
    }
    return 0;
}
""")
    output = tmp_path / "rotation.so"
    subprocess.run(["cc", "-O3", "-shared", "-fPIC", "-ffp-contract=off", source, "-lm", "-o", output], check=True)
    native = ct.CDLL(str(output)).compare
    native.argtypes = (ct.c_int32, ct.c_double, ct.c_double, ct.c_void_p, ct.c_void_p)
    native.restype = ct.c_int
    for start, offset, hz in ((0, .432, -800_000.5), (193_000, -.1213, 4_999_997.9), (100_000, 1.49987, -5_000_000.)):
        fast, stock = (np.empty((2816, 2), dtype=np.float64) for _ in range(2))
        assert not native(start, offset, hz, fast.ctypes.data, stock.ctypes.data)
        assert fast[::32].tobytes() == stock[::32].tobytes()
        assert np.max(np.linalg.norm(fast-stock, axis=1)) < 1e-9


def test_signed_membership_and_flags_cannot_be_smoothed_away():
    a = (0, 12, .125, -400_000., .35, .012)
    b = (*a[:4], a[4]+1e-12, a[5])
    trial.continuous_control([a], [b], dict(exact=0., rolled=0.), 1e-8)
    with pytest.raises(ValueError, match="candidate membership"):
        trial.continuous_control([a], [], {}, 1e-8)
    with pytest.raises(ValueError, match="Signed order"):
        trial.continuous_control([a], [(*a[:3], -a[3], *a[4:])], {}, 1e-8)
    one = (12, 7, -400_000., .125, 0., .35, .012)
    changed = (one[0], 5, *one[2:])
    trial.audited_flags([one], [changed, one], dict(verified_exact=0., verified_rolled=0.))
    with pytest.raises(ValueError, match="Native verifier flags"):
        trial.audited_flags([one], [changed], {})
