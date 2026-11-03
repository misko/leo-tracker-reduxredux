import sys
import unittest
from pathlib import Path
import numpy as np
from objective import GeometryObjective,receiver_logits,CONES,cones
sys.path.insert(0,str(CONES))
from test_cone_objective import synthetic

class GateTests(unittest.TestCase):
    def test_conditional_cannot_measure_both_absent_and_normalization_cancels(self):
        original,_=synthetic();theta=np.array([.3,.2,np.log(.1),0,0])
        ray=np.array([[0.,1.,0.]])
        marginal,_=cones.cone_marginals(ray,theta,original.frames)
        logits,_=receiver_logits(ray,theta,original.frames)
        self.assertTrue(np.all(logits<-20))
        np.testing.assert_allclose(marginal,.5,atol=1e-6)
        base=np.array([[.1,.1,.1]])
        np.testing.assert_allclose(cones.tilt(base,np.full_like(base,np.log(.1))),base,atol=1e-15)
    def test_control_parity_and_three_full_gradients(self):
        original,v=synthetic()
        for mode in ('control','conditional','absolute','absolute2'):
            obj=GeometryObjective(original.observations,original.bank,original.prior,original.score,mode=mode,theta=original.theta,frames=original.frames,support=original.support)
            value,g,_=obj.evaluate(v)
            if mode=='control':
                original.strength=0;a,b,_=original.evaluate(v)
                self.assertEqual(a,value);np.testing.assert_array_equal(b,g)
            for j in range(len(v)):
                h=.001 if j<2 else 1e-5;plus=v.copy();minus=v.copy();plus[j]+=h;minus[j]-=h
                numeric=(obj.evaluate(plus)[0]-obj.evaluate(minus)[0])/(2*h)
                self.assertAlmostEqual(g[j],numeric,delta=3e-5,msg=f'{mode} parameter{j}')
            if mode!='control':
                obj.evaluate(v);q=obj.last_geometry['q'];base=obj.last_geometry['base_q']
                self.assertTrue(np.all(q<=base+1e-15));self.assertTrue(np.all(q[base>0]>0))
                self.assertTrue(np.all(q.sum(axis=1)<base.sum(axis=1)))
    def test_front_back_and_sharpness(self):
        original,_=synthetic();rays=np.array([original.frames[0,2],-original.frames[0,2]])
        l,j=receiver_logits(rays,original.theta,original.frames)
        self.assertGreater(l[0,0],0);self.assertLess(l[1,0],0)
        sharp,_=receiver_logits(rays,original.theta,original.frames,2)
        np.testing.assert_array_equal(sharp,l*2)
        # Ellipse norm is nondifferentiable at its exact axial apex; audit a
        # generic ray away from that apex rather than inventing an apex slope.
        rays=rays+np.array([.02,.03,.01]);rays/=np.linalg.norm(rays,axis=1)[:,None]
        l,j=receiver_logits(rays,original.theta,original.frames)
        for i in range(3):
            d=np.eye(3)[i]*1e-6
            numeric=(receiver_logits(rays+d,original.theta,original.frames)[0]-receiver_logits(rays-d,original.theta,original.frames)[0])/2e-6
            np.testing.assert_allclose(j[:,:,i],numeric,atol=1e-5)

if __name__=='__main__':unittest.main()
