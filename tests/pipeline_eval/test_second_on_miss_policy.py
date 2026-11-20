from copy import deepcopy

import pytest

from tools.pipeline_eval.variants import second_on_miss
from tools.pipeline_eval.variants.negative_rescue import GATE, positive


def measured():
    probes = []
    for visit, rf, gates in [
        (0, 1, (True, True)),
        (1, 2, (False, True)),
        (3, 1, (True, False)),
        (4, 2, (False, False)),
    ]:
        for lane, gate in enumerate(gates):
            probes.append(
                dict(
                    visit_index=visit,
                    receiver_id=lane,
                    channel=rf,
                    edge="upper",
                    valid_start_counter=visit * 100,
                    candidates=[{GATE: False}, {GATE: gate}],
                )
            )
    return dict(
        delivery_clocks=list(range(5)),
        provenance=dict(
            window_count=5,
            processed_windows=4,
            invalid_capture=1,
            excluded_windows=[dict(visit=2)],
            detector_sha256="d",
        ),
        source=dict(input_manifest_sha256="origin", probes=probes),
    )


def test_branch_uses_only_original_primary_gates_and_preserves_all_positive_visits():
    doc = measured()
    before = deepcopy(doc)
    result, rows = second_on_miss.project(doc, {(1, "upper"): 100, (2, "upper"): 200})
    assert [(r["visit"], r["primary_receiver"], r["partner_required"]) for r in rows] == [
        (0, 0, False),
        (1, 0, True),
        (3, 1, True),
        (4, 1, True),
    ]
    assert doc == before and result["provenance"]["excluded_windows"] == [dict(visit=2)]
    new = result["source"]["probes"]
    assert new[1] == dict(doc["source"]["probes"][1], candidates=[])
    assert [new[0], *new[2:]] == [before["source"]["probes"][0], *before["source"]["probes"][2:]]
    for i in range(0, len(new), 2):
        assert any(map(positive, new[i : i + 2])) == any(
            map(positive, doc["source"]["probes"][i : i + 2])
        )
    assert result["provenance"]["detector_mode"] == second_on_miss.POLICY
    assert second_on_miss.mark(doc, new) == result


def test_no_gated_pilot_calls_partner_even_with_weak_peaks():
    assert second_on_miss.needs_partner(dict(candidates=[]))
    assert second_on_miss.needs_partner(dict(candidates=[{GATE: 1}]))
    assert not second_on_miss.needs_partner(dict(candidates=[{GATE: False}, {GATE: True}]))
    with pytest.raises(KeyError):
        second_on_miss.needs_partner(dict(candidates=[{"score": 0.89}]))
    with pytest.raises(ValueError, match="RF tuning"):
        second_on_miss.project(measured(), {(1, "upper"): 100})
