import itertools
import unittest
import numpy as np
from scipy.special import logsumexp
from receiver_model import state_probabilities,emission,presence_score,beam_logits
class ReceiverTests(unittest.TestCase):
    def test_normalization_dependence_and_zero_variance(self):
        p=state_probabilities(np.zeros((2,3,2)),0)
        np.testing.assert_allclose(p,.25)
        q=state_probabilities(np.zeros((2,3,2)),1)
        np.testing.assert_allclose(q.sum(axis=-1),1)
        self.assertTrue((q[...,3]>.25).all());self.assertTrue((q[...,0]>.25).all())
    def test_missing_is_marginalized_not_absent(self):
        p=np.array([[[.1,.2,.3,.4]],[[.1,.2,.3,.4]]])
        out=emission(p,np.array([[-1,-1],[1,-1]]))
        np.testing.assert_allclose(out[:,0],[0,np.log(.6)])
    def test_geometry_mapping_swap_and_strength_quadrature(self):
        los=np.array([[.6,0,.8],[-.6,0,.8]])
        x=beam_logits(los,10,[0,0],2)
        self.assertGreater(x[0,1],x[0,0]);np.testing.assert_allclose(x[0],x[1,::-1])
        a=state_probabilities(x,1,24);b=state_probabilities(x,1,48)
        np.testing.assert_allclose(a,b,atol=1e-8,rtol=0)
    def test_hmm_matches_enumeration_and_gaps(self):
        times=np.array([0.,.4,10.]);present=np.log(np.array([[.6,.2],[.5,.3],[.8,.1]]));absent=np.log([.4,.4,.2]);occ=.3;tau=2
        expected=[];pi=np.array([1-occ,occ])
        for k in range(2):
            scores=[]
            for path in itertools.product((0,1),repeat=3):
                score=np.log(pi[path[0]])
                for i,state in enumerate(path):
                    if i:
                        r=np.exp(-(times[i]-times[i-1])/tau);t=r*np.eye(2)+(1-r)*pi[None,:]
                        score+=np.log(t[path[i-1],state])
                    score+=present[i,k] if state else absent[i]
                scores.append(score)
            expected.append(logsumexp(scores))
        np.testing.assert_allclose(presence_score(times,present,absent,occ,tau),expected,atol=1e-12)
    def test_unobserved_held_values_cannot_change_training_score(self):
        t=[0,1,2];p=np.log(np.full((3,2),.3));a=np.log(np.full(3,.2));mask=[True,False,True]
        first=presence_score(t,p,a,.5,2,mask);p[1]=-100;a[1]=-200
        np.testing.assert_array_equal(first,presence_score(t,p,a,.5,2,mask))
