import unittest
import numpy as np
from scipy.special import logsumexp
from matching import partition,evidence

def brute(edges):
    records=[]
    def recurse(i,used,score,chosen):
        if i==len(edges):records.append((score,chosen));return
        recurse(i+1,used,score,chosen)
        for j in range(edges.shape[1]):
            if j not in used and np.isfinite(edges[i,j]):recurse(i+1,used|{j},score+edges[i,j],chosen+[(i,j)])
    recurse(0,set(),0.,[]);z=logsumexp([r[0] for r in records]);p=np.zeros_like(edges)
    for score,chosen in records:
        for i,j in chosen:p[i,j]+=np.exp(score-z)
    return z,p
class MatchingTests(unittest.TestCase):
    def test_exact_enumeration_and_exclusivity(self):
        a=np.array([[2.,-.4,1.],[.3,-np.inf,3.]])
        z,p=partition(a);bz,bp=brute(a)
        self.assertAlmostEqual(z,bz,places=12);np.testing.assert_allclose(p,bp,atol=1e-13)
        self.assertTrue((p.sum(axis=0)<=1+1e-12).all());self.assertTrue((p.sum(axis=1)<=1+1e-12).all())
    def test_no_information_cannot_increase_evidence(self):
        l=np.array([-10.,-20.]);r=np.array([-3.,-6.,-8.]);pairs=l[:,None]+r[None,:]
        out=evidence(l,r,pairs,np.full((2,3),1.4))
        self.assertAlmostEqual(out['log_evidence'],l.sum()+r.sum(),places=12)
    def test_permutation_and_transpose(self):
        a=np.array([[1.,2.,3.],[.5,1.2,-2.]])
        z,p=partition(a);zt,pt=partition(a.T);zr,pr=partition(a[::-1,::-1])
        self.assertAlmostEqual(z,zt);self.assertAlmostEqual(z,zr)
        np.testing.assert_allclose(p,pt.T);np.testing.assert_allclose(p,pr[::-1,::-1])
    def test_empty_impossible_and_budget(self):
        z,p=partition(np.empty((0,3)));self.assertEqual(z,0);self.assertEqual(p.shape,(0,3))
        z,p=partition(np.full((2,3),-np.inf));self.assertEqual(z,0);self.assertEqual(p.sum(),0)
        with self.assertRaises(ValueError):partition(np.zeros((3,3)),max_columns=2)
    def test_edge_derivative_matches_marginal(self):
        a=np.array([[1.,-.5],[2.,.3]])
        _,p=partition(a)
        for i in range(2):
            for j in range(2):
                d=np.zeros_like(a);d[i,j]=1e-5
                fd=(partition(a+d,marginals=False)-partition(a-d,marginals=False))/2e-5
                self.assertAlmostEqual(fd,p[i,j],places=8)
