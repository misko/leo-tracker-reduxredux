import copy
import pytest
from audit_ds23_reference_authority import canonical_digest,verify_pose


def test_pose_must_own_capture_digest_and_cover_complete_capture():
    authority=dict(valid_from_utc_ns=10,valid_until_utc_ns=30)
    body=dict(session_id="a",manifest_sha256="sha256:abc",capture_start_earliest_utc_ns=12,
        capture_end_utc_ns=25,pose_authority=authority,pose_authority_digest=canonical_digest(authority))
    document=dict(body,binding_digest=canonical_digest(body))
    verify_pose(document,"a","sha256:abc")
    with pytest.raises(ValueError,match="own"):
        verify_pose(document,"b","sha256:abc")
    changed=copy.deepcopy(document);changed["capture_end_utc_ns"]=31
    changed["binding_digest"]=canonical_digest({k:v for k,v in changed.items() if k!="binding_digest"})
    with pytest.raises(ValueError,match="validity"):
        verify_pose(changed,"a","sha256:abc")
    with pytest.raises(ValueError,match="digest"):
        verify_pose(dict(document,capture_end_utc_ns=20),"a","sha256:abc")
