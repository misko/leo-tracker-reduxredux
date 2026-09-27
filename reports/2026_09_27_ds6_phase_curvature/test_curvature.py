import importlib.util
import hashlib
import json
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('curvature',Path(__file__).with_name('run.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_shared_chirp_preserves_arbitrary_source_phases_and_predicts_held():
    t=np.r_[np.linspace(-.0028,.0026,5),np.linspace(-.0025,.0029,5)];s=np.repeat([-1,1],5)
    phi=np.where(s==-1,.8,-1.6);z=np.exp(1j*(phi+2*np.pi*37.2*t+np.pi*28000*t*t))
    model=m.fit(t,z,s,50000)
    assert abs(model['rate_hz']-37.2)<.01 and abs(model['chirp_hz_per_s']-28000)<10
    assert abs(m.wrap(model['phases_rad'][1]-model['phases_rad'][-1]+2.4))<1e-4
    held_t=t+1e-5;held_z=np.exp(1j*(phi+2*np.pi*37.2*held_t+np.pi*28000*held_t**2))
    assert max(abs(np.array(m.evaluate(model,held_t,held_z,s)['errors_rad'])))<1e-4


def test_zero_bound_recovers_linear_model_and_constant_phase_gauge():
    t=np.linspace(-.003,.003,12);s=np.where(np.arange(12)%2,1,-1);z=np.exp(1j*(s*.7+2*np.pi*63.7*t))
    a=m.fit(t,z,s,0);b=m.fit(t,z*np.exp(1j*1.3),s,0)
    assert a['chirp_hz_per_s']==b['chirp_hz_per_s']==0
    assert abs(a['rate_hz']-63.7)<.001
    assert abs(m.wrap((a['phases_rad'][1]-a['phases_rad'][-1])-(b['phases_rad'][1]-b['phases_rad'][-1])))<1e-5


def test_validation_preserves_qualified_windows_and_source_bindings():
    root=Path(__file__).resolve().parent;result=json.loads((root/'validation-results.json').read_text());protocol=json.loads((root/'validation-protocol.json').read_text())
    assert result['complete'] and len(result['scans'])==2
    assert result['protocol_sha256']==hashlib.sha256((root/'validation-protocol.json').read_bytes()).hexdigest()
    for scan in result['scans']:
        sid=scan['session_id'];oldpath=root.parent/'2026_09_27_ds6_common_rate_validation'/(sid+'-replay.json');old=json.loads(oldpath.read_text())
        assert hashlib.sha256(oldpath.read_bytes()).hexdigest()==protocol['source_hashes'][sid]['replay']
        key=lambda w:(w['visit'],w['group'],w['start_ms'])
        expected={key(w) for w in old['rows'] if w['original']['both_qualified']}
        assert {key(w) for w in scan['windows']}==expected and len(scan['windows'])==len(expected)
        assert hashlib.sha256((root/(sid+'-frames.json')).read_bytes()).hexdigest()==scan['frames_sha256']
        # Independent implementation agrees with the existing shared-rate arm.
        before={key(w):w for w in old['rows'] if w['original']['both_qualified']}
        for w in scan['windows']:
            assert abs(m.wrap(w['arms']['linear']['phase_dd_rad']-before[key(w)]['shared']['evaluation_dd']))<1e-4
