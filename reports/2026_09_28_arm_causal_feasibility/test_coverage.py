import unittest
from coverage import covered, distance, evaluate


class CausalCoverageTests(unittest.TestCase):
    def test_half_frame_stride_and_wrap(self):
        period = 2500000/750
        previous = 17
        projected = (previous-25000) % period
        self.assertAlmostEqual(distance(projected, previous, 25000, period), 0)
        self.assertFalse(covered({'epoch_sample':projected, 'acquired_cfo_hz':9000},
            [{'epoch_sample':previous, 'acquired_cfo_hz':0}],25000,period,2,8000))

    def test_missed_candidate_does_not_seed_next_window(self):
        # A static zero-stride fixture isolates the causality of region chaining.
        def c(epoch):
            return dict(epoch_sample=epoch, acquired_cfo_hz=0, margin=.1)
        probes = [dict(receiver_id=rx,probe_index=i,probe_start_ms=0,
            candidates=[c(0)] + ([c(100)] if i else []))
            for rx in (0,1) for i in range(11)]
        result=evaluate([dict(context={'rate_hz':2500000},result={'probes':probes})],16,2,8000)
        self.assertEqual(result['total']['baseline_hits'],42)
        self.assertEqual(result['total']['covered_hits'],22)
        self.assertEqual(result['total']['full_windows'],2)


if __name__ == '__main__':
    unittest.main()
