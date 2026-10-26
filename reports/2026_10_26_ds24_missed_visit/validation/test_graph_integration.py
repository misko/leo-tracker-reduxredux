"""Scientific support boundary of the original graph; local synthetic rows only."""

from prepare_overlay import rebuild_graph


def rows(n):
    return [dict(observation_id=f'test{i}',receiver=1,native_receiver_id=0,channel=5,
        time_s=2.*i,actual_rf_hz=11709687500.,measured_cfo_hz=10000.+40*(2*i)+4*(2*i)**2,
        fractional_margin=.1) for i in range(n)]


def test_four_sparse_targets_cannot_manufacture_an_eight_point_track():
    tracks,summary=rebuild_graph(rows(4),'synthetic',{})
    assert tracks==[]
    assert summary['graph_points']==0 and summary['curved_graph_points']==0


def test_distinct_time_curvature_can_enter_original_graph_without_satellite_identity():
    tracks,summary=rebuild_graph(rows(20),'synthetic',{})
    assert summary['graph_points']==20 and summary['curved_graph_points']==20
    assert len({oid for t in tracks for oid in t['observation_ids']})==20
    assert all('candidate_norad' not in t for t in tracks)
    assert {t['rf_hz'] for t in tracks}=={11709687500.}
