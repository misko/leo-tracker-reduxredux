"""Group membership and frozen evidence checks for the consistency audit."""
import hashlib
import json
from pathlib import Path

import numpy as np

from run_groups import groups

HERE=Path(__file__).resolve().parent


def test_group_membership_uses_only_receiver_and_channel():
    tracks=[dict(track_id=f'{rx}-{ch}',receiver_id=rx,channel=ch) for rx in [0,1] for ch in [1,2,3,4]]
    result=groups(tracks)
    assert set(result)=={'all','only_rx0','only_rx1',*[f'without_ch{ch}' for ch in [1,2,3,4]]}
    assert len(result['all'])==8
    for rx in [0,1]:assert {t['receiver_id'] for t in result[f'only_rx{rx}']}=={rx}
    for ch in [1,2,3,4]:assert len(result[f'without_ch{ch}'])==6 and all(t['channel']!=ch for t in result[f'without_ch{ch}'])
    assert 'only_rx0' not in groups([t for t in tracks if t['receiver_id']==1])


def test_complete_evidence_and_selection():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert hashlib.sha256((HERE/'run_groups.py').read_bytes()).hexdigest()==protocol['source_sha256']
    for name,value in {**protocol['inputs'],**protocol['dependencies']}.items():
        assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==value
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        source=json.loads((HERE.parent/'2026_09_27_ds6_common_rate_validation'/f'{session}-plan.json').read_text())
        expected=groups(source['tracks'])
        assert result['complete']
        assert result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        assert set(result['groups'])==set(expected)
        for name,row in result['groups'].items():
            assert row['track_ids']==sorted(t['track_id'] for t in expected[name])
            assert row['best']==max(row['runs'],key=lambda r:r['train'])
            assert row['maximum_interpolation_error_hz']<1.
            assert np.isfinite(row['included_held_gain'])
        assert result['groups']['all']['shift_from_all_km']<.1
