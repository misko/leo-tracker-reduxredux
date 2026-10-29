import numpy as np
import pytest
from discover_omitted_graph_branches import discover
from leo.analysis.polynomial_tracklets import TrackConfig


def test_native_lanes_stay_separate_and_lifts_reconstruct_alias_crossing():
    period=1/4.4e-6;times=np.arange(0.,40.,1.);rows=[]
    for lane,rf in enumerate([11.44e9,11.69e9]):
        values=(100000+1800*times+period/2)%period-period/2
        rows.extend(dict(observation_id=f'{lane}-{i}',receiver=1,channel=3,actual_rf_hz=rf,time_s=float(t),measured_cfo_hz=float(y)) for i,(t,y) in enumerate(zip(times,values,strict=True)))
    r=discover(rows,'test',method='graph',config=TrackConfig(max_slope_hz_s=8000,max_tracks=8))
    assert len(r['branches'])==2 and sum(t['points'] for t in r['branches'])==80
    for t in r['branches']:
        assert len({o.split('-')[0] for o in t['observation_ids']})==1
        np.testing.assert_allclose(t['values_hz'],t['raw_CFO_hz']+period*t['alias_lifts'])
        assert t['large'] and not t['accepted_association']
    with pytest.raises(ValueError,match='duplicate'):discover(rows+[rows[0]],'test',method='graph')


def test_block_control_preserves_native_ids_and_is_reproducible():
    rows=[dict(observation_id=str(i),receiver=1,channel=1,actual_rf_hz=11e9,time_s=float(i),measured_cfo_hz=float(i*1500)) for i in range(40)]
    a=discover(rows,'test',method='graph',scramble_seed=20261029);b=discover(rows,'test',method='graph',scramble_seed=20261029)
    assert a['lanes'][0]['null_block_offsets_hz']==b['lanes'][0]['null_block_offsets_hz']
    ids={o for t in a['branches'] for o in t['observation_ids']}|set(a['lanes'][0]['unresolved_ids'])
    assert ids=={str(i) for i in range(40)}
