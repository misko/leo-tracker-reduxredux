import pytest

from tools.pipeline_eval.qualification import parallel_position as run
from tools.pipeline_eval.qualification.parallel_position_results import terminal_rows
from tools.pipeline_eval.scoring import terminal_position_decision


def probes(visit, flags):
    return tuple(
        dict(
            visit_index=visit, receiver_id=rx, candidates=[dict(passed_fractional_margin_gate=flag)]
        )
        for rx, flag in enumerate(flags)
    )


def test_joint_packet_must_match_both_sealed_lanes_and_the_physical_clock():
    pair = probes(1, (True, False))
    clocks = [dict(monotonic_ns=100), dict(monotonic_ns=140)]
    doc = dict(
        source=dict(probes=list(pair)),
        provenance=dict(excluded_windows=[dict(visit=0)]),
        delivery_clocks=clocks,
    )
    invalid = dict(
        visit=0,
        arrival_ns=0,
        delivery_clock=clocks[0],
        status="invalid_capture",
        packet=None,
        finish_ns=None,
    )
    good = dict(
        visit=1,
        arrival_ns=40,
        delivery_clock=clocks[1],
        status="valid",
        packet=dict(visit=1, probes=list(pair)),
        finish_ns=56,
    )
    assert run.branch_events(doc, [invalid, good], False) == [(0, None, None), (40, 56, pair)]
    for override in (
        dict(packet=None),
        dict(delivery_clock=clocks[0]),
        dict(finish_ns=39),
        dict(packet=dict(visit=1, probes=probes(1, (True, True)))),
        dict(status="invalid_capture"),
    ):
        with pytest.raises(ValueError):
            run.branch_events(doc, [invalid, dict(good, **override)], False)


def test_cutoff_preserves_original_negatives_and_distinguishes_late_replies():
    wide_pair, orig_pair = probes(0, (True, False)), probes(0, (False, True))
    other = probes(1, (False, False))
    wide = [(0, 15_000_000, wide_pair), (30_000_000, None, None)]
    original = [(0, 25_000_000, orig_pair), (30_000_000, 30_000_001, other)]
    cutoff = 30_000_000
    replaced, choices, counts = run.compose(wide, original, "replace", cutoff)
    assert replaced == list(orig_pair) and choices == [(0, "original", "original")]
    assert counts["positive_losses"] == counts["positive_gains"] == 1
    assert counts["original_after_cutoff"] == 1
    filled, choices, _ = run.compose(wide, original, "fill", cutoff)
    assert filled == [wide_pair[0], orig_pair[1]] and choices == [(0, "wide", "original")]
    timely, choices, counts = run.compose(wide, original, "timely", cutoff)
    assert timely == list(wide_pair) and choices == [(0, "wide", "wide")]
    assert counts["positive_probes_within_20ms"] == 1
    with pytest.raises(ValueError, match="different scheduled arrivals"):
        run.compose(wide, [(1, *original[0][1:]), original[1]], "replace", cutoff)


def test_no_passing_measurement_is_a_terminal_withholding_in_the_plot():
    result = run.position.empty_result("withheld", "no_passing_probe_by_cutoff")
    record = dict(result=result, position_resources=None)
    (display,) = terminal_rows([record])
    assert terminal_position_decision(display["result"])
    assert not terminal_position_decision(result)
    with pytest.raises(ValueError, match="conflicts"):
        list(terminal_rows([dict(record, positive_probes=1)]))
