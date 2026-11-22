import ctypes as ct

import numpy as np

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.delay_product_native import coefficients
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Factor, Receiver
from tools.pipeline_eval.variants.experimental.receiver_build import build
from tools.pipeline_eval.variants.experimental.receiver_shortlist import (
    RANKS,
    ShortlistAudit,
    ShortlistFast,
    call_fast,
    ranks_summary,
)


def test_rank_summary_separates_absent_targets_and_unpruned_candidates():
    hit = dict.fromkeys(RANKS, 0) | dict(residual=(), first_confirmed=1, coarse_rank=7, verified_rank=7)
    miss = dict.fromkeys(RANKS, 0) | dict(residual=(), first_confirmed=1, timing_cell_rank=89)
    empty = dict.fromkeys(RANKS, 0) | dict(residual=None, first_confirmed=0)
    result = ranks_summary([hit, miss, empty])
    assert result["first_confirmed"] == result["verified_residual_targets"] == 2
    assert result["coverage"]["coarse_rank"] == result["coverage"]["timing_cell_rank"] == 1
    assert result["verified_rank_at_most_four"] == 0


def test_original_first_scout_rank_trace_verifies_a_planted_signed_carrier(tmp_path):
    binary = tmp_path / "shortlist.so"
    build(binary, fftw=False, fma=False, shortlist_audit=True)
    synthesis = qin_edge_pilot_frame(30_000_000, "lower")
    asset = np.concatenate([
        qin_edge_pilot_frame(10_000_000, "lower", symbol_roll=roll).view("<f4")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    ] + [coefficients(4), synthesis.view("<f4")]).astype("<f4")
    rng = np.random.default_rng(44)
    noise = rng.integers(-500, 501, size=(200000, 2, 2), dtype=np.int16)
    waveform, _ = unit_wave(synthesis, 400, -308000, 143, False)
    iq, clips = mix(noise, 0, [(waveform, 0)])
    assert not clips
    rx = Receiver(binary, asset)
    try:
        reference, *_ = rx.timed(iq, 0, 0)
        first = next(p for p in reference if p[0] == 0)
        assert abs(first[3] + 308000) < 400
        inspect = rx.lib.receiver_audit_shortlist
        inspect.argtypes = rx.run.argtypes[:-1] + [ct.c_double, ct.c_double, ct.POINTER(ShortlistAudit)]
        inspect.restype = ct.c_int
        observation = ShortlistAudit()
        assert inspect(rx.ctx, iq.ctypes.data, 0, -800000, 800000,
                       first[1] + first[2], first[3], ct.byref(observation)) == 0
        assert observation.first_confirmed and observation.seeds_used == 24
        assert 0 < observation.coarse_rank <= observation.verified_rank <= 4
        assert rx.timed(iq, 0, 0)[0] == reference
        fast = rx.lib.receiver_shortlist_fast
        fast.argtypes = rx.run.argtypes[:-1] + [ct.POINTER(ShortlistFast), ct.POINTER(Factor)]
        fast.restype = ct.c_int
        factors, _, stats = call_fast(rx, iq, 0, 0)
        assert factors == reference and stats["first_confirmed"] == 1
        assert stats["full_residual"] == 1
    finally:
        rx.close()
