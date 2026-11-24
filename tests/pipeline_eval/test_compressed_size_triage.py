from collections import Counter

import pytest

from reports.ALGO08.v3.compressed_size_triage import selection, tally


def segment(path, sizes):
    rows = []
    count = 0
    for i, (windows, ratio) in enumerate(sizes):
        rows.append(dict(segment_manifest=path, first_sequence=count, chunk_index=i, window_count=windows,
                         compressed_bytes=ratio*windows, uncompressed_bytes=10*windows))
        count += windows
    return rows


def test_scheduling_uses_only_complete_within_segment_quartets_and_stable_ties():
    chunks = segment("a", [(64, 5), (64, 3), (64, 3), (64, 7), (11, 1), (64, 1)])
    chunks += segment("b", [(64, 1), (64, 2)])
    case = dict(window_count=sum(c["window_count"] for c in chunks),
                raw_recording=dict(segments=[{"path": "a"}, {"path": "b"}], chunks=chunks))
    visits, groups, picks = selection(case)
    assert groups == [[0, 1, 2, 3]] and picks == [1] and len(visits) == case["window_count"]
    assert visits[4*64:4*64+11] == [4]*11
    chunks[-1]["first_sequence"] -= 1
    with pytest.raises(ValueError, match="extent"):
        selection(case)


def test_common_denominator_and_per_block_oracle_include_untouched_tails():
    costs = Counter({0: 6, 1: 3, 2: 1, 3: 2, 4: 1, 5: 2, 6: 2, 8: 10})
    result = tally(costs, [[0, 1, 2, 3], [4, 5, 6, 7]], [1, 4])
    assert result == dict(total=27, omitted_by_size=4, omitted_by_fixed_phases=[7, 5, 3, 2],
                          fixed_phase_mean=4.25, oracle_minimum=1)
