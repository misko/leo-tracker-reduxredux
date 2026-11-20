from types import SimpleNamespace

from tools.pipeline_eval.qualification import cadence_waveform as trial
from tools.pipeline_eval.qualification import cadence_waveform_results as results


class Evaluation:
    def __init__(self, hit):
        self.hit = hit

    def has_fractional_detection(self, _gate):
        return self.hit


def test_online_skip_reuses_the_primary_and_never_invokes_wide_acquisition():
    calls = []
    primary = {0: Evaluation(False), 1: Evaluation(True)}
    wide = Evaluation(False)
    gate = SimpleNamespace(glrt64_margin_gate=0.025)

    def evaluate(_samples, _gate, *, acquisition_config, receiver_id):
        count = len(acquisition_config.anchor_symbols)
        calls.append((receiver_id, count))
        return primary[receiver_id] if count == 12 else wide

    detector = SimpleNamespace(_evaluate_probe=evaluate)
    timer = trial.RetryCadence("miss")

    def call(timestamp, rf):
        with trial.dispatch(detector, timer, rf, timestamp) as (_, attempts):
            for antenna in (0, 1):
                detector._evaluate_probe(
                    None,
                    gate,
                    receiver_id=antenna,
                    acquisition_config=SimpleNamespace(anchor_symbols=range(12)),
                )
            retry = detector._evaluate_probe(
                None,
                gate,
                receiver_id=0,
                acquisition_config=SimpleNamespace(anchor_symbols=range(22)),
            )
        return retry, attempts[0]

    assert call(5, 100)[0] is wide
    calls.clear()
    obj, suppressed = call(7, 100)
    assert obj is primary[0]
    assert suppressed == dict(receiver=0, executed=False, hit=None, cpu_ns=0)
    assert calls == [(0, 12), (1, 12)]
    assert timer.next_allowed[(0, 100)] == 2_000_000_005
    assert call(9, 101)[0] is wide
    assert call(2_000_000_005, 100)[0] is wide


def test_cold_factor_schedule_resets_each_span_and_matches_control_counts():
    def probe(i, hit):
        return dict(
            receiver_id=i, actual_rf_hz=100.0, candidates=[dict(passed_fractional_margin_gate=hit)]
        )

    lock = dict(
        spans=[(0, 0, 3, 0), (0, 3, 6, 0)],
        reference={
            str(v): dict(
                primary=[probe(0, True), probe(1, False)],
                full=[probe(0, True), probe(1, hit)],
                excluded=None,
                delivery_clock=dict(monotonic_ns=v * 600_000_000),
            )
            for v, hit in enumerate((False, True, True, True, False, True))
        },
    )
    selected, events = results.expected(lock)
    assert selected == {"full": set(range(6)), "miss": {0, 3, 4}, "hit": {0, 1, 3}}
    for mode in ("miss", "hit"):
        control = results.equally_spaced(selected[mode], events)
        for span in (0, 1):
            assert sum(events[v][0] == span for v in control) == sum(
                events[v][0] == span for v in selected[mode]
            )


def test_equal_paced_cost_preserves_its_measured_and_inferred_boundaries():
    rows = {
        (v, 0, mode): dict(
            cpu_ns=70 if v == 0 and mode == "miss" else 100,
            attempts=[dict(executed=(v, mode) != (0, "miss"), cpu_ns=25)],
        )
        for v in range(3)
        for mode in trial.MODES
    }
    events = {v: (0, (1, 100.0), v, v == 2) for v in range(3)}
    result = results.control_cost(rows, {2}, events, 0)
    assert result["resident_cpu_s"] == (70 + (100 - 25) + 100) / 1e9
    assert result["measured_retry_cpu_s"] == 25 / 1e9
    assert result["rescues"] == 1
    assert result["visits_by_cost_source"] == {
        "observed_full_path": 1,
        "observed_skipped_path": 1,
        "inferred_skipped_path": 1,
    }
