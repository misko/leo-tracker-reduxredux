import hashlib
import json
from pathlib import Path

import numpy as np

from audit import retained_mass

HERE=Path(__file__).resolve().parent


def test_retained_mass_accounts_for_missing_hypotheses_and_log_shift():
    scores=np.log([.1,.2,.7]);ids=np.array([2,4,6])
    np.testing.assert_allclose(retained_mass(scores,ids,{2,4}),.3)
    np.testing.assert_allclose(retained_mass(scores-10000,ids,{2,4}),.3)
    assert retained_mass(scores,ids,{99})==0.
    np.testing.assert_allclose(retained_mass(scores,ids,{2,4,6}),1.)


def test_complete_audit_is_sealed_and_includes_every_baseline_track():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert hashlib.sha256((HERE/'audit.py').read_bytes()).hexdigest()==protocol['source_sha256']
    for name,value in protocol['files'].items():assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==value
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        baseline=json.loads((HERE.parent/'2026_09_27_ds6_full_cfo'/f'{session}.json').read_text())
        assert result['complete']
        assert result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        assert {r['track_id'] for r in result['tracks']}==set(baseline['shortlists'])
        for row in result['tracks']:
            assert 0<=row['retained_mass']<=1.000000001
            np.testing.assert_allclose(row['full_train_gain'],-np.log(row['retained_mass']),atol=1e-8)
            assert row['training_best_missing']==(row['training_best_candidate'] not in baseline['shortlists'][row['track_id']])
