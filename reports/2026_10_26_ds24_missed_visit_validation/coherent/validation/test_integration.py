import copy
import importlib.util
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import integrate


def test_stage_preserves_native_identity_and_measurement():
    native=dict(observation_id='native',receiver=2,native_receiver_id=1,channel=6,time_s=4.,actual_rf_hz=12e9,
        stream_generation='stream',start_counter=100)
    snapshot=copy.deepcopy(native)
    row=integrate.stage_row(native,123.5,.06)
    assert native==snapshot
    assert row==dict(observation_id='native',receiver=2,native_receiver_id=1,channel=6,time_s=4.,actual_rf_hz=12e9,
        measured_cfo_hz=123.5,fractional_margin=.06)


def test_corrected_metadata_receipt_and_runtime_parity_scope():
    assert integrate.read(HERE/'metadata_audit_v2.json')['all_passed']
    p=integrate.read(integrate.TIMING/'protocol.json')
    assert p['metadata_handoff_version']==2 and p['no_new_recovered_donors']
    for case in p['cases']:
        d=integrate.read(integrate.TIMING/'outcomes'/(case+'.json.gz'))
        assert d['fresh_blind_candidate_parity'] is False
        assert all(w['native_receipt']['fresh_per_window_paired_candidate_parity'] is False for w in d['rows'])


def test_graph_curve_projects_legendre_and_native_alias():
    from plot_blocks import native_curve_segments,PERIOD
    piece=dict(start_s=-1,end_s=1,reference_time_s=0,time_scale_s=1,coefficients_hz=[PERIOD+100,20,10],indices=[0,1])
    # P2(±1)=1; the graph's one-period lift must disappear on raw-CFO axes.
    track=dict(indices=[0,1],observation_ids=['a','b'],values=[PERIOD+90,PERIOD+130])
    obs={'a':dict(time_s=-1,measured_cfo_hz=90),'b':dict(time_s=1,measured_cfo_hz=130)}
    [(ts,ys)]=native_curve_segments(track,piece,obs,-1,1)
    assert abs(ys[0]-90)<1e-7 and abs(ys[-1]-130)<1e-7
