"""No fits, hardware, corpus or production imports: runner sequencing tests."""
from dataclasses import dataclass,replace
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

import inference as runner


class ToyModel:
    def __init__(self,labels):
        self.labels=np.array(labels);self.design=np.arange(6.).reshape(3,2)
        self.score=SimpleNamespace(clutter_rate=.15,detection_budget=1.6)
    def evaluate_joint(self,*args):return (3.,None,None,None)


class PublicLikeProxy:
    def __init__(self,base):self.base=base
    def __getattr__(self,name):return getattr(self.base,name)


@dataclass
class ToyContext:
    model:object
    vector:object
    nuisance:object
    observations:object
    bank:object
    train_mask:object
    fixed_c:bool


def contexts():
    obs=SimpleNamespace(window_ids=('a','b','c'),times_s=np.arange(3.),measured_hz=np.arange(3.),
        rf_hz=np.full(3,11e9),receiver=np.zeros(3,int),channel=np.ones(3,int),margin=np.ones(3))
    bank=SimpleNamespace(numbers=np.array([11,22]),nodes_s=np.array([-30.,330.]),
        position_km=np.zeros((2,2,3)),velocity_km_s=np.zeros((2,2,3)))
    return {key:ToyContext(ToyModel([0,1,2] if key.startswith('independent') else [0,0,1]),
        np.arange(10.)*(np.arange(10)!=6) if key.endswith('zero-c') else np.arange(10.),
        np.array([1.,2.]),obs,bank,np.ones(3,bool),key.endswith('zero-c')) for key in runner.CASES}


