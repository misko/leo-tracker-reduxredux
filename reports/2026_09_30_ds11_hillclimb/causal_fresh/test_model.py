import copy
import unittest
from unittest.mock import patch

import numpy as np

import model


class CausalFreshTests(unittest.TestCase):
    def setUp(self):
        self.grid = [-5., 0., 5.]
        self.config = dict(geographic_prior_center_deg=[38., -122.], timing_grid_s=self.grid)
        self.times = np.linspace(-2, 2, 13)
        receiver, up = model.fast.baseline.site(38., -122.)
        position = np.zeros((2, 3, 13, 3))
        velocity = np.zeros_like(position)
        for candidate in range(2):
            for node, tau in enumerate(self.grid):
                t = self.times + tau
                v = np.array([2., -3., 1.]) + candidate*.1
                position[candidate, node] = receiver + 600*up + t[:, None]*v
                velocity[candidate, node] = v + .001*t[:, None]
        track = dict(track_id='one', candidate_position_km=position,
                     candidate_velocity_km_s=velocity, mask=np.arange(13)%3 != 0,
                     catalogue_size=8000, times_s=self.times)
        self.doc = dict(session_id='scan-test', tracks=[track])
        predicted, _ = model.fast.Stationary(self.doc, self.config).prediction(track, np.zeros(3))
        track['y'] = predicted[0]+300+np.sin(self.times)*10
        self.manifest = dict(session_id='scan-test', timing_grid_s=self.grid,
                             tracks=[dict(track_id='one', index=0, slots_key='slots',
                                          position_key='pos', velocity_key='vel')])
        self.arrays = dict(slots=np.array([0]), pos=position[:1].copy(), vel=velocity[:1].copy())

    def test_no_delta_exact_original_score_gradient(self):
        patched = model.apply_arrays(self.doc, self.manifest, self.arrays, self.grid)
        x = np.array([.1, -.2, .3])
        old = model.Model(self.doc, self.config, {}).evaluate(x)
        new = model.Model(patched, self.config, {}).evaluate(x)
        self.assertEqual(new['score'], old['score'])
        np.testing.assert_array_equal(new['gradient'], old['gradient'])

    def test_state_copy_preserves_other_slots_measurements_mask(self):
        before = copy.deepcopy(self.doc)
        self.arrays['pos'] += .1
        patched = model.apply_arrays(self.doc, self.manifest, self.arrays, self.grid)
        for field in ('candidate_position_km', 'candidate_velocity_km_s', 'mask', 'y'):
            np.testing.assert_array_equal(self.doc['tracks'][0][field], before['tracks'][0][field])
        np.testing.assert_array_equal(patched['tracks'][0]['candidate_position_km'][1],
                                      before['tracks'][0]['candidate_position_km'][1])
        self.assertIs(patched['tracks'][0]['y'], self.doc['tracks'][0]['y'])
        self.assertIs(patched['tracks'][0]['mask'], self.doc['tracks'][0]['mask'])
        self.assertEqual(patched['tracks'][0]['catalogue_size'], 8000)

    def test_rejects_bad_session_grid_track_slots_and_values(self):
        for field, bad in [('session_id', 'other'), ('timing_grid_s', [-4., 0., 4.])]:
            manifest = dict(self.manifest, **{field: bad})
            with self.assertRaises(ValueError):
                model.apply_arrays(self.doc, manifest, self.arrays, self.grid)
        manifest = copy.deepcopy(self.manifest)
        manifest['tracks'][0]['track_id'] = 'different'
        with self.assertRaises(ValueError):
            model.apply_arrays(self.doc, manifest, self.arrays, self.grid)
        for slots in (np.array([0, 0]), np.array([-1]), np.array([2]), np.array([0.])):
            with self.assertRaises(ValueError):
                model.apply_arrays(self.doc, self.manifest, dict(self.arrays, slots=slots), self.grid)
        bad = self.arrays['pos'].copy()
        bad[0, 0, 0, 0] = np.nan
        with self.assertRaises(ValueError):
            model.apply_arrays(self.doc, self.manifest, dict(self.arrays, pos=bad), self.grid)

    def test_fresh_bank_derivative_and_held_independence(self):
        self.arrays['pos'] += .07
        patched = model.apply_arrays(self.doc, self.manifest, self.arrays, self.grid)
        engine = model.Model(patched, self.config, {})
        x = np.array([.1, -.2, .3])
        value = engine.evaluate(x)
        for axis in range(3):
            delta = np.eye(3)[axis]*1e-4
            numeric = (engine.evaluate(x+delta, False)['score']-engine.evaluate(x-delta, False)['score'])/2e-4
            self.assertAlmostEqual(numeric, value['gradient'][axis], places=5)
        patched['tracks'][0]['y'] = patched['tracks'][0]['y'].copy()
        patched['tracks'][0]['y'][~patched['tracks'][0]['mask']] += 10000
        self.assertEqual(engine.evaluate(x)['score'], value['score'])

    def test_completion_binds_bytes_session_and_actual_publication_time(self):
        document = dict(self.doc, start_utc_ns=300_000_000_000)
        manifest = dict(self.manifest, index=10, capture_start_utc_ns=document['start_utc_ns'])
        proof = dict(index=10, session=document['session_id'], capture_start_utc_ns=document['start_utc_ns'],
                     journal_published_unix_s=299., snapshot_collected_utc_ns=298_000_000_000,
                     qualified=True, archive_path='unused', snapshot_sha256='exact', provider='space-track')
        manifest['selected_snapshot'] = dict(provider='space-track', collected_utc_ns=298_000_000_000,
                                            sha256='exact', archive_path='unused')
        def envelope(row):
            return dict(schema='ds11-capture-start-snapshot-completion-proof/v1', scans=[row])
        with patch.object(model, 'digest', return_value='exact'):
            model.validate_completion(manifest, document, envelope(proof))
            for field, value in [('session', 'other'), ('capture_start_utc_ns', 400_000_000_000),
                                 ('journal_published_unix_s', 300.), ('journal_published_unix_s', 297.),
                                 ('qualified', False), ('snapshot_sha256', 'different')]:
                with self.assertRaises(ValueError):
                    model.validate_completion(manifest, document, envelope(dict(proof, **{field:value})))
            bad_manifest = copy.deepcopy(manifest)
            bad_manifest['selected_snapshot']['sha256'] = 'different'
            with self.assertRaises(ValueError):
                model.validate_completion(bad_manifest, document, envelope(proof))
