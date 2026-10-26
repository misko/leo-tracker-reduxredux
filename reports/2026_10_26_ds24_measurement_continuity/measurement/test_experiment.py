"""Owned construction/selection/actual graph-port checks; no detector invocation."""
import inspect
import json
import unittest

import numpy as np
import experiment as e


class MeasurementTests(unittest.TestCase):
    def test_template_boundary_mismatch_is_reproduced_not_repaired(self):
        a, b = e.frame('sampled_deployed'), e.frame('sampled_right')
        bad = np.flatnonzero(abs(a-b) > 5e-7)
        self.assertEqual(len(bad), 68)
        self.assertTrue(np.all(bad % 44 == 0))
        self.assertLess(float(max(abs(a[np.setdiff1d(np.arange(len(a)), bad)]-
                                    b[np.setdiff1d(np.arange(len(a)), bad)]))), 5e-7)

    def test_deployed_frame_anchors_are_rounded_per_frame(self):
        y = e.waveform('sampled_deployed', 127)
        f = e.frame('sampled_deployed')
        anchors = [127+round(k*e.PERIOD) for k in range(14)]
        self.assertEqual(set(np.diff(anchors)), {13333, 13334})
        for start in anchors:
            np.testing.assert_array_equal(y[start+88:start+13288], f[88:13288])

    def test_global_carrier_not_reset_each_window(self):
        s = e.sources(1., (127, 127))[0]
        t = np.array([1.25, 1.25+1/e.RATE])
        a = e.carrier(s, t)
        expected = np.exp(2j*np.pi*((s['cfo0']+1.25*s['rate'])*1/e.RATE+
                                  .5*s['rate']/e.RATE**2))
        self.assertLess(abs(a[1]/a[0]-expected), 5e-10)
        self.assertGreater(abs(a[0]-e.carrier(s, 0.)), .01)

    def test_noise_seed_is_paired_and_receivers_independent(self):
        a, b = e.noise(3), e.noise(3)
        np.testing.assert_array_equal(a, b)
        self.assertFalse(np.array_equal(a[:, 0], a[:, 1]))
        self.assertFalse(np.array_equal(a, e.noise(4)))
        rng = np.random.default_rng(20261026)
        old = e.NOISE_RMS/np.sqrt(2)*(rng.normal(size=(e.COUNT, 2))+
                                     1j*rng.normal(size=(e.COUNT, 2)))
        np.testing.assert_array_equal(e.noise(0, closure=True), old)

    def test_synthesis_quantization_and_waveform_pairing(self):
        s = e.sources(0., (127, 127), closure=True, single=True)
        _, a = e.synthesize('sampled_deployed', 0., s, 0)
        iq, b = e.synthesize('continuous', 0., s, 0)
        self.assertEqual(a['noise_sha256'], b['noise_sha256'])
        self.assertNotEqual(a['iq_sha256'], b['iq_sha256'])
        self.assertEqual(iq.shape, (200000, 2, 2))
        self.assertEqual(b['clipping_samples'], 0)

    def test_selection_exact_gate_tie_and_no_truth_backfill(self):
        base = dict(fractional_epoch_status='complete', fractional_epoch_offset_samples=0.,
                    fractional_tracking_cfo_hz=100000., fractional_margin=.025,
                    fractional_exact_score=.5, fractional_control_score=.1)
        a, b = dict(base, candidate_rank=4), dict(base, candidate_rank=2)
        self.assertEqual(e.choose([a, b])['candidate_rank'], 2)
        self.assertIsNone(e.choose([dict(a, fractional_margin=.024999)]))
        self.assertIsNone(e.choose([dict(a, fractional_epoch_status='failed')]))
        self.assertIsNone(e.choose([]))
        from leo.analysis.research.public_tracking_points import public_tracking_points
        self.assertIn("(c[\"fractional_margin\"], -c[\"candidate_rank\"])", inspect.getsource(public_tracking_points))

    def test_archived_detector_input_ports_and_original_id_mapping(self):
        old = json.loads((e.OLD/'strong_20261026.json').read_text())
        slots = [dict(status='complete', visit=i, time_s=t, receivers=old['receivers'])
                 for i, t in enumerate(e.TIMES)]
        rows = e.rows_from_slots(slots, 'owned-smoke')
        acquired = e.rows_from_slots(slots, 'owned-smoke', acquired=True)
        self.assertEqual([r['observation_id'] for r in rows], [r['observation_id'] for r in acquired])
        self.assertEqual([r['candidate_rank'] for r in rows], [r['candidate_rank'] for r in acquired])
        result = e.actual_graph(rows, 'owned-smoke')
        self.assertEqual(result['assigned'], 32)
        self.assertEqual(set(r['observation_id'] for r in rows),
                         set(x for t in result['tracks'] for x in t['observation_ids']))
        self.assertFalse(result['qualified_capture'])

    def test_truth_ambiguity_unmatched_and_modulo(self):
        self.assertEqual(e.label(100000, [100000, 103000])['label'], 'A')
        self.assertEqual(e.label(100200, [100000, 100400])['label'], 'ambiguous')
        self.assertEqual(e.label(101500, [100000, 103000])['label'], 'unmatched')
        self.assertEqual(e.label(100000+e.config().alias_spacing_hz,
                                 [100000, 103000])['label'], 'A')

    def test_actual_graph_rejects_duplicate_ownership(self):
        rows = [dict(observation_id=f'id{i}', receiver=1, native_receiver_id='0', channel=1,
                time_s=float(i), measured_cfo_hz=100000.+200*i, actual_rf_hz=10940312500.)
                for i in range(16)]
        result = e.actual_graph(rows, 'true-line')
        self.assertEqual(result['assigned'], 16)
        self.assertEqual(len(result['tracks']), 1)


if __name__ == '__main__':
    unittest.main()
