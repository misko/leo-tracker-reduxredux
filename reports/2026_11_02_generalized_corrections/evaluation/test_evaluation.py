import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
from evidence import native_inventory

spec=importlib.util.spec_from_file_location('generalized_runner',Path(__file__).with_name('run.py'))
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)


def record():
    return dict(case='T-1',dataset='T',identities=['id'],input_sha256='digest',selected=None,
                baseline={a:dict(objective=100.,associated=20) for a in runner.ARMS})


def endpoints(score=90.,qualified=True):
    return {a:dict(x=[1.,2.],reference=[0.],objective=score,rms_hz=3.,qualified=qualified,saved_arm_position_objective_at_final_reference=100.) for a in runner.ARMS}


class EvaluationTests(unittest.TestCase):
    def test_exact_fallback_on_failed_A_arm(self):
        row=record();bad=endpoints();bad['c0']=dict(status='cell_cap',qualified=False)
        result=runner.choose_A(row,bad,{a:dict(trigger=True) for a in runner.ARMS},1e-4)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['selected_output'],runner.fallback(row))

    def test_B_covariance_never_selected_by_score_gain(self):
        row=record();A=runner.selection(row,endpoints(),'A')
        result=runner.choose_B(row,endpoints(score=1000.),dict(status='ready'),A)
        self.assertTrue(result['accepted'])
        self.assertEqual(result['selected_output']['c0']['objective'],1000.)

    def test_A_compares_positions_at_common_final_reference(self):
        row=record();rows=endpoints(score=120.)
        for endpoint in rows.values():endpoint['saved_arm_position_objective_at_final_reference']=130.
        result=runner.choose_A(row,rows,{a:dict(trigger=True) for a in runner.ARMS},1e-4)
        self.assertTrue(result['accepted'])
        self.assertLess(result['objective_gains_diagnostic']['c0'],0.)
        self.assertGreater(result['common_final_reference_position_gains']['c0'],0.)

    def test_B_requires_both_arm_qualification_and_available_prior(self):
        row=record();A=runner.selection(row,endpoints(),'A')
        bad=endpoints();bad['c0']['qualified']=False
        for rows,prior in [(bad,dict(status='ready')),(endpoints(),dict(status='fallback'))]:
            result=runner.choose_B(row,rows,prior,A)
            self.assertFalse(result['accepted']);self.assertEqual(result['selected_output'],A)

    def test_deadline_preserves_completed_A_and_falls_back_B_to_A(self):
        row=record();result=runner.initial(row,'seal')
        A=runner.selection(row,endpoints(),'A')
        result['variants']['A'].update(accepted=True,status='accepted',selected_output=A)
        for label in ('A+B','A+B+C'):result['variants'][label]['selected_output']=A
        runner.terminal_fallback(result,'deadline','exhausted')
        self.assertTrue(result['variants']['A']['accepted'])
        self.assertEqual(result['variants']['A+B']['selected_output'],A)

    def test_roster_schedule_is_lexical_round_robin(self):
        rows=[dict(case='B2',dataset='B'),dict(case='A2',dataset='A'),dict(case='B1',dataset='B'),dict(case='A1',dataset='A')]
        self.assertEqual([r['case'] for r in runner.scheduled(rows)],['A1','B1','A2','B2'])

    def test_full_native_union_includes_ancillary_and_rejects_duplicate(self):
        p=SimpleNamespace(rows=[dict(candidate_norad=1)],members=[0],slices=[slice(0,2)],keep=np.array([True,False]),
                          scan=SimpleNamespace(tracks=[dict(observation_ids=['curved','unused'])]))
        d=dict(entries=[dict(observation_ids=['linear'],norad=2)],
               families=[SimpleNamespace(entries=[dict(observation_ids=['mixture'],norad=3)])])
        inventory=native_inventory(p,d)
        self.assertEqual(inventory['owners'],dict(curved=1,linear=2,mixture=3))
        d['entries'][0]['observation_ids']=['curved']
        with self.assertRaisesRegex(ValueError,'duplicated'):native_inventory(p,d)


if __name__=='__main__':unittest.main()
