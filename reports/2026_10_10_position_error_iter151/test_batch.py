import json
import tempfile
import unittest
from pathlib import Path
from batch import run_member,authoritative_status,member_receipt

class ControllerTests(unittest.TestCase):
    def test_controller_failure_is_not_a_scientific_terminal(self):
        from report import build
        def fail(*args):raise ValueError('orphan claim; no retry')
        row=member_receipt({'label':'x'},fail,lambda *a:None)
        self.assertIn('orphan claim',row['controller_failure'])
        self.assertNotIn('phases',row)
        with tempfile.TemporaryDirectory() as folder:
            Path(folder,'batch-0.json').write_text(json.dumps({'members':[row]}))
            with self.assertRaises(ValueError):
                build(dict(members=[dict(label='x',dataset='DS16')],source_sha256={},input_sha256={}),folder,'d',evaluation_factory=lambda *a:self.fail('references must remain closed'))
    def test_pending_resumes_terminal_failure_never_retries(self):
        calls=[];states={'search':['pending','complete'],'native':['failed'],'zero':['complete']}
        def invoke(label,phase):calls.append(phase);return states[phase].pop(0)
        result=run_member({'label':'x'},invoke,lambda *a:None)
        self.assertEqual(calls,['search','search','native','zero']);self.assertEqual(result['native'],'failed')
    def test_unfinished_claim_and_foreign_receipt_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'x'/'search'/'slices';path.mkdir(parents=True)
            (path/'01.started.json').write_text(json.dumps({'protocol_sha256':'d'}))
            with self.assertRaises(ValueError):authoritative_status(folder,'x','search','d')
            (path/'01.finished.json').write_text(json.dumps({'protocol_sha256':'wrong','status':'pending'}))
            with self.assertRaises(ValueError):authoritative_status(folder,'x','search','d')
    def test_bounded_pending_without_terminal_fails(self):
        with self.assertRaises(ValueError):run_member({'label':'x'},lambda *a:'pending',lambda *a:None)

if __name__=='__main__':unittest.main()
