import json
from pathlib import Path
import tempfile
import unittest
from score_cohort import audit,load_native


class ScoreTests(unittest.TestCase):
    def test_maximum_matching_does_not_double_count(self):
        ref=[{'epoch_sample':x,'tracking_cfo_hz':0} for x in (0,3)]
        got=[{'epoch':x,'tracking_cfo_hz':0} for x in (2,-2)]
        self.assertEqual(audit.maximum_matches(ref,got),2)
        self.assertEqual(audit.maximum_matches(ref,got[:1]),1)
        got[0]['tracking_cfo_hz']=8001
        self.assertEqual(audit.maximum_matches(ref,got),1)

    def test_zero_candidate_windows_valid_but_missing_window_fails(self):
        context=dict(session_id='test',visit_index=1,sha256='input')
        rows=[dict(receiver_id=rx,probe_index=i,candidate_count=0,candidates=[])
              for rx,i in sorted(audit.WINDOW_KEYS)]
        record=dict(context=context,rows=rows,returncode=0,stderr='')
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'rows.jsonl';p.write_text(json.dumps(record)+'\n')
            self.assertEqual(len(load_native(p,[context])[('test',1)]),22)
            rows[0]['candidate_count']=1
            rows[0]['candidates']=[dict(epoch=0,acquired_cfo_hz=0,tracking_cfo_hz=0,
                exact_score=0,control_score=0,margin=0)]
            for flag in (None,0):
                if flag is not None:rows[0]['candidates'][0]['glrt_complete']=flag
                p.write_text(json.dumps(record)+'\n')
                with self.assertRaisesRegex(ValueError,'GLRT incomplete'):
                    load_native(p,[context])
            rows[0]['candidates'][0]['glrt_complete']=1
            p.write_text(json.dumps(record)+'\n')
            self.assertEqual(len(load_native(p,[context])[('test',1)]),22)
            rows.pop();p.write_text(json.dumps(record)+'\n')
            with self.assertRaisesRegex(ValueError,'missing windows'):
                load_native(p,[context])


if __name__=='__main__':unittest.main()
