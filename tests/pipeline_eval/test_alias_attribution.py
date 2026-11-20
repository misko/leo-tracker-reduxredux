from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification.alias_attribution import (
    ALIAS_HZ,
    CFO,
    delta,
    manipulate,
    match_winners,
    shuffled,
)
from tools.pipeline_eval.qualification.alias_attribution_results import (
    coherent_spans,
    graph_comparison,
)


def native(cfo_values):
    probes = [
        {
            "receiver_id": 0,
            "actual_rf_hz": 12e9,
            "channel": 1,
            "edge": "lower",
            "valid_start_counter": i * 10_000,
            "candidates": [
                {
                    "integer_epoch_sample": 21,
                    "fractional_epoch_offset_samples": 0.25,
                    "passed_fractional_margin_gate": True,
                    "fractional_margin": 0.2,
                    "candidate_rank": 0,
                    CFO: cfo,
                },
            ],
        }
        for i, cfo in enumerate(cfo_values)
    ]
    return {
        "source": {"probes": probes, "sample_rate_hz": 10_000_000, "session_id": "fixture"},
        "clock_anchor": {"sample_counter": 0},
    }


def frequencies(doc):
    return [row["candidates"][0][CFO] for row in doc["source"]["probes"]]


def test_alias_and_residual_edits_are_independent_without_principal_boundary_glitch():
    target = native([ALIAS_HZ / 2 - 3, 500])
    donor = native([ALIAS_HZ / 2 + 2, 500 + ALIAS_HZ + 19])
    baseline = deepcopy(target)
    matches, counts = match_winners(donor, target)
    assert counts["selected"] == 2
    assert delta(frequencies(donor)[0], frequencies(target)[0]) == (0, 5)
    assert frequencies(manipulate(target, matches, "alias")[0]) == pytest.approx(
        [
            ALIAS_HZ / 2 - 3,
            500 + ALIAS_HZ,
        ]
    )
    assert frequencies(manipulate(target, matches, "residual")[0]) == pytest.approx(
        [ALIAS_HZ / 2 + 2, 519]
    )
    assert frequencies(manipulate(target, matches, "joint")[0]) == frequencies(donor)
    alternate, singleton = shuffled(target, matches)
    null, _ = manipulate(target, matches, "null", exchanged=alternate)
    assert frequencies(null) == pytest.approx([ALIAS_HZ / 2 - 3 + ALIAS_HZ + 19, 505])
    assert singleton == 0
    assert target == baseline


def test_competing_winner_families_are_not_used_to_edit_cfo():
    target = native([3])
    donor = native([-600])
    extra = dict(donor["source"]["probes"][0]["candidates"][0])
    extra.update(candidate_rank=1, integer_epoch_sample=22, **{CFO: 902})
    donor["source"]["probes"][0]["candidates"].append(extra)
    matches, counts = match_winners(donor, target)
    assert not matches
    assert counts["ambiguous_winner_families"] == 1


def test_graph_distinguishes_input_branch_flags_and_resolved_branch_choices():
    def graph(rows):
        return {
            "points": len(rows),
            "curved": 1,
            "tracks": [
                {
                    "ids": [r[0] for r in rows],
                    "times_s": list(range(len(rows))),
                    "graph_cfo_hz": [r[1] for r in rows],
                }
            ],
        }

    target = graph([("a", 20), ("b", 23), ("c", 24)])
    donor = graph([("a", 20), ("b", 23 + ALIAS_HZ), ("d", 24)])
    stats = graph_comparison(
        donor, target, [{"observation": "a", "steps": 1}, {"observation": "b", "steps": 0}]
    )
    assert stats["transition_counts"] == {"+1→+0": 1, "+0→+1": 1}
    assert stats["shared_graph_ids"] == 2 and stats["wide_graph_only"] == 1
    assert coherent_spans(target, {k: 1 for k in "abc"})["runs_ge3_and_2s"] == 1
