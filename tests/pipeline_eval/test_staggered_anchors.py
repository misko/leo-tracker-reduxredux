from reports.ALGO08.v3.staggered_anchors import (
    FULL, full_gap, held_replay, known_pairs, measured_rows, retention, schedule,
)


def probes(visits):
    return [dict(visit_index=visit, receiver_id=radio, edge="lower", actual_rf_hz=100. + channel,
                 channel=channel, valid_start_counter=visit*6_000_000, candidates=[])
            for visit, channel in visits for radio in (0, 1)]


def factor(cfo=800):
    return dict(fractional_tracking_cfo_hz=cfo, integer_epoch_sample=4, fractional_epoch_offset_samples=.1,
                fractional_margin=.2, candidate_rank=0, passed_fractional_margin_gate=True)


def test_phase_four_uses_per_stream_admission_without_tail_fill():
    rows, streams = schedule(probes([(i, 1) for i in range(16)] + [(98+i, 2) for i in range(3)]))
    original = full_gap(rows, streams, "coincident")
    shifted = full_gap(rows, streams, "phase_four")
    single = full_gap(rows, streams, "single_alternating")
    assert (original["full_calls_complete_cycles"], shifted["full_calls_complete_cycles"]) == (4, 4)
    assert (original["full_calls"], shifted["full_calls"], single["full_calls"]) == (6, 5, 3)
    assert (original["peak_full_calls_per_visit"], shifted["peak_full_calls_per_visit"]) == (2, 1)
    assert [row["slot"] for row in rows if row["opportunity"]["channel"] == 2] == [0, 0, 1, 1, 2, 2]
    anchors = [(row["slot"], row["opportunity"]["receiver_id"]) for row in rows
               if row["modes"]["single_alternating"] == FULL]
    assert anchors == [(0, 0), (8, 1), (0, 0)]


def test_unmeasured_aperture_is_distinct_from_measured_empty_and_bounds_are_sharp():
    rows, _ = schedule(probes([(0, 1)]))
    tape = [dict(opportunity=row["opportunity"], anchor=True, alternatives={FULL: []}) for row in rows]
    known = measured_rows(tape, rows, [])
    exact = [known_pairs(row, plan, "phase_four") for row, plan in zip(known, rows, strict=True)]
    assert exact == [(True, None), (False, None)]
    owned = [factor(), factor()]
    stats = retention(exact, owned, owned, [True, False])
    assert stats["shared_installed"] == 1 and stats["shared_lost"] == 1
    assert stats["installed_match_bounds"] == [0, 1]
    assert stats["exact_bounds"] == [0, 1]


def test_unknown_anchor_stops_held_history_without_treating_it_as_empty():
    rows, slots = schedule(probes([(i, 1) for i in range(16)]))
    values = [(True, factor())] * len(rows)
    values[9] = (False, None)

    def must_not_start():
        raise AssertionError("No continuation may receive an unmeasured input")

    tally, selected = held_replay(rows, slots, values, "phase_four", must_not_start)
    assert selected is None and tally["decision"] is None
    assert tally["held"][0] == {"complete": 2, "all_measurements_known": 2}
    assert tally["held"][1] == {"complete": 1, "partial": 1, "all_measurements_known": 0}


def test_held_history_erases_the_actual_shifted_anchor_and_keeps_seven_donors():
    rows, slots = schedule(probes([(i, 1) for i in range(16)]))
    all_factors = [(True, factor())] * len(rows)
    traces = []

    class Keep:
        def __init__(self):
            self.calls = []
            traces.append(self.calls)

        def select(self, row):
            active = bool(row["candidates"])
            self.calls.append((row["visit_index"], row["receiver_id"], active))
            return None, 0 if active else None, []

    report, selection = held_replay(rows, slots, all_factors, "phase_four", Keep)
    assert [(visit, radio) for visit, radio, has_factor in traces[0] if not has_factor] == [(0, 0), (4, 1), (8, 0), (12, 1)]
    assert all(active for _, _, active in traces[1])
    assert len(selection) == 32 and report["decision"] == "unfiltered"
