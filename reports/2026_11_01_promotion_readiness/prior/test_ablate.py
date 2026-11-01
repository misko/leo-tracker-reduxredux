"""Artifact-level scientific invariants for this fixed local experiment."""
import json
from pathlib import Path
import unittest
import numpy as np

OUT=Path(__file__).resolve().parent


class AblationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit=json.loads((OUT/'intervention_audit.json').read_text())

    def test_original_replays_published_normalized_score(self):
        base=json.loads((OUT.parents[1]/'2026_11_01_reconsideration_population/DS26-0058/baseline.json').read_text())
        for arm in ('c0','fitted_c'):
            self.assertAlmostEqual(self.audit['original'][arm]['objective'],base[arm]['objective'],places=5)

    def test_nonintervened_dimensions_and_native_evidence_preserved(self):
        cells=json.loads((OUT/'spec.json').read_text())['cells']
        for arm in ('c0','fitted_c'):
            old,new=self.audit['original'][arm],self.audit['complete'][arm]
            for name,parts in cells.items():
                row=self.audit[name][arm]
                self.assertEqual(row['native_keep_sha256'],old['native_keep_sha256'])
                np.testing.assert_array_equal(row['means'],(new if 'mean' in parts else old)['means'])
                np.testing.assert_array_equal(row['widths'],(new if 'width' in parts else old)['widths'])
                self.assertEqual(row['families'],(new if 'predictive' in parts else old)['families'])
                self.assertTrue(np.isfinite(row['objective']) and np.isfinite(row['normalization_constant']))
                for j,m in row['metadata'].items():
                    self.assertEqual(m['radial_sigma_km'],(new if 'radial' in parts else old)['metadata'][j]['radial_sigma_km'])
                    self.assertEqual(m['cross_sigma_km'],(new if 'cross' in parts else old)['metadata'][j]['cross_sigma_km'])

    def test_zero_mean_intervention_is_exact_null(self):
        for arm in ('c0','fitted_c'):
            self.assertEqual(self.audit['mean'][arm]['objective'],self.audit['original'][arm]['objective'])
            np.testing.assert_array_equal(self.audit['mean'][arm]['means'],0.)

    def test_causal_export_uses_only_prior_72h_availability(self):
        data=json.loads((OUT/'history/export.json').read_text());cutoff=data['request']['cutoff']
        for n,r in data['export']['chosen'].items():
            self.assertLessEqual(r['collected_utc_ns'],cutoff)
            self.assertGreaterEqual(r['collected_utc_ns'],cutoff-int(72*3.6e12))
            self.assertGreaterEqual(data['request']['latest'][n]-r['epoch_utc_ns'],1e9)

    def test_predictive_subablation_replays_whole_mixture(self):
        data=json.loads((OUT/'local_sensitivity.json').read_text())
        for arm in ('c0','fitted_c'):
            for cell,parent in [('original','original'),('complete','predictive')]:
                row=next(r for r in data['predictive_subcells'] if r['arm']==arm and r['cell']==cell)
                self.assertAlmostEqual(row['scores'][0],self.audit[parent][arm]['mixture_objective'],places=6)

    def test_complete_matches_saved_two_start_history_continuation(self):
        saved=json.loads((OUT.parents[1]/'2026_11_01_reconsideration_population/DS26-0058/history_candidate.json').read_text())
        actual=json.loads((OUT/'results/complete.json').read_text())['pair']
        for arm in ('c0','fitted_c'):
            expected=min((r for r in saved if r['arm']==arm and r['qualified']),key=lambda r:r['objective'])
            self.assertAlmostEqual(actual[arm]['objective'],expected['objective'],delta=.05)
            self.assertAlmostEqual(actual[arm]['error_m'],expected['error_m'],delta=2.)

    def test_all_planned_fits_have_matched_starts_and_native_evidence(self):
        spec=json.loads((OUT/'spec.json').read_text());all_ids=set();all_owners=set()
        for name in spec['cells']:
            rows=json.loads((OUT/'fits'/f'{name}.json').read_text())
            self.assertEqual({(r['arm'],r['start']) for r in rows},
                {(a,s) for a in ('c0','fitted_c') for s in ('c0','fitted_c')})
            self.assertTrue(all(r['status']=='complete' for r in rows))
            all_ids.update(r['native_ids_sha256'] for r in rows)
            all_owners.update(r['owners_sha256'] for r in rows)
        self.assertEqual(len(all_ids),1)
        self.assertEqual(len(all_owners),1)


if __name__=='__main__':unittest.main()
