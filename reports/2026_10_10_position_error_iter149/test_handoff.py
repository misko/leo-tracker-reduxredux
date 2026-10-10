import copy
import unittest
from handoff import promote, recovery_port

class Transition(unittest.TestCase):
    def setUp(self):self.fit=dict(vector=[1.,2.,0,0,0,0,0],objective=3.,converged=True)
    def audit(self,m,fit,arm):return dict(qualified=arm=='zero-c' or fit['vector'][6]==2,stationarity=0 if arm=='zero-c' else 1)
    def repair(self,*args,**kwargs):
        self.assertEqual(kwargs['maximum_rounds'],2);self.assertEqual(kwargs['maximum_evaluations'],100)
        fit=copy.deepcopy(self.fit);fit['vector'][6]=2
        return dict(qualified=True,fit=fit)
    def test_zero_qualified_free_failed_successful_repair(self):
        r=promote(None,self.fit,[1,2],'zero-c',audit=self.audit,qualify=self.repair)
        self.assertTrue(r['discovery_audit']['qualified']);self.assertFalse(r['fitted_audit']['qualified']);self.assertEqual(r['promoted']['vector'][6],2);self.assertEqual(self.fit['vector'][6],0)
    def test_failed_repair_no_handoff(self):
        r=promote(None,self.fit,[1,2],'zero-c',audit=self.audit,qualify=lambda *a,**k:dict(qualified=False))
        self.assertIsNone(r['promoted'])
    def test_native_already_free_qualified_no_repair(self):
        fit=copy.deepcopy(self.fit);fit['vector'][6]=2
        r=promote(None,fit,[1,2],'fitted-c',audit=self.audit,qualify=lambda *a,**k:self.fail('unexpected repair'))
        self.assertEqual(r['status'],'qualified')
    def test_rf_lock_and_fixed_position(self):
        fit=copy.deepcopy(self.fit);fit['vector'][6]=1
        with self.assertRaises(ValueError):promote(None,fit,[1,2],'zero-c',audit=self.audit,qualify=self.repair)
        with self.assertRaises(ValueError):promote(None,self.fit,[9,2],'zero-c',audit=self.audit,qualify=self.repair)
    def test_original_unqualified_does_not_repair(self):
        r=promote(None,self.fit,[1,2],'zero-c',audit=lambda *a:dict(qualified=False),qualify=lambda *a,**k:self.fail('unexpected repair'))
        self.assertEqual(r['status'],'discovery-unqualified')
        self.assertIsNone(r['promoted'])
    def test_repaired_final_audit_can_fail(self):
        r=promote(None,self.fit,[1,2],'zero-c',audit=lambda m,f,a:dict(qualified=a=='zero-c'),qualify=self.repair)
        self.assertEqual(r['status'],'promotion-unqualified')
        self.assertIsNone(r['promoted'])
    def test_moved_repair_rejected(self):
        def moved(*a,**k):
            fit=copy.deepcopy(self.fit);fit['vector'][0]=9
            return dict(qualified=True,fit=fit)
        with self.assertRaises(ValueError):promote(None,self.fit,[1,2],'zero-c',audit=self.audit,qualify=moved)
    def test_recovery_environment_isolation_and_receipts(self):
        import types
        import numpy as np
        fit=copy.deepcopy(self.fit)
        class Problem:
            def __init__(self,model,vector,**options):self.arm=options['rf_arm']
            def stationarity(self,vector,gradient):return 0 if self.arm=='zero-c' or vector[6]==2 else 1
            def feasible(self,vector):return True
        class Model:
            def evaluate(self,v):return 3.,np.zeros(len(v)),None
        direct=types.SimpleNamespace(continuation=types.SimpleNamespace(_Problem=Problem),qualification=types.SimpleNamespace(qualify=self.repair),validated_postfit=lambda m,f,p:f,fresh_calibration=lambda *a:dict(calibration={'fresh':True}))
        old=lambda *a:'original'
        environment=dict(direct=direct,np=np,core=types.SimpleNamespace(json_value=lambda x:x),verify_coarse=lambda *a:(Model(),fit),recover_calibration=old)
        exec('def recovered_region(observations,bank,prior,trigger,stage):\n    return recover_calibration(observations,bank,prior,trigger)',environment)
        original=environment['recovered_region']
        port=recovery_port({'recovered_region':original},'zero-c')
        trigger=dict(key='point:1:2',original={'bootstrap':{'satellite_indices':[0,1]}})
        result=port(None,None,None,trigger,None)
        self.assertIs(original.__globals__['recover_calibration'],old)
        self.assertEqual(result['handoff']['original'],fit)
        self.assertTrue(result['handoff']['legacy_gate_rejected_original'])
        self.assertEqual(result['direct_prefit']['vector'][6],2)
        def failed(*args):raise AssertionError('postfit validation failed')
        direct.validated_postfit=failed
        failed_result=port(None,None,None,trigger,None)
        self.assertIsNone(failed_result['calibration'])
        self.assertEqual(failed_result['status'],'promoted-calibration-failed')
        self.assertTrue(failed_result['handoff']['legacy_gate_rejected_original'])
        self.assertIn('postfit validation failed',failed_result['error'])
    def test_report_terminal_gate(self):
        import report,tempfile
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(ValueError):report.build({},path,'notbound')
    def test_wrapper_source_and_default_output(self):
        import importlib.util
        from pathlib import Path
        folder=Path(__file__).resolve().parent
        def load(name,path):
            spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
        wrapper=load('run149_test',folder/'run.py')
        previous=load('run148_test',wrapper.PREVIOUS/'run.py')
        source=wrapper.recovery_source(previous.transformed_source((previous.PARENT/'run.py').read_text()))
        namespace=dict(__name__='synthetic149',__file__=str(previous.PARENT/'run.py'),EXPERIMENT_HERE=folder,continue_branch=lambda *a:None,RECOVERY_PORT=lambda *a:None)
        exec(compile(source,'synthetic149','exec'),namespace)
        self.assertEqual(namespace['HERE'],folder)
        self.assertIn('default=HERE / "results"',source)
        self.assertIn('RECOVERY_PORT(backend',source)
        with self.assertRaises(ValueError):wrapper.recovery_source('unsupported')

if __name__=='__main__':unittest.main()
