import unittest
from dataclasses import replace
import numpy as np
from leo.contracts.regional_position import PositionObservations,PositionOrbitBank,RegionalPrior,POSITION_SCORES
from leo.analysis.regional_position_score import PositionObjective,observer,predict_orbits
from cone_objective import ConeObjective,directions,cone_marginals,tilt,_model,_enu,cone_bundle

class SmoothSupport:
    def evaluate(self,u):
        j=np.zeros_like(u);j[...,0]=.1
        return .7+.1*u[...,0],j

def synthetic():
    rng=np.random.default_rng(5);prior=RegionalPrior();n,k=8,12
    times=np.linspace(.23,2.13,n);rf=np.linspace(11e9,12e9,n)
    obs=PositionObservations(tuple(map(str,range(n))),times,np.zeros(n),rf,np.arange(n)%2,np.arange(n),np.ones(n))
    nodes=np.arange(-30.,31.);site=observer(prior,[0,0])[0];rotation=_enu(prior,[0,0])
    u=rng.normal(size=(k,3));u[:,2]=np.abs(u[:,2])+.7;u/=np.linalg.norm(u,axis=1)[:,None]
    positions=site+(600*u@rotation)[:,None,:]+nodes[None,:,None]*(rng.normal(size=(k,3))*.0004)[:,None,:]
    velocities=np.broadcast_to(rng.normal(size=(k,1,3))*.004,positions.shape).copy()
    bank=PositionOrbitBank(np.arange(1,k+1),nodes,positions,velocities)
    score=replace(POSITION_SCORES['V16'],relative_sigma_s=1.)
    theta=np.array([.6,.4,np.log(.3),.2,.7]);frames=np.array([_model.frame(270,70),_model.frame(90,70)])
    obj=ConeObjective(obs,bank,prior,score,strength=.7,theta=theta,frames=frames,support=SmoothSupport())
    v=np.r_[4.,-6.,12.,.1,-5.,-.2,14.,.031,np.linspace(-.03,.025,k-1)]
    pred=predict_orbits(bank,obs,prior,v[:2],v[7]+obj.basis@v[8:])[0]
    obs=replace(obs,measured_hz=pred[:,0]+np.linspace(-40,40,n))
    obj=ConeObjective(obs,bank,prior,score,strength=.7,theta=theta,frames=frames,support=SmoothSupport())
    return obj,v

class ConeTests(unittest.TestCase):
    def test_zero_strength_exact_parity(self):
        obj,v=synthetic();obj.strength=0
        base=PositionObjective(obj.observations,obj.bank,obj.prior,obj.score,receiver_baseline_hz=obj.baseline)
        a,g,t=obj.evaluate(v);b,h,s=base.evaluate(v)
        self.assertEqual(a,b);np.testing.assert_array_equal(g,h)
        np.testing.assert_array_equal(t.responsibilities,s.responsibilities)
    def test_full_gradient(self):
        obj,v=synthetic();value,g,_=obj.evaluate(v)
        for i in range(len(v)):
            h=.001 if i<2 else 1e-5
            plus=v.copy();minus=v.copy();plus[i]+=h;minus[i]-=h
            numeric=(obj.evaluate(plus)[0]-obj.evaluate(minus)[0])/(2*h)
            self.assertAlmostEqual(g[i],numeric,delta=2e-5,msg=f'index{i}: analytic{g[i]} numeric{numeric}')
        obj.evaluate(v);q=obj.last_geometry['q'];b=obj.last_geometry['base_q']
        np.testing.assert_allclose(q.sum(axis=1),b.sum(axis=1),atol=1e-15)
        self.assertTrue(np.all(q[b>0]>0));self.assertTrue(np.all(q<1))
    def test_direction_derivatives_and_rx_mapping(self):
        obj,v=synthetic();unit,dp,dt=directions(obj.bank,obj.observations,obj.prior,v,obj.basis)
        np.testing.assert_allclose(np.linalg.norm(unit,axis=2),1,atol=1e-12)
        for i in range(2):
            d=np.zeros(len(v));d[i]=.001
            numeric=(directions(obj.bank,obj.observations,obj.prior,v+d,obj.basis)[0]-directions(obj.bank,obj.observations,obj.prior,v-d,obj.basis)[0])/.002
            np.testing.assert_allclose(dp[:,:,:,i],numeric,atol=1e-8)
        theta=np.array([.3,.2,np.log(.1),0,0]);frames=np.array([_model.frame(270,70),_model.frame(90,70)])
        marg,_=cone_marginals(frames[:,2],theta,frames)
        self.assertGreater(marg[0,0],marg[0,1]);self.assertGreater(marg[1,1],marg[1,0])
        self.assertLess(frames[0,2,0],0);self.assertGreater(frames[1,2,0],0)
        rays=np.array([frames[0,2],-frames[0,2]])
        logits,_=_model.logits_and_jacobian(theta,_model.project(rays))
        self.assertGreater(logits[0,0],0);self.assertLess(logits[1,0],0)
    def test_tilt_invisible_and_empty_rows(self):
        base=np.array([[.2,.2,0],[0,0,0.]])
        q=tilt(base,np.array([[-1,-.2,4],[2,3,4.]]))
        np.testing.assert_allclose(q.sum(axis=1),base.sum(axis=1),atol=1e-15)
        self.assertEqual(q[0,2],0);np.testing.assert_array_equal(q[1],0)
    def test_bundle_frozen_shapes(self):
        theta,frames,support=cone_bundle()
        self.assertEqual(theta.shape,(5,));self.assertEqual(frames.shape,(2,3,3))
        val,_=support.evaluate(np.array([[0.,0.,1.]]));self.assertTrue(np.isfinite(val).all())

if __name__=='__main__':unittest.main()
