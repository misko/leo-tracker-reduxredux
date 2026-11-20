import ctypes as ct
import subprocess
from pathlib import Path

import numpy as np

from tools.pipeline_eval.qualification import native_hotpath_build, native_hotpath_eval
from tools.pipeline_eval.variants import differential_pilot

WITNESS = r"""
#include <stdint.h>
#include <string.h>
typedef float fftwf_complex[2];
static const int lags[3] = {1, 3, 5};
#include "native_hotpath_fold.h"
#include "native_hotpath_rank.h"

int rank_first(const double *scores, int n, int *epoch) {
    return native_hotpath_first(scores, n, epoch);
}

int exact_fold(void) {
#ifdef LEO_NATIVE_HOTPATH_AVX2
    if (!__builtin_cpu_supports("avx2")) return 1;
    const int16_t values[] = {INT16_MIN, INT16_MAX, -25793, 0, 1, 19, -17747};
    int16_t raw[4*27];
    for (size_t i=0; i<sizeof(raw)/sizeof(*raw); ++i)
        raw[i] = values[(i*i + 3*i + i/3) % 7];
    size_t valid[3] = {19, 17, 16};
    for (int rx=0; rx<2; ++rx) {
        fftwf_complex folded[3][20] = {{{0}}}, scalar[3][20] = {{{0}}};
        fftwf_complex *rows[] = {folded[0], folded[1], folded[2]};
        for (int offset=0; offset<3; ++offset) {
            size_t done = native_hotpath_fold4(rows, raw, 0, offset, valid, rx);
            if (done != 16) return 0;
            for (int m=0; m<3; ++m) for (size_t k=0; k<done; ++k) {
                const int16_t *a=raw+4*(offset+k)+2*rx, *b=a+4*lags[m];
                float ai=a[0], aq=a[1], bi=b[0], bq=b[1];
                scalar[m][k][0] += bi*ai+bq*aq;
                scalar[m][k][1] += bq*ai-bi*aq;
            }
            if (memcmp(folded, scalar, sizeof(folded))) return 0;
        }
    }
#endif
    return 1;
}
"""


def test_native_fold_and_first_rank_preserve_original_arithmetic(tmp_path):
    unit = tmp_path / "unit.c"
    unit.write_text(WITNESS)
    library = tmp_path / "unit.so"
    subprocess.run(
        [
            "cc",
            "-O3",
            "-ffp-contract=off",
            "-shared",
            "-fPIC",
            "-I",
            str(native_hotpath_build.VARIANTS),
            str(unit),
            "-o",
            str(library),
        ],
        check=True,
    )
    port = ct.CDLL(str(library))
    assert port.exact_fold() == 1
    port.rank_first.argtypes = (ct.POINTER(ct.c_double), ct.c_int, ct.POINTER(ct.c_int))
    rng = np.random.default_rng(59291)
    zero = np.zeros(differential_pilot.FRAME)
    tied = zero.copy()
    tied[[0, 1, 125, 126, -1]] = 1
    cases = (zero, tied, np.ones_like(zero), -np.ones_like(zero), rng.standard_normal(zero.shape))
    for scores in cases:
        expected = differential_pilot.ranked_centers(scores)
        got = ct.c_int()
        assert (
            port.rank_first(scores.ctypes.data_as(ct.POINTER(ct.c_double)), len(scores), got) == 0
        )
        assert got.value == (expected[0] if expected else -1)
    zero[17] = np.nan
    assert port.rank_first(zero.ctypes.data_as(ct.POINTER(ct.c_double)), len(zero), got) != 0


def test_receipt_rejects_changed_selection_and_support():
    saved = dict(payload_sha256="rows", hints=[12, 24], trace=["complete"])
    evidence = {name: dict(saved) for name in native_hotpath_eval.ROLES}
    assert native_hotpath_eval.comparable(evidence)
    evidence["hotpath"]["hints"] = [12, 25]
    assert not native_hotpath_eval.comparable(evidence)
    evidence["hotpath"] = saved | {"trace": ["changed"]}
    assert not native_hotpath_eval.comparable(evidence)


def test_overlay_is_confined_to_shared_dual_lane_fold():
    path = Path(native_hotpath_build.DERIVED)
    source = (
        "static void fold_three(fftwf_complex *out[3],const int16_t *raw)\n{\n"
        "#ifdef LEO_PROPOSAL_NEON_FOLD\n    keep_existing_neon();\n"
        "#else\n    fold_three_scalar(out,raw,start,off,valid,rx);\n#endif\n}\n"
        "static void fold_three_single(void) { keep_existing_single(); }\n"
    )
    result = native_hotpath_build.overlay(source)
    assert path.name == "proposal_core.c"
    assert "native_hotpath_fold4" in result
    assert "keep_existing_neon();" in result
    assert (
        result.rsplit("static void fold_three_single", 1)[1]
        == source.rsplit("static void fold_three_single", 1)[1]
    )
