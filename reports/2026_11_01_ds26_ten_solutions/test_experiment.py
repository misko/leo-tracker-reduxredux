import unittest
import numpy as np
from experiment import *

class ExperimentTests(unittest.TestCase):
    def test_centered_shared_rate(self):
        t=np.array([0.,150.,300.]);j=np.full(3,2);ev=[dict(kind='family',candidate_index=2,time_s=0.,transition_s=300.,sigma_hz=150.,centered_rate=True)]
        design=centered_event_design(t,np.ones(3),np.ones(3),np.full(3,11.5e9),j,ev)
        np.testing.assert_allclose(design[:,0],[-75,0,75])
        np.testing.assert_allclose(centered_event_design(t,np.ones(3),np.ones(3),np.full(3,11.5e9),j+1,ev),0)

    def test_original_model_replayed(self):
        for case in CASES:
            z=read(INPUT/(case+'.json'));d=reconstruct(z)
            for a,(old,x) in d['problems'].items():
                p,ctx=builder('control')(d,z,a,old.reference)
                self.assertAlmostEqual(objective(p,ctx,x),objective(old,d,x),places=6)
                base=d.get('problem_factory',make_problem);args=(d['scan'],d['node'],d['keep'],a,old.reference,d['powers'],d['means'],d['model']['multiplier'],d['model']['nu'])
                q=prior_factory(base,'control')(*args);r=base(*args)
                self.assertAlmostEqual(q.calculate(x)['negative_twice_elbo'],r.calculate(x)['negative_twice_elbo'],places=6)

    def test_no_event_conditional_adapter(self):
        from conditional_satellite_refresh import attach_conditional_satellite_refresh
        z=read(INPUT/'DS26-0251.json');d=reconstruct(z);pr=read(Path(z['gap_selected']['path'])/'protocol.json');labels=[e['candidate_index'] for e in pr['targets']]
        for a,(old,x) in d['problems'].items():
            problems=[]
            for attach in (attach_conditional_satellite_refresh,conditional_with_events):
                kw={'base_problem_factory':d['problem_factory']} if 'problem_factory' in d else {}
                p=make_event_problem(d['scan'],d['node'],d['keep'],a,old.reference,d['powers'],d['means'],d['model'],[],**kw)
                attach_event_predictive(p,d['entries'],d['powers']);attach(p,d['entries'],d['powers'],labels);problems.append(p)
            self.assertAlmostEqual(problems[0].calculate(x)['negative_twice_elbo'],problems[1].calculate(x)['negative_twice_elbo'],places=6)
            np.testing.assert_allclose(problems[0].calculate(x)['coefficient'],problems[1].calculate(x)['coefficient'])

    def test_random_blocks_with_guards(self):
        q=read(OUT/'predictive_protocol.json');self.assertEqual(q['seed'],20261102)
        f=read(PRIOR/'DS26-0070/family_diagnostic.json');times=np.concatenate([r['times_s'] for r in f['tracks']]);blocks=np.floor(times/5).astype(int)
        for split in q['splits']:
            train=np.asarray(split['train']);test=np.asarray(split['test']);self.assertFalse(np.any(train&test))
            self.assertFalse(np.any(np.isin(blocks[train],split['excluded_training_blocks'])))
            np.testing.assert_array_equal(test,np.isin(blocks,split['held_blocks']))

    def test_completed_trials_preserve_fit_evidence(self):
        for case in CASES:
            hashes=set()
            for path in (OUT/case).glob('*/*.json'):
                z=read(path)
                for r in z.get('rows',[]):
                    if r['status']!='complete':continue
                    hashes.add(r['native_fit_ids_sha256'])
                    if r['qualified']:
                        self.assertTrue(r['all_gates_pass'] and r['phase_closed'] and r['optimizer_success'])
                        self.assertFalse(r['lost_ids'] or r['unexpected_reassigned_ids'])
                        self.assertTrue(all(e['all_pass'] for e in r['exact']))
            self.assertEqual(len(hashes),1)

if __name__=='__main__':unittest.main()
