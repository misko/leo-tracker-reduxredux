import importlib.util
import hashlib
import json
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('robust',Path(__file__).with_name('run.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_contaminated_density_normalizes_and_is_periodic():
    x=np.linspace(-np.pi,np.pi,20000,endpoint=False)
    for k in [4,16]:
        assert abs(np.exp(m.log_density(x,k)).mean()-1)<1e-12
        np.testing.assert_allclose(m.log_density(x+2*np.pi,k),m.log_density(x,k),atol=1e-12)


def test_outlier_does_not_erase_true_source_difference():
    t=np.tile(np.linspace(-.003,.003,7),2);s=np.repeat([-1,1],7);phi=np.where(s==-1,.8,-1.1)
    clean=np.exp(1j*(phi+2*np.pi*27.3*t));z=clean.copy();z[2]*=np.exp(1j*2.7)
    robust=m.fit(t,z,s,16);linear=m.base.fit(t,z,s,0)
    error=lambda model:abs(m.base.wrap(model['phases_rad'][1]-model['phases_rad'][-1]+1.9))
    assert error(robust)<.03 and error(robust)<error(linear)
    assert robust['inlier_probabilities'][2]<.1
    assert max(abs(np.array(m.base.evaluate(robust,t,clean,s)['errors_rad'])))<.03


def test_real_artifacts_retain_every_qualified_window_and_held_pilot():
    root=Path(__file__).resolve().parent
    for prefix in ['', 'transfer-']:
        result=json.loads((root/(prefix+'results.json')).read_text());protocol=json.loads((root/(prefix+'protocol.json')).read_text())
        assert result['complete'] and result['protocol_sha256']==hashlib.sha256((root/(prefix+'protocol.json')).read_bytes()).hexdigest()
        for scan in result['scans']:
            sid=scan['session_id'];source=root.parent/('2026_09_27_ds6_dwell_phase' if prefix else '2026_09_27_ds6_phase_curvature')/(sid+'-frames.json')
            assert hashlib.sha256(source.read_bytes()).hexdigest()==protocol['source_hashes'][sid]
            cached=json.loads(source.read_text());frames=[w for w in cached if w['result']['both_qualified']] if prefix else [w['frame'] for w in cached]
            assert len(frames)==len(scan['windows'])
            for frame,w in zip(frames,scan['windows']):
                for arm in w['arms'].values():
                    assert len(arm['errors_rad'])==len(frame['data']['evaluation']['t'])
