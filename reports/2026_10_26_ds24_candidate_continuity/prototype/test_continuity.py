import copy
import unittest
import numpy as np
import continuity as c


def fixture(times=tuple(range(16)), sources=2):
    rows = []
    fs = 10_000_000
    for i, t in enumerate(times):
        w = dict(window_id=f'w{i}', observation_id=f'o{i}', physical_acquisition_id=f'a{i}',
            receiver_id='0', channel=1, actual_rf_hz=10940312500., time_s=float(t)+.01,
            window_start_counter=round(t*fs), origin_counter=0, candidates=[])
        for j in range(sources):
            local = (100+2*t) if j == 0 else (800-3*t)
            w['candidates'].append(dict(candidate_id=f'w{i}c{j}', candidate_rank=j,
                cfo_hz=(100000+200*t) if j == 0 else (103000-200*t),
                local_epoch_samples=local, global_epoch_samples=c.global_epoch(w['window_start_counter'], 0, local, fs),
                margin=.8 if (i < 8) == (j == 0) else .6, acquired_cfo_hz=None))
        rows.append(w)
    return rows


class ContinuityTests(unittest.TestCase):
    def test_large_native_counter_exact_reduction(self):
        origin = 2**59+3; start = origin+10000017
        expected = (((10000017*750) % 10_000_000)/750+127.25) % (10_000_000/750)
        self.assertEqual(c.global_epoch(start, origin, 127.25, 10_000_000), expected)
        self.assertEqual(c.global_epoch(start+2**45, origin+2**45, 127.25, 10_000_000), expected)

    def test_counter_and_origin_common_translation(self):
        a = fixture(sources=1); b = copy.deepcopy(a)
        for w in b:
            w['window_start_counter'] += 2**55; w['origin_counter'] += 2**55
        x = c.select_paths(a, 10_000_000, True); y = c.select_paths(b, 10_000_000, True)
        self.assertEqual([p['score'] for p in x['paths']], [p['score'] for p in y['paths']])

    def test_global_phase_changes_when_device_time_not_payload_time(self):
        a = c.global_epoch(20000333, 0, 127., 10_000_000)
        b = c.global_epoch(20000000, 0, 127., 10_000_000)
        self.assertAlmostEqual(float(c.circular(a-b, 10_000_000/750)), 333., places=8)

    def test_whole_alias_and_frame_period_translation(self):
        a = fixture(sources=1); b = copy.deepcopy(a)
        for w in b:
            for n in w['candidates']:
                n['cfo_hz'] += c.SETTINGS['cfo_period_hz']
                n['local_epoch_samples'] += 10_000_000/750
                n['global_epoch_samples'] = c.global_epoch(w['window_start_counter'], 0,
                                                          n['local_epoch_samples'], 10_000_000)
        x = c.select_paths(a, 10_000_000, True); y = c.select_paths(b, 10_000_000, True)
        self.assertEqual([n['candidate_id'] for n in x['paths'][0]['nodes']],
                         [n['candidate_id'] for n in y['paths'][0]['nodes']])
        self.assertAlmostEqual(x['paths'][0]['score'], y['paths'][0]['score'], places=8)

    def test_candidate_exclusivity_without_window_count_inflation(self):
        w = fixture(); a = c.select_paths(w, 10_000_000, True)
        ids = [n['candidate_id'] for p in a['paths'] for n in p['nodes']]
        self.assertEqual(len(ids), len(set(ids)))
        for p in a['paths']:
            self.assertEqual(len(p['nodes']), len({n['window_id'] for n in p['nodes']}))
        self.assertLessEqual(a['unique_receiver_windows'], 16)
        self.assertLessEqual(a['candidate_hypotheses_selected'], 32)
        self.assertLessEqual(len(a['paths']), 2)

    def test_crossing_fixture_deterministic_not_a_detector_result(self):
        w = fixture()
        a = c.select_paths(w, 10_000_000, True); b = c.select_paths(w, 10_000_000, True)
        self.assertEqual(a, b)
        self.assertEqual(a['unique_receiver_windows'], 16)
        self.assertEqual(len(a['paths']), 2)
        # Symmetric known paths need not be ordered by their arbitrary source name.
        ranks = [set(n['candidate_rank'] for n in p['nodes']) for p in a['paths']]
        self.assertTrue(all(len(x) == 1 for x in ranks))
        self.assertEqual(set.union(*ranks), {0, 1})

    def test_gap_resets_and_empty_windows_preserved(self):
        w = fixture(times=tuple(range(8))+tuple(range(20, 28)), sources=1)
        a = c.select_paths(w, 10_000_000, True)
        self.assertEqual(len(a['paths']), 2)
        self.assertTrue(all(max(q['elapsed_s'] for q in p['intervals']) <= 10 for p in a['paths']))
        for n in w: n['candidates'] = []
        b = c.select_paths(w, 10_000_000, True)
        self.assertEqual(len(b['paths']), 0)
        self.assertEqual(len(b['windows_without_selected_path']), 16)

    def test_linear_epoch_drift_is_allowed(self):
        w = fixture(sources=1)
        for n in w:
            local = 127.+75*n['time_s']
            n['candidates'][0]['local_epoch_samples'] = local
            n['candidates'][0]['global_epoch_samples'] = c.global_epoch(n['window_start_counter'], 0, local, 10_000_000)
        result = c.select_paths(w, 10_000_000, True)
        self.assertEqual(len(result['paths'][0]['nodes']), 16)
        self.assertTrue(all(abs(e['epoch_slope_samples_s']-75) < 1e-8 for e in result['paths'][0]['intervals']))

    def test_duplicate_nonfinite_and_wrong_clock_rejected(self):
        for kind in ('duplicate', 'nonfinite', 'clock'):
            w = fixture()
            if kind == 'duplicate': w[1]['candidates'][0]['candidate_id'] = w[0]['candidates'][0]['candidate_id']
            if kind == 'nonfinite': w[0]['candidates'][0]['cfo_hz'] = float('nan')
            if kind == 'clock': w[0]['candidates'][0]['global_epoch_samples'] += 10
            with self.assertRaises(ValueError): c.select_paths(w, 10_000_000, True)

    def test_winner_gate_and_rank_tie_no_truth(self):
        w = fixture(sources=2)
        for n in w:
            for p in n['candidates']: p['margin'] = .025
        self.assertTrue(all(n['candidate_rank'] == 0 for n in c.winner_rows(w)))
        self.assertTrue(all('source' not in n for n in c.winner_rows(w)))


if __name__ == '__main__':
    unittest.main()
