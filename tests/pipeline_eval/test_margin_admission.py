import math
from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.margin_admission_results import confusion
from tools.pipeline_eval.variants import margin_admission as gate


def test_equal_recording_prevalence_weights_and_exact_tie_rule():
    one = [(0.04, True), (0.05, True)]
    two = [(0.06, False)] * 8
    assert gate.threshold([one, two]) == math.nextafter(0.05, math.inf)
    assert gate.threshold([one + two]) == math.nextafter(0.06, math.inf)
    assert gate.threshold([[(0.055, True), (0.055, False)]]) == gate.STOCK
    assert gate.threshold([[(-math.inf, True), (0.06, True)]]) == gate.STOCK


def probe(value, visit):
    return dict(
        visit_index=visit,
        receiver_id=0,
        probe_index=0,
        candidates=[
            dict(
                candidate_rank=0,
                fractional_margin=value,
                fractional_tracking_cfo_hz=-657.0,
                **{gate.FLAG: value >= gate.STOCK},
            )
        ],
    )


def test_inclusive_gate_changes_only_admission_and_thin_matches_budget():
    before = [probe(x, i) for i, x in enumerate((0.01, 0.025, 0.05, 0.05, 0.19))]
    adjusted = deepcopy(before)
    gate.bind(adjusted, 0.05)
    assert [p["candidates"][0][gate.FLAG] for p in adjusted] == [False, False, True, True, True]
    assert [{k: v for k, v in p["candidates"][0].items() if k != gate.FLAG} for p in adjusted] == [
        {k: v for k, v in p["candidates"][0].items() if k != gate.FLAG} for p in before
    ]
    duplicate, sample = deepcopy(before), deepcopy(before)
    gate.thin(sample, 3, "session")
    gate.thin(duplicate, 3, "session")
    assert sample == duplicate
    assert sum(p["candidates"][0][gate.FLAG] for p in sample) == 3
    assert not sample[0]["candidates"][0][gate.FLAG]


def test_source_admission_must_match_ordinary_threshold():
    invalid = probe(0.02, 0)
    invalid["candidates"][0][gate.FLAG] = True
    with pytest.raises(ValueError, match="ordinary gate"):
        gate.bind([invalid], 0.025)


def test_teacher_agreement_keeps_skipped_and_ordinary_negative_probes():
    probes = [(0, -math.inf, True), (1, -math.inf, False), (2, 0.04, False), (3, 0.20, True)]
    stock = confusion(probes, 0.025)
    scalar = confusion(probes, 0.04 + 0.01)
    assert scalar["probes"] == stock["probes"] == 4
    assert scalar["teacher_recall"] == stock["teacher_recall"] == 0.5
    assert stock["teacher_negative_admission"] == 0.5
    assert scalar["teacher_negative_admission"] == 0.0
    assert scalar["teacher_precision"] == 1.0
