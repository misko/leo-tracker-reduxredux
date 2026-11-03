from visit_split import checking_visits


def test_channel_balance_and_probe_duplicates():
    visits = [(i % 3, i) for i in range(18)]
    expected = frozenset([(0, 6), (0, 15), (1, 7), (1, 16), (2, 8), (2, 17)])
    assert checking_visits(visits*4) == expected
    assert checking_visits(visits[::-1]) == expected


def test_small_channels_do_not_disappear_from_training():
    assert checking_visits([(0, 1), (0, 2), (1, 1)]) == frozenset()
