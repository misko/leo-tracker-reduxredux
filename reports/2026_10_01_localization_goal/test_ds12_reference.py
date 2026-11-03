"""Reference admission rejects tampering and ineligible capture intervals."""
from copy import deepcopy

import pytest
from admit_ds12_reference import canonical_digest, validate


def fixture():
    pose = dict(radio_id='radio', valid_from_utc_ns=10, valid_until_utc_ns=100,
                latitude_deg=38., longitude_deg=-121.)
    capture = dict(session_id='scan', manifest_sha256='sha256:abc',
                   capture_start_earliest_utc_ns=20, capture_end_utc_ns=30,
                   radio_id='radio', receiver_ids=[0, 1], utc_qualified=True)
    document = {k: capture[k] for k in ['session_id', 'manifest_sha256',
                'capture_start_earliest_utc_ns', 'capture_end_utc_ns']}
    document.update(pose_authority=deepcopy(pose), pose_authority_digest=canonical_digest(pose))
    document['binding_digest'] = canonical_digest(document)
    return document, capture, pose


def test_valid_and_tampered_binding():
    document, capture, pose = fixture()
    assert validate(document, capture, pose, 40) == [38., -121.]
    document['pose_authority']['latitude_deg'] = 39.
    with pytest.raises(ValueError, match='binding digest'):
        validate(document, capture, pose, 40)


@pytest.mark.parametrize('key,value', [('manifest_sha256', 'different'),
                                     ('session_id', 'other'), ('radio_id', 'other'),
                                     ('utc_qualified', False)])
def test_capture_mismatch(key, value):
    document, capture, pose = fixture()
    capture[key] = value
    with pytest.raises(ValueError):
        validate(document, capture, pose, 40)


def test_superseding_boundary_and_authority_mismatch():
    document, capture, pose = fixture()
    with pytest.raises(ValueError, match='interval'):
        validate(document, capture, pose, 30)
    pose['longitude_deg'] = -122.
    with pytest.raises(ValueError, match='authority'):
        validate(document, capture, pose, 40)
