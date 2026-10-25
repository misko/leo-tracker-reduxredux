import unittest
from check_context import owner_metadata, native_matches


class MetadataTests(unittest.TestCase):
    def test_projection_does_not_copy_CFO_or_candidate_fields(self):
        owner = dict(key='owner', receiver=2, channel=3, rf_hz=11e9,
                     times=[1.], observation_ids=['a'], values=object(), candidate_norad=object())
        self.assertEqual(set(owner_metadata(owner)),
                         {'key', 'receiver', 'channel', 'rf_hz', 'times', 'observation_ids'})

    def test_exact_native_metadata_required(self):
        owner = dict(receiver=2, channel=3, rf_hz=11e9, times=[1.], observation_ids=['a'])
        observation = dict(receiver=2, channel=3, actual_rf_hz=11e9, time_s=1., measured_cfo_hz=object())
        self.assertTrue(native_matches(owner, {'a': observation}))
        self.assertFalse(native_matches(owner, {'a': dict(observation, time_s=2.)}))


if __name__ == '__main__':
    unittest.main()
