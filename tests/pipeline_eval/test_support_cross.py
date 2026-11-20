from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import support_cross as cross
from tools.pipeline_eval.qualification.factor_cross import GATE, winner


def recording(availability, source):
    rows = []
    for i, good in enumerate(availability):
        rows.append(
            dict(
                visit_index=i,
                receiver_id=0,
                probe_index=0,
                channel=2,
                actual_rf_hz=11e9,
                valid_start_counter=i * 10000,
                candidates=[
                    {GATE: False, "tag": source, "fractional_margin": 0.01, "candidate_rank": 0},
                    {GATE: good, "tag": source, "fractional_margin": 0.8, "candidate_rank": 1},
                ],
            )
        )
    return dict(
        **{key: 1 for key in cross.CLOCK_FIELDS},
        provenance={"excluded_windows": []},
        source=dict(**{key: 2 for key in cross.AUTHORITY_FIELDS}, probes=rows),
    )


def test_all_four_availability_cells_preserve_winner_and_support():
    a = recording((True, True, False, False), "wide")
    b = recording((True, False, True, False), "capture")
    entering = deepcopy([a, b])
    order = cross.join(a, b)
    assert order == ["11", "10", "01", "00"]
    expected = {
        "wide": (True, True, False, False),
        "remove": (True, False, False, False),
        "restore": (True, True, True, False),
        "both": (True, False, True, False),
    }
    for cell, availability in expected.items():
        out = cross.intervene(a, b, order, cell)["source"]["probes"]
        assert tuple(map(cross.positive, out)) == availability
        assert out[0] == a["source"]["probes"][0] and winner(out[0]["candidates"]) == 1
        assert out[3] == a["source"]["probes"][3]
        assert out[2] == (b if availability[2] else a)["source"]["probes"][2]
        assert [{k: v for k, v in c.items() if k != GATE} for c in out[1]["candidates"]] == [
            {k: v for k, v in c.items() if k != GATE}
            for c in a["source"]["probes"][1]["candidates"]
        ]
    assert [a, b] == entering


@pytest.mark.parametrize("field", ("actual_rf_hz", "channel", "valid_start_counter"))
def test_reject_join_with_different_physical_probe_metadata(field):
    a, b = recording((True,), "wide"), recording((True,), "capture")
    b["source"]["probes"][0][field] += 1
    with pytest.raises(ValueError, match="hardware probe metadata"):
        cross.join(a, b)


def test_reject_clock_drift_and_duplicate_keys():
    a, b = recording((True,), "wide"), recording((True,), "capture")
    b["delivery_clocks"] += 1
    with pytest.raises(ValueError, match="acquisition clock"):
        cross.join(a, b)
    a["source"]["probes"] *= 2
    with pytest.raises(ValueError, match="duplicate"):
        cross.join(a, a)
