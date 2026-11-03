import unittest
from run_subset_batch import cases,check_scan,selection_file,position_namespace


class SubsetBatchTests(unittest.TestCase):
    def test_warning_results_do_not_share_clean_namespace(self):
        self.assertEqual(position_namespace(),'position-fisher-v2')
        self.assertEqual(position_namespace(True),'position-fisher-v2-calibration-warning')

    def test_selection_stays_in_scan_directory(self):
        self.assertEqual(selection_file('selection-curvature-1.1.json'),'selection-curvature-1.1.json')
        for value in ('../selection-x.json','/selection-x.json','observations.json'):
            with self.assertRaisesRegex(ValueError,'local selection'):selection_file(value)

    def test_full_set_is_shared_not_three_experiments(self):
        values=cases(['rms','support','glrt'],[.25,.5,.75,1.])
        self.assertEqual(len(values),10)
        self.assertEqual(sum(f==1. for _,f in values),1)

    def test_invalid_case_and_locked_scan_rejected(self):
        with self.assertRaises(ValueError):cases(['rms'],[.3])
        with self.assertRaises(ValueError):cases(['answer'],[.5])
        cohort={'scans':[{'label':'T','split':'locked_test'}]}
        with self.assertRaisesRegex(ValueError,'locked-test'):check_scan(cohort,'T')
        check_scan(cohort,'T',True)
