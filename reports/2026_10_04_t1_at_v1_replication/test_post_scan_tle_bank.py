import unittest
from post_scan_tle_bank import choose_post_scan,HOUR_NS,element_records


def candidate(epoch,collection,tag='a'):
    return dict(epoch_utc_ns=epoch*HOUR_NS,collected_utc_ns=collection*HOUR_NS,line1=tag,line2='b')


class PostScanSelectionTests(unittest.TestCase):
    def test_epoch_not_collection_time_controls_selection(self):
        rows=[candidate(-1,1),candidate(5,6),candidate(2,20)]
        self.assertEqual(choose_post_scan(rows,0),rows[2])

    def test_no_post_epoch_returns_fallback_signal(self):
        self.assertIsNone(choose_post_scan([candidate(-1,3),candidate(25,26),candidate(1,49)],0))
        self.assertIsNone(choose_post_scan([candidate(1,-1)],0))

    def test_ties_are_deterministic_and_independent_of_order(self):
        rows=[candidate(2,8),candidate(2,6,'z'),candidate(2,6,'a')]
        self.assertEqual(choose_post_scan(rows,0),rows[2])
        self.assertEqual(choose_post_scan(rows[::-1],0),rows[2])

    def test_paired_lines_and_epoch_decoding(self):
        first='1 64361U 25126T   26274.59828692  .00006819  00000-0  24143-3 0  9997'
        second='2 64361  70.0012 231.3533 0003145 267.7291  92.3524 15.29580112 71624'
        result=element_records(first+'\n'+second+'\n',{64361})[64361]
        self.assertTrue(result['epoch_utc'].startswith('2026-10-01T14:21:31.989888'))
        with self.assertRaises(ValueError):element_records(first+'\n2 12345 invalid\n',{64361})


if __name__=='__main__':unittest.main()
