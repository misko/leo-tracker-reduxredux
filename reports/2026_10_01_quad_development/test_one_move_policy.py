from one_move_policy import choose


def test_positive_maximum_and_stable_tie():
    rows=[dict(track=0,mixture_gain=-1),dict(track=1,mixture_gain=2),dict(track=2,mixture_gain=2)]
    assert choose(rows) is rows[1]


def test_no_change_for_nonpositive_or_tolerance_only():
    assert choose([]) is None
    assert choose([dict(mixture_gain=1e-6),dict(mixture_gain=-.1)]) is None
