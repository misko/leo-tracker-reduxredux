import numpy as np
from ds23_age_covered_phase_prior import target_times,cost,qualify


def test_targets_only_use_available_features_and_pre_scan_proxy_labels():
    a=dict(epoch=10,collected_utc_ns=20);b=dict(epoch=30,collected_utc_ns=40)
    c=dict(epoch=70,collected_utc_ns=80)
    assert target_times(a,b,c,80)==[40,50,60,70]
    assert target_times(a,b,c,79)==[]
    assert target_times(a,dict(b,collected_utc_ns=25),c,80)==[]


def test_repeated_targets_do_not_inflate_likelihood_or_effective_sample_count():
    model=dict(shrinkage=0.,multiplier=1.,nu=4.)
    row=dict(validation_time_ns=1,next_innovation_s=2.,unit_forecast_s=0.,
             predicted_sigma_s=1.,old_middle_alignment_s=.5,age_s=10.,epoch_gap_s=20.,weight=1.)
    np.testing.assert_allclose(cost([row],model),cost([dict(row,weight=.25)]*4,model))
    assert not qualify([dict(row,weight=.25)]*100,1,model,model)["qualified"]
