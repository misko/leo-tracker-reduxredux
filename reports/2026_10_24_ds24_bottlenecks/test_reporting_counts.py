import csv
import json
from pathlib import Path
import unittest

from reporting_counts import likelihood_point_count

HERE=Path(__file__).resolve().parent
HALF=Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
FULL=Path('/srv/bulk/leo/research/ds25-20261024')

class Counts(unittest.TestCase):
    def test_modern_and_legacy_schema(self):
        self.assertEqual(likelihood_point_count(dict(active_points=11,predictive_points=7)),18)
        self.assertEqual(likelihood_point_count(dict(active_points=11,additional_predictive_points=7)),18)
        self.assertEqual(likelihood_point_count(dict(active_points=11),legacy_predictive_points=7),18)

    def test_explicit_zero_is_not_missing(self):
        self.assertEqual(likelihood_point_count(dict(active_points=11,predictive_points=0),legacy_predictive_points=7),11)

    def test_conflicting_fields_rejected(self):
        with self.assertRaises(ValueError):
            likelihood_point_count(dict(active_points=11,predictive_points=7,additional_predictive_points=9))

    def test_all_frozen_primary_arms(self):
        observed={}
        cases=sorted({r['case'] for r in csv.DictReader((HALF/'tables/positions.csv').open()) if r['status']=='localized'})
        for group,root in [('all_channels',FULL),('ch1_4',HALF/'ch1_4'),('ch5_8',HALF/'ch5_8')]:
            totals={a:0 for a in ('c0','fitted_c')}
            for case in cases:
                saved=json.loads((root/'family_cavity/position'/f'{case}.json').read_text())
                for arm,fit in saved['policy_arms'].items():
                    totals[arm]+=likelihood_point_count(fit)
            self.assertEqual(totals['c0'],totals['fitted_c'])
            observed[group]=totals['c0']
        self.assertEqual(observed,dict(all_channels=78067,ch1_4=42621,ch5_8=33339))

if __name__=='__main__': unittest.main()
