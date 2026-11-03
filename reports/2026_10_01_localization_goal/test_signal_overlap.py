from audit_signal_overlap import comparison


def point(candidate='a', group='g', receiver=0, start=0, end=10):
    return dict(candidate_id=candidate, source_group_id=group, receiver_id=receiver,
                source_sample_start=start, source_sample_end=end)


def test_distinct_candidates_can_share_raw_support():
    assert comparison([point()], [point(candidate='b')]) == dict(
        shared_candidates=0, shared_source_groups=1, overlapping_sample_points=1)


def test_support_is_half_open_and_receiver_specific():
    assert comparison([point()], [point('b', 'h', start=10, end=20),
                                  point('c', 'i', receiver=1)]) == dict(
        shared_candidates=0, shared_source_groups=0, overlapping_sample_points=0)


def test_duplicate_identity_is_counted_once_per_left_point():
    assert comparison([point()], [point(), point()]) == dict(
        shared_candidates=1, shared_source_groups=1, overlapping_sample_points=1)
