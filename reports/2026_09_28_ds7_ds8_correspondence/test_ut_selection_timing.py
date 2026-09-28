from ut_selection_timing import predict


def test_phase_lookup_predicts_known_period_on_disjoint_ticks():
    train = [dict(tick=t, label=str(t % 3)) for t in range(30)]
    test = [dict(tick=t, label=str(t % 3)) for t in range(30, 60)]
    assert predict(train, test, 3) == [r["label"] for r in test]
    assert predict(train, test, 2) != [r["label"] for r in test]


def test_unseen_phase_uses_training_mode_not_test_label():
    train = [dict(tick=0, label="a"), dict(tick=3, label="a")]
    assert predict(train, [dict(tick=1, label="b")], 3) == ["a"]
