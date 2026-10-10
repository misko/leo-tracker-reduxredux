import unittest
from audit import retain,gate

def p(e,n,score=0):return dict(east_km=e,north_km=n,score=score,spacing_km=5)

class SelectionTests(unittest.TestCase):
    def test_ties_separation(self):
        self.assertEqual([r['east_km'] for r in retain([p(25,0),p(0,0),p(12.5,0)],3)],[0,12.5,25])
    def test_exact_gate_boundary(self):
        self.assertFalse(gate(p(0,12.5),[p(0,0),p(50,0),p(100,0)])[0])
        self.assertTrue(gate(p(0,12.5001),[p(0,0),p(50,0),p(100,0)])[0])
    def test_bad_domains(self):
        for rows,size in [([p(0,0)],400),([p(0,0),p(0,0)],2),([p(0,0,float('nan'))],1)]:
            with self.assertRaises(ValueError):retain(rows,size)

if __name__=='__main__':unittest.main()
