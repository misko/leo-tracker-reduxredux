import ctypes as ct

import numpy as np

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.delay_product_native import coefficients
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Factor, Receiver
from tools.pipeline_eval.variants.experimental.receiver_build import build
from tools.pipeline_eval.variants.experimental.receiver_tracking import History, TimingHint, TrackingStats


def test_forecast_uses_counter_thirds_signed_slopes_and_causal_order():
    history = History()
    first = 2_400_000_000_000_003
    times = [first + i * 3_000_007 for i in range(5)]

    def factor(time):
        elapsed = (time - first) / 10_000_000
        epoch = (5701. - 400. * elapsed - (3 * time % 40000)) % 40000 / 3
        return 0, int(epoch), epoch % 1., -260000. - 3100. * elapsed, .42, .21

    assert history.force_full() and history.predict(times[0]) == []
    history.update(times[0], (factor(times[0]),))
    assert history.force_full() and history.predict(times[1]) == []
    history.update(times[1], (factor(times[1]),))
    assert not history.force_full()
    epoch, hz = history.predict(times[2])[0]
    expected = factor(times[2])
    assert abs(epoch - expected[1] - expected[2]) <= .5
    assert abs(hz - expected[3]) < 1e-8
    assert history.predict(times[1] + 20_000_001) == []
    history.update(times[2], (expected,))
    assert history.force_full()


def test_short_residual_can_find_a_birth_and_lost_support_reacquires(tmp_path):
    binary = tmp_path / "tracking.so"
    build(binary, tracking=True, fftw=False, fma=False)
    edge = "lower"
    synthesis = qin_edge_pilot_frame(30_000_000, edge)
    asset = np.concatenate([
        qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll).view("<f4")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    ] + [coefficients(4), synthesis.view("<f4")]).astype("<f4")
    noise = np.random.default_rng(8005).integers(-100, 101, size=(200000, 2, 2), dtype=np.int16)
    first, _ = unit_wave(synthesis, 400, -308000, 143, False)
    newborn, _ = unit_wave(synthesis, 17000, 221000, 201, True)
    sole, _ = mix(noise, 1, [(first, -4)])
    two, _ = mix(noise, 1, [(first, -4), (newborn, -8)])
    rx = Receiver(binary, asset)
    try:
        reference, *_ = rx.timed(sole, 1, 0.)
        assert len(reference) == 1
        ordinary, *_ = rx.timed(two, 1, 0.)
        assert len(ordinary) == 2
        fn = rx.lib.cancellation_factors_tracking
        fn.argtypes = rx.run.argtypes[:-1] + [ct.POINTER(TimingHint), ct.c_uint, ct.c_int,
                                            ct.POINTER(TrackingStats), ct.POINTER(Factor)]
        fn.restype = ct.c_int
        factor = reference[0]
        hint = TimingHint(round(factor[1] + factor[2]), factor[3])
        output, stats = (Factor * 2)(), TrackingStats()
        assert fn(rx.ctx, two.ctypes.data, 1, -800000, 800000, ct.byref(hint), 1, 0,
                  ct.byref(stats), output) == 2
        assert stats.narrow_first == stats.short_residual == 1
        assert stats.global_first == stats.reacquire == 0
        assert abs(output[0].hz + 308000) < 400 or abs(output[1].hz + 308000) < 400
        assert abs(output[0].hz - 221000) < 400 or abs(output[1].hz - 221000) < 400
        assert all(row.exact - row.control >= .025 for row in output)
        assert fn(rx.ctx, noise.ctypes.data, 1, -800000, 800000, ct.byref(hint), 1, 0,
                  ct.byref(stats), output) == 0
        assert stats.reacquire == stats.global_first == 1
    finally:
        rx.close()
