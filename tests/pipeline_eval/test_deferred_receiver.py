from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import blind_compact_run
from tools.pipeline_eval.qualification.full_v5_check import _probe
from tools.pipeline_eval.variants.experimental.deferred_receiver import (
    DeferredReceiver,
    _immutable_iq,
)


def samples():
    return np.zeros((200_000, 2, 2), dtype="<i2")


def test_iq_backing_is_immutable_for_a_delayed_request():
    source = samples()
    stable = np.frombuffer(source.tobytes(), dtype="<i2").reshape(source.shape)
    assert _immutable_iq(stable) is stable
    exposed = source.view()
    exposed.flags.writeable = False
    snapshot = _immutable_iq(exposed)
    source[0, 0, 0] = 12
    assert snapshot[0, 0, 0] == 0
    assert exposed[0, 0, 0] == 12
    assert not snapshot.flags.writeable
    with pytest.raises(ValueError):
        snapshot.flags.writeable = True


def test_queries_only_one_lane_on_a_stable_older_window_and_releases_pending_data():
    calls = []

    @contextmanager
    def detector(method, edge, *, binary=None, pilot=None):
        assert method == "cancellation" and edge == "lower"
        real = blind_compact_run.Continuation()

        def receive(window):
            visit = window.acquisition["global_visit"]
            calls.append((visit, window.receiver_ids))
            rows = []
            for lane in window.receiver_ids:
                assert window.samples[0, lane, 0] == 100 * visit + lane
                hz = 42_000 - 80_000 * lane
                candidates = [factor(hz)]
                if visit == 6:
                    candidates = [factor(hz + 250_000, margin=.9), factor(hz, rank=1)]
                row = _probe(window, lane, candidates)
                _, index, _ = real.select(row)
                rows.append(dict(row, candidates=[] if index is None else [candidates[index]]))
            return rows

        yield receive

    def factor(hz, rank=0, margin=.2):
        return dict(fractional_tracking_cfo_hz=hz, candidate_rank=rank, fractional_margin=margin)

    raw = samples()

    def window(visit):
        raw[0, :, 0] = [100 * visit, 100 * visit + 1]
        return SimpleNamespace(
            acquisition=dict(global_visit=visit, sample_start=visit * 4_000_000,
                             actual_if_center_hz=1000),
            target=dict(rf_center_hz=1000, lnb_lo_hz=0, edge="lower",
                        channel=2 if visit == 7 else 1),
            receiver_ids=(0, 1), sample_rate_hz=10_000_000, samples=raw,
        )

    visits = 8
    with detector("cancellation", "lower") as stock:
        expected = [stock(window(visit)) for visit in range(visits)]
    calls.clear()
    continuation = blind_compact_run.Continuation
    adapter = DeferredReceiver()
    with adapter.wrap(detector)("cancellation", "lower") as deferred:
        assert blind_compact_run.Continuation is continuation
        for visit in range(visits):
            current = window(visit)
            assert deferred(current) == expected[visit]
            raw[0, :, 0] = -99
            current.acquisition["global_visit"] = -1
            current.target["channel"] = 8
        assert adapter.planner.pending
    assert all(len(lanes) == 1 for _, lanes in calls)
    assert calls[0] == (3, (0,)) and (0, (0,)) in calls[1:]
    assert adapter.native_calls == len(calls) < 2 * visits
    assert adapter.query_cpu_ns > 0
    assert not adapter.planner.pending
    assert all(visit.measure is None for history in adapter.planner.lanes.values()
               for visit in history)
    assert expected[6][0]["candidates"] == [factor(42_000, rank=1)]
    assert expected[6][1]["candidates"] == [factor(-38_000, rank=1)]
    with pytest.raises(RuntimeError, match="scope has closed"):
        deferred(window(visits))


def test_invalid_signed_band_fails_before_the_first_deferred_decision():
    @contextmanager
    def detector(*args, **kwargs):
        def receive(window):
            pytest.fail("invalid signed band reached the detector")

        yield receive

    window = SimpleNamespace(
        acquisition=dict(actual_if_center_hz=0),
        target=dict(rf_center_hz=4_200_001, lnb_lo_hz=0),
        receiver_ids=(0, 1), sample_rate_hz=10_000_000, samples=samples(),
    )
    adapter = DeferredReceiver()
    with (
        adapter.wrap(detector)("cancellation", "lower") as receive,
        pytest.raises(ValueError, match="native exported factors"),
    ):
        receive(window)
    assert adapter.native_calls == 0
