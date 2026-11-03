import unittest
from types import SimpleNamespace
import numpy as np

from local_segments import Configuration, circular, extract


def observations(t, y, rx=None, ch=None, rf=None):
    return SimpleNamespace(times_s=np.asarray(t), measured_hz=np.asarray(y),
        receiver=np.zeros(len(t), int) if rx is None else np.asarray(rx),
        channel=np.ones(len(t), int) if ch is None else np.asarray(ch),
        rf_hz=np.full(len(t), 11e9) if rf is None else np.asarray(rf))


class SegmentTests(unittest.TestCase):
    def test_alias_crossing_curve_recovered_amid_clutter(self):
        rng=np.random.default_rng(50);t=np.arange(0.,40.,.4)
        y=circular(100000+2200*t-21*t*t+rng.normal(0,35,len(t)),Configuration().alias_period_hz)
        clutter=np.arange(4,len(t),5);y[clutter]=rng.uniform(-110000,110000,len(clutter))
        d=extract(observations(t,y));selected=set(r for p in d['selected'] for r in p['rows'])
        self.assertGreater(len(selected-set(clutter)),40)
        self.assertLess(len(selected&set(clutter)),4)
        self.assertTrue(all(p['rms_hz']<100 for p in d['selected']))

    def test_no_cross_receiver_channel_or_rf_merging(self):
        t=np.tile(np.arange(0.,20.,.5),4);group=np.repeat(np.arange(4),40)
        y=20000+300*t+7*t*t+group*1000
        obs=observations(t,y,group//2,group%2+1,11e9+group*1e6)
        d=extract(obs)
        self.assertEqual({int(group[p['rows'][0]]) for p in d['selected']},set(range(4)))
        for p in d['selected']:
            self.assertEqual(len(set(group[list(p['rows'])])),1)

    def test_deterministic_and_no_bridging_long_gaps(self):
        t=np.r_[np.arange(0.,10.,.5),np.arange(20.,30.,.5)]
        obs=observations(t,4000+200*t+5*t*t)
        first=extract(obs);self.assertEqual(first,extract(obs))
        self.assertTrue(first['selected'])
        for p in first['proposals']:
            self.assertLessEqual(np.diff(t[list(p['rows'])]).max(),4.)

    def test_input_not_mutated_and_future_values_do_not_enter_local_fit(self):
        t=np.arange(0.,80.,.5);y=2000+30*t+4*t*t;original=y.copy()
        first=extract(observations(t,y));y[t>=40]+=30000
        second=extract(observations(t,y))
        before=lambda d:[p for p in d['proposals'] if max(t[list(p['rows'])])<20]
        self.assertEqual(before(first),before(second))
        np.testing.assert_array_equal(original[:80],y[:80])

    def test_sparse_invalid_or_short_inputs_do_not_invent_support(self):
        self.assertEqual(extract(observations([],[]))['selected'],[])
        self.assertEqual(extract(observations(np.arange(5),np.arange(5)))['selected'],[])
        with self.assertRaises(ValueError):Configuration(minimum_span_s=21)
        with self.assertRaises(ValueError):extract(observations([0,np.nan],[1,2]))

    def test_crossing_curves_do_not_force_one_mixed_track(self):
        t=np.arange(0.,20.,.4)
        a=1000+1800*t+8*t*t
        b=37000-1800*t-7*t*t
        # Alternating receivers are not used to separate the two trajectories:
        # both occupy the same lane with interleaved observation times.
        tt=np.ravel(np.column_stack([t,t+.1]))
        yy=np.ravel(np.column_stack([a,b]))
        d=extract(observations(tt,yy))
        recovered=[]
        for p in d['proposals']:
            ix=np.array(p['rows']);fractions=np.bincount(ix%2,minlength=2)/len(ix)
            if fractions.max()>.85:recovered.append(int(fractions.argmax()))
        self.assertEqual(set(recovered),{0,1})

    def test_segment_inside_window_does_not_need_to_occupy_each_time_third(self):
        t=np.arange(0.,20.,.4)
        y=np.where(t<11,20000-1700*t+12*t*t,-100000+600*t)
        d=extract(observations(t,y))
        early=set(np.flatnonzero(t<11))
        self.assertTrue(any(len(early&set(p['rows']))>=20 for p in d['proposals']))


if __name__=='__main__':unittest.main()
