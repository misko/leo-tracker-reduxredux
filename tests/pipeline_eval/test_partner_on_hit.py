from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.partner_on_hit_results import effects
from tools.pipeline_eval.variants.one_lane_schedule import dispatch
from tools.pipeline_eval.variants.partner_on_hit import project


def test_projection_keeps_complete_lanes_on_strict_hit_and_excludes_invalid_parity():
    gate = "passed_fractional_margin_gate"
    doc = dict(
        clock_anchor=1,
        delivery_clocks=list(range(5)),
        provenance=dict(
            window_count=5,
            processed_windows=4,
            invalid_capture=1,
            excluded_windows=[dict(visit=1)],
        ),
        source=dict(analysis_manifest_sha256="stock", probes=[]),
    )
    probes = doc["source"]["probes"]
    for visit, gates in (
        (0, (True, True)),
        (2, (True, False)),
        (3, (1, False)),
        (4, (False, False)),
    ):
        for rx, flag in enumerate(gates):
            probes.append(
                dict(
                    visit_index=visit,
                    receiver_id=rx,
                    channel=1,
                    edge="lower",
                    clock=visit + 42,
                    candidates=[{gate: flag, "CFO": 123}, {gate: False, "CFO": 321}],
                )
            )
    original = deepcopy(doc)
    schedule = dispatch(doc, {(1, "lower"): 2_000_000})
    assert [entry["selected_receiver"] for entry in schedule] == [0, 1, 0, 1]
    projected, counts = project(doc, schedule)
    assert counts == dict(
        valid_visits=4,
        primary_hits=1,
        covisible_partner_hits=1,
        partner_only_hits=1,
        neither_hits=2,
        invalid_visits=1,
    )
    output = projected["source"]["probes"]
    assert output[:2] == probes[:2] and output[0] is probes[0] and output[1] is probes[1]
    assert output[2] == dict(probes[2], candidates=[]) and output[3] is probes[3]
    assert output[4] is probes[4] and output[5] == dict(probes[5], candidates=[])
    assert output[6] == dict(probes[6], candidates=[]) and output[7] is probes[7]
    assert projected["delivery_clocks"] == doc["delivery_clocks"]
    assert doc == original
    with pytest.raises(ValueError, match="original physical primary"):
        project(doc, [dict(schedule[0], visit=2), *schedule[1:]])


def test_factorial_effects_and_unknown_cell():
    assert effects(10, 12, 9, 15) == dict(
        add_hit_without_miss=2,
        add_hit_with_miss=6,
        add_miss_without_hit=-1,
        add_miss_with_hit=3,
        interaction=4,
    )
    assert effects(10, None, 9, 15) == dict(
        add_hit_without_miss=None,
        add_hit_with_miss=6,
        add_miss_without_hit=-1,
        add_miss_with_hit=None,
        interaction=None,
    )
