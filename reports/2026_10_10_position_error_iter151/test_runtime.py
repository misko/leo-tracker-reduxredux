"""Synthetic execution of real transformed hierarchy; no recording models."""
import tempfile
import unittest
from types import SimpleNamespace
from ports import dependencies,search_slice,continue_slice

class RuntimeTests(unittest.TestCase):
    def test_actual_search_keeps_arm_keys_and_resume(self):
        _,driver,_=dependencies();original=driver.case_identity
        driver.case_identity=lambda case:{'synthetic':True}
        calls=[];seeds=[]
        case=dict(observations=None,bank=None,prior=SimpleNamespace(radius_km=240.),tracks=None)
        class Evaluator:
            def __init__(self,*a):self.seeds={}
            def bootstrap(self,o,b,p,point,t,**k):
                seeds.append(tuple(point));return driver.PositionBootstrap((0,1),driver.np.array([*point,*([0.]*7)]),())
            def __call__(self,e,n,arm):
                calls.append((e,n,arm))
                return dict(fit=dict(converged=True),scores={'native':{'objective':(e-(80 if arm=='zero-c' else 0))**2+n*n}})
        try:
            with tempfile.TemporaryDirectory() as folder:
                plan={};member=dict(label='synthetic',binding={})
                result=search_slice(plan,member,folder,lambda b:case,driver,evaluator_factory=Evaluator)
                self.assertEqual(result['status'],'complete')
                self.assertEqual(set(result['searches']),{'native','zero'})
                self.assertEqual(sum(a=='fitted-c' for _,_,a in calls),400)
                self.assertEqual(sum(a=='zero-c' for _,_,a in calls),400)
                self.assertEqual(len(calls),len(set(calls)))
                self.assertEqual(len(seeds),len(set(seeds)))
                before=len(calls)
                replay=search_slice(plan,member,folder,lambda b:case,driver,evaluator_factory=Evaluator)
                self.assertEqual(replay,result);self.assertEqual(len(calls),before)
        finally:driver.case_identity=original
    def test_actual_zero_continuation_own_seed_and_transition_port(self):
        from pathlib import Path
        _,driver,adapter=dependencies();original=driver.case_identity;driver.case_identity=lambda c:{'same':True}
        calls=[];injected=[];plan={};member=dict(label='synthetic',binding={});digest=driver.canonical_digest(plan)
        class Expired(Exception):pass
        def claim(folder,phase,bound,**options):
            self.assertEqual(phase,'candidate');self.assertEqual(options['maximum'],2);return 1
        def recover(o,b,p,trigger,stage):
            calls.append(trigger);return dict(finals=[],recovery=stage(trigger['key'],90,lambda:dict(calibration=None,status='synthetic-failure')))
        def factory(backend,arm):injected.append(arm);return recover
        namespace={};exec('def load_case(document): return None',namespace)
        namespace.update(core=SimpleNamespace(HARD60_SCORE={},RegionalSliceExpired=Expired),claim_slice=claim,recovered_region=lambda *a:self.fail('uninjected'),run_joint_stages=lambda o,b,p,r,s:({}, {}, ['all failed']))
        case=dict(observations=None,prior={},bank=SimpleNamespace(numbers=driver.np.array([1,2])),identity={'input_manifest_sha256':'input'})
        class Loader:
            load_case=namespace['load_case']
            def __call__(self,binding):return case
        try:
            with tempfile.TemporaryDirectory() as folder:
                search=Path(folder)/'search';regions=[dict(east_km=float(i),north_km=0.) for i in range(3)]
                driver.append(search/'result.json',dict(protocol_sha256=digest,label='synthetic',status='complete',searches={'zero':dict(regions=regions)}))
                driver.append(search/'case.json',dict(protocol_sha256=digest,identity={'same':True}))
                for i in range(3):
                    point=[float(i),0.];v=[*point,*([0.]*7)]
                    for key,value in [(['bootstrap',point],dict(satellite_indices=[0,1],vector=v)),(['point',*point,'zero-c'],dict(fit=dict(vector=v,objective=1.,converged=True)))]:
                        driver.append(search/'points'/(driver.canonical_digest(key)[7:]+'.json'),dict(protocol_sha256=digest,key=key,status='complete',value=value))
                result=continue_slice(plan,member,'zero',Path(folder)/'zero',search,Loader(),driver,adapter,recovery_factory=factory)
                self.assertEqual(result['status'],'complete');self.assertEqual(injected,['zero-c']);self.assertEqual(len(calls),3)
                self.assertTrue(all(t['identity']['local_radius_km']==25 for t in calls))
                self.assertEqual(result['reasons'],['all failed'])
        finally:driver.case_identity=original

if __name__=='__main__':unittest.main()
