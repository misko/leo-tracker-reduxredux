from types import SimpleNamespace

import numpy as np

from leo.analysis.research.orbital_support import restrict_to_active_orbital_support, include_active_orbital_uncertainty, requires_multiple_orbital_owners


def model(mask):
    tracks = [dict(receiver=1, channel=1), dict(receiver=1, channel=3),
              dict(receiver=1, channel=1), dict(receiver=2, channel=8),
              dict(receiver=1, channel=8)]
    return SimpleNamespace(
        rows=[dict(candidate_index=j) for j in (10, 10, 10, 20, 20)],
        members=list(range(5)), slices=[slice(2*i, 2*i+2) for i in range(5)],
        keep=np.asarray(mask, bool), scan=SimpleNamespace(tracks=tracks),
        labels=[10, 20], supported=[10, 20], supported_local=[0, 1],
        reference=np.array([.5, -.2]), alias=[0, 0, 1, -1, 0],
        mode_bank=object(),
    )


def test_failed_second_owner_reduces_complexity_without_dropping_good_data():
    p = model([1, 1, 0, 0, 1, 1, 1, 1, 1, 1])
    before = (p.keep.copy(), p.reference.copy(), p.alias.copy(), p.mode_bank)
    assert restrict_to_active_orbital_support(p) is p
    assert p.supported == [20] and p.supported_local == [1]
    assert p.orbital_support_backoff["disabled_families"] == [10]
    assert p.orbital_support_backoff["active_owners"][10] == [(1, 1)]
    np.testing.assert_array_equal(p.keep, before[0])
    np.testing.assert_array_equal(p.reference, before[1])
    assert p.alias == before[2] and p.mode_bank is before[3]


def test_two_distinct_channels_keep_orbit_modes_and_empty_rows_do_not_vote():
    p = model([1]*6 + [0]*4)
    restrict_to_active_orbital_support(p)
    assert p.supported == [10] and p.supported_local == [0]
    assert p.orbital_support_backoff["disabled_families"] == [20]


def test_all_supported_evidence_preserves_existing_model_coordinates():
    p = model([1]*10)
    restrict_to_active_orbital_support(p)
    assert p.supported == [10, 20] and p.supported_local == [0, 1]
    assert not p.orbital_support_backoff["disabled_families"]


def test_single_active_owner_retains_causal_prior_and_rebuilds_missing_bank():
    p=model([1,1]+[0]*8);p.supported=[];p.supported_local=[]
    mask=p.keep.copy();reference=p.reference.copy();aliases=p.alias.copy();calls=[]
    bank=object()
    def builder(labels):
        calls.append(labels);return bank,{10:{'source':'causal'}}
    include_active_orbital_uncertainty(p,builder)
    assert calls==[[10]] and p.supported==[10] and p.supported_local==[0]
    assert p.mode_bank is bank and p.mode_metadata[10]['source']=='causal'
    np.testing.assert_array_equal(p.keep,mask);np.testing.assert_array_equal(p.reference,reference)
    assert p.alias==aliases


def test_target_only_prior_preserves_incumbent_uncertainty():
    p=model([1,1]+[0]*8);p.supported=[20];p.supported_local=[1]
    calls=[]
    def builder(labels):calls.append(labels);return object(),{}
    include_active_orbital_uncertainty(p,builder,families=[10])
    assert p.supported==[10,20] and calls==[[10,20]]
    assert not requires_multiple_orbital_owners(p,10)
    assert requires_multiple_orbital_owners(p,20)
    include_active_orbital_uncertainty(p,builder,families=[10])
    assert not requires_multiple_orbital_owners(p,10)
    assert requires_multiple_orbital_owners(p,20)


def test_default_owner_gate_unchanged_and_failed_builder_is_atomic():
    import pytest
    p=model([1]*10)
    assert requires_multiple_orbital_owners(p,10)
    assert requires_multiple_orbital_owners(p,20)
    assert not requires_multiple_orbital_owners(p,30)
    p.supported=[20]
    def failed(labels):raise ValueError('missing causal inputs')
    with pytest.raises(ValueError,match='causal'):
        include_active_orbital_uncertainty(p,failed,families=[10])
    assert p.supported==[20] and not hasattr(p,'orbital_owner_gate_families')


def test_actual_retention_keeps_prior_only_curve_but_rejects_structured_residual():
    from audit_ds23_algo01_coverage import retained_metrics
    times=np.arange(100.);values=np.random.default_rng(419).normal(0,20,len(times))
    track=dict(key='one',receiver=1,channel=1,rf_hz=11.5e9,times=times,values=values,
               observation_ids=[str(k) for k in range(len(times))])
    scan=SimpleNamespace(tracks=[track],rx_basis=[np.zeros((len(times),1))],
                         hardware=lambda t,b:np.zeros(len(t['times'])))
    p=SimpleNamespace(scan=scan,rows=[dict(candidate_index=10,candidate_norad=123)],
        members=[0],slices=[slice(0,len(times))],alias=[0],labels=[10],supported=[10],
        keep=np.ones(len(times),bool),state=lambda x:dict(beta=np.zeros(8),smooth=np.zeros((2,1))),
        calculate=lambda x:dict(conditional_residual_hz=track['values']),
        conditional_frequency=lambda x:(np.zeros(len(times)),np.full(len(times),20.)))
    assert not retained_metrics(p,[0,0])['tracks'][0]['compatible']
    p.supported=[]
    include_active_orbital_uncertainty(p,lambda labels:(object(),{}))
    assert retained_metrics(p,[0,0])['tracks'][0]['compatible']
    track['values']=values+300*(times>=50)
    assert not retained_metrics(p,[0,0])['tracks'][0]['compatible']
