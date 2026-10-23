import copy
import unittest
import ast
from pathlib import Path
from report_full import ARMS, REFERENCE, build_rows, coverage, comparisons, metrics, summaries, ablations, promotion, block_intervals


def view(offset=0):
    return dict(arms={a:dict(endpoint_latlon=[REFERENCE[0]+offset,REFERENCE[1]],RMS_hz=2) for a in ARMS},
                coverage={a:dict(associated=2,total_GLRT=4,accepted_observation_ids=['a','b']) for a in ARMS})


class ReportTests(unittest.TestCase):
    def test_missing_failure_and_fallback_denominators(self):
        members=[dict(dataset_label=c,recording_format='short_window_iq_recording') for c in ('a','b','c')]
        prior={c:dict(status='complete',reference=view(),candidate=view(.01)) for c in ('a','b','c')}
        current={'a':dict(status='complete',final=view()),'b':dict(status='failed',final=view())}
        rows,status=build_rows(members,current,prior)
        full=next(r for r in summaries(rows) if r['cohort']=='all' and r['comparison_cohort']=='full_denominator' and r['method']=='ordinary' and r['arm']=='c0')
        self.assertEqual((full['localized'],full['population'],full['unlocalized_or_missing']),(1,3,2))
        self.assertEqual((full['failed_fits'],full['missing_or_pending']),(1,1))
        common=next(r for r in summaries(rows) if r['cohort']=='all' and r['comparison_cohort']=='common_completed')
        self.assertEqual(common['population'],1)
        self.assertEqual([s['status'] for s in status],['complete','failed','missing'])
        self.assertEqual(len(comparisons(rows)),4)
        self.assertEqual(len(ablations(rows)),7)
        current['b']['status']='reference_fallback'
        rows,_=build_rows(members,current,prior)
        self.assertEqual(sum(r['error_km'] is not None for r in rows if r['method']=='ordinary'),4)

    def test_unique_original_ids_required(self):
        cov=view()['coverage']['c0']
        self.assertEqual(coverage(cov),(2,4))
        for change in ({'accepted_observation_ids':['a','a']},{'associated':3},{'total_GLRT':1}):
            with self.assertRaises(ValueError): coverage(dict(cov,**change))

    def test_nonfinite_rejected(self):
        v=view();v['arms']['c0']['endpoint_latlon'][0]=float('nan')
        with self.assertRaises(ValueError):
            build_rows([dict(dataset_label='a',recording_format='short_window_iq_recording')],{'a':dict(status='complete',final=v)}, {})

    def test_empty_summary(self):
        result=metrics([],3)
        self.assertIsNone(result['p95_km'])
        self.assertEqual(result['unlocalized_or_missing'],3)

    def test_carries_are_deployed_but_not_scientific_completed(self):
        members=[dict(dataset_label='a',recording_format='short_window_iq_recording')]
        rows,_=build_rows(members,{'a':dict(status='frozen_bank_incomplete',final=view())},
                          {'a':dict(reference=view(),candidate=view())})
        common=[r for r in summaries(rows) if r['comparison_cohort']=='common_completed']
        self.assertTrue(all(r['population']==0 for r in common))
        self.assertFalse(promotion(rows,comparisons(rows),audit_passed=True)['eligible'])
        intervals=block_intervals(comparisons(rows),draws=5)
        self.assertEqual(len(intervals),8)
        self.assertTrue(all(r['lower_delta_km']==0 for r in intervals))

    def test_prior_noncompletion_excluded_from_common(self):
        members=[dict(dataset_label='a',recording_format='short_window_iq_recording')]
        rows,_=build_rows(members,{'a':dict(status='complete',final=view())},
                          {'a':dict(status='execution_fallback',reference=view(),candidate=view())})
        self.assertTrue(all(r['population']==0 for r in summaries(rows) if r['comparison_cohort']=='common_completed'))
        candidate=next(r for r in rows if r['method']=='rejected_candidate')
        self.assertEqual(candidate['source_status'],'execution_fallback')
        self.assertFalse(candidate['search_complete'])

    def test_explicit_search_flag_is_authoritative(self):
        rows,status=build_rows([dict(dataset_label='a',recording_format='short_window_iq_recording')],
                              {'a':dict(status='complete',search_complete=False,final=view())},
                              {'a':dict(status='complete',reference=view(),candidate=view())})
        self.assertFalse(status[0]['search_complete'])
        self.assertFalse(promotion(rows,comparisons(rows))['all_scientific_completed'])

    def test_expected_inherited_carry_not_new_promotion_requirement(self):
        members=[dict(dataset_label='DS23-0004',recording_format='short_window_iq_recording')]
        rows,_=build_rows(members,{'DS23-0004':dict(status='frozen_bank_incomplete',search_complete=False,final=view())},
                          {'DS23-0004':dict(status='complete',reference=view(.01),candidate=view(.01))})
        decision=promotion(rows,comparisons(rows),{'DS23-0004'},audit_passed=True)
        self.assertFalse(decision['all_scientific_completed'])
        self.assertTrue(decision['computational_eligibility'])
        self.assertTrue(decision['eligible'])
        provisional=promotion(rows,comparisons(rows),{'DS23-0004'})
        self.assertIsNone(provisional['computational_eligibility'])
        self.assertIsNone(provisional['eligible'])
        missing=promotion(rows,comparisons(rows),{'DS23-0004','absent'},audit_passed=True)
        self.assertFalse(missing['eligible'])

    def test_constant_paired_shift_block_intervals(self):
        changes=[dict(case=str(i),captured_utc_ns=i,arm=arm,baseline='reference',
                      baseline_error_km=1.,ordinary_error_km=1.25,delta_error_km=.25)
                 for arm in ARMS for i in range(25)]
        first=block_intervals(changes,draws=10)
        self.assertEqual(first,block_intervals(changes,draws=10))
        self.assertTrue(all(r['lower_delta_km']==.25 and r['upper_delta_km']==.25 for r in first))

    def test_error_canary_exact_published_helper(self):
        # Extract only the published pure helper; importing its runner would load inference code.
        import math
        from report_full import position_error
        path=Path('/srv/bulk/leo/research/algo04-candidate-20261023/source/upstream_tools/report_algo02_ds23.py')
        tree=ast.parse(path.read_text())
        helper=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='position_error')
        namespace={'math':math,'REFERENCE':REFERENCE}
        exec(compile(ast.Module(body=[helper],type_ignores=[]),str(path),'exec'),namespace)
        points=[REFERENCE,(0.,0.),(-37.,122.),(37.85,-122.48),(90.,180.),(-90.,-180.)]
        maximum=max(abs(position_error(p)-namespace['position_error'](p)) for p in points)
        self.assertEqual(maximum,0.)


if __name__=='__main__': unittest.main()
