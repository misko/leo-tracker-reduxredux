import ctypes as ct
import math
import os
import subprocess

import numpy as np
import pytest

from leo.analysis.starlink.templates import OFDM_SYMBOL_DURATION_S, qin_edge_pilot_frame
from tools.pipeline_eval.variants import phase_scout, phase_scout_coherent

RATE = 10_000_000
ALL = (1 << 21) - 1


@pytest.fixture(scope="module")
def mask(tmp_path_factory):
    directory = tmp_path_factory.mktemp("lag")
    source, target = directory / "scout.c", directory / "scout.so"
    source.write_text(
        '#include "phase_scout_mask.h"\n'
        "unsigned check(const float *iq, double rate) { double f[3],rho[3];\n"
        "return phase_scout_mask((const float(*)[2])iq,rate,f,rho);}\n"
    )
    subprocess.run(
        [
            "cc",
            "-std=c11",
            "-shared",
            "-fPIC",
            "-I",
            str(phase_scout.HEADER.parent),
            str(source),
            "-lm",
            "-o",
            str(target),
        ],
        check=True,
        env=os.environ | {"TMPDIR": str(directory)},
    )
    function = ct.CDLL(str(target)).check
    function.argtypes = [ct.POINTER(ct.c_float), ct.c_double]
    function.restype = ct.c_uint

    def evaluate(hz, strength=0.12, rate=RATE):
        a = (ct.c_float * 6)(
            *(
                s
                for f, lag in zip(hz, (1, 3, 5), strict=True)
                for s in (
                    strength * math.cos(2 * math.pi * f * lag / rate),
                    strength * math.sin(2 * math.pi * f * lag / rate),
                )
            )
        )
        return function(a, rate)

    return evaluate


@pytest.mark.parametrize("hz", [-798_000, -357_122, 109_323, 795_001])
def test_signed_off_grid_lag_resolution(mask, hz):
    selected = mask([hz] * 3)
    expected = round((hz + 800_000) / 80_000)
    assert selected & (1 << expected)
    assert 3 <= selected.bit_count() <= 5


def test_weak_inconsistent_alias_and_unsupported_use_complete_grid(mask):
    assert mask([0] * 3, strength=0.02) == ALL
    assert mask([-200_000, 300_000, -200_000]) == ALL
    assert mask([995_000] * 3) == ALL
    assert mask([300_000] * 3, rate=2_500_000) == ALL


@pytest.mark.parametrize("edge, hz", [("lower", -360_555), ("upper", 736_100)])
def test_pilot_coherent_phase_matches_signed_clean_iq(edge, hz):
    t = qin_edge_pilot_frame(RATE, edge)
    v = np.zeros(RATE // 50, dtype=complex)
    for k in range(14):
        begin = round(k * RATE / 750) + 735
        v[begin : begin + len(t)] = t
    v *= np.exp(2j * np.pi * hz * np.arange(len(v)) / RATE)
    estimator = phase_scout_coherent.CoherentPilot(t, OFDM_SYMBOL_DURATION_S)
    selected, _ = estimator.allocate(v, 735)
    assert selected != ALL and selected & 1 << round((hz + 800_000) / 80_000)
    assert estimator.allocate(np.zeros_like(v), 735)[0] == ALL
