import copy
import unittest
import numpy as np
import joint


class JointRuleTests(unittest.TestCase):
    def fixture(self):
        screens={}
        for n,v in [(10,30),(20,40)]:
            p=dict(name=f'{n}_to_{v}',norad=v,mapping={str(n):v},aliases={str(n):0},phases={str(v):0},penalty=2.,predictive={a:dict(pass_check=False) for a in joint.ARMS})
            screens[n]=dict(proposals=[p],whole={a:{str(v):dict(training_score=1.)} for a in joint.ARMS})
        return screens

    def test_pair_precedes_singleton_predictive_gate(self):
        pairs,excluded=joint.pair_rule([10,20],self.fixture(),{10,20})
        self.assertEqual(len(pairs),1);self.assertEqual(excluded,[])
        self.assertGreater(pairs[0]['penalty'],4.)

    def test_forbid_duplicate_or_untouched_destination(self):
        screens=self.fixture();screens[20]['proposals'][0]['norad']=30
        screens[20]['whole']={a:{'30':dict(training_score=1.)} for a in joint.ARMS}
        self.assertEqual(joint.pair_rule([10,20],screens,{10,20})[0],[])
        self.assertEqual(joint.pair_rule([10,20],self.fixture(),{10,20,30})[0],[])

    def test_random_group_guards_and_unique_splits(self):
        times=np.tile(np.arange(0.,300.,.5),2);groups=np.repeat([0,1],600)
        splits=joint.rec.masks(times,groups,unique=True)
        self.assertEqual(len(splits),5);self.assertEqual(len({tuple(s['held_blocks']) for s in splits}),5)
        blocks=np.floor(times/5).astype(int)
        for s in splits:
            self.assertFalse(np.any(s['train']&s['test']))
            self.assertFalse(np.isin(blocks[s['train']],np.r_[s['held_blocks']-1,s['held_blocks'],s['held_blocks']+1]).any())

    def test_recorded_replay_and_native_evidence(self):
        for case in ['DS26-0203','DS26-0070']:
            replay=joint.read(joint.OUT/case/'replay.json')
            self.assertTrue(all(abs(v)<1e-4 for v in replay['rebuilt'].values()))
            padding=joint.read(joint.OUT/case/'supplement/padding_replay.json')
            self.assertTrue(all(abs(v)<1e-4 for v in padding.values()))
            hashes=set()
            for path in (joint.OUT/case).rglob('*fits.json'):
                for row in joint.read(path):
                    if row['status']!='complete':continue
                    hashes.add(row['native_ids_sha256'])
                    if row['qualified']:
                        self.assertTrue(row['phase_closed'] and row['optimizer_success'] and row['all_gates_pass'])
                        self.assertEqual(row['lost_ids'],[]);self.assertEqual(row['unexpected_reassigned_ids'],[])
            self.assertEqual(len(hashes),1)

    def test_original_results_preserve_published_fallback(self):
        for case in ['DS26-0203','DS26-0070']:
            result=joint.read(joint.OUT/case/'result.json')
            self.assertIsNone(result['selected'])
            self.assertEqual(result['final'],joint.read(joint.OUT/case/'baseline.json'))

    def test_merge_has_disjoint_native_observations(self):
        rows=joint.read(joint.OUT/'DS26-0203/merge_audit/audit.json')
        self.assertEqual(len(rows),4)
        for row in rows:self.assertEqual(row['duplicate_native_ids'],[])


if __name__=='__main__':unittest.main()
