import unittest
from audit import retain,gate,ordinary_radius

def p(e,n,score=0):return dict(east_km=e,north_km=n,score=score,spacing_km=5)

class SelectionTests(unittest.TestCase):
    def test_radius_is_not_basin_separation(self):
        for spacing in (5,10,20):self.assertEqual(ordinary_radius(spacing),25)
        self.assertAlmostEqual(ordinary_radius(40),28.2842712474619)
        for spacing in (0,-1,float('nan')):
            with self.assertRaises(ValueError):ordinary_radius(spacing)
    def test_ties_separation(self):
        self.assertEqual([r['east_km'] for r in retain([p(25,0),p(0,0),p(12.5,0)],3)],[0,12.5,25])
    def test_exact_gate_boundary(self):
        self.assertFalse(gate(p(0,12.5),[p(0,0),p(50,0),p(100,0)])[0])
        self.assertTrue(gate(p(0,12.5001),[p(0,0),p(50,0),p(100,0)])[0])
    def test_bad_domains(self):
        for rows,size in [([p(0,0)],400),([p(0,0),p(0,0)],2),([p(0,0,float('nan'))],1)]:
            with self.assertRaises(ValueError):retain(rows,size)

if __name__=='__main__':unittest.main()
