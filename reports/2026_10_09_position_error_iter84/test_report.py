from report import variant_metrics


def test_pending_or_failed_member_blocks_full_candidate_mean():
    assert variant_metrics([dict(status="pending")], "protected0.25", "fitted-c") is None
    assert variant_metrics([dict(status="failed")], "protected0.25", "fitted-c") is None


def test_failed_fit_uses_fallback_without_hiding_raw_failure():
    fallback = dict(error_km=53, posterior_rms_hz=90, converged=True, stage="slope-0.5")
    raw = dict(error_km=0.01, posterior_rms_hz=1, converged=False)
    row = dict(status="complete", archived={"fitted-c": fallback},
               baseline={"fitted-c": dict(error_km=60)}, result=dict(
                   operational={"protected0.25": {"fitted-c": fallback},
                                "uniform0.5": {"fitted-c": fallback}},
                   raw={"protected0.25": {"fitted-c": raw}}))
    result = variant_metrics([row], "protected0.25", "fitted-c")
    assert result["position"]["mean"] == 53
    assert result["raw_failed"] == 1
    assert result["versus_new_control"]["tied"] == 1
