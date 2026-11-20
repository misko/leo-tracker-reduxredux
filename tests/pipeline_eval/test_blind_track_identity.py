from types import SimpleNamespace

import numpy as np

from tools.pipeline_eval.variants import blind_track_identity as method


def arc(norads, levels, t, rate=0):
    t = np.asarray(t)
    levels = np.array(levels, dtype=float)
    return method.Candidates(
        (0, 2, 11e9),
        t,
        np.zeros(len(t)),
        9,
        np.array(norads),
        np.zeros(len(norads)),
        method.fixed.fold(levels[:, None] + rate * (t - 60)),
        levels,
        np.full(len(norads), rate),
        np.zeros(len(norads)),
    )


def test_another_track_clock_disambiguates_untied_orbits():
    t = np.arange(16, dtype=float)
    target = arc([101, 201], [18000, -10000], t)
    other = arc([102, 202], [18000, -25000], t + 22)
    third = arc([103, 203], [18000, -40000], t + 55)
    result = method.identify([target, other, third], 120, common=True)
    assert {a.norads[j] for a, j, _, _ in result} == {101, 102, 103}
    assert method.identify([target, other, third], 120, common=False) == []
    assert method.identify([target, other], 120, common=True) == []


def test_clock_refinement_respects_the_wrapped_receiver_axis():
    t = np.arange(16, dtype=float)
    peers = [(arc([100], [113600], t + 20, 8.0), 0), (arc([200], [113600], t + 91, 8.0), 0)]
    level, drift = method.refine_clock(peers, 120, -113000, 0)
    assert abs(method.fixed.fold(level - 113600)) < 1e-7
    assert abs(drift - 8) < 1e-7


def test_training_linker_never_ingests_held_or_guard_peaks(monkeypatch):
    visits = []

    class Recorder:
        def ingest(self, t, _key, rows):
            visits.append((t, rows))

        def document(self):
            return {"tracks": []}, {}

    monkeypatch.setattr(method, "Tracker", Recorder)
    times = [1, 26, 29, 36, 45, 51]
    peaks = [
        dict(
            candidate_rank=0,
            fractional_margin=0.07,
            fractional_tracking_cfo_hz=1200,
            passed_fractional_margin_gate=True,
        )
    ]
    probes = [
        dict(
            receiver_id=0,
            channel=2,
            actual_rf_hz=11e9,
            valid_start_counter=t * 10**7,
            visit_index=i,
            candidates=peaks,
        )
        for i, t in enumerate(times)
    ]
    cap = SimpleNamespace(
        probes=probes, first_counter=0, sample_rate_hz=1e7, probe_ms=20, duration_s=75
    )
    lanes, tracks, _ = method.observations(cap, False)
    assert len(lanes[0].t) == len(times) and tracks == []
    assert [int(t) for t, _ in visits] == [1, 26, 51]
