import hashlib
import json
from pathlib import Path

import numpy as np

from audit_links import alias_align

HERE=Path(__file__).resolve().parent


def test_alias_alignment_removes_only_integer_cycles():
    offsets=np.array([1234.,201234.,-198746.])
    aligned,aliases=alias_align(offsets,200000.)
    np.testing.assert_array_equal(aliases,[0,1,-1])
    np.testing.assert_array_equal(aligned,[1234.,1234.,1254.])
    np.testing.assert_array_equal(aligned+aliases*200000.,offsets)


def test_completed_groups_have_consistent_training_assignments():
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert hashlib.sha256((HERE/'audit_links.py').read_bytes()).hexdigest()==protocol['source_sha256']
    for name,value in protocol['files'].items():assert hashlib.sha256((HERE.parent/name).read_bytes()).hexdigest()==value
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text());assert result['complete']
        assert result['protocol_sha256']==hashlib.sha256((HERE/'protocol.json').read_bytes()).hexdigest()
        tracks={t['track_id']:t for t in result['tracks']}
        for group in result['groups']:
            members=[tracks[t] for t in group['track_ids']]
            assert len(members)>=2
            assert all(t['confidence']>=.99 for t in members)
            for key in ['receiver_id','channel','rf_hz','candidate_index']:
                assert all(t[key]==group[key] for t in members)
            aligned,aliases=alias_align([t['offset'] for t in members],group['normalized_alias_hz'])
            np.testing.assert_array_equal(aliases,group['aliases'])
            np.testing.assert_allclose(aligned,group['aligned_offsets_hz'])
            assert np.isfinite(group['held_change'])
