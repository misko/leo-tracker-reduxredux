"""Public metadata IDs, peak ambiguity and unavailable fractional anchors."""
from types import SimpleNamespace as NS
import unittest
from inventory import group_id, original_winners, probe_epochs


def fixture():
    candidates = [NS(candidate_rank=i, integer_epoch_sample=epoch,
        fractional_epoch_offset_samples=frac, passed_fractional_margin_gate=passed,
        fractional_margin=20.-i) for i, (epoch, frac, passed) in
        enumerate([(500, .25, True), (600, .25, True), (500, .3, False)])]
    source = NS(sample_rate_hz=2500000, input_manifest_sha256='sha256:'+'0'*64,
        timing=NS(session_start_device_sample_counter=2**60, first_sample_estimate_utc_ns=1790000000000000000))
    probe = NS(visit_index=1, receiver_id=0, probe_index=4, valid_start_counter=2**60+10000,
        probe_start_ms=4, candidates=candidates)
    return source, probe


class InventoryTests(unittest.TestCase):
    def test_multiple_peaks_remain_visible_without_cfo_access_or_clustering(self):
        source, probe = fixture()
        result = probe_epochs(source, probe)
        self.assertEqual(result['all_available']['unique_integer_anchors'], 2)
        self.assertEqual(result['all_available']['exact_unique_fractional_phases'], 3)
        self.assertEqual(result['passed_available']['exact_unique_fractional_phases'], 2)
        self.assertEqual(result['relative_probe_counter'], 20000)
        self.assertAlmostEqual(result['candidates'][1]['positive_arrival_phase_samples']
            -result['candidates'][0]['positive_arrival_phase_samples'], 100.)
        self.assertEqual(result['candidates'][0]['first_frame_device_integer_counter'], 2**60+20500)

    def test_missing_fractional_offset_is_explicit_not_reconstructed(self):
        source, probe = fixture()
        probe.candidates[0].fractional_epoch_offset_samples = None
        result = probe_epochs(source, probe)
        self.assertEqual(result['missing_fractional_candidate_count'], 1)
        self.assertFalse(result['candidates'][0]['phase_available'])
        self.assertNotIn('positive_arrival_phase_samples', result['candidates'][0])

    def test_group_identity_binds_receiver_and_original_winner_is_score_only(self):
        source, probe = fixture()
        first = group_id(source, probe)
        probe.receiver_id = 1
        self.assertNotEqual(first, group_id(source, probe))
        points = [NS(source_group_id=first, margin=10., candidate_rank=1, candidate_id='b'),
            NS(source_group_id=first, margin=10., candidate_rank=0, candidate_id='a')]
        # No point has CFO, phase or satellite fields: any such read would fail.
        selected = original_winners(points)
        self.assertEqual(selected[first].candidate_rank, 0)


if __name__ == '__main__':
    unittest.main()
