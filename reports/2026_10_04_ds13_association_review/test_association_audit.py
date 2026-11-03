import unittest
import json
from pathlib import Path
import numpy as np
from association_audit import polynomial_audit, observer_enu, sky_geometry, interpolate_positions


class AuditTests(unittest.TestCase):
    def test_exact_linear(self):
        t=np.linspace(0,100,30);r=17+2*t
        out=polynomial_audit(t,r,np.ones(len(t)))
        self.assertLess(out['linear_rms_hz'],1e-10)
        self.assertAlmostEqual(out['linear_slope_hz_s'],2.)
        self.assertIsNone(out['ratio'])

    def test_channel_bias_control(self):
        t=np.linspace(-1,1,100);ch=(abs(t)>.5).astype(int)
        residual=60*ch+3*t+np.sin(93*t)
        pooled=polynomial_audit(t,residual,ch)
        controlled=polynomial_audit(t,residual,ch,True)
        self.assertGreater(pooled['ratio'],1.3)
        self.assertLess(controlled['ratio'],1.01)
        self.assertEqual(controlled['quadratic_rank'],4)

    def test_real_curvature(self):
        t=np.linspace(0,50,70);r=.1*(t-25)**2+np.sin(12*t)
        out=polynomial_audit(t,r,np.ones(len(t)))
        self.assertGreater(out['ratio'],10)
        self.assertAlmostEqual(out['quadratic_coefficient_hz_s2'],.1,places=3)
        self.assertEqual(out['quadratic_dof'],67)

    def test_geometry_axes(self):
        axes={'RX0':[-np.sin(np.deg2rad(20)),0,np.cos(np.deg2rad(20))],
              'RX1':[np.sin(np.deg2rad(20)),0,np.cos(np.deg2rad(20))]}
        observer,rotation=observer_enu(37.,-122.)
        directions=np.array([axes['RX0'],axes['RX1']])
        position=observer+550*directions@rotation
        geometry=sky_geometry(position,37.,-122.,np.array([0,1]),axes)
        np.testing.assert_allclose(geometry['own_axis_advantage_deg'],40,atol=2e-6)
        np.testing.assert_allclose(geometry['azimuth_deg'],[270,90],atol=1e-10)
        np.testing.assert_allclose(geometry['elevation_deg'],70,atol=1e-10)

    def test_interpolation_bounds(self):
        nodes=np.array([0,1,2]);positions=np.column_stack([nodes,2*nodes,3*nodes])
        np.testing.assert_allclose(interpolate_positions(nodes,positions,np.array([.5,1.25])),[[.5,1,1.5],[1.25,2.5,3.75]])
        with self.assertRaises(ValueError):
            interpolate_positions(nodes,positions,np.array([2.]))

    def test_saved_audit_memberships_and_geometry(self):
        folder=Path(__file__).parent
        receipt=json.loads((folder/'association-audit.json').read_text())
        for scan in receipt['scans']:
            with np.load(folder/f'{scan["scan"]}-assigned-observations.npz') as arrays:
                self.assertEqual(len(arrays['row_id']),scan['assigned'])
                self.assertEqual(len(set(arrays['row_id'])),scan['assigned'])
                self.assertEqual(len(set(arrays['satellite'])),scan['satellites'])
                self.assertTrue(np.all(np.abs(arrays['fitted_c_residual_hz'])<=600))
                self.assertEqual(int(sum(arrays['own_axis_advantage_deg']<0)),scan['wrong_hemisphere_observations'])
                for name in arrays.files:
                    self.assertTrue(np.all(np.isfinite(arrays[name])),name)
            for arm in ('fitted-c','zero-c'):
                tracks=[r for r in scan['all_tracks'] if r['arm']==arm]
                self.assertEqual(sum(r['n'] for r in tracks),scan['assigned'])
                self.assertEqual(len(tracks),scan['receiver_tracks'])
                for row in tracks:
                    for prefix in ('pooled','channel_controlled'):
                        self.assertLessEqual(row[f'{prefix}_quadratic_rms_hz'],row[f'{prefix}_linear_rms_hz']+1e-8)


if __name__=='__main__':unittest.main()
