import copy
import unittest
import predictor as p


def fabricated():
    rate = 10000000
    base = 1700000000000
    header = dict(prediction_id='fabricated/CH7/RX0', case='fabricated', channel=7, receiver_id=0,
        edge='lower', sample_rate_hz=rate, window_samples=200000, start_counter=base + 20000000,
        stop_counter=base + 20200000, generation='fabricated', source_id='fabricated-no-IQ')
    history = []
    for i, offset in enumerate([5000000, 10000000, 15000000]):
        t = offset / rate
        ep = (300 + 4 * t - offset) % (rate / 750)
        candidate = dict(candidate_rank=0, integer_epoch_sample=int(ep), fractional_epoch_offset_samples=ep-int(ep),
            fractional_tracking_cfo_hz=100000 + 100*(t+.01), fractional_margin=.1,
            passed_fractional_margin_gate=True)
        history.append(dict(valid_start_counter=base+offset, visit_index=i, probe_index=0,
            receiver_id=0, channel=7, edge='lower', candidates=[candidate]))
    return header, history


class SparsePredictionTests(unittest.TestCase):
    def test_rates_origin_and_midpoint_propagation(self):
        h, earlier = fabricated()
        f = p.predict(h, earlier)
        mode = f['modes'][0]
        self.assertEqual(mode['donor_count'], 3)
        self.assertAlmostEqual(mode['full']['CFO_hz'], 100201, places=6)
        self.assertAlmostEqual(mode['halves'][0]['CFO_hz'], 100200.5, places=6)
        self.assertAlmostEqual(mode['halves'][1]['CFO_hz'], 100201.5, places=6)
        full = mode['full']['epoch_samples']
        self.assertAlmostEqual(p.wrap(mode['halves'][0]['epoch_samples']-full, 1e7/750), 0, places=6)
        self.assertAlmostEqual(p.wrap(mode['halves'][1]['epoch_samples']-(full-100000+.04), 1e7/750), 0, places=6)
        self.assertAlmostEqual(mode['model']['timing_fit']['rate_per_s'], 4, places=6)

    def test_missing_visits_and_one_donor(self):
        h, earlier = fabricated()
        earlier[1]['candidates'] = []
        mode = p.predict(h, earlier)['modes'][0]
        self.assertEqual(mode['donor_count'], 2)
        self.assertEqual(mode['missed_visits_between_donors'], 1)
        earlier[-1]['candidates'] = []
        mode = p.predict(h, earlier)['modes'][0]
        self.assertEqual(mode['status'], 'one_donor_fallback')
        self.assertEqual(mode['missed_visits_after_latest'], 2)
        self.assertGreater(mode['full']['timing_sigma_samples'], 200)

    def test_target_redaction_cell_and_causal_guards(self):
        h, earlier = fabricated()
        result = p.predict(h, earlier)
        self.assertEqual(result, p.predict(dict(h, candidates=[dict(CFO_hz=9e20)]), earlier))
        earlier[-1]['valid_start_counter'] = h['start_counter']
        with self.assertRaises(ValueError):
            p.predict(h, earlier)

    def test_alternatives_caps_and_rank_alias_policy(self):
        h, earlier = fabricated()
        for row in earlier:
            alias = copy.deepcopy(row['candidates'][0]);alias['candidate_rank']=1
            row['candidates'].append(alias)
            other = copy.deepcopy(alias);other['candidate_rank']=2;other['fractional_tracking_cfo_hz']+=1000
            row['candidates'].append(other)
        result = p.predict(h, earlier)
        self.assertGreater(len(result['modes']), 1)
        self.assertLessEqual(len(result['modes']), 8)
        self.assertGreater(result['ambiguous_extensions'], 0)
        self.assertTrue(all(d['candidate_rank'] != 1 for m in result['modes'] for d in m['donors']))
        for last in {m['donors'][-1]['observation_id'] for m in result['modes']}:
            self.assertLessEqual(sum(m['donors'][-1]['observation_id']==last for m in result['modes']), 2)


if __name__ == '__main__':
    unittest.main()
