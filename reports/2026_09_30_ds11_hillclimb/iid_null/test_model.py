import copy
import unittest
from unittest.mock import patch

import numpy as np
from scipy.stats import multivariate_normal

import model


class Engine:
    def __init__(self,document,config):
        pass

    def prediction(self,track,x):
        t=np.asarray(track['times_s'])
        base=np.array([30*t+2*t*t, -40*t+3*t*t])
        pred=base+x[0]*t+x[1]*t*t+x[2]*np.sin(t)
        return pred,np.array([True,True])


class NullTests(unittest.TestCase):
    def test_gaussian_covariance_normalization_and_offset(self):
        t=np.array([0.,.2,.8,1.1,2.])
        y=np.array([800.,1200.,2400.,3000.,4800.])+np.array([0,10,-20,30,-10])
        mask=np.ones(len(t),bool)
        u=t-t.mean()
        c=10000*np.eye(len(t))+2000**2*np.outer(u,u)
        offset=y.sum()/(len(y)+10000/1e12)
        expected=multivariate_normal.logpdf(y,mean=np.full(len(y),offset),cov=c)-.5*offset**2/1e12
        self.assertAlmostEqual(model.trend_score(y,t,mask),expected,places=6)
        precision=np.linalg.solve(c,y-offset)
        self.assertAlmostEqual(float(precision.sum()-offset/1e12),0.,places=10)

    def test_training_only_time_origin_and_values(self):
        mask=np.array([True,False,True,False,True])
        t=np.arange(5.,dtype=float)
        y=400+50*t
        before=model.trend_score(y,t,mask)
        y[~mask]=1e15
        t[~mask]=-1e15
        self.assertEqual(model.trend_score(y,t,mask),before)
        self.assertAlmostEqual(model.trend_score(y,t+1000,mask),before,places=9)

    def test_mixture_gradient_and_held_independence(self):
        t=np.linspace(-2,2,21)
        mask=np.arange(len(t))%3!=0
        track=dict(times_s=t,y=500+30*t+2*t*t+np.sin(3*t)*25,mask=mask,catalogue_size=8000)
        doc=dict(tracks=[track])
        x=np.array([.2,-.1,.3])
        with patch.object(model.fast,'Stationary',Engine):
            m=model.Model([doc],{},.2)
            r=m.evaluate(x)
            g=[]
            for delta in np.eye(3)*1e-4:
                g.append((m.evaluate(x+delta,False)['score']-m.evaluate(x-delta,False)['score'])/2e-4)
            np.testing.assert_allclose(r['gradient'],g,atol=2e-6)
            changed=copy.deepcopy(doc)
            changed['tracks'][0]['y'][~mask]=1e9
            changed['tracks'][0]['times_s'][~mask]=1e9
            result=model.Model([changed],{},.2).evaluate(x)
            self.assertAlmostEqual(result['score'],r['score'],places=9)
            np.testing.assert_allclose(result['gradient'],r['gradient'],atol=1e-8)


if __name__=='__main__':
    unittest.main()
