import unittest
from ports import admit,adapter

class Admission(unittest.TestCase):
    def setUp(self):
        self.seed=dict(satellite_indices=[0,1],vector=[1,2,0,0,0,0,9,0,0])
        self.fit=dict(vector=[1,2,0,0,0,0,0,0,0],objective=3.,converged=False)
    def test_zero_lock_and_qualification_preserved(self):
        value=admit([1,2],self.seed,self.fit,2,'zero-c',3)
        self.assertFalse(value['fits']['V16']['fit']['converged'])
        self.assertEqual(value['bootstrap']['vector'][6],9)
    def test_bad_lock_score_or_position_rejected(self):
        for change in ('lock','score','position'):
            fit=dict(self.fit);fit['vector']=list(self.fit['vector'])
            if change=='lock':fit['vector'][6]=1
            if change=='position':fit['vector'][0]=3
            with self.assertRaises(ValueError):admit([1,2],self.seed,fit,2,'zero-c',4 if change=='score' else 3)
    def test_all_three_regions_and_failures_preserved(self):
        def recover(*args):return dict(failed=True)
        def joint(*args):return {},[],['all failed']
        case=dict(observations=None,bank=None,prior=None)
        value=adapter().continue_branch(case,[dict(key=str(i)) for i in range(3)],None,recover=recover,joint=joint)
        self.assertEqual(len(value['regions']),3);self.assertEqual(value['reasons'],['all failed'])
    def test_import_runner_inert(self):
        import run
        self.assertTrue(callable(run.main))
    def test_wrapper_compiles_without_numerical_imports(self):
        import run
        from ports import PARENT,HERE
        transformed=run.transformed_source((PARENT/'run.py').read_text())
        namespace=dict(__name__='synthetic148',__file__=str(PARENT/'run.py'),EXPERIMENT_HERE=HERE,continue_branch=adapter().continue_branch)
        exec(compile(transformed,'synthetic123','exec'),namespace)
        self.assertEqual(namespace['HERE'],HERE)
        self.assertTrue(callable(namespace['main']))
        with self.assertRaises(ValueError):run.transformed_source('wrong source')
    def test_preflight_rejects_hash_mismatch(self):
        import run
        with self.assertRaises(ValueError):run.preflight(dict(source_sha256={'reports/2026_10_10_position_error_iter148/run.py':'bad'},input_sha256={}))
    def test_reporting_refuses_unsealed_and_keeps_failures(self):
        import tempfile
        from report import sealed_receipts,coverage
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(ValueError):sealed_receipts(path)
        raw={'native':dict(status='failed',reason='stagefailed',attempts=[{'converged':False}])}
        self.assertEqual(coverage(raw)['native']['attempts'],[{'converged':False}])
    def test_build_does_not_open_evaluation_before_seal(self):
        import tempfile
        from report import build
        called=[]
        with tempfile.TemporaryDirectory() as path:
            with self.assertRaises(ValueError):build({},path,'digest',evaluation_factory=lambda *a:called.append(True))
        self.assertEqual(called,[])
    def test_tampered_source_rejected_before_evaluation(self):
        import tempfile,json
        from pathlib import Path
        from report import build
        called=[]
        with tempfile.TemporaryDirectory() as folder:
            for branch in ('native','zero'):
                path=Path(folder)/branch;path.mkdir();(path/'result.json').write_text(json.dumps(dict(status='failed',protocol_sha256='d',branch=branch,fallback_available=False)))
            plan=dict(source_sha256={'reports/2026_10_10_position_error_iter148/run.py':'bad'},input_sha256={},evaluation_source_sha256={})
            with self.assertRaises(ValueError):build(plan,folder,'d',evaluation_factory=lambda *a:called.append(True))
        self.assertEqual(called,[])
    def test_partial_coverage_does_not_invent_attempts(self):
        import tempfile,json
        from pathlib import Path
        from report import stage_coverage,coverage
        records={b:dict(status='budget-exhausted') for b in ('native','zero')}
        plan=dict(branches={b:[dict(point=[i,0]) for i in range(3)] for b in records})
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'zero'/'stages';path.mkdir(parents=True)
            (path/'one.json').write_text(json.dumps(dict(protocol_sha256='d',key='stage',value=dict(result=None,reason='failed'))))
            result=stage_coverage(plan,folder,'d',records)
        self.assertEqual(len(result['zero']['expected_regions']),3)
        self.assertEqual(result['zero']['stage_receipts'][0]['status'],'failed')
        self.assertIsNone(coverage(records)['zero']['attempts'])
    def test_clock_and_nonfinite_mismatch(self):
        from report import finite_equal
        self.assertFalse(finite_equal({'clock':[1.]},{'clock':[2.]},1e-6))
        self.assertFalse(finite_equal([float('nan')],[float('nan')],1e-6))
        self.assertTrue(finite_equal({'state':[[1.,2.]]},{'state':[[1.,2.]]},1e-6))

if __name__=='__main__':unittest.main()
