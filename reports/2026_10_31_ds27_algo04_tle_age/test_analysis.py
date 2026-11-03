"""Unit and artifact checks for the scientific extraction/aggregation."""
import unittest
from types import SimpleNamespace
import numpy as np
import pandas as pd
from analyze import age_fields, phase_fields, orbit_fields
from summarize import partial_rank, load


class AnalysisTests(unittest.TestCase):
    def test_age_uses_epoch_not_collection(self):
        scan=SimpleNamespace(receipt=dict(origin_utc_ns=36_000_000_000_000,cutoff_utc_ns=35_000_000_000_000),
                             elements={'1':{'provenance':dict(element_epoch_utc_ns=0,collected_utc_ns=32_400_000_000_000)}})
        v=age_fields(scan,1)
        self.assertEqual(v['tle_age_h'],10.)
        self.assertEqual(v['collection_age_h'],1.)
        scan.elements['1']['provenance']['collected_utc_ns']=36_000_000_000_000
        with self.assertRaises(ValueError):age_fields(scan,1)

    def test_phase_innovation_is_relative_to_prior_mean(self):
        v=phase_fields(5,4,2)
        self.assertEqual(v['abs_phase_s'],5)
        self.assertEqual(v['abs_phase_pull'],.5)

    def test_orbit_conversion_to_physical_units(self):
        metadata=dict(mean_motion_sigma_rev_day=.001,inclination_sigma_deg=.01,raan_sigma_deg=.02,
                      radial_sigma_km=.3,cross_sigma_km=.1)
        v=orbit_fields(np.array([3.,0.,-4.]),metadata)
        self.assertEqual(v['orbital_pull_norm'],5.)
        self.assertAlmostEqual(v['mean_motion_rev_day'],.003)
        self.assertAlmostEqual(v['raan_deg'],-.08)
        self.assertEqual(orbit_fields(None,metadata),{})

    def test_removing_scan_effects_changes_confounded_direction(self):
        d=pd.DataFrame(dict(case=['a']*5+['b']*5,tle_age_h=[1,2,3,4,5,11,12,13,14,15],
                            value=[5,4,3,2,1,15,14,13,12,11]))
        self.assertAlmostEqual(partial_rank(d,'value',['case']),-1.)

    def test_matched_arms_unique_family_rows_and_exact_replays(self):
        d,r,c,inv=load()
        self.assertEqual(d.case.nunique(),13)
        self.assertFalse(d.duplicated(['case','arm','norad']).any())
        self.assertLess(c.objective_difference.abs().max(),1e-5)
        self.assertLess(c.state_max_difference.abs().max(),1e-5)
        self.assertTrue((d.collected_utc_ns<=d.origin_utc_ns).all())
        self.assertTrue((d.tle_age_h>=0).all())
        self.assertEqual(len(r),26)

    def test_saturated_satellite_controls_are_not_identifiable(self):
        d=pd.DataFrame(dict(case=['a']*5+['b']*5,norad=range(10),tle_age_h=range(10),value=range(10)))
        self.assertTrue(np.isnan(partial_rank(d,'value',['case','norad'])))


if __name__=='__main__':unittest.main()
