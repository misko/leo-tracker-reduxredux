import pytest

from tools.pipeline_eval.qualification import second_on_miss_whole as trial
from tools.pipeline_eval.qualification import second_on_miss_whole_raw as raw


def candidate(status, margin):
    return {
        "epoch": 321,
        "fractional_epoch": dict(
            status=status,
            margin=margin,
            offset_samples=0.01,
            tracking_cfo_hz=-70_420,
            exact_score=0.156,
            control_score=0.131,
        ),
    }


@pytest.mark.parametrize("primary", [0, 1])
def test_gate_projects_the_normal_native_complete_margin_and_keeps_the_entire_row(
    monkeypatch, primary
):
    incomplete = candidate("unbracketed", 0.2)
    positive = candidate("complete", 0.025)
    original = [incomplete, positive]
    executed = []

    def analyze(_native, _samples, rx, *, include_timings):
        executed.append(rx)
        return dict(rows=[dict(receiver_id=rx, candidates=original)], detector_cpu_ms=3.0)

    monkeypatch.setattr(raw, "analyze_native", analyze)
    found, partner = raw.detect(None, object(), primary, include_timings=True)
    assert executed == [primary]
    assert not partner
    assert found["receiver_count"] == 2
    assert found["rows"][primary]["candidates"] == original
    assert not found["rows"][1 - primary]["candidates"]
    assert found["detector_cpu_ms"] == 3.0


def test_both_full_rows_are_preserved_after_a_primary_miss(monkeypatch):
    executed = []
    rows = [
        dict(receiver_id=0, candidates=[candidate("complete", 0.012)]),
        dict(receiver_id=1, candidates=[candidate("not_evaluated", None)]),
    ]

    def analyze(_native, _samples, rx, *, include_timings):
        executed.append(rx)
        return dict(rows=[rows[rx]], detector_cpu_ms=4.0)

    monkeypatch.setattr(raw, "analyze_native", analyze)
    result, partner = raw.detect(None, object(), 1, include_timings=True)
    assert executed == [1, 0] and partner is True
    assert result["rows"] == rows
    assert result["detector_cpu_ms"] == 8.0


def test_actual_dispatch_requires_strict_bool_and_an_empty_unmeasured_partner():
    plan = [
        {"visit": 7, "selected_receiver": 1},
        {"visit": 8, "selected_receiver": 0},
    ]
    probes = [dict(visit_index=v, receiver_id=rx, candidates=[]) for v in (7, 8) for rx in (0, 1)]
    positive = {"passed_fractional_margin_gate": True}
    probes[1]["candidates"] = [positive]
    probes[3]["candidates"] = [positive]
    doc = dict(source=dict(probes=probes))
    seen = [[7, 1, False], [8, 0, True]]
    trial.verify_dispatch(doc, plan, seen)
    probes[0]["candidates"] = [positive]
    with pytest.raises(ValueError, match="unmeasured partner"):
        trial.verify_dispatch(doc, plan, seen)
    with pytest.raises(ValueError, match="emitted primary gate"):
        trial.verify_dispatch(doc, plan, [[7, 1, 0], [8, 0, True]])
