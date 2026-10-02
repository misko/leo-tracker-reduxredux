import itertools
import unittest
from candidate_path import solve,score

class PathTests(unittest.TestCase):
    def test_matches_exhaustive_irregular_times(self):
        groups=[[dict(t=t,y=2*t+offset,margin=m) for offset,m in [(0,.6),(400*(-1)**i,.8)]] for i,t in enumerate((0.,.4,1.2,2.,4.))]
        path,value=solve(groups)
        brute=min(score(groups,p) for p in itertools.product(range(2),repeat=5))
        self.assertAlmostEqual(value,brute,places=12)
        self.assertEqual(len(path),5)
    def test_impossible_support(self):
        groups=[[dict(t=t,y=y,margin=.5)] for t,y in [(0.,0.),(1.,20000.)]]
        with self.assertRaises(ValueError):solve(groups)
    def test_offset_invariance(self):
        g=[[dict(t=float(i),y=float(i*i),margin=.5),dict(t=float(i),y=200.,margin=.6)] for i in range(5)]
        h=[[dict(p,y=p['y']+12345) for p in row] for row in g]
        p,v=solve(g);q,w=solve(h);self.assertEqual(p,q);self.assertAlmostEqual(v,w)

if __name__=='__main__':unittest.main()
