import unittest,json
from copy import deepcopy
from pathlib import Path
from coverage_ledger import enforce_rejected_ids,coverage_with_ledger,accepted_ids

def fixture():
    rows=[dict(component='old',compatible=True,points=2,observation_ids=['a','b']),dict(component='extension',compatible=True,points=2,observation_ids=['c','d'])]
    return dict(associated=4,total_GLRT=10,percent=40,associated_tracks=2,accepted_observation_ids=['a','b','c','d'],associations=dict(tracks=rows),predictive_points=2,active_curved_points=2)

class LedgerTests(unittest.TestCase):
    def test_overlap_refused(self):
        with self.assertRaisesRegex(ValueError,'overlap'):enforce_rejected_ids(fixture(),['a'],['a','b'])
    def test_consistent_whole_record_and_idempotence(self):
        cov=fixture();original=deepcopy(cov);out=enforce_rejected_ids(cov,['c'],['a','b'])
        self.assertEqual(cov,original);self.assertEqual(out['associated'],2);self.assertEqual(out['percent'],20)
        self.assertEqual(out['associated_tracks'],1);self.assertEqual(out['predictive_points'],2)
        self.assertEqual(out['accepted_observation_ids'],['a','b']);self.assertEqual(out,enforce_rejected_ids(out,['c'],['a','b']))
        self.assertEqual(out,coverage_with_ledger(lambda:cov,rejected_ids=['c'],parent_accepted_ids=['a','b']))
    def test_collateral_protected_refused(self):
        with self.assertRaisesRegex(ValueError,'whole-record'):enforce_rejected_ids(fixture(),['c'],['d'])
    def test_duplicate_or_stale_input_refused(self):
        cov=fixture();cov['associated']=3
        with self.assertRaisesRegex(ValueError,'disagree'):enforce_rejected_ids(cov,[],['a'])
        cov=fixture();cov['associations']['tracks'][1]['observation_ids']=['a','c']
        with self.assertRaisesRegex(ValueError,'duplicate'):enforce_rejected_ids(cov,[],['a'])
    def test_previous_results_replay(self):
        d=json.loads((Path(__file__).parent/'results.json').read_text())
        self.assertEqual([len(r['removed_readmitted_ids']) for r in d['rows']],[0,9,0,0])
        self.assertEqual([r['after'] for r in d['rows']],[2088,2088,2194,2194])
        for r in d['rows']:
            c=r['coverage'];self.assertEqual(len(accepted_ids(c['associations']['tracks'])),c['associated'])
            self.assertEqual(c['associated_tracks'],len(c['associations']['tracks']));self.assertEqual(r['collateral_removed_ids'],[])
if __name__=='__main__':unittest.main()
