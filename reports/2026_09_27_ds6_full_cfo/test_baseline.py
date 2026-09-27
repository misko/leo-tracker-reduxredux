"""Shortlist accounting and partial/full baseline artifact checks."""
import hashlib
import json
from pathlib import Path

import numpy as np

from run_baseline import select_top

HERE=Path(__file__).resolve().parent


def test_shortlist_unions_all_timing_columns_and_reports_omitted_mass():
    score=np.array([[0.,-10.],[-10.,0.],[-10.,-10.]])
    chosen,mass=select_top(score,np.array([11,22,33]),k=1)
    assert chosen=={11,22}
    np.testing.assert_allclose(mass,1/(1+2*np.exp(-10.)))
    all_ids,all_mass=select_top(score,np.array([11,22,33]),k=8)
    assert all_ids=={11,22,33}
    np.testing.assert_allclose(all_mass,1.)


def test_available_results_are_bound_to_protocol_and_selected_on_training():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert len(protocol['sessions'])==len(set(protocol['sessions']))==43
    assert hashlib.sha256((HERE/'run_baseline.py').read_bytes()).hexdigest()==protocol['source_sha256']
    for name,value in protocol['files'].items():assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==value
    paths=list(HERE.glob('scan-fw-*.json'))
    assert paths,'No baseline evidence yet'
    for path in paths:
        result=json.loads(path.read_text());session=result['session_id']
        assert session in protocol['sessions']
        assert result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        source=HERE.parent/'2026_09_27_ds6_cfo_dataset'/f'{session}-plan.json'
        assert result['input_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
        if result['state']=='unavailable':
            assert result['reason'];continue
        assert result['best']==max(result['runs'],key=lambda r:r['train'])
        assert result['tracks']==len(result['shortlists'])
        assert 0<=result['minimum_anchor_top8_mass']<=1.000000001
        assert result['maximum_interpolation_error_hz']<1.
        assert np.isfinite(result['exact_held'])


def test_full_sweep_contains_every_frozen_scan():
    protocol=json.loads((HERE/'protocol.json').read_text())
    paths=list(HERE.glob('scan-fw-*.json'))
    assert {p.stem for p in paths}==set(protocol['sessions'])
    assert len(paths)==43
    for path in paths:
        result=json.loads(path.read_text())
        assert result['complete'] and result['state'] in {'complete','unavailable'}
