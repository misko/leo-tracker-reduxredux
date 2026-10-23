from types import SimpleNamespace

import numpy as np
import pytest

from ds23_curved_core_view import curved_core_view
from leo.analysis.research.retained_track_likelihood import PERIOD,projected_receiver_basis,whitening


def fixture():
    tracks=[]
    for k,n in enumerate([8,10]):
        t=np.linspace(0,25,n)
        tracks.append(dict(key=f't{k}',times=t,values=t*t,observation_ids=[f'{k}-{i}' for i in range(n)],receiver=1,channel=k+1,rf_hz=11e9))
    scan=SimpleNamespace(tracks=tracks,curved=[0,1],rx_basis=[projected_receiver_basis(t['times']) for t in tracks],
        white=[whitening(t['times']) for t in tracks],index=[np.arange(len(t['times'])) for t in tracks])
    rows=[dict(component=t['key'],active_curvature=True,candidate_index=k,candidate_norad=100+k) for k,t in enumerate(tracks)]
    p=SimpleNamespace(members=[0,1],slices=[slice(0,8),slice(8,18)],rows=rows)
    data=dict(scan=scan,node=dict(seed=dict(rows=rows),aliases=[0,0]),keep=np.r_[np.ones(8,bool),np.zeros(10,bool)],powers=np.array([1.,.5]))
    f=dict(observation_ids=tracks[1]['observation_ids'][1:],values=tracks[1]['values'][1:]+PERIOD,candidate_index=1,norad=101)
    return data,p,f


def test_derived_curved_core_adds_native_rows_without_changing_incumbent_or_source():
    data,p,f=fixture();changed,entry,receipt=curved_core_view(data,p,f,1)
    assert len(data['scan'].tracks)==2 and len(data['node']['seed']['rows'])==2
    assert changed['scan'].curved==[0,1,2] and data['scan'].curved==[0,1]
    np.testing.assert_array_equal(changed['keep'][:18],data['keep'])
    assert changed['keep'][18:].all() and changed['keep'].sum()==17
    assert entry['alias']==1 and changed['node']['aliases']==[0,0,1]
    assert changed['powers'][-1]==.5
    assert changed['scan'].tracks[2]['observation_ids']==f['observation_ids']
    np.testing.assert_array_equal(changed['scan'].tracks[1]['values'],data['scan'].tracks[1]['values'])
    assert receipt[0]['omitted_ids']==['1-0']


def test_curved_core_cannot_reuse_active_calibration_or_alter_a_cfo_value():
    data,p,f=fixture();data['keep'][8]=True
    with pytest.raises(ValueError,match='wholly unused'):curved_core_view(data,p,f,1)
    data,p,f=fixture();f['values'][0]+=1.
    with pytest.raises(ValueError,match='native CFO'):curved_core_view(data,p,f,1)


def test_alternative_candidates_are_bounded_by_frozen_rf_qualification():
    from probe_ds23_iteration008_alternatives import choices
    candidates=[dict(qualified=False,conditional_RMS_hz=1),dict(qualified=True,conditional_RMS_hz=800)]
    candidates+=[dict(qualified=True,conditional_RMS_hz=50,k=i) for i in range(5)]
    assert [r['k'] for r in choices(dict(candidates=candidates))]==[0,1,2]
