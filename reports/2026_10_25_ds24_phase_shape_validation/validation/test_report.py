"""Evaluator policy, missingness, ownership and release barriers on fake data."""
import copy
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import report as e


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.files = {}

    def put(self, path, value):
        path = self.root / path; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        self.files[str(path.resolve())] = e.sha(path)
        return path

    def fit(self, offset=.01, RMS=100., score=1000.):
        return dict(endpoint_latlon=[e.SITE[0]+offset, e.SITE[1]], RMS_hz=RMS,
            negative_twice_elbo=score, active_points=2, final_phase_change_s=.001)

    def fixture(self, valid=False):
        self.put('protocol.json', dict(cases=['fake']))
        baseline = {arm:self.fit() for arm in e.ARMS}
        candidate = {arm:self.fit(offset=.001 if arm == 'c0' else .05, RMS=90., score=900.) for arm in e.ARMS}
        cold = {arm:self.fit(offset=.002, RMS=99., score=999.) for arm in e.ARMS}
        def coverage(ids): return dict(accepted_observation_ids=ids, associated=len(ids), total_GLRT=4)
        cov = {name:{arm:coverage(ids) for arm in e.ARMS} for name, ids in
            [('baseline',['a','b','c']),('matched_cold_baseline',['a','b','c']),('rx1_rf50',['a','b'])]}
        comparison = dict(status='complete', case='fake', baseline=baseline, adopted=valid,
            policy_source='rx1_rf50' if valid else 'baseline', GPS_or_error_used=False,
            protocol_sha256=e.sha(self.root/'protocol.json'), seconds=3., coverage=cov,
            lost_baseline_postfit_IDs={arm:['c'] for arm in e.ARMS},
            likelihood_membership=dict(curved_unique=2,predictive_unique=1,union_unique=3,total_GLRT=4,union_ids_sha256='native'),
            results=dict(rx1_rf50=dict(arms=candidate,paired_valid=valid),
                matched_cold_baseline=dict(arms=cold,paired_valid=False)))
        self.put('fake/comparison.json', comparison)
        audit = dict(baseline_available=True,baseline_paired_valid=True,comparison_available=True)
        return comparison, audit

    def test_original_haversine_and_site_identity(self):
        import numpy as np
        self.assertEqual(e.distance(e.SITE), 0.)
        for point in ([37.85,-122.48], [0.,0.], [-37.849061591561885,57.51425031907088]):
            p,q = np.radians(np.asarray([point,e.SITE]))
            a = np.sin((p[0]-q[0])/2)**2 + np.cos(p[0])*np.cos(q[0])*np.sin((p[1]-q[1])/2)**2
            expected = float(12742*np.arcsin(np.sqrt(np.clip(a,0,1))))
            self.assertAlmostEqual(e.distance(point), expected, places=8)

    def test_pair_rejection_falls_back_exactly_despite_opposite_geographic_results(self):
        _,audit = self.fixture(valid=False)
        rows = e.case_rows(self.root,'fake',audit,self.files,dict(status='complete',seconds=10.))
        for arm in e.ARMS:
            base,policy = [next(row for row in rows if row['arm']==arm and row['variant']==v) for v in ('baseline','primary_policy')]
            self.assertEqual(policy['lat'], base['lat']); self.assertEqual(policy['lon'], base['lon'])
            self.assertEqual(policy['error_change_km'],0.); self.assertEqual(policy['RMS_change_hz'],0.)
            self.assertEqual(policy['objective_change'],0.); self.assertEqual(policy['source'],'baseline')
        raw = [row for row in rows if row['variant']=='raw_candidate']
        self.assertLess(raw[0]['error_change_km'],0.); self.assertGreater(raw[1]['error_change_km'],0.)
        self.assertTrue(all(not row['qualified'] for row in raw))

    def test_postfit_loss_is_reported_without_adding_a_policy_gate(self):
        _,audit = self.fixture(valid=True)
        rows = e.case_rows(self.root,'fake',audit,self.files,dict(status='complete'))
        for row in rows:
            self.assertEqual(row['likelihood_union_unique'],3)
            if row['variant']=='primary_policy':
                self.assertTrue(row['qualified']); self.assertTrue(row['adopted'])
                self.assertEqual(row['lost_baseline_postfit_IDs'],['c'])
                self.assertEqual(row['postfit_unique_ids'],2)

    def test_runtime_failure_keeps_qualified_baseline_and_partial_raw_arm(self):
        self.put('protocol.json',dict(cases=['fake']))
        baseline = {arm:self.fit() for arm in e.ARMS}
        self.put('family_cavity/position/fake.json',dict(status='complete',policy_arms=baseline))
        self.put('fake/rx1_rf50_c0.json',self.fit(offset=.002))
        audit = dict(baseline_available=True,baseline_paired_valid=True,comparison_available=False)
        rows = e.case_rows(self.root,'fake',audit,self.files,dict(status='execution_failed',error='bounded timeout'))
        policy = [row for row in rows if row['variant']=='primary_policy']
        self.assertTrue(all(row['error_change_km']==0. for row in policy))
        raw = [row for row in rows if row['variant']=='raw_candidate']
        self.assertIsNotNone(raw[0]['error_km']); self.assertIsNone(raw[1]['error_km'])
        summaries = e.summaries(rows,['fake'])
        self.assertTrue(all(row['selected_cases']==1 for row in summaries))

    def test_unavailable_reference_has_missing_errors_and_ecdf_keeps_denominator(self):
        self.put('protocol.json',dict(cases=['fake']))
        audit = dict(baseline_available=False,baseline_paired_valid=False,comparison_available=False)
        rows = e.case_rows(self.root,'fake',audit,self.files,dict(status='input_unqualified'))
        self.assertEqual(len(rows),8); self.assertTrue(all(row['error_km'] is None for row in rows))
        summary = e.summaries(rows,['fake'])
        self.assertTrue(all(row['errors_km']['n_available']==0 and row['selected_cases']==1 for row in summary))
        self.assertEqual(e.ecdf([.5,None,1.,None],4),([.5,1.],[25.,50.]))

    def test_duplicate_likelihood_and_postfit_IDs_fail(self):
        comparison,audit = self.fixture(valid=True)
        comparison['likelihood_membership']['union_unique']=2
        self.put('fake/comparison.json',comparison)
        with self.assertRaisesRegex(ValueError,'likelihood'): e.case_rows(self.root,'fake',audit,self.files,dict(status='complete'))
        with self.assertRaisesRegex(ValueError,'postfit'): e.postfit_metrics(dict(accepted_observation_ids=['x','x'],associated=2,total_GLRT=3),None)

    def authorization_fixture(self):
        comparison,audit = self.fixture()
        self.put('execution.json',dict(all_terminal=True,rows=[dict(case='fake',status='complete')]))
        for name in ('report.py','test_report.py'): (self.root/name).write_text('synthetic fixture source')
        e.freeze(self.root)
        seal = dict(all_selected_terminal=True,protocol_immutable=True,original_gates_replayed=True,bindings_audited=True,
            protocol_sha256=e.sha(self.root/'protocol.json'),files=copy.deepcopy(self.files),per_case={'fake':audit})
        path = self.root/'RF_seal.json'; path.write_text(json.dumps(seal))
        return path,seal

    def test_RF_prerequisites_precede_endpoint_parsing(self):
        path,seal = self.authorization_fixture(); seal['original_gates_replayed']=False; path.write_text(json.dumps(seal))
        with patch.object(e,'read',wraps=e.read) as reads:
            with self.assertRaisesRegex(ValueError,'original_gates'): e.authorize(self.root,path)
            self.assertFalse(any(Path(call.args[0]).name=='comparison.json' for call in reads.call_args_list))

    def test_binding_mutation_and_nonterminal_denominator_fail_before_evaluation(self):
        path,seal = self.authorization_fixture()
        (self.root/'fake/comparison.json').write_text('changed')
        with self.assertRaisesRegex(ValueError,'artifact changed'): e.authorize(self.root,path)
        self.put('fake/comparison.json',dict(fake=True)); seal['files']=copy.deepcopy(self.files)
        self.put('execution.json',dict(all_terminal=True,rows=[])); seal['files']=copy.deepcopy(self.files); path.write_text(json.dumps(seal))
        with self.assertRaisesRegex(ValueError,'denominator'): e.authorize(self.root,path)

    def test_evaluator_mutation_blocks_authorized_inputs(self):
        path,_ = self.authorization_fixture(); (self.root/'report.py').write_text('changed evaluator')
        with self.assertRaisesRegex(ValueError,'evaluator changed'): e.authorize(self.root,path)

    def test_complete_report_writes_raw_rejected_outliers_without_selecting_them(self):
        path,_ = self.authorization_fixture()
        with redirect_stdout(io.StringIO()): e.main(self.root,path)
        summary = e.read(self.root/'report/summary.json')
        self.assertEqual(summary['adopted_count'],0)
        for item in summary['summaries']:
            self.assertEqual(item['selected_cases'],1)
            if item['variant']=='primary_policy': self.assertEqual(item['paired_error_changes_km']['mean'],0.)
            if item['variant']=='raw_candidate': self.assertEqual(item['unqualified_raw_endpoints'],1)
        raw_fitted = next(row for row in summary['summaries'] if row['variant']=='raw_candidate' and row['arm']=='fitted_c')
        self.assertGreater(raw_fitted['errors_km']['maximum'],5.)
        for name in ('positions.csv','FINDINGS.md','error_ecdf.png','paired_errors.png','RF_vs_position.png','seal.json'):
            self.assertTrue((self.root/'report'/name).is_file())


if __name__=='__main__': unittest.main()
