import copy
import unittest
from unittest.mock import patch

import confirmation_model as model


class ConfirmationProofTests(unittest.TestCase):
    def setUp(self):
        self.doc = dict(start_utc_ns=300, session_id='scan')
        snapshot = dict(provider='p', collected_utc_ns=100, sha256='bytes', archive_path='file')
        self.manifest = dict(capture_start_utc_ns=300, session_id='scan', tracks=[{}],
                             selected_snapshots=[snapshot], proofs=[dict(snapshot,
                                journal_published_utc_ns=200, qualified=True, capture_start_utc_ns=300)])

    def test_exact_snapshot_and_completion_binding(self):
        with patch.object(model.core, 'digest', return_value='bytes'):
            model.validate_proofs(self.manifest, self.doc)
            for key, value in [('journal_published_utc_ns', 300), ('journal_published_utc_ns', 99),
                               ('qualified', False), ('capture_start_utc_ns', 301), ('sha256', 'other')]:
                bad = copy.deepcopy(self.manifest)
                bad['proofs'][0][key] = value
                with self.assertRaises(ValueError):
                    model.validate_proofs(bad, self.doc)

    def test_all_selected_snapshots_must_have_proofs(self):
        bad = copy.deepcopy(self.manifest)
        bad['selected_snapshots'][0]['provider'] = 'other'
        with patch.object(model.core, 'digest', return_value='bytes'):
            with self.assertRaises(ValueError):
                model.validate_proofs(bad, self.doc)
        bad = copy.deepcopy(self.manifest)
        bad['proofs'] = []
        bad['selected_snapshots'] = []
        with self.assertRaises(ValueError):
            model.validate_proofs(bad, self.doc)

    def test_proven_noop_requires_no_new_snapshot(self):
        manifest = dict(capture_start_utc_ns=300, session_id='scan', tracks=[],
                        selected_snapshots=[], proofs=[])
        model.validate_proofs(manifest, self.doc)
        invalid = copy.deepcopy(self.manifest)
        invalid['tracks'] = []
        with self.assertRaises(ValueError):
            model.validate_proofs(invalid, self.doc)
        manifest['session_id'] = 'different'
        with self.assertRaises(ValueError):
            model.validate_proofs(manifest, self.doc)
