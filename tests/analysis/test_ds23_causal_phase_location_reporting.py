from evaluate_ds23_causal_phase_location_full import aggregate, capture_format


def test_unavailable_positions_and_failed_trial_fallback_stay_in_denominator():
    rows = []
    for arm in ('c0', 'fitted_c'):
        rows.extend([
            dict(arm=arm, baseline_error_km=1., error_km=.4),
            # A failed new trial keeps its original 2 km result.
            dict(arm=arm, baseline_error_km=2., error_km=2.),
            dict(arm=arm, baseline_error_km=None, error_km=None),
        ])
    result = aggregate(rows)
    for arm in result.values():
        assert arm['population'] == 3
        assert arm['qualified'] == 2
        assert arm['unavailable'] == 1
        assert arm['trial']['mean_km'] == 1.2
        assert arm['trial']['below_half_km'] == 1
        assert arm['unchanged'] == 1


def test_unavailable_only_group_has_no_invented_error():
    result = aggregate([dict(arm=arm, baseline_error_km=None, error_km=None)
                        for arm in ('c0','fitted_c')])
    for arm in result.values():
        assert arm['population'] == 1
        assert arm['unavailable'] == 1
        assert arm['trial']['mean_km'] is None


def test_capture_formats_match_the_ds23_manifest_contract():
    assert capture_format('short_window_iq_recording') == 'fast'
    assert capture_format('starlink_adaptive_hop_iq') == 'adaptive'
