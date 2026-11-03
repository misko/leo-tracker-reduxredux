"""Owned hardware-free tests of exact transport and two-case orchestration."""
from dataclasses import dataclass
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

import control


class Model:
    def __init__(self):
        self.original=SimpleNamespace(design=np.arange(4.))
        self.band_design=np.eye(2);self.original_offsets_hz=np.array([-15.,40.])
        self.basis=np.array([[1.],[-1.]])/np.sqrt(2.)
        self.group_limits=np.array([2.,100.]);self.group_scales=np.array([.5,5.]);self.precision=np.eye(2)
        self.score=SimpleNamespace(clutter_rate=.1,detection_budget=1.6)
    def evaluate_joint(self,*args):return (3.,None,None,None)


@dataclass
class Context:
    model:object
    vector:object
    nuisance:object
    train_mask:object
    fixed_c:bool


def contexts():
    return {key:Context(Model(),np.r_[np.arange(6.),0. if key.endswith('zero-c') else 6.,7.,8.],
        np.array([.2,40.]),np.ones(2,bool),key.endswith('zero-c')) for key in control.CASES}


class ControlTests(unittest.TestCase):
    def services(self,output,*,fail_second=False,mutate=False):
        calls=[]
        def fit(ctx,v,n,**kwargs):
            self.assertEqual(kwargs,dict(max_evaluations=1000,max_seconds=120.,fixed_c=ctx.fixed_c))
            calls.append('fit')
            if fail_second and calls.count('fit')==2:raise RuntimeError('intentional mock failure')
            if mutate:ctx.model.original.design[0]+=1
            return dict(vector=v,nuisance=n,diagnostics=dict(evaluations=1000,accepted=False,stationarity=2.))
        def audit(ctx,v,n):
            ctx.model.evaluate_joint(v,n);calls.append('audit');return dict(feasible=True,accepted=False)
        def metadata():
            self.assertTrue((output/'outcomes_seal.json').exists());calls.append('metadata')
            return SimpleNamespace(window_ids=('train','held'),times_s=np.array([0.,1.]),rf_hz=np.full(2,11e9),
                receiver=np.zeros(2,int),channel=np.ones(2,int),measured_hz=np.zeros(2)),dict(train=np.array([True,False]),held=np.array([False,True]))
        def predict(ctx,v,n,meta):
            self.assertTrue((output/'outcomes_seal.json').exists());self.assertFalse((output/'predictions_seal.json').exists())
            calls.append('predict');return dict(prediction_hz=np.zeros((2,2)),visibility_weight=np.ones((2,2)),
                correction_hz=np.zeros(2),detection_probability=np.array([.6,1.]),number=np.array([11,22]))
        return SimpleNamespace(refit=fit,endpoint_status=audit,load_metadata=metadata,predict=predict),calls

    def test_matched_budgets_retains_both_nonstrict_seals_then_predicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'out';services,calls=self.services(output)
            control.execute(contexts(),output=output,services=services,verify_frozen=lambda:None,authorities={})
            self.assertEqual(calls,['fit','audit','fit','audit','metadata','predict','predict'])
            for key in control.CASES:
                row=control.read(output/f'fit_{key}.json')
                self.assertFalse(row['result']['diagnostics']['accepted'])
                self.assertFalse(row['independent_endpoint_status']['accepted'])
                self.assertEqual(row['cost']['combined_objectives'],1001)
                with np.load(output/f'predictions_{key}.npz') as p:self.assertNotIn('measured_hz',p)
            self.assertTrue(control.read(output/'predictions_seal.json')['all_two_sealed'])
            with self.assertRaises(FileExistsError):
                control.execute(contexts(),output=output,services=services,verify_frozen=lambda:None,authorities={})

    def test_second_failure_durable_without_retry_or_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'out';services,calls=self.services(output,fail_second=True)
            with self.assertRaisesRegex(RuntimeError,'intentional mock'):
                control.execute(contexts(),output=output,services=services,verify_frozen=lambda:None,authorities={})
            row=control.read(output/'failure.json')
            self.assertEqual(len(row['completed_outcomes']),1);self.assertFalse(row['automatic_retry'])
            self.assertEqual(calls,['fit','audit','fit']);self.assertFalse((output/'outcomes_seal.json').exists())

    def test_model_mutation_stops_with_raw_result_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'out';services,calls=self.services(output,mutate=True)
            with self.assertRaisesRegex(ValueError,'mutated'):
                control.execute(contexts(),output=output,services=services,verify_frozen=lambda:None,authorities={})
            self.assertTrue((output/f'raw_{control.CASES[0]}.json').exists())
            self.assertEqual(calls,['fit']);self.assertTrue((output/'failure.json').exists())

    def test_exact_seed_authorities_include_original_band_state_and_labels(self):
        old=contexts()[control.CASES[0]];old.bank=SimpleNamespace(numbers=np.array([11,22]))
        new=SimpleNamespace(model=Model());new.model.labels=np.array([0,1])
        seed=dict(vector=old.vector.tolist(),nuisance=old.nuisance.tolist(),labels=[0,1],candidate_numbers=[11,22],train_mask=[True,True])
        inventory=dict(cases={'independent_fitted-c':seed})
        preparation=dict(qualified_seeds={'independent_fitted-c':seed})
        fit=dict(original_seed=seed)
        control.exact_seed(old,new,'fitted-c',inventory,preparation,fit)
        new.model.original_offsets_hz[0]+=1
        with self.assertRaisesRegex(ValueError,'original_offsets_hz'):
            control.exact_seed(old,new,'fitted-c',inventory,preparation,fit)

    def test_source_binding_mutation_is_rejected_without_any_fit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'source';path.write_text('source')
            bindings={str(path):control.digest(path)};control.io.verify_bindings(bindings)
            path.write_text('changed')
            with self.assertRaisesRegex(ValueError,'Frozen source'):control.io.verify_bindings(bindings)

    def test_root_gate_binds_passed_qualification_inventory_source_and_runner(self):
        import json
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)
            (p/'control.py').write_text('runner')
            (p/'qualification.json').write_text(json.dumps(dict(passed=True,fits=0)))
            (p/'actual_inventory.json').write_text(json.dumps(dict(cases=list(control.CASES))))
            (p/'source_freeze.json').write_text(json.dumps(dict(files={str(p/'control.py'):control.digest(p/'control.py')})))
            gate=dict(authorized=True,cases=list(control.CASES),max_evaluations_per_fit=1000,max_seconds_per_fit=120,
                **{key:control.digest(p/file) for key,file in [('runner_sha256','control.py'),('qualification_sha256','qualification.json'),
                    ('actual_inventory_sha256','actual_inventory.json'),('source_freeze_sha256','source_freeze.json')]})
            path=p/'gate.json';path.write_text(json.dumps(gate))
            with patch.object(control,'HERE',p):
                control.validate_fit_gate(path)
                path.write_text(json.dumps(dict(gate,authorized=False)))
                with self.assertRaisesRegex(ValueError,'root two-fit'):control.validate_fit_gate(path)
                path.write_text(json.dumps(gate));(p/'actual_inventory.json').write_text('{}')
                with self.assertRaisesRegex(ValueError,'actual_inventory'):control.validate_fit_gate(path)


if __name__=='__main__':unittest.main()
