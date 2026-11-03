"""Requires the pinned scientific runtime (SciPy); no radio/storage access."""
import numpy as np
from types import SimpleNamespace
import accelerate_four_scan_profile as module


def test_warm_start_preserves_site_probability_and_original_verifier():
    class Objective:
        def __init__(self,*args):
            self.initial=np.array([0.,0.,-10.,0.]);self.size=3
            self.scale=np.array([1.,1.,10.,10.]);self.bounds=[(None,None)]*4
            self.likelihood=SimpleNamespace(detection_probability=None);self.best=None
        def evaluate(self,v):
            assert self.likelihood.detection_probability==.07
            diff=v-np.array([3.,4.,5.,2.]);value=float(diff@diff)
            if self.best is None or value<self.best['objective']:
                self.best=dict(objective=value,vector=v.copy())
            return value,2*diff
    called=[]
    def verifier(data,initial,sats,rf,position,**kwargs):
        np.testing.assert_allclose(kwargs['start_vector'],[3.,4.,5.,2.],atol=1e-6)
        assert kwargs['probability_override']==.07
        assert kwargs['budget_s']==8
        called.append(True);return dict(success=True,objective=0.)
    objective,original=module.CalibrationObjective,module.original
    diagnostics=module.diagnostics
    try:
        module.CalibrationObjective=Objective;module.original=verifier;module.diagnostics=[{}]
        module.accelerated(None,[0,0,0],[0],[0.],np.array([3.,4.]),probability_override=.07)
        assert called==[True]
    finally:
        module.CalibrationObjective=objective;module.original=original;module.diagnostics=diagnostics


def test_polish_keeps_fixed_position_and_reduces_gradient():
    obj=SimpleNamespace(scale=np.array([1.,10.,10.]),base=SimpleNamespace(deadline=0.))
    target=np.array([3.,5.,2.])
    def evaluate(v):
        diff=v-target
        return 1e5+float(diff@diff),2*diff
    obj.evaluate=evaluate
    result=module.polish(obj,np.array([3.,5.0001,1.9999]),[(3.,3.),(None,None),(None,None)])
    np.testing.assert_allclose(result,target,atol=1e-10)


if __name__=='__main__':
    test_warm_start_preserves_site_probability_and_original_verifier()
    test_polish_keeps_fixed_position_and_reduces_gradient()
    print('Warm-start and polishing invariance tests passed')
