import unittest
import numpy as np
from model import Model,Geometry,fast
class HeightTests(unittest.TestCase):
    def fixture(self):
        times=np.linspace(0,20,12);grid=np.array([-5.,0.,5.]);rng=np.random.default_rng(44)
        pos=np.zeros((2,3,12,3));vel=np.zeros_like(pos)
        for k in range(2):
            for j,tau in enumerate(grid):
                pos[k,j]=np.column_stack([np.full(12,6900.+k*70),-100+5*(times+tau),np.full(12,100+k*50)])
                vel[k,j,:,1]=5
        t=dict(candidate_position_km=pos,candidate_velocity_km_s=vel,mask=np.arange(12)<8,catalogue_size=2)
        doc=dict(tracks=[t]);cfg=dict(geographic_prior_center_deg=[0.,0.],timing_grid_s=grid)
        t['y']=Geometry(doc,cfg).prediction(t,np.zeros(4))[0][0]+rng.normal(0,70,12)+500
        return doc,cfg
    def test_height_gradient_and_held_isolation(self):
        doc,cfg=self.fixture();m=Model(doc,cfg);x=np.array([.2,-.1,.3,.1]);a=m.evaluate(x)
        fd=[]
        for axis in range(4):
            d=np.eye(4)[axis]*1e-4
            fd.append((m.evaluate(x+d,False)['score']-m.evaluate(x-d,False)['score'])/.0002)
        np.testing.assert_allclose(a['gradient'],fd,atol=1e-5,rtol=0)
        doc['tracks'][0]['y'][8:]+=1000;b=m.evaluate(x)
        self.assertEqual(a['score'],b['score']);np.testing.assert_array_equal(a['gradient'],b['gradient'])
        self.assertNotEqual(a['held'],b['held'])
    def test_zero_height_geometry_parity(self):
        doc,cfg=self.fixture();t=doc['tracks'][0];x=np.array([.2,-.1,.3])
        np.testing.assert_array_equal(Geometry(doc,cfg).prediction(t,np.r_[x,0])[0],fast.Stationary(doc,cfg).prediction(t,x)[0])
