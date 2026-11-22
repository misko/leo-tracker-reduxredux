from collections import Counter

import numpy as np

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.delay_product_native import coefficients
from tools.pipeline_eval.variants.experimental.receiver_aperture import compare
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver
from tools.pipeline_eval.variants.experimental.receiver_build import build


def test_counts_weak_residual_loss_independently_of_an_extra():
    primary = (0, 120, 0., -350000., .39, .05)
    weaker = (1, 9000, 0., -550000., .19, .06)
    extra = (1, 323, .01, 440000., .13, .07)
    counts = Counter()
    compare([primary, weaker], [primary, extra], counts)
    assert counts["missed_second_scan"] == counts["missed_lower_margin"] == 1
    assert counts["extra_second_scan"] == counts["extra_lower_margin"] == 1


def test_half_window_can_miss_a_real_planted_pilot_in_the_late_half(tmp_path):
    exact, short = tmp_path / "exact.so", tmp_path / "short.so"
    build(exact, fftw=False, fma=False)
    build(short, fftw=False, fma=False, short_aperture=True)
    edge = "lower"
    synthesis = qin_edge_pilot_frame(30_000_000, edge)
    asset = np.concatenate([
        qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll).view("<f4")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    ] + [coefficients(4), synthesis.view("<f4")]).astype("<f4")
    rng = np.random.default_rng(8005)
    noise = rng.integers(-500, 501, size=(200000, 2, 2), dtype=np.int16)
    waveform, _ = unit_wave(synthesis, 400, -308000, 143, False)
    iq, clips = mix(noise, 0, [(waveform, 5)])
    assert not clips
    iq[:100000, 0] = 0
    full, prefix = Receiver(exact, asset), Receiver(short, asset)
    try:
        factors, *_ = full.timed(iq, 0, 0)
        assert any(abs(row[3] + 308000.) < 400 and row[4] - row[5] >= .025 for row in factors)
        measured, *_ = prefix.timed(iq, 0, 0)
        assert not measured
    finally:
        full.close()
        prefix.close()
