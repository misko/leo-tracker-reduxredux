from summarize_first_start_replay import statistics, matched


def row(first, baseline):
    def outcome(error):
        return dict(accepted=error is not None, error_m=error)
    return dict(first=outcome(first), baseline=outcome(baseline))


def test_planned_denominators_and_asymmetric_failures():
    rows = [row(500, 700), row(None, 200), row(400, None), row(None, None)]
    s = statistics(rows, 'first')
    assert s['planned'] == 4 and s['accepted'] == 2 and s['within_1km'] == 2
    assert s['median_m'] == 450
    m = matched(rows)
    assert (m['jointly_accepted'], m['first_only'], m['baseline_only'], m['neither']) == (1, 1, 1, 1)
    assert m['median_change_m'] == -200


def test_empty_acceptance_and_tie_tolerance():
    assert statistics([row(None, None)], 'first')['p90_m'] is None
    m = matched([row(100., 100.5), row(102., 100.)])
    assert m['ties_within_1m'] == 1 and m['worsens_over_1m'] == 1
