"""Owned tests for nomination and immutable complete-point correction policy."""
import unittest
from prepare import nominate,quantile_ids


class NominationTests(unittest.TestCase):
    def test_duration_count_key_and_complete_both_arms(self):
        tracks=[]
        for rx in (1,2):
            for ch in (7,8):
                for key,times in [('Z',[0,10]),('A',[0,5,10]),('B',[0,5,10]),('excluded',[0,100])]:
                    ids=[f'{rx}-{ch}-{key}-{i}' for i in range(len(times))]
                    tracks.append(dict(key=f'RX{rx}CH{ch}{key}',receiver=rx,channel=ch,times=times,observation_ids=ids))
        ids={o for t in tracks for o in t['observation_ids']}
        second=ids-{o for t in tracks if 'excluded' in t['key'] for o in t['observation_ids'][-1:]}
        selected,candidates=nominate(tracks,range(len(tracks)),dict(c0=ids,fitted_c=second))
        self.assertEqual(len(selected),4)
        self.assertTrue(all(s['owner'].endswith('A') for s in selected))
        self.assertEqual(sum(not c['eligible'] for c in candidates),4)
        self.assertEqual(sum(s['count'] for s in selected),12)

    def test_fixed_time_quantiles_not_rank_or_outcome(self):
        owner=dict(points=[dict(native_id='c',time_s=10.),dict(native_id='a',time_s=0.),dict(native_id='b',time_s=3.)])
        self.assertEqual(quantile_ids(owner),['b','c'])

    def test_missing_cell_fails_without_replacement(self):
        with self.assertRaises(ValueError):
            nominate([],[],dict(c0=[],fitted_c=[]))


if __name__=='__main__':
    unittest.main()
