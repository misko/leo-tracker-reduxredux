from report_algo04_candidate import promotion


def test_more_coverage_cannot_override_position_regression():
    reference=dict(mean_km=1.,median_km=1.,p95_km=2.,max_km=3.)
    candidate=dict(mean_km=.9,median_km=.9,p95_km=2.1,max_km=3.)
    checks=promotion(reference,candidate,[dict(delta_error_km=.7)])
    assert checks['mean_improves'] and checks['median_improves']
    assert not checks['p95_does_not_increase'] and not checks['no_regression_above_half_km']
