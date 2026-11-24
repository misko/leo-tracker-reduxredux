import ctypes as ct
import math
import subprocess

import numpy as np
import pytest

from reports.ALGO08.v3.verifier_pilot_support import HELPER


@pytest.fixture(params=((80_000, 5), (200_000, 15)))
def gather(tmp_path, request):
    points, frames = request.param
    source = tmp_path / "support.c"
    source.write_text(f"""
#include <stdint.h>
#include <stddef.h>
#include <string.h>
enum {{n = 13333, first = 88, stop = 2904}};
typedef struct {{ double re, im; }} PortableFineSample;
typedef struct {{ struct {{ PortableFineSample fine[{points}]; }} iq; }} PortableVerifier;
#define SUPPORT_LOADED_SAMPLES {points}
#define SUPPORT_ANALYSIS_FRAMES {frames}
static int frame_start(unsigned epoch, unsigned frame) {{
    return (int)(epoch + (frame * 40000 + 1) / 3);
}}
int portable_verifier_load(PortableVerifier *w, const int16_t *iq, unsigned lane) {{
    for (size_t i = 0; i < {points}; ++i)
        w->iq.fine[i] = (PortableFineSample){{iq[4*i+2*lane], iq[4*i+2*lane+1]}};
    return 0;
}}
#include "{HELPER}"
""")
    binary = tmp_path / "support.so"
    subprocess.run(["cc", "-O3", "-shared", "-fPIC", str(source), "-o", str(binary)], check=True)
    library = ct.CDLL(str(binary))
    load = library.portable_verifier_load_support
    load.argtypes = [ct.c_void_p, ct.c_void_p, *([ct.c_uint] * 3)]
    load.restype = ct.c_int
    stats = library.portable_verifier_support_counts
    stats.argtypes = [ct.POINTER(ct.c_uint64), ct.c_int]
    stats.restype = None
    return points, frames, load, stats


def test_support_preserves_original_samples_stencil_and_fractional_halo(gather):
    points, frames, load, stats = gather
    data = np.arange(4*points, dtype=np.int16).reshape(points, 2, 2)
    signed_period = 13333
    for lane, (a, b) in enumerate(((2, 13_330), (3000, signed_period), (3005, 3001), (4000, 4000))):
        read = np.zeros(points, dtype=bool)
        for epoch in {a, b} - {signed_period}:
            for frame in range(frames):
                origin = epoch + (frame*40_000 + 1)//3
                for shift in range(-2, 3):
                    if origin + 2904 + shift <= points:
                        read[origin + 88 + shift:origin + 2904 + shift] = True
                for offset in (-1.5, -1, 0.0, 0.25, 1, 1.5):
                    lo = math.floor(origin + 88 + offset) - 7
                    hi = math.floor(origin + 2903 + offset) + 9
                    if hi <= points:
                        read[lo:hi] = True
        output = np.full((points, 2), np.nan)
        assert load(output.ctypes.data, data.ctypes.data, lane % 2, a, b) == 0
        written = ~np.isnan(output[:, 0])
        assert written[read].all() and written.sum() < points//2
        assert np.array_equal(output[written], data[written, lane % 2])
        counters = (ct.c_uint64 * 3)()
        stats(counters, 1)
        assert tuple(counters) == (1, written.sum(), 0)


def test_wrapped_stencil_takes_full_loader(gather):
    points, _, load, stats = gather
    data = np.arange(4*points, dtype=np.int16).reshape(points, 2, 2)
    for a, b in ((1, 13333), (500, 13332)):
        output = np.full((points, 2), np.nan)
        assert load(output.ctypes.data, data.ctypes.data, 1, a, b) == 0
        assert np.array_equal(output, data[:, 1])
    counters = (ct.c_uint64 * 3)()
    stats(counters, 1)
    assert tuple(counters) == (2, 2*points, 2)
