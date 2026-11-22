from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import single_scan_trial
from tools.pipeline_eval.qualification.full_v5_check import _probe, factor_candidate
from tools.pipeline_eval.qualification.single_scan_position import Factor
from tools.pipeline_eval.variants.experimental import residual_receiver


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    binary, asset = tmp_path / "reviewed.so", tmp_path / "lower.f32"
    binary.write_bytes(b"reviewed conditional library")
    digest = sha256(binary.read_bytes()).hexdigest()
    monkeypatch.setattr(residual_receiver, "DETECTOR_SHA256", digest)
    np.zeros(133413, dtype="<f4").tofile(asset)
    return binary, asset


def window(visit):
    return SimpleNamespace(
        acquisition=dict(global_visit=visit, sample_start=visit * 4_000_000,
                         actual_if_center_hz=1000),
        target=dict(channel=2 if visit == 4 else 1, edge="lower",
                    rf_center_hz=1003, lnb_lo_hz=0),
        receiver_ids=(0, 1), sample_rate_hz=10_000_000,
        samples=np.zeros((200_000, 2, 2), dtype="<i2"),
    )


def test_eager_calls_preserve_lane_order_and_use_cold_continuation(inputs, monkeypatch):
    binary, asset = inputs
    records, closed = [], []
    current = None

    def raw_candidate(lane):
        hz = 60_000 if lane else -25_000
        return Factor(0, 321, .25, hz, .5, .1)

    def entry(residual):
        def run(ctx, pointer, lane, lo, hi, vector):
            assert ctx == 7
            assert pointer == current.samples.ctypes.data
            assert (lo, hi) == (-799997, 800003)
            visit = current.acquisition["global_visit"]
            records.append((visit, lane, residual))
            raw = raw_candidate(lane)
            if residual and lane == 0 and visit in (0, 3):
                # A stronger, separate frequency appears first in native order.
                vector[0] = Factor(1, 111, .75, 600_000 + 50_000 * visit, .9, .02)
                vector[1] = raw
                return 2
            vector[0] = raw
            return 1
        return run

    class Native:
        def __init__(self, path, payload):
            assert path == binary and payload.shape == (133413,)
            self.ctx = 7
            self.lib = SimpleNamespace(cancellation_factors=entry(True),
                                       cancellation_primary_factors=entry(False))

        def close(self):
            closed.append(True)

    monkeypatch.setattr(single_scan_trial, "Native", Native)
    receiver = residual_receiver.ResidualReceiver()
    with receiver.detector("cancellation", "lower", binary=binary, pilot=asset) as receive:
        for visit in range(5):
            current = window(visit)
            rows = receive(current)
            expected = []
            for lane in (0, 1):
                f = raw_candidate(lane)
                selected = [factor_candidate(
                    f.rank, f.integer, status="complete", offset=f.offset, cfo=f.hz,
                    exact=f.exact, control=f.control, margin=f.exact - f.control,
                )] if visit == 3 else []
                expected.append(_probe(current, lane, selected))
            assert rows == expected
    assert closed == [True]
    assert records == [(visit, lane, lane == 0 or visit in (0, 3, 4))
                       for visit in range(5) for lane in (0, 1)]
    assert receiver.receipt() == dict(
        factor_calls=10, residual_requests=8, primary_only_requests=2,
        schedule_reasons={"sentinel": 6, "activity": 2, "skip": 2},
        query_cpu_ns=receiver.query_cpu_ns,
    )
    assert receiver.query_cpu_ns > 0
    with pytest.raises(RuntimeError, match="scope has closed"):
        receive(window(5))


def test_binary_pin_is_checked_before_loading_the_native_library(inputs, monkeypatch):
    binary, asset = inputs
    binary.write_bytes(b"tampered conditional library")
    monkeypatch.setattr(
        single_scan_trial, "Native", lambda *_: pytest.fail("loaded unreviewed native"),
    )
    receiver = residual_receiver.ResidualReceiver()
    with (
        pytest.raises(ValueError, match="reviewed native detector"),
        receiver.detector("cancellation", "lower", binary=binary, pilot=asset),
    ):
        pytest.fail("opened unreviewed native")
