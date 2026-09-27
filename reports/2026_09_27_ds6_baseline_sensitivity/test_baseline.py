import importlib.util
import hashlib
import json
from pathlib import Path
import numpy as np
spec=importlib.util.spec_from_file_location('baseline',Path(__file__).with_name('run.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_baseline_grid_contains_nominal_and_directed_pairs():
    rows=m.baselines();assert len(rows)==42
    for row in rows:
        v=np.array(row['enu_m']);assert abs(np.linalg.norm(v)-row['length_m'])<1e-12
        assert any(np.linalg.norm(v+np.array(other['enu_m']))<1e-12 for other in rows)
    nominal=[r['enu_m'] for r in rows if r['length_m']==.08 and r['azimuth_deg']==90 and r['elevation_deg']==0]
    np.testing.assert_allclose(nominal,[[.08,0,0]],atol=1e-12)


def test_shared_baseline_uses_all_training_and_only_target_held():
    scans=[dict(train=[[0.,0.],[-2.,-2.]],joint=[[-1.,-1.],[-4.,-4.]]),dict(train=[[-3.,-3.],[0.,0.]],joint=[[-5.,-5.],[-1.,-1.]])]
    r=m.shared_score(scans,[0,1]);np.testing.assert_allclose(r['baseline_posterior'],np.exp([-3,-2])/np.exp([-3,-2]).sum())
    scans[1]['joint']=[[-100,-100],[-100,-100]];changed=m.shared_score(scans,[0,1]);assert changed['held_by_scan'][0]==r['held_by_scan'][0]


def test_nominal_real_factors_reproduce_prior_association():
    root=Path(__file__).resolve().parent;result=json.loads((root/'results.json').read_text());protocol=json.loads((root/'protocol.json').read_text());old=json.loads((root.parent/'2026_09_27_ds6_likelihood_association/results.json').read_text())
    assert result['complete'] and len(result['scans'])==2 and result['protocol_sha256']==hashlib.sha256((root/'protocol.json').read_bytes()).hexdigest()
    indices=[next(i for i,b in enumerate(protocol['baselines']) if b['length_m']==.08 and b['elevation_deg']==0 and b['azimuth_deg']==az) for az in [270,90]]
    for scan,prior in zip(result['scans'],old['scans']):
        assert scan['session_id']==prior['session_id']
        for g,p in zip(scan['groups'],prior['groups']):
            assert g['group']==p['group'] and g['pair_counts']==p['pair_counts']
            for k in ['train','joint']:np.testing.assert_allclose(np.array(g[k])[indices],p['arms']['phase_contamination_10pct'][k],rtol=0,atol=1e-9)
