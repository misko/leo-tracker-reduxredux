from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from threading import Event

from tools.pipeline_eval.__main__ import encoded
from tools.pipeline_eval.qualification import online_full as full
from tools.pipeline_eval.qualification import online_prefix as prefix
from tools.pipeline_eval.reference.native_archive import NativeArchive


def document():
    first, rate = 2000, 10_000_000
    start_offsets = [0, 1_199_700_000, 1_200_000_000, 2_400_000_000, 2_999_600_000]
    clocks, probes = [], []
    for visit, off in enumerate(start_offsets):
        clocks.append(dict(monotonic_ns=3_000_000 + off * 100, realtime_ns=9_000_000 + off * 100))
        for receiver in (0, 1):
            probes.append(
                dict(
                    visit_index=visit,
                    receiver_id=receiver,
                    channel=visit % 8 + 1,
                    valid_start_counter=first + off,
                    probe_start_ms=0,
                    probe_index=0,
                )
            )
    return dict(
        source=dict(
            probes=probes,
            sample_rate_hz=rate,
            probe_ms=20,
            session_id="acquisition-start",
            analysis_manifest_sha256="full",
        ),
        clock_anchor=dict(
            sample_counter=first,
            before=dict(monotonic_ns=0, realtime_ns=6_000_000),
            after=clocks[0],
        ),
        provenance=dict(
            window_count=len(clocks),
            invalid_capture=0,
            processed_windows=len(clocks),
            excluded_windows=[],
        ),
        delivery_clocks=clocks,
        last_sample_counter=first + start_offsets[-1] + 200_000,
        secret="future-only",
    )


def test_native_prefix_copies_only_complete_accounted_visits_and_clock_envelope():
    original = document()
    view, receipt = prefix.snapshot(original, 120)
    assert len(view["source"]["probes"]) == 4
    assert len(view["delivery_clocks"]) == 2
    assert len(list(NativeArchive(StringIO(encoded(view).decode())))) == 4
    assert view["provenance"]["window_count"] == 2
    assert "secret" not in view and "analysis_manifest_sha256" not in view["source"]
    assert (
        receipt["first_noncausal_end_counter"]
        > original["clock_anchor"]["sample_counter"] + 120 * 10_000_000
    )
    view, receipt = prefix.snapshot(original, 300)
    assert receipt["uses_complete_capture"]
    assert view["source"]["probes"] == original["source"]["probes"]
    assert receipt["available_at_elapsed_s"] == [300, 300]


def row(t, point, ids, *, refreshed=True, wall=5):
    support = {str(i): dict(latest_s=(t - 0.1 if refreshed and i < 2 else 110)) for i in ids}
    return dict(
        checkpoint=t,
        capture=dict(actual_last_sample_s=t, available_at_elapsed_s=[t, t + 0.1]),
        orbit_support={"c0": support},
        worker_wall_s=wall,
        result=dict(arms={"c0": dict(latlon=point, forced_latlon=(0, 0))}),
    )


def test_stopping_uses_adjacent_publications_and_new_observations_on_shared_orbits():
    rows = [row(t, (0, t / 200_000), range(4)) for t in prefix.HORIZONS]
    assert prefix.stable_stop(rows, "c0")[:2] == (1, "adjacent agreement")
    rows[1] = row(180, None, range(4))
    assert prefix.stable_stop(rows, "c0")[0] == 3
    rows[1] = row(180, (0, 0), range(2, 6))
    assert prefix.stable_stop(rows, "c0")[0] == 3
    rows[3] = row(300, (0, 0), range(4), refreshed=False)
    assert prefix.stable_stop(rows, "c0")[:2] == (3, "ordinary deadline")


def test_time_scenario_backlogs_work_but_overlaps_acquisition():
    rows = [row(120, None, [], wall=65), row(180, None, [], wall=5), row(240, None, [], wall=11)]
    assert prefix.timeline(rows) == [[185, 185.1], [190, 190.1], [251, 251.1]]


def test_parallel_runner_serializes_pilot_cutoff_and_keeps_distinct_frontiers(
    monkeypatch, tmp_path
):
    original = prefix.contiguous_prefix.restrict
    entered, release, later_invoked, later_entered = (Event() for _ in range(4))

    def observe(data, *, prefix):
        source = full.prefix.contiguous_prefix
        cutoff = source.PREFIX_SECONDS
        if not entered.is_set():
            entered.set()
            assert release.wait(3)
        else:
            later_entered.set()
        assert cutoff == source.PREFIX_SECONDS
        return original(data, prefix=prefix)

    monkeypatch.setattr(prefix.contiguous_prefix, "restrict", observe)

    def item(name):
        return dict(path=f"/input/{name}", sha256=name)

    job = dict(
        id="test",
        recording="test",
        condition="matched",
        request=dict(
            native=item("native"),
            catalogue=item("catalogue"),
            track_config=item("track_config"),
            offer={},
        ),
    )
    earlier, later = tmp_path / "earlier", tmp_path / "later"
    earlier.mkdir()
    later.mkdir()

    def later_job():
        later_invoked.set()
        return full.snapshot_job(job, document(), {}, 180, later)

    with ThreadPoolExecutor(2) as pool:
        first = pool.submit(full.snapshot_job, job, document(), {}, 120, earlier)
        assert entered.wait(3)
        second = pool.submit(later_job)
        assert later_invoked.wait(3)
        try:
            assert not later_entered.wait(0.1)
        finally:
            release.set()
        a = first.result(timeout=3)[2]["capture"]
        b = second.result(timeout=3)[2]["capture"]
    assert (a["expected_probes"], b["expected_probes"]) == (4, 6)
    assert a["actual_last_sample_s"] <= 120 and b["actual_last_sample_s"] <= 180
