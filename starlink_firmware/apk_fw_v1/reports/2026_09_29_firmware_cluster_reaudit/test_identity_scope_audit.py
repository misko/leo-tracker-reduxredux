from identity_scope_audit import episode_metrics


def test_repeated_gallery_does_not_upweight_an_episode():
    def row(session, value):
        return dict(session=session, candidate=1, sign_credit=value, nearest_time_credit=value,
                    nearest_cfo_credit=value, uniform_chance=value)
    count, metrics = episode_metrics([row("a", 1)] * 5 + [row("b", 0)])
    assert count == 2
    assert all(value == .5 for value in metrics.values())
