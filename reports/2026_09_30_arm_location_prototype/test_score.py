"""Independent NumPy/server-scorer checks of the research C loop."""
import json
import subprocess
from pathlib import Path

import numpy as np
from check import pack
from leo.analysis.adaptive_tle_position import AdaptiveTrackPrediction,score_track_prediction

HERE=Path(__file__).resolve().parent

def test_score_matches_server_on_supplied_predictions(tmp_path):
    m=json.loads((HERE/'inputs.json').read_text())
    allstates=np.load(HERE/'local/states.npy',mmap_mode='r')
    # Include saved winners and unrelated catalogue identities; preserve full
    # time support of four deterministic tracks. No reference position fitting.
    wanted={int(x['candidate_id']) for p in m['points'] for x in p['expected_tracks'][:4] if x['candidate_id'] is not None}
    chosen=[i for i,k in enumerate(m['satellite_ids']) if k in wanted]+[0,1]
    ids=np.array(m['satellite_ids'])[chosen];states=np.array(allstates[chosen,::10])
    tracks=m['tracks'][:4];fixture=tmp_path/'test.bin';pack(fixture,m,states,10,tracks,ids)
    for binary in ('score-host','score-san'):
        result=json.loads(subprocess.check_output([str(HERE/'local'/binary),str(fixture)],text=True))
        for point,got in zip(m['points'],result['points'],strict=True):
            for tr,row in zip(tracks,got['tracks'],strict=True):
                times=np.array(tr['times_s']);taus=np.arange(-5.,6.);query=times[None,:]+taus[:,None]
                q=(query-m['knot_start_s'])/10;i=np.floor(q).astype(int);u=q-i;u=u[None,:,:,None]
                a=states[:,i,:];b=states[:,i+1,:]
                p=(2*u**3-3*u**2+1)*a[...,:3]+(u**3-2*u**2+u)*10*a[...,3:]+(-2*u**3+3*u**2)*b[...,:3]+(u**3-u**2)*10*b[...,3:]
                v=((6*u**2-6*u)*a[...,:3]+(-6*u**2+6*u)*b[...,:3])/10+(3*u**2-4*u+1)*a[...,3:]+(3*u**2-2*u)*b[...,3:]
                delta=p-np.array(point['receiver']);visible=np.max(delta@np.array(point['up']),axis=(1,2))>=0
                pred=-11.2e9/299792.458*np.sum(delta*v,axis=-1)/np.linalg.norm(delta,axis=-1)
                expected=score_track_prediction(AdaptiveTrackPrediction(tr['track_id'],tuple(tr['observation_ids']),times,np.array(tr['measured_hz']),np.array(tr['training_mask'],bool),ids,taus,pred,visible))
                assert str(row['candidate_id'])==str(expected.candidate_id)
                assert row['tau_s']==expected.tau_s
                assert abs(row['held_hz']-expected.heldout_rms_hz)<1e-7
                assert abs(row['fit_hz']-expected.training_rms_hz)<1e-7
                assert abs(row['offset_hz']-expected.frequency_offset_hz)<1e-7


def test_truncated_input_fails(tmp_path):
    fixture=tmp_path/'short.bin';fixture.write_bytes(b'LOC1')
    for binary in ('score-host','score-san'):
        result=subprocess.run([str(HERE/'local'/binary),str(fixture)],capture_output=True)
        assert result.returncode==2


def test_unmatched_penalty_and_deterministic_identity_tie(tmp_path):
    tr=dict(times_s=[0.,1.,2.,3.,4.,5.],measured_hz=[0.,1.,2.,3.,4.,5.],training_mask=[True,False,True,False,True,False])
    m=dict(knot_start_s=-10.,satellite_ids=[20,10],tracks=[tr],points=[dict(receiver=[6378.,0.,0.],up=[1.,0.,0.])])
    states=np.zeros((2,4,6));states[:,:,0]=7000
    fixture=tmp_path/'tie.bin';pack(fixture,m,states,10)
    for binary in ('score-host','score-san'):
        r=json.loads(subprocess.check_output([str(HERE/'local'/binary),str(fixture)],text=True))['points'][0]
        assert r['tracks'][0]['candidate_id']==10
        assert r['tracks'][0]['tau_s']==-5
    states[:,:,0]=-7000;pack(fixture,m,states,10)
    for binary in ('score-host','score-san'):
        r=json.loads(subprocess.check_output([str(HERE/'local'/binary),str(fixture)],text=True))['points'][0]
        assert r['score_hz']==800
        assert r['tracks'][0]['candidate_id']==-1
        assert r['tracks'][0]['held_hz'] is None
