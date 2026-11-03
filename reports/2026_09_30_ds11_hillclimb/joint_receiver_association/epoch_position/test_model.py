import itertools
import unittest
import numpy as np
from scipy.special import logsumexp
from model import adjust, coefficients, partition


class TimingModelTests(unittest.TestCase):
    def test_exact_three_track_assignments(self):
        unary=np.array([[.2,-.4,.5],[-.3,.7,.1]])
        matrix=np.array([[0,.8,-.2],[0,0,.4],[0,0,0.]])
        bits=(np.arange(8)[:,None]>>np.arange(3))&1
        factors=[([0,1,2],bits@u,np.zeros((8,1))) for u in unary]
        got=partition(3,adjust(factors,matrix))[0]
        expected=[]
        for assignment in itertools.product(range(2),repeat=3):
            expected.append(sum(unary[c,i] for i,c in enumerate(assignment))+sum(matrix[i,j] for i in range(3) for j in range(i+1,3) if assignment[i]==assignment[j]))
        self.assertAlmostEqual(got,logsumexp(expected),places=12)
        self.assertAlmostEqual(partition(3,adjust(factors,np.zeros((3,3))))[0],sum(logsumexp(unary,axis=0)),places=12)

    def test_ownership_training_and_duplicates(self):
        c=dict(integer_epoch_sample=10,fractional_epoch_offset_samples=0.,fractional_tracking_cfo_hz=1.,fractional_exact_score=.6,fractional_control_score=.1)
        raw={k:(dict(c),5e6) for k in ('a','aa','b','c','d')}
        raw['d']=(dict(c,integer_epoch_sample=500),5e6)
        meta={'l':dict(receiver=0,candidate_ids=['a','aa','c'],window_ids=['w','w','v']),'r':dict(receiver=1,candidate_ids=['b','d'],window_ids=['w','v'])}
        masks={'l':[True,True,False],'r':[True,False]}
        cal=dict(threshold_us=.03,event_log_ratio=dict(hit=2.,miss=-3.))
        args=(['l','r'],meta,masks,{'assignment':{}},raw,cal)
        self.assertEqual(coefficients(*args)[0,1],2.)
        self.assertEqual(coefficients(*args,held=True)[0,1],-.5)
        self.assertEqual(coefficients(['l','r'],meta,masks,{'assignment':{'a':'other','aa':'other'}},raw,cal)[0,1],0.)
