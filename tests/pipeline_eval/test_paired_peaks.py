from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import paired_peaks as paired


def test_same_epoch_and_cfo_alias_merge_to_one_evidence_factor():
    frame = 10_000_000 / 750
    lo = np.array([[frame - 0.2, 107500.0, 1.0, 1.0], [8.0, -40000.0, 1.0, 1.0]])
    hi = np.array([[0.15, -104000.0, 1.4, 1.0], [330.0, 30000.0, 1.1, 1.0]])
    pair = paired.edges(lo, hi, frame)
    assert pair[0].tolist() == [0] and pair[1].tolist() == [0]
    delta = float(paired.stock.fold(hi[0, 1] - lo[0, 1]))
    fused = paired.fused_visit(lo, hi, pair, delta)
    assert fused[0, 1] == lo[0, 1]
    assert fused[:, 2].sum() == 1


def test_relative_clock_is_trained_without_final_held_observations():
    times = np.arange(0.0, 300.0, 2.0)
    center = -39_000.0
    drift = 3.0
    events = [
        (t, int(t), np.array([0.15, 0.60]), np.array([center + drift * (t - 150), 500.0 * t]))
        for t in times
    ]
    fit = paired.calibrate(events, 300.0)
    assert fit["supported"] and fit["aligned_calibration_check"] >= 8
    assert abs(fit["offset_hz"] - center) < 1
    assert abs(fit["drift_hz_per_s"] - drift) < 0.1
    assert fit["final_relative_cfo_rms_hz"] < 1.0
    wrong = [(t, v, dt, df + 18_000 if 30 <= t % 60 < 45 else df) for t, v, dt, df in events]
    failed = paired.calibrate(wrong, 300.0)
    assert failed["supported"] and failed["aligned_final_hold"] == 0
    assert failed["offset_hz"] == fit["offset_hz"]


def test_simultaneous_sample_without_exact_rf_agreement_is_ineligible():
    probe = dict(
        visit_index=1,
        receiver_id=0,
        valid_start_counter=100,
        actual_rf_hz=11.5e9,
        probe_start_ms=0,
        channel=7,
        candidates=[],
    )
    other = dict(probe, receiver_id=1, actual_rf_hz=11.7e9)
    data = SimpleNamespace(
        probes=[probe, other],
        first_counter=0,
        sample_rate_hz=10_000_000,
        duration_s=60,
        probe_ms=20,
    )
    streams, info = paired.synchronized(data, False)
    assert not streams and info["unsupported_visits"] == 1
