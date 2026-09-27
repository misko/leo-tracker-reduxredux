import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from run_linked import group_scores

HERE=Path(__file__).resolve().parent


@pytest.mark.parametrize('shared',[False,True])
def test_training_scores_ignore_held_residuals(shared):
    mask=np.array([True,False]*10)
    residuals=[np.linspace(-50,50,20)+offset for offset in [1000.,1100.]]
    before=group_scores(residuals,[mask,mask],shared)
    changed=[r+np.where(mask,0.,100000.) for r in residuals]
    after=group_scores(changed,[mask,mask],shared)
    assert before[0]==after[0]
    assert after[1]<before[1]


def test_single_fragment_has_identical_scores_in_both_arms():
    residual=np.linspace(-100,100,40)+300.
    mask=np.arange(40)%3!=0
    assert group_scores([residual],[mask],True)==group_scores([residual],[mask],False)


def test_finished_results_preserve_all_tracks_and_fixed_groups():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert hashlib.sha256((HERE/'run_linked.py').read_bytes()).hexdigest()==protocol['source_sha256']
    for name,value in protocol['files'].items():assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==value
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        baseline=json.loads((HERE.parent/'2026_09_27_ds6_full_cfo'/f'{session}.json').read_text())
        audit=json.loads((HERE.parent/'2026_09_27_ds6_fragment_links'/f'{session}.json').read_text())
        assert result['complete']
        assert result['tracks']==baseline['tracks']
        assert result['groups']==audit['groups']
        members=[t for g in result['groups'] for t in g['track_ids']]
        assert len(members)==len(set(members))
        for arm in result['arms'].values():
            assert arm['best']==max(arm['runs'],key=lambda r:r['train'])
            assert arm['maximum_interpolation_error_hz']<1.
            assert np.isfinite(arm['exact_held'])
        if not result['groups']:
            assert result['arms']['separate']==result['arms']['shared']
