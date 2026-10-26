"""Channel attribution partitions deltas, retaining every original point."""
import unittest
from channel_diagnostic import subsets


class ChannelTests(unittest.TestCase):
    def test_complete_disjoint_partition_independent_of_delta(self):
        rows=[dict(native_observation_id='a',role='CH7_control',correction_delta_hz=0),
              dict(native_observation_id='b',role='CH8_target',correction_delta_hz=100),
              dict(native_observation_id='c',role='CH8_target',correction_delta_hz=-100)]
        value=subsets(rows)
        self.assertEqual([r['native_observation_id'] for r in value['CH7_only']],['a'])
        self.assertEqual([r['native_observation_id'] for r in value['CH8_only']],['b','c'])

    def test_unknown_role_fails_without_point_drop(self):
        with self.assertRaises(ValueError):
            subsets([dict(native_observation_id='a',role='unknown')])


if __name__=='__main__':
    unittest.main()
