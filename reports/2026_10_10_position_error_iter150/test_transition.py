import copy
import unittest
from transition import transition, recovery_port

class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.original = dict(vector=[1,2,0,0,0,0,0],objective=3.,converged=True)
    def audit(self,model,fit,arm):
        return dict(qualified=arm=='zero-c' or fit['vector'][6]==2,feasible=True)
    def bounded(self,model,vector,**options):
        self.assertEqual(vector,self.original['vector'])
        self.assertEqual(options,dict(rf_arm='fitted-c',fixed_position=True,slope_half_width_hz_s=60,maximum_seconds=5,maximum_iterations=200))
        fit=copy.deepcopy(self.original);fit['vector'][6]=2;fit['objective']=2.
        return fit,dict(evaluations=10)
    def test_original_state_success_no_polish(self):
        r=transition(None,self.original,[1,2],'zero-c',audit=self.audit,bounded=self.bounded,qualify=lambda *a,**k:self.fail('polish unexpected'))
        self.assertEqual(r['promoted']['vector'][6],2)
        self.assertEqual(self.original['vector'][6],0)
    def test_unsuccessful_nonlinear_then_polish(self):
        r=transition(None,self.original,[1,2],'zero-c',audit=self.audit,bounded=lambda *a,**k:(copy.deepcopy(self.original),{}),qualify=lambda *a,**k:dict(qualified=False))
        self.assertEqual(r['status'],'promotion-unqualified')
        self.assertIsNotNone(r['nonlinear']);self.assertIsNotNone(r['polish'])
    def test_native_gate_skips_nonlinear(self):
        fit=copy.deepcopy(self.original);fit['vector'][6]=2
        r=transition(None,fit,[1,2],'fitted-c',audit=self.audit,bounded=lambda *a,**k:self.fail('unexpected fit'),qualify=None)
        self.assertEqual(r['status'],'qualified')
    def test_failed_promotion_keeps_original_audits(self):
        def failed(*a,**k):raise TimeoutError('bounded failure')
        r=transition(None,self.original,[1,2],'zero-c',audit=self.audit,bounded=failed,qualify=None)
        self.assertEqual(r['status'],'nonlinear-promotion-failed')
        self.assertTrue(r['discovery_audit']['qualified'])
        self.assertEqual(r['original'],self.original)
    def test_moved_point_rejected(self):
        def moved(*a,**k):
            fit=copy.deepcopy(self.original);fit['vector'][0]=9
            return fit,{}
        r=transition(None,self.original,[1,2],'zero-c',audit=self.audit,bounded=moved,qualify=None)
        self.assertEqual(r['status'],'nonlinear-promotion-failed')
    def test_available_solver_state_retained_when_audit_raises(self):
        def audit(m,f,a):
            if f['vector'][6]==2:raise ValueError('audit failed')
            return self.audit(m,f,a)
        r=transition(None,self.original,[1,2],'zero-c',audit=audit,bounded=self.bounded,qualify=None)
        self.assertEqual(r['nonlinear']['fit']['vector'][6],2)
        self.assertEqual(r['nonlinear']['solver']['evaluations'],10)
        self.assertIn('audit failed',r['nonlinear']['error'])
    def test_unqualified_original_does_not_fit(self):
        r=transition(None,self.original,[1,2],'zero-c',audit=lambda *a:dict(qualified=False),bounded=lambda *a,**k:self.fail('unexpected'),qualify=None)
        self.assertEqual(r['status'],'discovery-unqualified')
    def test_increased_score_and_infeasible_fit(self):
        for invalid in ('score','feasible'):
            def bounded(*a,**k):
                fit=copy.deepcopy(self.original);fit['vector'][6]=2;fit['objective']=4 if invalid=='score' else 2
                return fit,{}
            def audit(m,f,a):return dict(qualified=a=='zero-c' or f['vector'][6]==2,feasible=not (invalid=='feasible' and f['vector'][6]==2))
            r=transition(None,self.original,[1,2],'zero-c',audit=audit,bounded=bounded,qualify=None)
            self.assertEqual(r['status'],'nonlinear-promotion-invalid')
    def test_polish_moved_position_rejected(self):
        def polish(*a,**k):
            fit=copy.deepcopy(self.original);fit['vector'][0]=9
            return dict(qualified=True,fit=fit)
        with self.assertRaises(ValueError):transition(None,self.original,[1,2],'zero-c',audit=self.audit,bounded=lambda *a,**k:(copy.deepcopy(self.original),{}),qualify=polish)
    def test_bound_mutation_cannot_change_original(self):
        def bounded(m,v,**k):
            v[6]=2
            return dict(self.original,vector=v,objective=2),{}
        r=transition(None,self.original,[1,2],'zero-c',audit=self.audit,bounded=bounded,qualify=None)
        self.assertEqual(r['original']['vector'][6],0)
        self.assertEqual(self.original['vector'][6],0)
    def test_none_bounded_state_is_explicit_failure(self):
        r=transition(None,self.original,[1,2],'zero-c',audit=self.audit,bounded=lambda *a,**k:(None,{'evaluations':4}),qualify=None)
        self.assertEqual(r['status'],'nonlinear-promotion-failed')
        self.assertEqual(r['nonlinear']['solver']['evaluations'],4)
    def test_report_gate_and_fresh_wrapper_directory(self):
        import tempfile,importlib.util
        from pathlib import Path
        folder=Path(__file__).resolve().parent
        spec=importlib.util.spec_from_file_location('report150_test',folder/'report.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(ValueError):module.build({},path,'unsealed')
        source=(folder/'run.py').read_text()
        self.assertIn('EXPERIMENT_HERE=HERE',source)
        self.assertIn('HERE = Path(__file__).resolve().parent',source)
    def test_recovery_port_preserves_identity_and_solver_receipts(self):
        import numpy as np
        import types
        class Problem:
            def __init__(self,m,v,**options):self.arm=options['rf_arm']
            def stationarity(self,v,g):return 0 if self.arm=='zero-c' or v[6]==2 else 1
            def feasible(self,v):return True
        class Model:
            def evaluate(self,v):return (2. if v[6]==2 else 3.),np.zeros(len(v)),None
        def fit(model,vector,**options):return self.bounded(model,vector.tolist(),**options)
        direct=types.SimpleNamespace(continuation=types.SimpleNamespace(_Problem=Problem,fit_bounded_position=fit),qualification=types.SimpleNamespace(qualify=lambda *a,**k:self.fail('unexpectedpolish')),validated_postfit=lambda m,f,p:f,fresh_calibration=lambda *a:dict(calibration={'fresh':True}))
        old=lambda *a:'old'
        environment=dict(direct=direct,np=np,core=types.SimpleNamespace(json_value=lambda x:x),verify_coarse=lambda *a:(Model(),self.original),recover_calibration=old)
        exec('def recovered_region(o,b,p,t,s):\n return recover_calibration(o,b,p,t)',environment)
        original=environment['recovered_region'];port=recovery_port({'recovered_region':original},'zero-c')
        trigger=dict(key='point:1:2',identity={'unchanged':True},original={'bootstrap':{'satellite_indices':[0,1]}})
        before=copy.deepcopy(trigger);receipt=port(None,None,None,trigger,None)
        self.assertEqual(trigger,before);self.assertIs(original.__globals__['recover_calibration'],old)
        self.assertEqual(receipt['handoff']['nonlinear']['solver']['evaluations'],10)
        self.assertEqual(receipt['handoff']['original'],self.original)

if __name__=='__main__':unittest.main()
