"""Regression checks for paired coverage, scoring denominators, and publication integrity."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import score as report
from panels import PANEL_SIZES, select_panel


class PairedReportTest(unittest.TestCase):
    def test_replay_defaults_to_four_recordings_on_one_allowed_core(self):
        import run
        with patch.object(run.os,"sched_getaffinity",return_value={4,7,9}):
            args=run.parse_args(["receiver.so","results"])
        self.assertEqual(PANEL_SIZES[args.panel],4)
        self.assertEqual(args.cpus,"4")

    def test_stages_are_nested_and_keep_the_frozen_order(self):
        rows=[{"method":"compact_two_scan","case":str(i)} for i in reversed(range(455))]
        for panel,size in PANEL_SIZES.items():
            self.assertEqual(select_panel(rows,panel),rows[:size])

    def test_default_scoring_panel_is_four_and_requires_both_receipts(self):
        rows=[{"method":"compact_two_scan","case":str(i)} for i in range(455)]
        cohort={"members":[{"id":row["case"]} for row in rows]}
        with tempfile.TemporaryDirectory() as work, patch.object(report,"read",side_effect=[cohort,{"predictions":rows}]):
            path=Path(work)
            with self.assertRaises(FileNotFoundError) as caught:
                report.lock_predictions(path,path)
            self.assertEqual(Path(caught.exception.filename),path/"0"/"deployed.json")
            self.assertFalse((path/"panel.json").exists())

    def test_incomplete_cohort_cannot_publish(self):
        with tempfile.TemporaryDirectory() as work:
            path=Path(work)
            with self.assertRaises(FileNotFoundError):
                report.lock_predictions(path,path)
            self.assertFalse((path/"predictions.zip").exists())

    def test_error_cdf_denominator_includes_withheld(self):
        import matplotlib.pyplot as plt
        fig,ax=plt.subplots()
        try:
            report.ecdf(ax,[3.,1.],4,"-","k","example")
            self.assertEqual(list(ax.lines[0].get_xdata()),[1.,1.,3.])
            self.assertEqual(list(ax.lines[0].get_ydata()),[0.,.25,.5])
        finally:
            plt.close(fig)

    def test_different_outcomes_are_scored(self):
        case=dict(id="test",recording_state="incomplete")
        arms={a:dict(latlon=[20.,-10.],rf_rms_hz=27.) for a in report.ARMS}
        p=dict(case="test",mode="deployed",cpu=7,order=1,windows=8,eligible_visits=6,
               factor_digest="a",owners={},status="ok",arms=arms)
        for k in report.STAGES:
            for u in ("cpu","wall"):
                p[f"{k}_{u}_s"]=2.
        q=dict(p,mode="optimized",status="withheld",order=0,factor_digest="b",
               arms={a:dict(latlon=None) for a in report.ARMS})
        refs=dict(cases=[dict(dataset_label="test",authority_eligible=True,
                             reference=dict(latitude_deg=20.,longitude_deg=-10.))])
        prior=[dict(case="test",arm=a,state="ok",latitude="20",longitude="-10",rf_rms_hz="27")
               for a in report.ARMS]
        with patch.object(report,"read",return_value=refs),patch.object(report,"records",return_value=prior):
            times,positions=report.score([case],{"test/deployed.json":p,"test/optimized.json":q})
        self.assertFalse(times[0]["same_factors"])
        self.assertFalse(times[0]["same_decision"])
        self.assertEqual(len(positions),2)
        for r in positions:
            self.assertIsNone(r["optimized_error_km"])
            self.assertEqual(r["deployed_error_km"],0.)
            self.assertTrue(r["deployed_matches_frozen"])
            self.assertFalse(r["identical_position"])


if __name__=="__main__":
    unittest.main()
