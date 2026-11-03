import unittest
from run import validate,canonical_digest
class BindingTests(unittest.TestCase):
    def test_valid_and_tampered_authority(self):
        pose=dict(valid_from_utc_ns=0,valid_until_utc_ns=10)
        d=dict(session_id='s',manifest_sha256='m',pose_authority=pose,pose_authority_digest=canonical_digest(pose),capture_start_earliest_utc_ns=1,capture_end_utc_ns=9)
        d['binding_digest']=canonical_digest(d);entry=dict(session_id='s',manifest_sha256='m')
        self.assertEqual(validate(d,entry),pose)
        d['pose_authority']['valid_until_utc_ns']=11
        with self.assertRaises(AssertionError):validate(d,entry)
    def test_wrong_capture_binding(self):
        pose=dict(valid_from_utc_ns=0,valid_until_utc_ns=10)
        d=dict(session_id='s',manifest_sha256='m',pose_authority=pose,pose_authority_digest=canonical_digest(pose),capture_start_earliest_utc_ns=1,capture_end_utc_ns=9)
        d['binding_digest']=canonical_digest(d)
        with self.assertRaises(AssertionError):validate(d,dict(session_id='other',manifest_sha256='m'))
