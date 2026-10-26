"""Owned causal, counter, ambiguity and uncertainty checks; no raw dependencies."""
import copy
import unittest
import study


def candidate(rank, epoch, cfo, margin=.1):
    return dict(candidate_rank=rank, integer_epoch_sample=int(epoch),
                fractional_epoch_offset_samples=epoch - int(epoch), fractional_tracking_cfo_hz=cfo,
                fractional_margin=margin, passed_fractional_margin_gate=margin >= .025)


class NaturalRevisitTests(unittest.TestCase):
    def fixture(self):
        rate = 10000000
        header = dict(sample_rate_hz=rate, receiver_id=0, channel=7, edge='lower', target_start_counter=20000000)
        earlier = []
        for counter in [5000000, 10000000, 15000000]:
            t = counter / rate
            ep = (300 + 4 * t - counter) % (rate / 750)
            earlier.append(dict(valid_start_counter=counter, receiver_id=0, channel=7, edge='lower',
                                candidates=[candidate(1, ep, 100000 + 100 * t)]))
        return header, earlier

    def test_native_counter_drift_and_causality(self):
        header, earlier = self.fixture()
        result = study.forecast(header, earlier)
        mode = result['modes'][0]
        self.assertEqual(result['status'], 'available')
        self.assertAlmostEqual(mode['linear']['CFO_hz'], 100200, places=6)
        self.assertAlmostEqual(study.wrap(mode['linear']['epoch_samples'] - (308 - 20000000) % (1e7 / 750), 1e7 / 750), 0, places=6)
        self.assertGreater(mode['CFO_fit']['heuristic_half_width_3scale'], 150)
        earlier[-1]['valid_start_counter'] = header['target_start_counter']
        with self.assertRaises(ValueError):
            study.forecast(header, earlier)

    def test_target_response_redaction_and_rank_policy(self):
        header, earlier = self.fixture()
        original = study.forecast(header, earlier)
        changed = dict(header, candidates=[candidate(0, 900, -999999)])
        self.assertEqual(original, study.forecast(changed, earlier))
        for probe in earlier:
            alias = copy.deepcopy(probe['candidates'][0])
            alias.update(candidate_rank=0, fractional_margin=.026)
            probe['candidates'].append(alias)
        self.assertEqual(study.forecast(header, earlier)['modes'][0]['seed_rank'], 0)

    def test_ambiguous_and_absent_modes_retained(self):
        header, earlier = self.fixture()
        distinct = copy.deepcopy(earlier[0]['candidates'][0])
        distinct.update(candidate_rank=2, fractional_tracking_cfo_hz=distinct['fractional_tracking_cfo_hz'] + 1000)
        earlier[0]['candidates'].append(distinct)
        result = study.forecast(header, earlier)
        self.assertEqual(result['modes'][0]['status'], 'ambiguous_earlier_matches')
        self.assertIsNone(result['primary_mode'])
        earlier[0]['candidates'] = []
        self.assertEqual(study.forecast(header, earlier)['modes'][0]['status'], 'missing_earlier_matches')


if __name__ == '__main__':
    unittest.main()
