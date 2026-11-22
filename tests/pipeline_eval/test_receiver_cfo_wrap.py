import ctypes as ct
import gzip
import json
from importlib import import_module
from pathlib import Path

import pytest

wrap = import_module("reports.ALGO08.single-core-2x.receiver_cfo_wrap_build")
lineage = import_module("reports.ALGO08.single-core-2x.receiver_cfo_lineage_trial")
RESULT = ct.c_double * 4
MEASUREMENTS = Path(wrap.__file__).parent / "measurements"

SAMPLE_PATHS = """
#include <math.h>
typedef struct { int epoch; double hz; } Request;

__attribute__((section(".text.unlikely.delay_refine")))
int delay_refine(const float *iq, const float *pilot, int epoch, double hz,
                 double lo, double hi, double *out) {
    if (!iq || !pilot || !out || epoch < 0 || epoch >= 13333 || !isfinite(hz) || !(hi > lo))
        return -1;
    out[0] = SENTINEL;
    out[1] = hz;
    out[2] = epoch;
    return 0;
}

int delay_decimate(void) { return SENTINEL; }

int delay_refine_bank(const float *iq, const float *pilot, const Request *request,
                      int size, double lo, double hi, double (*out)[4]) {
    if (!iq || !pilot || !request || !out || size < 0 || !(hi > lo)) return -1;
    for (int i = 0; i < size; ++i) {
        Request seed = request[i];
        if (size <= 4 && seed.epoch >= 4 && seed.epoch < 13329 && isfinite(seed.hz)) {
            out[i][0] = -SENTINEL;
        } else if (delay_refine(iq, pilot, seed.epoch, seed.hz, lo, hi, out[i])) {
            return -1;
        }
    }
    return 0;
}
"""


@pytest.fixture(scope="module")
def sample_library(tmp_path_factory):
    location = tmp_path_factory.mktemp("wrap_dispatch")
    source = location / "sample.c"
    source.write_text(SAMPLE_PATHS)
    flags = ("-O2", "-fPIC", "-ffunction-sections", "-fdata-sections", "-ffp-contract=off")
    pgo, ref = location / "pgo.o", location / "ref.o"
    for file, value in ((pgo, "20"), (ref, "10")):
        wrap.run(["cc", *flags, f"-DSENTINEL={value}", "-c", source, "-o", file])
    pieces, _ = wrap.splice_objects(location, pgo, ref, "cc", flags)
    patched, baseline = location / "wrapped.so", location / "baseline.so"
    wrap.run(["cc", "-shared", "-Wl,--gc-sections", *pieces, "-o", patched])
    wrap.run(["cc", "-shared", "-Wl,--gc-sections", pgo, "-o", baseline])
    assert wrap.exports(patched) == wrap.exports(baseline)
    return ct.CDLL(str(patched))


def test_wrapping_boundary_and_invalid_inputs(sample_library):
    ptr = ct.c_void_p
    refine = lineage.bind(sample_library, "delay_refine", ct.c_int, ptr, ptr, ct.c_int,
                          ct.c_double, ct.c_double, ct.c_double, ct.POINTER(ct.c_double))
    samples = (ct.c_float * 2)()
    expected = {0: 10, 1: 10, 2: 10, 3: 10, 4: 20, 6500: 20,
                13328: 20, 13329: 10, 13330: 10, 13331: 10, 13332: 10}
    for epoch, routine in expected.items():
        out = RESULT()
        assert refine(samples, samples, epoch, -3000, -800000, 800000, out) == 0
        assert tuple(out[:3]) == (routine, -3000, epoch)
    cases = ((-1, 0., -1., 1.), (13333, 0., -1., 1.), (0, float("nan"), -1., 1.),
             (13332, float("inf"), -1., 1.), (4, 0., 1., 1.), (3, 0., 1., -1.))
    for epoch, hz, lo, hi in cases:
        out = RESULT(1., 2., 3., 4.)
        assert refine(samples, samples, epoch, hz, lo, hi, out) == -1
        assert tuple(out) == (1., 2., 3., 4.)


def test_retains_batched_and_full_coverage_paths(sample_library):
    request = lineage.Request
    bank = lineage.bind(sample_library, "delay_refine_bank", ct.c_int, ct.c_void_p, ct.c_void_p,
                        ct.POINTER(request), ct.c_int, ct.c_double, ct.c_double, ct.POINTER(RESULT))
    samples = (ct.c_float * 2)()
    for epochs, expected in (((0, 4, 13328, 13332), (10, -20, -20, 10)),
                             ((0, 4, 13328, 13332, 100), (10, 20, 20, 10, 20))):
        count = len(epochs)
        seeds = (request * count)(*(request(epoch, 0.) for epoch in epochs))
        out = (RESULT * count)()
        assert bank(samples, samples, seeds, count, -1., 1., out) == 0
        assert tuple(row[0] for row in out) == expected
    assert bank(samples, samples, (request * 1)(), 0, -1., 1., (RESULT * 1)()) == 0
    assert bank(samples, samples, None, 0, -1., 1., None) == -1
    assert sample_library.delay_decimate() == 20


def test_saved_diagnostics_match_full_restoration_byte_for_byte():
    trace = MEASUREMENTS / "receiver-cfo-wrap-trace.json.gz"
    receipt = json.loads(gzip.decompress(trace.read_bytes()))
    assert {(row["visit"], row["lane"], row["channel"]) for row in receipt["rows"]} == set(
        lineage.VISITS
    )
    for row in receipt["rows"]:
        stages = {stage["build"]: stage for stage in row["builds"]}
        restored = stages["restored-delay-product"]
        wrapped = stages["wrapped-delay-refinement"]
        assert restored["refinement"] == wrapped["refinement"]
        assert restored["scout"] == wrapped["scout"]
        for old, new in zip(restored["all_factors"], wrapped["all_factors"], strict=True):
            assert lineage.same_factor(old, new)
