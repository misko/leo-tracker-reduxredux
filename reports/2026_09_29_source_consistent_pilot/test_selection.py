import unittest
from selection import select


class SelectionTest(unittest.TestCase):
    def test_seeded_alternative_beats_unseeded_closure(self):
        rows=[dict(track_id='a',groups=['x','y'],training_count=5),dict(track_id='b',groups=['x'],training_count=3),dict(track_id='c',groups=['y'],training_count=3)]
        out=select(rows)
        self.assertEqual(out['track_ids'],['b','c'])
        self.assertEqual(out['training_count'],6)
        self.assertEqual(select(list(reversed(rows)))['track_ids'],out['track_ids'])

    def test_tie_and_within_track_conflict(self):
        rows=[dict(track_id='b',groups=['x'],training_count=2),dict(track_id='a',groups=['x'],training_count=2)]
        self.assertEqual(select(rows)['track_ids'],['a'])
        with self.assertRaises(AssertionError):
            select([dict(track_id='a',groups=['x','x'],training_count=2)])


if __name__=='__main__':
    unittest.main()
