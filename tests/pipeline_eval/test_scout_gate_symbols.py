import ctypes as ct
import subprocess

import numpy as np

from reports.ALGO08.v3.scout_gate_symbols import HELPER, overlay
from reports.ALGO08.v3.verifier_pilot_support_trial import SCOUT_ORDERS


def test_native_symbols_keep_float_bytes_and_scalar_fallback(tmp_path):
    c, dso = tmp_path / "gate.c", tmp_path / "gate.so"
    c.write_text(f"""
typedef struct {{ float re, im; }} Sample;
enum {{ symbol = 44 }};
#include "{HELPER}"
void symbols(const Sample *samples, const Sample *rotation, Sample *out) {{
    if (!scout_gate_symbols_try(samples, rotation, out)) {{
        for (int s = 0; s < 64; ++s) {{
            float re = 0.f, im = 0.f;
            for (int k = 0; k < symbol; ++k) {{
                int j = s*symbol+k;
                Sample a = samples[j], b = rotation[j];
                Sample z = {{a.re*b.re-a.im*b.im, a.re*b.im+a.im*b.re}};
                re += z.re;
                im += z.im;
            }}
            out[s] = (Sample){{re, im}};
        }}
    }}
}}
""")
    subprocess.run(["cc", "-O3", "-ffp-contract=off", "-Wall", "-Werror", "-shared", "-fPIC",
                    str(c), "-o", str(dso)], check=True)
    lib = ct.CDLL(str(dso))
    switch = lib.scout_gate_symbols_mode
    switch.argtypes, switch.restype = [ct.c_int], ct.c_int
    run = lib.symbols
    run.argtypes, run.restype = [ct.c_void_p]*3, None
    rng = np.random.default_rng(54390)
    data = rng.integers(-32768, 32768, size=(64*44, 2)).astype(np.float32)
    rot = rng.normal(size=data.shape).astype(np.float32)
    pos = np.arange(len(data))
    for weight in (1., -1., 0., -0., np.float32(2**-59)):
        samples = data * weight
        # Tiny and exact cancellation, alternated signs, and unaligned copies.
        samples[pos % 13 == 0] = -0.
        expected = np.empty((64, 2), dtype=np.float32)
        got = np.empty_like(expected)
        assert switch(0) == 0
        run(samples.ctypes.data, rot.ctypes.data, expected.ctypes.data)
        assert switch(1) in (0, 1)
        run(samples.ctypes.data, rot.ctypes.data, got.ctypes.data)
        assert got.tobytes() == expected.tobytes()


def test_overlay_retains_exact_fallback_and_transform():
    source = """static int gate(TimingFirst *w, Peak *p) {
            for (int s = 0; s < 64; ++s) {
                w->scratch[s] = compute(s);
            }
            transform(w, 64, 0);
}
"""
    patched = overlay(source)
    assert 'if (!scout_gate_symbols_try(w->data + offset, rotation, w->scratch)) {' in patched
    assert patched.count("w->scratch[s] = compute(s);") == 1
    assert patched.count("transform(w, 64, 0);") == 1
    assert SCOUT_ORDERS[0] == SCOUT_ORDERS[1][::-1]
