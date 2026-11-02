import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
import unittest
from unittest.mock import patch
import numpy as np

spec=importlib.util.spec_from_file_location('age_prior_runner_tests',Path(__file__).with_name('run.py'))
driver=importlib.util.module_from_spec(spec);sys.modules[spec.name]=driver;spec.loader.exec_module(driver)


def record():
    return dict(case='TEST-1',dataset='TEST',identities=['recording'],input_sha256='input',previous_row_sha256='row',
        target_family=123,saved_nomination_sha256='nomination',
        baseline={arm:dict(objective=100.,associated=2) for arm in driver.ARMS},
        selected_A={arm:dict(source='exact_saved_ALGO07',objective=100.,associated=2,selected_replacement=None) for arm in driver.ARMS},
        selected_B={arm:dict(source='old_B',objective=90.,associated=2) for arm in driver.ARMS})


def endpoints():
    return {arm:dict(qualified=True,x=[1.,2.],reference=[0.],objective=200.,rms_hz=10.) for arm in driver.ARMS}


class RunnerTests(unittest.TestCase):
    def test_both_arms_and_ready_age_prior_required(self):
        r=record();rows=endpoints();rows['c0']['qualified']=False
        for fitted,receipt in [(rows,dict(status='ready',pair_count=3)),(endpoints(),dict(status='fallback',pair_count=3)),
                               ({'c0':endpoints()['c0']},dict(status='ready',pair_count=3))]:
            outcome=driver.choose(r,fitted,receipt)
            self.assertFalse(outcome['candidate_accepted']);self.assertEqual(outcome['selected_output'],r['selected_A'])

    def test_history_prior_is_not_chosen_by_in_sample_score(self):
        outcome=driver.choose(record(),endpoints(),dict(status='ready',pair_count=3))
        self.assertTrue(outcome['candidate_accepted'])
        self.assertEqual(outcome['selected_output']['c0']['objective'],200.)

    def test_primary_and_exploratory_share_one_endpoint_with_fixed_support_rules(self):
        rows=endpoints();outcome=driver.choose(record(),rows,dict(status='ready',pair_count=2))
        self.assertFalse(outcome['policies']['Age3']['accepted'])
        self.assertTrue(outcome['policies']['Age2']['accepted'])
        self.assertEqual(outcome['policies']['Age2']['selected_output']['c0']['x'],rows['c0']['x'])
        outcome=driver.choose(record(),rows,dict(status='ready',pair_count=3))
        for label in ['Age3','Age2']:self.assertEqual(outcome['policies'][label]['selected_output']['c0']['x'],rows['c0']['x'])

    def test_fallback_does_not_mutate_immutable_A_comparator(self):
        r=record();outcome=driver.choose(r,{},dict(status='fallback'))
        outcome['selected_output']['c0']['objective']=999.
        self.assertEqual(r['selected_A']['c0']['objective'],100.)

    def test_schedule_is_balanced_lexical_and_accepts_empty_queue(self):
        self.assertEqual(driver.scheduled([]),[])
        rows=[dict(case='B2',dataset='B'),dict(case='A1',dataset='A'),dict(case='B1',dataset='B')]
        self.assertEqual([r['case'] for r in driver.scheduled(rows)],['A1','B1','B2'])

    def test_unique_helper_import_reuses_existing_module_identity(self):
        again=driver.module('age_prior_frozen_numerical',driver.PREVIOUS/'solver/numerical.py')
        self.assertIs(again,driver.numerical)
        with self.assertRaisesRegex(ValueError,'collision'):
            driver.module('age_prior_frozen_numerical',driver.PREVIOUS/'evaluation/evidence.py')

    def test_baseline_native_hash_mismatch_cannot_enter_new_candidate(self):
        r=record();r['previous_baseline_replay']={arm:dict(native_ids_sha256='old',fitted_owners_sha256='owner') for arm in driver.ARMS}
        p=SimpleNamespace();d=dict(problems={arm:(p,np.zeros(2)) for arm in driver.ARMS})
        z=dict(baseline_arms={arm:dict(endpoint_east_north_km=[0.,0.]) for arm in driver.ARMS},
               baseline_owners={arm:dict(o=123) for arm in driver.ARMS})
        inventory=dict(owners=dict(o=123),native_ids_sha256='changed',fitted_owners_sha256='owner',counts=dict(curved=1))
        with patch.object(driver,'objective',return_value=100.),patch.object(driver.evidence,'native_inventory',return_value=inventory):
            with self.assertRaisesRegex(ValueError,'native input/owner parity'):
                driver.baseline_parity(d,z,r)

    def test_model_arm_uses_original_shared_RF_start_and_reference(self):
        common=(SimpleNamespace(reference=np.array([.2,.3])),np.array([2.,3.]))
        fitted=dict(reference=np.array([.2,.3]),x=np.array([1.,1.]),objective=10.)
        policy=dict(cell_seconds=120,solver=dict(max_rounds=15))
        d=dict(problems={'c0':(None,np.array([0.,0.]))})
        with (TemporaryDirectory() as temp,patch.object(driver.numerical,'fit',return_value=fitted) as fit,
                patch.object(driver.e,'build',return_value=(None,{})),patch.object(driver,'objective',return_value=10.),
                patch.object(driver.evidence,'qualify',return_value=dict(qualified=True))):
            result=driver.cell(d,{},'c0',common,policy,Path(temp))
        np.testing.assert_array_equal(fit.call_args.kwargs['start'],common[1])
        np.testing.assert_array_equal(fit.call_args.kwargs['reference'],common[0].reference)
        self.assertTrue(result['qualified'])


if __name__=='__main__':unittest.main()
