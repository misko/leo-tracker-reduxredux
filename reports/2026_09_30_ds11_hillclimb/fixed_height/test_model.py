import unittest
import numpy as np
from model import Model,physical


class FixedHeightTests(unittest.TestCase):
    def fixture(self):
        times=np.linspace(0,20,15);grid=np.array([-5.,0,5.])
        position=np.zeros((2,3,15,3));velocity=np.zeros_like(position)
        for c in range(2):
            for i,tau in enumerate(grid):
                position[c,i]=np.column_stack((np.full(15,6900+70*c),-100+5*(times+tau),np.full(15,100+50*c)))
                velocity[c,i,:,1]=5
        track=dict(candidate_position_km=position,candidate_velocity_km_s=velocity,
                   mask=np.arange(15)<10,catalogue_size=2)
        doc=dict(tracks=[track]);config=dict(geographic_prior_center_deg=[0,0],timing_grid_s=grid)
        track['y']=Model(doc,config,120).prediction(track,np.zeros(3))[0][0]+np.random.default_rng(22).normal(0,70,15)+400
        return doc,config

    def test_nonzero_height_gradient_and_held_isolation(self):
        doc,cfg=self.fixture();m=Model(doc,cfg,120);x=np.array([.2,-.1,.3]);a=m.evaluate(x)
        fd=[]
        for i in range(3):
            delta=np.eye(3)[i]*1e-4
            fd.append((m.evaluate(x+delta,False)['score']-m.evaluate(x-delta,False)['score'])/.0002)
        np.testing.assert_allclose(a['gradient'],fd,atol=1e-5,rtol=0)
        doc['tracks'][0]['y'][10:]+=1000;b=m.evaluate(x)
        self.assertEqual(a['score'],b['score']);np.testing.assert_array_equal(a['gradient'],b['gradient'])
        self.assertNotEqual(a['held'],b['held'])
        self.assertEqual(m.state(x)[3],.12)

    def test_zero_height_and_no_free_height_parameter(self):
        doc,cfg=self.fixture();m=Model(doc,cfg,0);x=np.array([.2,-.1,.3]);track=doc['tracks'][0]
        np.testing.assert_array_equal(m.prediction(track,x)[0],physical.fast.Stationary(doc,cfg).prediction(track,x)[0])
        with self.assertRaises(ValueError):m.evaluate([0,0,0,1])
        with self.assertRaises(ValueError):Model(doc,cfg,float('nan'))
