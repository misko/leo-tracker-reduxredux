import ctypes as ct

import numpy as np
import pytest

from leo.analysis.starlink.templates import CONTROL_SYMBOL_ROLL, qin_edge_pilot_frame
from tools.pipeline_eval.qualification.two_carrier_injections import mix, unit_wave
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.delay_product_native import coefficients
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver
from tools.pipeline_eval.variants.experimental.receiver_build import build


@pytest.fixture(scope="module")
def binaries(tmp_path_factory):
    root = tmp_path_factory.mktemp("receiver")
    oracle, experiment = root / "oracle.so", root / "experiment.so"
    build(oracle, fftw=False, fma=False, early_gate=False, reuse=False)
    build(experiment, fftw=False, fma=False)
    return oracle, experiment


def test_overlapped_refinement_preserves_reduction_order(binaries):
    rng = np.random.default_rng(1134)
    signal = rng.integers(-2048, 2048, 400000).astype(np.float32)
    pilot = rng.normal(size=2 * 2816).astype(np.float32)
    fir = coefficients(4)
    filter_output = []
    refined = []
    for binary in binaries:
        lib = ct.CDLL(str(binary))
        decimate = lib.delay_decimate
        decimate.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_int, ct.c_void_p]
        result = np.empty(100000, np.float32)
        assert decimate(signal.ctypes.data, fir.ctypes.data, len(fir), 4, result.ctypes.data) == 0
        filter_output.append(result)

        refine = lib.delay_refine
        refine.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int, ct.c_double, ct.c_double,
                           ct.c_double, ct.POINTER(ct.c_double)]
        rows = []
        for epoch in (0, 3, 4, 77, 7281, 13328, 13329, 13332):
            for frequency in (-798000, -171000, 411000, 798000):
                result = (ct.c_double * 4)()
                assert refine(signal.ctypes.data, pilot.ctypes.data, epoch, frequency,
                              -800000, 800000, result) == 0
                rows.append(tuple(result))
        refined.append(rows)
    assert np.array_equal(*filter_output)
    assert refined[0] == refined[1]


@pytest.mark.parametrize("edge", ["lower", "upper"])
def test_keeps_verified_pair_and_independent_causal_lane_history(binaries, edge):
    synthesis = qin_edge_pilot_frame(30_000_000, edge)
    asset = np.concatenate([
        qin_edge_pilot_frame(10_000_000, edge, symbol_roll=roll).view("<f4")
        for roll in (0, CONTROL_SYMBOL_ROLL)
    ] + [coefficients(4), synthesis.view("<f4")]).astype("<f4")
    rng = np.random.default_rng(8005)
    noise = rng.integers(-100, 101, size=(200000, 2, 2), dtype=np.int16)
    left, _ = unit_wave(synthesis, 400, -308000, 143, False)
    right, _ = unit_wave(synthesis, 17000, 221000, 201, True)
    two, clips = mix(noise, 1, [(left, -7), (right, -9)])
    assert clips == 0
    swapped = two[:, ::-1, :].copy()
    arms = []
    for binary in binaries:
        receiver = Receiver(binary, asset)
        try:
            history = Continuation()
            rows = []
            for index in range(6):
                for lane in (0, 1):
                    factors, *_ = receiver.timed(two, lane, 0)
                    selection = history.select(dict(receiver_id=lane, channel=3, actual_rf_hz=0,
                                                    valid_start_counter=index * 5_000_000,
                                                    candidates=[receiver.criteria(*f) for f in factors]))
                    rows.append((factors, selection))
            assert receiver.timed(swapped, 0, 0)[0] == rows[1][0]
            assert receiver.timed(swapped, 1, 0)[0] == rows[0][0]
        finally:
            receiver.close()
        arms.append(rows)
    assert arms[0] == arms[1]
    assert not arms[0][0][0]
    factors = arms[0][1][0]
    assert len(factors) == 2
    np.testing.assert_allclose(sorted(f[3] for f in factors), [-308000, 221000], atol=400)
    assert all(f[4] - f[5] >= 0.025 for f in factors)
    assert all(arms[0][2 * i + 1][1][1] is None for i in range(3))
    assert all(arms[0][2 * i + 1][1][1] is not None for i in range(3, 6))
