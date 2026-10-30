import numpy as np
import pytest
from discover_graph_bundle_components import alias_components,union_polynomial,canonical_sources
from leo.analysis.research.retained_track_likelihood import PERIOD


def test_alias_cycles_must_close_and_no_bad_edge_is_silently_dropped():
    edges=[dict(first='a',second='b',alias_lift=-1),dict(first='b',second='c',alias_lift=2),dict(first='a',second='c',alias_lift=1)]
    result=alias_components(edges);assert len(result)==1 and result[0]['consistent']
    assert result[0]['lifts']=={'a':0,'b':-1,'c':1}
    edges[-1]['alias_lift']=0;result=alias_components(edges)
    assert not result[0]['consistent'] and result[0]['conflicts']
    assert set(result[0]['lifts'])=={'a','b','c'}


def test_disconnected_components_have_independent_alias_origins():
    rows=alias_components([dict(first='b',second='a',alias_lift=1),dict(first='d',second='c',alias_lift=-2)])
    assert [r['lifts'] for r in rows]==[{'a':0,'b':-1},{'c':0,'d':2}]


def test_union_checks_every_member_not_only_pooled_rms():
    tracks=[]
    for k in range(3):
        t=np.arange(k,90,3,dtype=float);tracks.append(dict(times=t,values=10+30*t+k*PERIOD,observation_ids=[f'{k}-{x}' for x in t]))
    good=union_polynomial(tracks,[0,-1,-2]);assert good['eligible'] and good['RMS_hz']<1e-6
    tracks[2]['values']=tracks[2]['values']+1000
    assert not union_polynomial(tracks,[0,-1,-2])['eligible']
    tracks[2]['observation_ids'][0]=tracks[1]['observation_ids'][0]
    assert union_polynomial(tracks,[0,-1,-2])['reason']=='duplicate_observation_or_time'


def test_two_c_arms_cannot_duplicate_inventory_curves_or_pair_edges():
    rows=[dict(track_id='a',track_index=2,current_large=False),dict(track_id='a',track_index=2,current_large=True),
          dict(track_id='b',track_index=3,current_large=True)]
    result=canonical_sources(rows,{'a','b'});assert len(result)==2 and result[0]['current_large']
    rows[1]['track_index']=4
    with pytest.raises(ValueError,match='inconsistent'):canonical_sources(rows,{'a','b'})
    with pytest.raises(ValueError,match='missing'):canonical_sources([],{'a'})
