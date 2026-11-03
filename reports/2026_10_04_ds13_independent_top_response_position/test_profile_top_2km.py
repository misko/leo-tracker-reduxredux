import unittest,json
import numpy as np
from profile_top_2km import point_design,OUT,Engine
from position_top_2km_inputs import winners

class PositionProtocolTests(unittest.TestCase):
    def test_seeded_disk_design(self):
        a=point_design();b=point_design();self.assertEqual(a,b)
        self.assertEqual(len(a),73)
        self.assertEqual(sum(r['kind']=='random' for r in a),48)
        self.assertEqual(sum(r['kind']=='boundary' for r in a),16)
        self.assertTrue(all(np.hypot(r['east_m'],r['north_m'])<=2000+1e-8 for r in a))
        self.assertNotEqual(a,point_design(4))
        self.assertEqual(len({(r['east_m'],r['north_m']) for r in a}),73)

    def test_winners_keep_receivers_separate_and_fallback(self):
        r=[dict(row_index=1,probe_key=[1,0,0],original_margin=.9,refinement={}),
           dict(row_index=2,probe_key=[1,0,0],original_margin=.8,refinement={'margin':.9}),
           dict(row_index=3,probe_key=[1,1,0],original_margin=.1,refinement={'margin':.2})]
        self.assertEqual(winners(r),{1,3})

    def test_geometry_and_matched_rf_arms(self):
        # Explicit archived-analysis fixture dependency; never silently skipped.
        a=Engine('A','fitted-c');b=Engine('A','zero-c')
        np.testing.assert_array_equal(a.data.measured,b.data.measured)
        np.testing.assert_array_equal(a.data.numbers,b.data.numbers)
        self.assertNotEqual(a.obj.bounds[-1],b.obj.bounds[-1]);self.assertEqual(b.obj.bounds[-1],(0.,0.))
        np.testing.assert_allclose(a.coordinate([0,0]),a.meta['roof_position_km'],atol=1e-9,rtol=0)
        m=a.meta['model_reconstruction_max_error_hz'];self.assertLess(m,1e-5)

    def test_position_derivative_audit(self):
        rows=json.loads((OUT/'analytic-gradient-audit.json').read_text())
        for r in rows:
            self.assertLess(r['error'],.001)
            if r['index'] in (0,1):self.assertLess(r['error'],1e-4)

if __name__=='__main__':unittest.main()
