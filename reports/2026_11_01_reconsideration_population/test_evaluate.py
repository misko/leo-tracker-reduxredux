"""Tests of policy isolation, causal history and actual ALGO06 replay."""
import unittest
import numpy as np
import evaluate as e


class EvaluationTests(unittest.TestCase):
    def test_history_requires_actual_earlier_available_element(self):
        receipt={'sources':{'1':{'epoch_utc_ns':10_000_000_000,'collected_utc_ns':12_000_000_000}}}
        self.assertTrue(e.eligible_previous(1,11_000_000_000,receipt,{1},13_000_000_000))
        self.assertFalse(e.eligible_previous(1,10_500_000_000,receipt,{1},13_000_000_000))
        self.assertFalse(e.eligible_previous(1,11_000_000_000,receipt,{1},11_000_000_000))
        self.assertFalse(e.eligible_previous(1,11_000_000_000,receipt,set(),13_000_000_000))

    def test_selection_ignores_position_error(self):
        baseline={a:{'associated':10} for a in e.ARMS}
        def candidate(name,gain,error):
            return dict(name=name,gains=dict.fromkeys(e.ARMS,gain),accepted=True,
                pair={a:dict(x=[0,0],error_m=error,objective=1.,rms_hz=2.) for a in e.ARMS})
        rows=[candidate('good_RF',10,99999),candidate('good_GPS',1,0)]
        self.assertEqual(e.choose(rows,baseline)['selected'],'good_RF')
        rows[0]['accepted']=False
        self.assertEqual(e.choose(rows,baseline)['selected'],'good_GPS')

    def test_exact_fallback_and_paired_qualification(self):
        baseline={'c0':{'x':[1,2]},'fitted_c':{'x':[3,4]}}
        self.assertIs(e.choose([],baseline)['final'],baseline)
        rows=[dict(arm='c0',qualified=False,objective=-100),dict(arm='c0',qualified=True,objective=5),
              dict(arm='c0',qualified=True,objective=3),dict(arm='fitted_c',qualified=False,objective=-100)]
        result=e.paired(rows)
        self.assertEqual(result['c0']['objective'],3);self.assertIsNone(result['fitted_c'])

    def test_algo06_recovery_not_lost_in_baseline(self):
        d,z,r=e.load_case('DS28-0002')
        self.assertEqual(len(z['baseline_owners']['c0']),3050)
        self.assertEqual(r['algo06']['c0']['added_points'],28)
        for a in e.ARMS:
            self.assertLess(abs(r['algo06'][a]['objective_difference']),1e-4)
            self.assertLess(abs(r['rebuilt'][a]),1e-4)

    def test_gradient_only_trigger_matches_original(self):
        d,z,_=e.load_case('DS26-0034')
        before,targets=e.rec.rank_families(d,z)
        after,new_targets=e.rank_families(d,z)
        self.assertEqual(targets,new_targets)
        self.assertEqual([r['norad'] for r in before],[r['norad'] for r in after])
        np.testing.assert_array_equal([r['rank_score'] for r in before],[r['rank_score'] for r in after])

    def test_saved_accepted_outputs_preserve_evidence_and_gates(self):
        paths=list(e.OUT.glob('DS*/result.json'))
        self.assertGreater(len(paths),0,'Requires this study local numerical outputs')
        for path in paths:
            result=e.read(path)
            for method,item in result['methods'].items():
                for a in e.ARMS:self.assertEqual(item['final'][a]['associated'],result['baseline'][a]['associated'])
                if item['selected'] is None:
                    self.assertEqual(item['final'],result['baseline']);continue
                candidates=result['history_records'] if item['selected']=='complete_history' else result['records'][method]
                chosen=next(r for r in candidates if r['name']==item['selected'])
                self.assertTrue(chosen['accepted']);self.assertTrue(all(v>0 for v in chosen['gains'].values()))
                for a,r in chosen['pair'].items():
                    self.assertTrue(r['qualified'] and r['all_gates_pass'] and r['phase_closed'] and r['optimizer_success'] and r['mixture_phase_interior'])
                    self.assertFalse(r['lost_ids']);self.assertFalse(r['unexpected_reassigned_ids'])
                    if 'control' in chosen:self.assertEqual(r['native_ids_sha256'],chosen['control'][a]['native_ids_sha256'])

    def test_actual_history_exports_are_causal_and_distinct(self):
        paths=list(e.OUT.glob('DS*/**/export.json'));self.assertGreater(len(paths),0)
        for path in paths:
            r=e.read(path);cutoff=r['request']['cutoff']
            for n,old in r['export']['chosen'].items():
                self.assertLessEqual(old['collected_utc_ns'],cutoff)
                self.assertGreaterEqual(old['collected_utc_ns'],cutoff-int(72*3.6e12))
                self.assertGreaterEqual(r['request']['latest'][n]-old['epoch_utc_ns'],1_000_000_000)


if __name__=='__main__':unittest.main()
