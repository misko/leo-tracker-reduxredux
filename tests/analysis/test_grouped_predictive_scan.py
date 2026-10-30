from types import SimpleNamespace
import numpy as np
from grouped_predictive_scan import predictive_training_views
from leo.analysis.research.grouped_prediction import grouped_split,replay_split
from leo.analysis.research.retained_track_likelihood import whitening


def test_predictive_views_exclude_held_and_guarded_values_without_mutating_scan():
    t=np.arange(0.,100.,2.);values=t*3;ids=[str(i) for i in range(len(t))]
    track=dict(key='curve',times=t,values=values,observation_ids=ids)
    scan=SimpleNamespace(tracks=[track],white=[whitening(t)],rx_basis=[np.c_[t,t*t]],
        fixed_window_noise=dict(extra_parameter_BIC_gain=10.,per_observation_noise_sigma_hz={}),radio_sigma_hz=42.,
        times=t,index=[np.arange(len(t))],curved=[0])
    _,_,split=grouped_split(t,t,seed=317)
    entry=dict(track_index=0,component='curve',points=len(t),observation_ids=ids,candidate_index=8,alias=1)
    changed,entries,receipts=predictive_training_views(scan,[entry],split)
    train,held=replay_split(t,split);view=changed.tracks[entries[0]['track_index']]
    np.testing.assert_array_equal(view['times'],t[train]);np.testing.assert_array_equal(view['values'],values[train])
    np.testing.assert_array_equal(changed.rx_basis[-1],scan.rx_basis[0][train])
    assert not set(view['observation_ids'])&set(np.asarray(ids)[~train])
    assert scan.tracks==[track] and changed.tracks[0] is track
    assert changed.times is scan.times and changed.index is scan.index and changed.curved is scan.curved
    assert scan.radio_sigma_hz==42. and scan.fixed_window_noise['extra_parameter_BIC_gain']==10.
    assert changed.radio_sigma_hz==150. and changed.fixed_window_noise['extra_parameter_BIC_gain']==0.
    assert receipts[0]['held_points']==held.sum() and entries[0]['candidate_index']==8 and entries[0]['alias']==1
    view['values'][:]=0;np.testing.assert_array_equal(scan.tracks[0]['values'],values)


def test_insufficient_training_is_explicit_and_does_not_append():
    t=np.arange(0.,100.,2.);_,_,split=grouped_split(t,t,seed=317)
    track=dict(key='curve',times=t,values=t,observation_ids=list(map(str,t)))
    scan=SimpleNamespace(tracks=[track],white=[whitening(t)],rx_basis=[t[:,None]],fixed_window_noise={},radio_sigma_hz=42.)
    changed,entries,receipts=predictive_training_views(scan,[dict(track_index=0,component='curve')],split,minimum_points=100)
    assert not entries and not receipts[0]['included'] and len(changed.tracks)==1
