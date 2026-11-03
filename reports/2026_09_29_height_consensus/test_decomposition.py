import unittest
from build import decompose


class DecompositionTests(unittest.TestCase):
    def test_common_translation_invisible_to_scatter(self):
        base=[[0.,0.],[1.,0.],[0.,1.]]
        same=decompose(base,base)
        moved=decompose(base,[[x+3,y+4] for x,y in base])
        self.assertAlmostEqual(same['scatter_rms_m'],moved['scatter_rms_m'])
        self.assertEqual(moved['centroid_shift_m'],5000)
        self.assertEqual(moved['differential_shift_rms_m'],0)
        self.assertEqual(moved['shared_shift_energy_fraction'],1)

    def test_pure_differential_change(self):
        result=decompose([[0,0],[0,0]],[[-1,0],[1,0]])
        self.assertEqual(result['centroid_shift_m'],0)
        self.assertEqual(result['differential_shift_rms_m'],1000)
        self.assertEqual(result['shared_shift_energy_fraction'],0)

    def test_invalid_membership(self):
        with self.assertRaises(ValueError):decompose([],[])
        with self.assertRaises(ValueError):decompose([[0,0]],[])
