import math
import unittest
from conservative import blend, score, lse


class Tests(unittest.TestCase):
    def test_endpoints(self):
        p, q = [math.log(.9),math.log(.1)], [math.log(.2),math.log(.8)]
        self.assertEqual(blend(p,q,0),p)
        self.assertEqual(blend(p,q,1),q)
        self.assertAlmostEqual(math.exp(blend(p,q,.5)[0]), .55)

    def test_null(self):
        p = [math.log(.9),math.log(.1)]
        self.assertAlmostEqual(score(p,p,[-5,-2],3,.5)['gain'],0)

    def test_extreme_loss_bound(self):
        p,q = [0.,-1000.],[-1000.,0.]
        s=score(p,q,[0.,-1000.],2,.5)
        self.assertAlmostEqual(s['gain'], -math.log(2)/2)
        self.assertAlmostEqual(s['maximum_loss_bound'],math.log(2)/2)

    def test_predictive_mixture_identity(self):
        p,q = [math.log(.9),math.log(.1)],[math.log(.2),math.log(.8)]
        held=[-7.,-3.]
        a,b=score(p,q,held,2,0),score(p,q,held,2,1)
        expected=-lse([math.log(.75)-2*a['nll'],math.log(.25)-2*b['nll']])/2
        self.assertAlmostEqual(score(p,q,held,2,.25)['nll'],expected)

    def test_invalid(self):
        for p,q,f in [([0],[0],-1),([0],[0],float('nan')),([0,0],[0,0],.5),([0],[],.5)]:
            with self.assertRaises(ValueError): blend(p,q,f)
        for n in [0,True,1.2]:
            with self.assertRaises(ValueError): score([0],[0],[0],n,.5)


if __name__ == '__main__': unittest.main()
