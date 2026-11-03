from track_fragments import append_fragments


def track(name, times, visits):
    return dict(track_id=name, times_s=times, visits=visits, measured_hz=list(times),
                training_mask=[True]*len(times), receiver_id=0, channel=1, rf_hz=11.2e9)


def test_baseline_preserved_partial_track_salvaged_and_unique():
    first = track('a', [0, 1, 2], [0, 1, 2])
    second = track('b', list(range(1, 10)), list(range(1, 10)))
    result = append_fragments([second, first])
    assert result[0] == first
    assert result[1]['visits'] == list(range(3, 10))
    ids = [v for t in result for v in t['visits']]
    assert len(ids) == len(set(ids))
    assert append_fragments([first, second]) == result


def test_long_gaps_split_and_short_pieces_rejected():
    first = track('a', [0, 1, 2], [0, 1, 2])
    second = track('b', [1, 3, 4, 5, 20, 21, 22, 23, 24, 25], list(range(1, 11)))
    result = append_fragments([first, second])
    assert len(result) == 2
    assert result[1]['times_s'] == [20, 21, 22, 23, 24, 25]


def test_later_fragments_cannot_reuse_salvaged_visits():
    first = track('a', [0, 1, 2], [0, 1, 2])
    second = track('b', list(range(1, 10)), list(range(1, 10)))
    third = track('c', list(range(1, 11)), list(range(1, 11)))
    result = append_fragments([first, second, third])
    assert len(result) == 2
