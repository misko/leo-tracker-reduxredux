"""Scientific identity and alias boundary tests, independent of native binaries."""
from pathlib import Path

import pytest

from leo.native_pipeline import membership as m


def test_raw_measurement_cannot_be_overwritten_by_tracker(tmp_path):
    lane = m.Lane(0,1,'lower',11200000000.0)
    obs = {'a':m.Observation('a','source',lane,10,15,20,1000.0)}
    path = tmp_path/'tracks.tsv'
    prefix = 'SUMMARY\t1\t1\t1\nCONFIG\ttest\nTRACK\t0\ts\tt\t0\t1\tlower\t11200000000\t10\t20\t15\t0\t1000\t0\t0\t1\t1\n'
    path.write_text(prefix+'POINT\t0\ta\tsource\t0\t1001\t1001\n')
    with pytest.raises(ValueError,match='raw CFO'): m.read_tracks(path,obs)
    path.write_text(prefix+'POINT\t0\ta\tsource\t1\t1000\t1000\n')
    with pytest.raises(ValueError,match='alias conversion'): m.read_tracks(path,obs)
    path.write_text(prefix+'POINT\t0\ta\tsource\t0\t1000\t1000\n')
    assert m.read_tracks(path,obs).values[0].points[0].raw_cfo_hz == 1000


def test_extra_points_can_fail_purity_despite_full_coverage():
    lane = m.Lane(0,1,'lower',11200000000.0)
    observations = {str(i):m.Observation(str(i),str(i),lane,i,i,i+1,1000.) for i in range(10)}
    points = tuple(m.Point(str(i),str(i),1000.,1000.,0) for i in range(10))
    ref = m.Track(0,lane,0,10,0,0,1000,points[::2])
    output = m.Track(0,lane,0,10,0,0,1000,points)
    sources = {str(i):(i,0,0) for i in range(10)}
    settings = dict(alias_spacing_hz=1/4.4e-6,canonical_rf_hz=11200000000.,
                    same_source_circular_cfo_gate_hz=2500.,minimum_reference_source_coverage=.8,
                    minimum_in_span_output_purity=.8)
    result = m.membership_metrics(ref,output,observations,observations,sources,sources,settings)
    assert result['reference_source_coverage'] == 1
    assert result['in_span_output_purity'] == .5
    assert not m.complete(result,settings)
