import numpy as np
import pytest

from ds23_temporal_predictive_recovery import wrapped_density,transition,hmm,path_indices,PERIOD


def test_wrapped_density_is_normalized_even_for_an_uncalibrated_receiver():
    grid=np.linspace(-PERIOD/2,PERIOD/2,30001)
    for sigma in [200.,.2*PERIOD,5*PERIOD]:
        assert np.trapezoid(wrapped_density(grid,sigma),grid)==pytest.approx(1.,abs=1e-9)


def test_transitions_remain_normalized_when_a_satellite_goes_below_horizon():
    step=transition([True,True],[False,True],1.,5.)
    np.testing.assert_allclose(step.sum(axis=1),1.)
    assert step[1,1]==0.
    assert step[2,2]>step[0,2]


def test_uniform_emissions_have_identical_clutter_evidence_and_normalized_posteriors():
    result=hmm(np.arange(12.),np.full((12,2),1/PERIOD),np.ones((12,2),bool),5.)
    assert result['log_ratio_vs_clutter']==pytest.approx(0.,abs=1e-10)
    np.testing.assert_allclose(result['posterior'].sum(axis=1),1.,atol=1e-12)


def test_zero_persistence_matches_the_independent_mixture():
    density=np.array([[.1,.01],[.02,.05],[1/PERIOD,1/PERIOD]])
    result=hmm(np.arange(3.),density,np.ones((3,2),bool),0.)
    expected=np.log(.5/PERIOD+.5*density.mean(axis=1)).sum()
    assert result['log_likelihood']==pytest.approx(expected)


def test_temporal_proposal_can_leave_a_large_outlier_as_clutter():
    times=np.arange(12.);density=np.full((12,2),1e-12);density[:,0]=.002;density[6]=1e-30
    result=hmm(times,density,np.ones((12,2),bool),5.)
    assert result['states'][6]==0
    assert np.all(result['states'][np.arange(12)!=6]==1)
    paths=path_indices(times,result['states'],minimum_points=8,minimum_span=6.)
    assert len(paths)==1 and len(paths[0][1])==11


def test_appended_paths_are_predictive_only_and_ownership_is_unique():
    from types import SimpleNamespace
    from ds23_temporal_predictive_recovery import append_fragments
    times=np.arange(8.)
    template=dict(receiver=1,channel=2,rf_hz=11e9,times=times,values=times,
                  key='old',observation_ids=['old'+str(i) for i in range(8)])
    scan=SimpleNamespace(tracks=[template],index=[np.arange(8)],white=[None],
                         rx_basis=[None],curved=[0],times=times)
    fragment=dict(template,key='new',channel=7,rf_hz=12e9,observation_ids=['new'+str(i) for i in range(8)],
                  candidate_index=3,norad=123)
    changed,entries=append_fragments(scan,[],[fragment])
    assert changed.curved==[0] and len(changed.tracks)==2 and len(scan.tracks)==1
    assert changed.tracks[1]['pieces']==[] and entries[0]['alias']==0
    with pytest.raises(ValueError,match='already belongs'):
        append_fragments(scan,entries,[fragment])


def test_residual_filter_preserves_a_whole_path_and_requires_both_arms():
    from refine_ds23_temporal_predictive_recovery import whole_path_filter
    paths=[dict(key='a',observation_ids=['a1','a2']),dict(key='b',observation_ids=['b1','b2'])]
    gates={'c0':[dict(component='a',compatible=True),dict(component='b',compatible=True)],
           'fitted_c':[dict(component='a',compatible=True),dict(component='b',compatible=False)]}
    selected=whole_path_filter(paths,gates)
    assert selected==paths[:1] and selected[0] is paths[0]


def test_following_archive_window_is_read_only_bounded_and_deduplicates_earliest_collection():
    from types import SimpleNamespace
    from prepare_ds23_dbg01_following import archive_window
    refs=[SimpleNamespace(sha256=d,collected_utc_ns=t,digest='sha256:'+d)
          for d,t in [('old',1),('same',15),('same',12),('late',30)]]
    class Reader:
        def __init__(self):self.reads=[]
        def list_snapshots(self,provider):
            assert provider=='space-track';return refs
        def read(self,ref):self.reads.append(ref.collected_utc_ns);return 'payload'
    reader=Reader();rows,adapter=archive_window(reader,10,20,{123})
    assert reader.reads==[12] and rows[0]['collected']==12
    assert 'ordinary read-only' in adapter
