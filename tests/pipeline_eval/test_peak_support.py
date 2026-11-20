from copy import deepcopy
from itertools import groupby

from tools.pipeline_eval.qualification.factor_cross import CFO, GATE, MARGIN
from tools.pipeline_eval.qualification.peak_support import (
    ALIAS_HZ,
    circular_indices,
    compare,
    corroborated,
    family_probe,
    lane,
    subset,
    thinned,
)


def candidate(rank, epoch, cfo, gate):
    return {
        "integer_epoch_sample": epoch,
        "fractional_epoch_offset_samples": 0.25,
        "candidate_rank": rank,
        CFO: cfo,
        GATE: gate,
        MARGIN: 0.08 if gate else 0.02,
    }


def prepare(*candidates):
    return family_probe(candidates, 13333, 2)


def test_family_is_gate_independent_and_collapses_alias_representations():
    picked = candidate(5, 0, 12, True)
    alias = candidate(1, 13332, 12 + ALIAS_HZ, False)
    first = prepare(picked, alias)
    assert len(first[0]) == 1 and len(first[0][0][0]) == 2
    picked[GATE] = False
    unpassed = prepare(picked, alias)
    assert first[0][0][0] == unpassed[0][0][0]
    assert unpassed[1] is None


def test_miss_decomposition_separates_epoch_cfo_gate_and_nonwinner():
    source = prepare(candidate(0, 15, 100, True))
    alternatives = [
        (prepare(candidate(0, 22, 100, True)), "no_target_epoch"),
        (prepare(candidate(0, 15, 1200, True)), "epoch_without_folded_cfo"),
        (prepare(candidate(0, 15, 100, False)), "reciprocal_gate_failed"),
        (
            prepare(candidate(1, 15, 100, True), candidate(0, 50, 100, True)),
            "reciprocal_gated_nonwinner",
        ),
    ]
    for right, expected in alternatives:
        _, outcomes = compare(source, right, 13333, 2, 1000)
        assert outcomes[0][0] == expected
    right = prepare(candidate(0, 17, 100 + ALIAS_HZ, True))
    matches, outcomes = compare(source, right, 13333, 2, 1000)
    assert matches == {0: 0}
    assert outcomes[0] == ("same_winner_family", "middle", 1, True)


def test_triangle_requires_same_gated_family_in_all_three_sources():
    a = prepare(candidate(0, 15, 10, True))
    b = prepare(candidate(0, 15, 10, True))
    c = prepare(candidate(0, 15, 10, True), candidate(1, 40, 10, True))
    assert corroborated([a, b, c], [{0: 0}, {0: 0}, {0: 0}])
    assert not corroborated([a, b, c], [{0: 0}, {0: 0}, {0: 1}])


def test_null_and_random_thin_hold_lane_and_complete_rows():
    probes = [
        dict(
            receiver_id=i % 2,
            channel=1,
            actual_rf_hz=12000000000,
            edge="lower",
            visit_index=i // 2,
            valid_start_counter=i // 2,
            candidates=[candidate(0, 15, 10, True)],
        )
        for i in range(12)
    ]
    shifted = circular_indices(probes)
    assert sorted(shifted) == list(range(12))
    assert all(i != j and lane(probes[i]) == lane(probes[j]) for i, j in enumerate(shifted))
    doc = dict(
        source=dict(probes=probes, sample_rate_hz=10),
        clock_anchor=dict(sample_counter=0),
        provenance=dict(excluded_windows=[]),
    )
    before = deepcopy(doc)
    fixed = [0, 2, 3, 5, 7, 9]
    picked = thinned("case", doc, fixed)
    assert picked == thinned("case", doc, fixed)

    def rows_per_lane(indices):
        return {
            k: len(list(values)) for k, values in groupby(sorted(lane(probes[i]) for i in indices))
        }

    assert rows_per_lane(fixed) == rows_per_lane(picked)
    assert subset(doc, picked, {})["source"]["probes"] == [probes[i] for i in picked]
    assert doc == before
