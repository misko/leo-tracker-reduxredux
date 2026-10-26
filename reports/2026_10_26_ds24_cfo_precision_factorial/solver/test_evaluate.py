import unittest
import numpy as np
from evaluate import contrasts


class ContrastTests(unittest.TestCase):
    def test_signed_interaction_and_symmetric_closure(self):
        p={'00':[1.,2.],'10':[2.,4.],'01':[0.,3.],'11':[4.,5.]};r=contrasts(p);v=r['vectors_km']
        np.testing.assert_array_equal(v['interaction'],[3.,0.])
        np.testing.assert_array_equal(np.array(v['symmetric_CFO'])+v['symmetric_packet'],v['total'])
        self.assertNotAlmostEqual(r['norms_m']['symmetric_CFO']+r['norms_m']['symmetric_packet'],r['norms_m']['total'])

    def test_missing_or_invalid_endpoint_never_backfilled(self):
        self.assertFalse(contrasts({'00':[0.,0.]})['complete'])
        with self.assertRaises(ValueError):contrasts(dict.fromkeys(('00','10','01','11'),[float('nan'),0.]))


if __name__=='__main__':unittest.main()
