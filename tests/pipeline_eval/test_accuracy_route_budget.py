from reports.ALGO08.v3.accuracy_route_budget import budgets, prefer_cumulative


def test_uniform_rate_threshold_separates_median_from_pooled_allowance():
    rows = [dict(baseline_s=10, compressed_MB=10, stock=dict(wall=wall), hindsight='stock')
            for wall in (1, 4, 6)]
    result = budgets(rows, 'wall', 'hindsight')
    assert result['median_gate_MB_s'] == 10
    assert result['summed_gate_MB_s'] == 7.5
    assert result['individual_gate_MB_s'] == [2.5, 10, None]


def test_hindsight_route_preserves_both_position_errors():
    errors = dict(stock=dict(c0=1, fitted_c=1), cumulative=dict(c0=0.5, fitted_c=1.2))
    assert not prefer_cumulative(errors)
    assert prefer_cumulative(errors | dict(cumulative=dict(c0=1, fitted_c=0.9)))
