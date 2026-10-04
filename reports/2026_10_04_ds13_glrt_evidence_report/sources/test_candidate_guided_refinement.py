import unittest
from candidate_guided_refinement import refine,ALIAS

class Tests(unittest.TestCase):
    def test_convergence_without_orbit(self):
        def score(f,e):return dict(tracking_cfo_hz=105000.,margin=1-abs(f-105000.)/1e6-(e-3.25)**2)
        r=refine(score,105300.,3.)
        self.assertEqual(r['status'],'refined');self.assertEqual(r['tracking_cfo_hz'],105000.)
        self.assertEqual(r['epoch'],3.25);self.assertEqual(r['calls'],13)
        self.assertTrue(all(a['margin']<=b['margin'] for a,b in zip(r['trace'],r['trace'][1:])))
    def test_nonlocal_rejected(self):
        self.assertEqual(refine(lambda f,e:dict(tracking_cfo_hz=f+2000,margin=1),0,0)['status'],'no_local_maximum')
    def test_bad_input(self):
        with self.assertRaises(ValueError):refine(None,float('nan'),0)

if __name__=='__main__':unittest.main()
