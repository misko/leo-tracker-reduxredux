"""Synthetic checks for streaming state and the native replay's cutoff."""

from io import StringIO
import json
import unittest

import numpy as np

from native_archive import ARCHIVE_BLOCK_CHARS, SAMPLE_RATE_HZ
from prototype import Replay
from tracker import MAX_LIFETIME_S, MAX_SUPPORT, PERIOD, Tracker, distinct_candidates, wrap


LANE = (1, 1, 10.7e9)


def candidate(hz, margin, rank, *, passed=True):
    return {'fractional_tracking_cfo_hz': hz, 'fractional_margin': margin,
            'candidate_rank': rank, 'passed_fractional_margin_gate': passed}


def trajectory(now):
    return 94_000. - 3200. * now + 9. * now * now


class TrackerTests(unittest.TestCase):
    def test_alias_deduplication_keeps_best_four_distinct_peaks(self):
        values = [candidate(9000, 11, 0, passed=False), candidate(2000 + PERIOD, 9, 1),
                  candidate(1980, 8, 2), candidate(4000, 7, 3), candidate(6000, 7, 4),
                  candidate(8000, 6, 5), candidate(12_000, 5, 6)]
        np.testing.assert_allclose(distinct_candidates(values), [2000, 4000, 6000, 8000])

    def test_two_curved_tracks_unwrap_and_compact_without_mixing(self):
        tracker = Tracker()
        for now in np.arange(250) * .4:
            value = trajectory(now)
            tracker.ingest(now, LANE, [wrap(value), wrap(value - 35_000.)])
        doc, info = tracker.document()
        self.assertEqual(info['confirmations'], 2)
        self.assertEqual(info['first_track_confirmed_midpoint_air_s'], 2.)
        self.assertEqual(info['solver_segments'], 2)
        self.assertEqual(info['peak_active_total'], 2)
        for item, offset in zip(doc['tracks'], (0, 35_000), strict=True):
            self.assertLessEqual(len(item['times']), MAX_SUPPORT)
            self.assertEqual(item['times'][0], 0.)
            self.assertEqual(item['times'][-1], tracker.latest)
            np.testing.assert_allclose(item['values'], trajectory(item['times']) - offset, atol=1e-9)

    def test_simultaneous_competition_skips_candidate(self):
        tracker = Tracker()
        for now in np.arange(10) * .4:
            f = 2000. - 500.*now
            tracker.ingest(now, LANE, [-f, f])
        tracker.ingest(4., LANE, [0.])
        self.assertEqual(tracker.stats['ambiguous_candidates_skipped'], 1)
        self.assertEqual([track.hits for track in tracker.lanes[LANE]], [10, 10])

    def test_absolute_lifetime_retires_even_continuously_linked_track(self):
        tracker = Tracker()
        for now in np.arange(185.):
            tracker.ingest(now, LANE, [wrap(trajectory(now))])
        self.assertEqual(len(tracker.retired), 1)
        self.assertGreater(tracker.lanes[LANE][0].samples[0][0], MAX_LIFETIME_S)
        with self.assertRaisesRegex(ValueError, 'nondecreasing'):
            tracker.ingest(0., LANE, [])

    def test_archive_applies_end_of_probe_cutoff_before_candidate_parse(self):
        cap = int(100. * SAMPLE_RATE_HZ)
        document = dict(clock_anchor={'sample_counter': 0, 'before': {'realtime_ns': 10},
                                      'after': {'realtime_ns': 20}},
                        delivery_clocks=['-' * ARCHIVE_BLOCK_CHARS], last_sample_counter=cap,
                        source=dict(probe_ms=20, probes=[], sample_rate_hz=SAMPLE_RATE_HZ, timing=None))
        for i, counter in enumerate((0, SAMPLE_RATE_HZ*80)):
            document['source']['probes'].append(dict(actual_rf_hz=LANE[2], candidates=[], channel=1,
                                                      receiver_id=0, valid_start_counter=counter, visit_index=i))
        data = json.dumps(document, separators=(',', ':'))
        prefix, suffix = data.rsplit('"candidates":[]', 1)
        replay = Replay(StringIO(prefix + '"candidates":invalid' + suffix))
        replay.advance(.019)
        self.assertEqual(replay.tracker.stats['probes'], 0)
        replay.advance(60.)
        self.assertEqual(replay.latest_probe_end, .02)
        self.assertEqual(replay.tracker.stats['probes'], 1)
        with self.assertRaises(json.JSONDecodeError):
            replay.advance(85.)


if __name__ == '__main__':
    unittest.main()
