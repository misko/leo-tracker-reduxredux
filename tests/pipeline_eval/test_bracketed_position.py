from copy import deepcopy
from json import loads

import pytest

from tools.pipeline_eval.qualification import bracketed_position_edits as edits
from tools.pipeline_eval.qualification import bracketed_position_results as results


def native(*flags):
    doc = dict(
        schema_version=2,
        provenance={"detector": "original"},
        source={
            "probes": [
                dict(
                    visit_index=8,
                    receiver_id=0,
                    candidates=[{edits.GATE: flag, "cfo_hz": n} for n, flag in enumerate(flags)],
                )
            ]
        },
    )
    return (edits.whole_iq.recording.encoded(doc) + "\n").encode()


def test_private_candidate_only_flips_the_selected_existing_gate_bit():
    stock = native(False, False)
    candidate, receipt = edits.apply_edits(stock, [dict(probe_index=0, candidate_index=1)])
    actual = loads(candidate)
    expected = loads(stock)
    expected["source"]["probes"][0]["candidates"][1][edits.GATE] = True
    assert actual == expected
    assert receipt[0]["candidate"] == {edits.GATE: False, "cfo_hz": 1}
    assert receipt[0]["recorded_visit_index"] == 8
    same, receipt = edits.apply_edits(stock, [])
    assert same is stock and not receipt


@pytest.mark.parametrize(
    ("stock", "rows"),
    [
        (native(True, False), [(0, 1)]),
        (native(False, False), [(0, 1), (0, 0)]),
        (native(False), [(0, 1)]),
        (native(False), [(-1, 0)]),
    ],
)
def test_materializer_rejects_any_address_outside_an_entirely_failing_probe(stock, rows):
    with pytest.raises(ValueError):
        edits.apply_edits(stock, [dict(probe_index=p, candidate_index=c) for p, c in rows])


def test_only_timing_is_ignored_when_repeating_archived_position_science():
    stock = dict(
        status="ok",
        arms={"c0": {"latlon": [37, -122]}},
        metrics={"stage_s": {"fit": 5}, "tracks": 3},
    )
    fresh = deepcopy(stock)
    fresh["metrics"]["stage_s"]["fit"] = 7
    assert results.scientific(stock) == results.scientific(fresh)
    fresh["metrics"]["tracks"] += 1
    assert results.scientific(stock) != results.scientific(fresh)
