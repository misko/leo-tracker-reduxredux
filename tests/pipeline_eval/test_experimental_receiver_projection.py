import numpy as np

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.delay_product_native import coefficients
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver
from tools.pipeline_eval.variants.experimental.receiver_build import build
from tools.pipeline_eval.variants.experimental.receiver_projection import ProjectionVisit, bind, score, timed


def test_score_tracks_both_passes_and_signed_carrier_branch():
    exact = [(0, 13332, 0., -270000., .12, .04), (1, 4000, 0., 350000., .08, .03)]
    trace = ProjectionVisit()
    for scan, factor in zip(trace.scan, exact, strict=True):
        scan.attempted = scan.seed_count = 1
        scan.seeds[0].hz = factor[3]
        scan.seeds[0].epoch = factor[1]
    trace.scan[0].seeds[0].epoch = 0
    trace.scan[1].seeds[0].hz *= -1
    counts = score(exact, exact[:1], trace)
    assert counts["first_shortlist_recall"] == counts["first_finally_matched"] == 1
    assert counts["residual_shortlist_recall"] == counts["residual_finally_matched"] == 0


def test_guarded_projection_keeps_signed_residual_verification(tmp_path):
    binary = tmp_path / "projection.so"
    build(binary, fftw=False, fma=False, projection=True)
    synthesis = qin_edge_pilot_frame(30_000_000, "lower")
    asset = np.concatenate([
        qin_edge_pilot_frame(10_000_000, "lower", symbol_roll=roll).view("<f4")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    ] + [coefficients(4), synthesis.view("<f4")]).astype("<f4")
    noise = np.random.default_rng(8005).integers(-1024, 1025, size=(200000, 2, 2), dtype=np.int16)
    noise[:, 0, :] = 0
    first, _ = unit_wave(synthesis, 400, -308000, 143, False)
    second, _ = unit_wave(synthesis, 17000, 221000, 201, True)
    raw, clips = mix(noise, 1, [(first, 10), (second, -2)])
    assert not clips
    receiver = Receiver(binary, asset)
    try:
        bind(receiver)
        empty, silent_trace, _ = timed(receiver, raw, 0, 0, "guarded")
        assert not empty and silent_trace.scan[0].zero and not silent_trace.fallback
        exact, *_ = timed(receiver, raw, 1, 0, "exact")
        matched, trace, _ = timed(receiver, raw, 1, 0, "guarded")
        assert exact == matched and len(matched) == 2
        assert trace.fallback == trace.scan[0].attempted == trace.scan[1].attempted == 1
        assert not trace.scan[1].zero
    finally:
        receiver.close()
