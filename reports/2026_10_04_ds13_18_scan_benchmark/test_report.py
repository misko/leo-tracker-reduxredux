import copy
import unittest
import json
import tempfile
from pathlib import Path
from render_report import validate_export,finalist_section,heldout_section,position_completion,leaderboard_section,require_final_audit,heldout_interpretation


class AccountingTests(unittest.TestCase):
    def test_heldout_interpretation_uses_unrounded_coverage(self):
        rows=[dict(scan=str(i),split='locked_test',method='alternatives',arm='fitted-c',
                   coverage=x,position_error_m=None) for i,x in enumerate((.89967,.89809,.81468,.63723))]
        text=heldout_interpretation(rows)
        self.assertIn('0/4 reach 90%',text)
        self.assertIn('63.72%–89.97%',text)
        self.assertIn('present for 0/4',text)
        self.assertIn('not confirmed satellite identity',text)
        self.assertIn('pending',heldout_interpretation(rows[:3]))
        self.assertIn('pending',heldout_interpretation(rows[:3]+[rows[0]]))
        for r in rows:r.update(position_error_m=0.,position_eligible=False)
        self.assertIn('0/4 pass the convergence',heldout_interpretation(rows))
        rows[0]['position_eligible']=True
        self.assertIn('1/4 pass the convergence',heldout_interpretation(rows))

    def test_final_publish_requires_positive_evidence_not_status_alone(self):
        for value in ({'status':'incomplete','checks':[{'verified':True}]},
                      {'status':'analysis_artifacts_verified','checks':[]},
                      {'status':'analysis_artifacts_verified','checks':[{'verified':False}]}):
            with self.assertRaisesRegex(ValueError,'required evidence'):require_final_audit(value)
        require_final_audit({'status':'analysis_artifacts_verified','checks':[{'verified':True}]})

    def test_leaderboard_discloses_matched_eligible_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'leaderboard';folder.mkdir()
            (folder/'summary.json').write_text(json.dumps({'sources':{},'aggregate':[]}))
            text=leaderboard_section(root,{})
            self.assertIn('eligible in <em>both</em>',text)
            self.assertIn('not certified global minima',text)

    def test_subset_completion_requires_both_arms_and_all_rankings(self):
        rows=[dict(scan='A',ranking=r,fraction=f,arm=a) for r in ('rms','support','glrt')
              for f in (.25,.5,.75) for a in ('fitted-c','zero-c')]
        rows += [dict(scan='A',ranking='support',fraction=1.,arm=a) for a in ('fitted-c','zero-c')]
        self.assertEqual(position_completion(rows),(1,1))
        self.assertEqual(position_completion(rows[1:]),(1,0))

    def test_heldout_section_discloses_conditional_denominator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folder=root/'heldout-calibration';folder.mkdir()
            (folder/'summary.json').write_text(json.dumps({'sources':{}}))
            text=heldout_section(root,{})
            self.assertIn('denominator can differ',text)
            self.assertIn('not fully held-out',text)

    def test_validation_shortlist_is_not_a_test_unlock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);sources={}
            self.assertEqual(finalist_section(root,sources),'')
            (root/'validation-shortlist.json').write_text(json.dumps({'sources':{}}))
            text=finalist_section(root,sources)
            self.assertIn('test scans remain locked',text)
            self.assertIn('inconclusive',text)
            self.assertIn(str(root/'validation-shortlist.json'),sources)

    def fixture(self):
        return dict(signature=dict(cohort_sha256='cohort', manifest_sha256='capture'),
                    records=[dict(candidate_id='a', group_id='g'), dict(candidate_id='b', group_id='g')],
                    summary=dict(projected_passing_candidates=2, passing_windows=1))

    def test_two_candidates_are_one_window(self):
        validate_export(self.fixture(), dict(manifest_sha256='capture'), 'cohort')

    def test_no_alias_inflation_of_windows(self):
        doc = self.fixture()
        doc['summary']['passing_windows'] = 2
        with self.assertRaisesRegex(ValueError, 'window accounting'):
            validate_export(doc, dict(manifest_sha256='capture'), 'cohort')

    def test_changed_cohort_rejected(self):
        with self.assertRaisesRegex(ValueError, 'current cohort'):
            validate_export(self.fixture(), dict(manifest_sha256='capture'), 'different')


if __name__ == '__main__':
    unittest.main()
