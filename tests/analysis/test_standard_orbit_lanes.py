from types import SimpleNamespace
import numpy as np
import pytest

import standard_orbit_lanes as adapter
from leo.analysis.research.predictive_track import receiver_design
from leo.analysis.research.retained_track_likelihood import projected_receiver_basis


def test_calibrated_frame_full_scan_orbits_and_unchanged_owners(monkeypatch):
    calls=[]
    def frequency(bank,times,labels,phase,*coordinates):
        calls.append(np.asarray(times))
        return 10*np.asarray(times)+phase[0]*20, np.where(np.asarray(times)<2,-1.,1.)
    monkeypatch.setattr(adapter,'paired_phase_frequency',frequency)
    p=SimpleNamespace(labels=[0],supported=[],hardware=np.zeros((1,9)),smooth=np.zeros((1,22)),
        fitted_c=True,reference=np.array([1.]),sky={'time_s':np.arange(-40,341),'position_km':np.zeros((1,381,3))},
        scan=SimpleNamespace(norads=np.array([123]),tracks=[]),state=lambda x:{'phases':np.array([2.])})
    coefficient=np.arange(31)/100
    observations=[dict(observation_id=str(k),receiver=1,channel=1,time_s=float(k),actual_rf_hz=12e9,
                       measured_cfo_hz=500.) for k in (1,2)]
    owners={'1':123}
    lanes=adapter.calibrated_lanes(p,np.zeros(2),{'coefficient':coefficient},observations,owners,[],[])
    assert len(lanes)==16
    lane=lanes[0]
    correction=receiver_design(np.array([1.,2.]),12e9,1,1,projected_receiver_basis([1.,2.]),fitted_c=True)@coefficient
    assert [peak.frequency_hz for peak in lane.peaks]==pytest.approx(500-correction)
    assert [peak.satellite_id for peak in lane.peaks]==['123',None]
    curve=lane.curves[0]
    assert (curve.time_s[0],curve.time_s[-1],len(curve.time_s))==(0.,300.,1201)
    assert np.isnan(curve.frequency_hz[0])
    assert curve.frequency_hz[-1]==pytest.approx((3000+40)*12/11.5)
    assert owners=={'1':123}


def test_duplicate_renderer_defers_without_replaying_or_publishing(tmp_path,monkeypatch):
    import fcntl
    import render_standard_fast as worker
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
    store=FastStandardAnalysisStore(tmp_path);folder=store.folder('run');folder.mkdir(parents=True)
    calls=[]
    monkeypatch.setattr(worker,'_publish',lambda *args:calls.append(args) or {'state':'complete'})
    with (folder/'render.lock').open('a') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        assert worker.publish(None,store,{'run_id':'run'})=={'state':'rendering','artifacts':[]}
        assert not calls
    assert worker.publish(None,store,{'run_id':'run'})=={'state':'complete'}
    assert len(calls)==1