class InferenceTests(unittest.TestCase):
    def services(self,output,*,fail_at=None,mutate=False,excess=False):
        calls=[]
        def refit(ctx,v,n,**kwargs):
            calls.append(('fit',kwargs,ctx))
            self.assertEqual(kwargs,dict(max_evaluations=1000,max_seconds=120.,fixed_c=ctx.fixed_c))
            if fail_at==len([a for a in calls if a[0]=='fit']):raise RuntimeError('mock optimizer failure')
            if mutate:ctx.model.design[0,0]+=1
            # Deliberately nonstationary: all four must still be persisted.
            return dict(vector=v+.01,nuisance=n+.01,diagnostics=dict(evaluations=1001 if excess else 1000,
                accepted=False,stationarity=3.,objective=2.,reason='evaluation-or-wall-budget'))
        def audit(ctx,v,n):
            calls.append(('audit',))
            ctx.model.evaluate_joint(v,n)
            return dict(feasible=True,accepted=False,stationarity=3.)
        def metadata():
            self.assertTrue((output/'outcomes_seal.json').exists())
            seal=runner.read(output/'outcomes_seal.json');self.assertEqual(len(seal['outcomes']),4)
            self.assertFalse((output/'predictions_seal.json').exists())
            calls.append(('metadata',))
            return SimpleNamespace(window_ids=('a','b','c','held'),times_s=np.arange(4.),
                measured_hz=np.zeros(4),rf_hz=np.full(4,11e9),receiver=np.zeros(4,int),channel=np.ones(4,int)),
        def load_metadata():
            obj=metadata()[0]
            return obj,dict(train=np.array([True,True,True,False]),held=np.array([False,False,False,True]),boundary=np.zeros(4,bool))
        def predict(ctx,v,n,metadata):
            self.assertTrue((output/'outcomes_seal.json').exists())
            self.assertFalse((output/'predictions_seal.json').exists())
            self.assertTrue(np.all(metadata.measured_hz==0));calls.append(('predict',))
            return dict(prediction_hz=np.zeros((4,2)),visibility_weight=np.ones((4,2)),
                correction_hz=np.zeros(4),detection_probability=np.array([.6,1.]),number=np.array([11,22]))
        return SimpleNamespace(refit=refit,endpoint_status=audit,load_metadata=load_metadata,predict=predict),calls

    def run_fake(self,output,**kwargs):
        services,calls=self.services(output,**kwargs)
        runner.execute(contexts(),output=output,services=services,verify_frozen=lambda:None,
            authorities=dict(root_gate_sha256='testgate',qualification_sha256='testqual',runner_source_freeze_sha256='testfreeze'),
            preparation=dict(public_training_context_loads=1))
        return calls

    def test_all_four_nonstationary_outcomes_retained_then_predictions_sealed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'results';calls=self.run_fake(output)
            self.assertEqual([a[0] for a in calls],['fit','audit']*4+['metadata']+['predict']*4)
            for key in runner.CASES:
                row=runner.read(output/f'fit_{key}.json')
                self.assertFalse(row['result']['diagnostics']['accepted'])
                self.assertFalse(row['independent_endpoint_status']['accepted'])
                self.assertEqual(row['cost']['combined_objective_calls'],1001)
                with np.load(output/f'predictions_{key}.npz') as p:
                    self.assertNotIn('measured_hz',p)
                    self.assertEqual(p['held_mask'].sum(),1)
            seal=runner.read(output/'predictions_seal.json')
            self.assertTrue(seal['all_four_sealed']);self.assertFalse(seal['held_CFO_scored'])
            for row in seal['predictions']:self.assertEqual(runner.digest(row['path']),row['sha256'])
            self.assertEqual(runner.read(output/'outcomes_seal.json')['original_shared_score'],
                dict(clutter_rate=.15,detection_budget=1.6))
            # A completed namespace cannot accidentally rerun or overwrite.
            with self.assertRaises(FileExistsError):self.run_fake(output)

    def test_fit_exception_is_durable_stops_without_retry_or_prediction(self):
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'results';services,calls=self.services(output,fail_at=2)
            with self.assertRaisesRegex(RuntimeError,'mock optimizer'):
                runner.execute(contexts(),output=output,services=services,verify_frozen=lambda:None,authorities={},preparation={})
            failure=runner.read(output/'failure.json')
            self.assertEqual(failure['phase'],'fit');self.assertFalse(failure['automatic_retry'])
            self.assertEqual(len(failure['completed_outcomes']),1)
            self.assertEqual(sum(a[0]=='fit' for a in calls),2)
            self.assertFalse(any(a[0]=='metadata' for a in calls))
            self.assertFalse((output/'outcomes_seal.json').exists())

    def test_context_mutation_or_excess_calls_durably_stop_and_preserve_raw_result(self):
        for kwargs,reason in [(dict(mutate=True),'mutated'),(dict(excess=True),'budget')]:
            with tempfile.TemporaryDirectory() as tmp:
                output=Path(tmp)/'results'
                with self.assertRaisesRegex(ValueError,reason):self.run_fake(output,**kwargs)
                self.assertTrue((output/f'raw_{runner.CASES[0]}.json').exists())
                self.assertTrue((output/'failure.json').exists())
                self.assertFalse((output/'outcomes_seal.json').exists())

    def test_complete_fingerprint_tracks_source_model_data_and_fresh_copy(self):
        import copy
        ctx=contexts()[runner.CASES[0]];before=runner.fingerprint(ctx)
        self.assertEqual(before,runner.fingerprint(copy.deepcopy(ctx)))
        self.assertEqual(before,runner.fingerprint(ctx))
        for path in [('model','design'),('observations','measured_hz'),('bank','position_km')]:
            changed=copy.deepcopy(ctx);getattr(getattr(changed,path[0]),path[1]).flat[0]+=1.
            self.assertNotEqual(before,runner.fingerprint(changed))

    def test_fresh_parameters_share_immutable_public_proxy_without_deepcopy(self):
        import copy
        ctx=contexts()[runner.CASES[0]];ctx=replace(ctx,model=PublicLikeProxy(ctx.model))
        with self.assertRaises(RecursionError):copy.deepcopy(ctx.model)
        before=runner.fingerprint(ctx);fresh=runner.fresh_context(ctx)
        self.assertIs(fresh.model,ctx.model);self.assertIs(fresh.bank,ctx.bank)
        self.assertIs(fresh.observations,ctx.observations)
        fresh.vector[0]+=10;fresh.nuisance[0]+=20;fresh.train_mask[0]=False
        self.assertEqual(runner.fingerprint(ctx),before)
        self.assertNotEqual(runner.fingerprint(fresh),before)

    def test_inventory_exactness_includes_labels_seed_mask_bank_and_c0(self):
        ctx=contexts();inventory=dict(cases={key:dict(vector=value.vector.tolist(),nuisance=value.nuisance.tolist(),
            labels=value.model.labels.tolist()) for key,value in ctx.items()})
        runner.check_inventory(ctx,inventory)
        inventory['cases'][runner.CASES[1]]['labels'][0]=999
        with self.assertRaises(AssertionError):runner.check_inventory(ctx,inventory)

    def test_gate_requires_authorization_exact_qualification_and_runner_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp);source=p/'source.py';source.write_text('frozen source\n')
            def write(name,value):
                (p/name).write_text(json.dumps(value))
            write('source_freeze.json',dict(source_sha256={str(source):runner.digest(source)}))
            write('actual_inventory.json',dict(cases={key:{} for key in runner.CASES}))
            write('qualification.json',dict(passed=True,fits=0,held_CFO_scored=False,cases=[dict(case=k) for k in runner.CASES]))
            (p/'inference.py').write_text('runner source\n')
            gate=dict(authorized=True,cases=list(runner.CASES),max_evaluations_per_fit=1000,max_seconds_per_fit=120,
                qualification_path=str(p/'qualification.json'),qualification_sha256=runner.digest(p/'qualification.json'),
                source_freeze_sha256=runner.digest(p/'source_freeze.json'),actual_inventory_sha256=runner.digest(p/'actual_inventory.json'),
                runner_sha256=runner.digest(p/'inference.py'))
            write('gate.json',gate);runner.validate_gate(p/'gate.json',directory=p)
            write('gate.json',dict(gate,authorized=False))
            with self.assertRaisesRegex(ValueError,'authorization'):runner.validate_gate(p/'gate.json',directory=p)
            write('gate.json',gate);source.write_text('changed source\n')
            with self.assertRaisesRegex(ValueError,'Frozen source'):runner.validate_gate(p/'gate.json',directory=p)


if __name__=='__main__':unittest.main()
