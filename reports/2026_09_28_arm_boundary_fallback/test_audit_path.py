import json
import tempfile
import unittest
from pathlib import Path
from audit_path import audit


class PathAuditTests(unittest.TestCase):
    def test_fallback_and_direct_fields_and_multiplicity(self):
        with tempfile.TemporaryDirectory() as temporary:
            folders={name:Path(temporary)/name for name in ('candidate','direct','full')}
            for name,folder in folders.items():
                folder.mkdir();windows=[]
                for rx in (0,1):
                    for probe in range(11):
                        candidates=[]
                        for rank in range(8):
                            fallback=rank==0
                            tracking=(-1/(2*4.4e-6) if fallback else 5)
                            if name=='full' or (name=='candidate' and fallback):tracking=9
                            c=dict(coarse_epoch=rank,coarse_bin=5,epoch=rank,
                                acquired_cfo_hz=0,tracking_cfo_hz=tracking,
                                exact_score=.2,control_score=.1,margin=.1,glrt_complete=1,
                                conditioned_fallback=fallback,conditioned_cfo_hz=None,
                                conditioned_score=None,acquire_score=None,verify_score=None,
                                verify_control_score=None)
                            if name=='full' or (name=='candidate' and fallback):
                                c['conditioned_cfo_hz']=0;c['conditioned_score']=.5
                            candidates.append(c)
                        windows.append(dict(receiver_id=rx,probe_index=probe,candidates=candidates))
                (folder/'manifest.json').write_text(json.dumps(dict(complete=True,processed_dwells=1)))
                (folder/'rows.jsonl').write_text(json.dumps(dict(context=dict(session_id='test',visit_index=1,sha256='hash'),rows=windows,returncode=0,stderr=''))+'\n')
            x=audit(**folders)
            self.assertEqual(x['counts']['candidate_entries'],176)
            self.assertEqual(x['counts']['conditioned_fallbacks'],22)
            self.assertEqual(x['counts']['actual_glrt_kernel_calls'],198)
            p=folders['candidate']/'rows.jsonl';r=json.loads(p.read_text())
            r['rows'][0]['candidates'][0]['tracking_cfo_hz']=10
            p.write_text(json.dumps(r)+'\n')
            with self.assertRaises(AssertionError):audit(**folders)


if __name__=='__main__':unittest.main()
