import pickle
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]/'tools'))
from replay_standard_glrt_scan import Batch, validate_scope


@pytest.mark.parametrize('expected,maximum', [(2218,2218), (2216,2)])
def test_full_and_explicit_partial_scopes(expected, maximum):
    validate_scope('scan-fw-b34e380766e24b3b', 'sha256:'+'a'*64, expected, maximum)


@pytest.mark.parametrize('session,digest,expected,maximum', [
    ('../../escape','sha256:'+'a'*64,2218,2),
    ('scan-fw-b34e380766e24b3b','sha256:wrong',2218,2),
    ('scan-fw-b34e380766e24b3b','sha256:'+'a'*64,2218,2219),
    ('scan-fw-b34e380766e24b3b','sha256:'+'a'*64,2218,0),
])
def test_invalid_scope_rejected(session,digest,expected,maximum):
    with pytest.raises(ValueError):validate_scope(session,digest,expected,maximum)


def test_worker_payload_preserves_distinct_capture_authority():
    # Spawn/forkserver workers must receive scope explicitly, not inherit edited
    # module globals from a previous scan in the parent.
    batches=[Batch((0,1),'/output','/readonly','task',name,'sha256:'+digit*64,count)
             for name,digit,count in [('scan-fw-b34e380766e24b3b','a',2218),
                                      ('scan-fw-ee2831131a88440f','b',2216)]]
    copied=pickle.loads(pickle.dumps(batches))
    assert copied==batches
    assert copied[0].session_id!=copied[1].session_id
    assert copied[0].manifest_digest!=copied[1].manifest_digest
