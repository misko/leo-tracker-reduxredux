import numpy as np
import pytest

from ds23_historical_phase_consensus import build_rows,temporal_split,balanced_temporal_split,fit_mean,predict,runtime_means


def row(target,available,norad,refs):
    return dict(target_utc_ns=target,label_available_utc_ns=available,norad=norad,reference_ids=refs)


def test_historical_consensus_split_respects_label_and_forecast_issue_times():
    rows=[row(1,3,11,['a']),row(2,6,12,['b']),row(4,8,13,['c']),row(7,9,15,['d']),row(10,12,16,['e'])]
    split=temporal_split(rows,12,fraction=.6)
    assert split['boundary_ns']==8
    assert [r['norad'] for r in split['training']]==[11,12,13]
    assert [r['norad'] for r in split['future']]==[16]
    assert not split['disjoint_future']


def test_historical_reference_reuse_between_train_and_future_is_rejected():
    rows=[row(1,3,11,['shared']),row(4,6,12,['b']),row(7,9,15,['shared'])]
    with pytest.raises(ValueError,match='crossed'):temporal_split(rows,9,fraction=.7)


def test_mean_fit_recovers_signal_without_reducing_uncertainty():
    random=np.random.default_rng(723)
    rows=[dict(predicted_sigma_s=.2,age_s=1000.,unit_forecast_s=u,consensus_phase_s=.75*u+random.normal(scale=.01))
        for u in random.uniform(-1,1,300)]
    model=dict(shrinkage=0.,multiplier=1.,nu=4.)
    fit=fit_mean(rows,model,'consensus_phase_s')
    assert fit['shrinkage']==.75 and fit['kind'] is None
    assert model==dict(shrinkage=0.,multiplier=1.,nu=4.)
    assert np.sqrt(np.mean((predict(rows,model,fit)-[r['consensus_phase_s'] for r in rows])**2))<.15


def test_support_balanced_boundary_cannot_use_phase_outcomes_or_row_order():
    rows=[row(k,k+2,10+k,[str(k)]) for k in range(1,14)]
    first=balanced_temporal_split(rows,20)
    changed=[dict(r,consensus_phase_s=1e9*(i+1)) for i,r in enumerate(reversed(rows))]
    second=balanced_temporal_split(changed,20)
    assert first['boundary_ns']==second['boundary_ns']
    assert first['training'] and first['disjoint_future']
    assert all(r['label_available_utc_ns']<=first['boundary_ns'] for r in first['training'])
    assert all(r['target_utc_ns']>first['boundary_ns'] for r in first['future'])


def test_current_post_scan_reference_is_rejected_before_any_TLE_parsing():
    history=dict(cutoff_utc_ns=10,past_versions={'1':[dict(epoch=9,collected_utc_ns=11,lines=['invalid','invalid'])]})
    with pytest.raises(ValueError,match='post-scan'):build_rows(history)


def test_runtime_mapping_uses_the_same_unclipped_forecast_and_missing_history_fallback():
    receipts=[dict(old_new_alignment_s=-.2,previous_epoch_gap_s=100.,age_s=50.,sigma_s=.5),
        dict(old_new_alignment_s=None,previous_epoch_gap_s=None,age_s=50.,sigma_s=.5)]
    model=dict(shrinkage=.5,multiplier=.7,nu=4.)
    fit=dict(shrinkage=.75,kind='standardized',coefficient=.2)
    output,used=runtime_means(receipts,model,fit,[.1,-.3])
    expected=predict([dict(predicted_sigma_s=.5,age_s=200.,unit_forecast_s=.4)],model,fit)[0]
    np.testing.assert_allclose(output,[expected,-.3]);assert used==[0]
