"""Freeze membership/causality and preserve interrupted member accounting."""
import copy
import unittest
import preparation as p


class PreparationTests(unittest.TestCase):
    def test_actual_sealed_members_clock_and_byte_identity(self):
        self.assertEqual(p.sha(p.RUN / 'sample.json'), p.SAMPLE_SHA)
        self.assertEqual(len(p.members(p.read(p.RUN / 'sample.json'))), 4)

    def test_no_replacement_and_no_creation_time_as_causal_cutoff(self):
        sample = p.read(p.RUN / 'sample.json')
        changed = copy.deepcopy(sample)
        changed['selected'][0]['dataset_label'] = 'REPLACEMENT'
        with self.assertRaises(ValueError): p.members(changed)
        changed = copy.deepcopy(sample)
        changed['selected'][0]['capture_time_authority']['causal_cutoff_utc_ns'] += 1
        with self.assertRaises(ValueError): p.members(changed)

    def test_interruption_keeps_all_four_slots(self):
        rows = p.all_slots(p.LABELS, {p.LABELS[0]: dict(case=p.LABELS[0], status='timeout')})
        self.assertEqual([r['case'] for r in rows], list(p.LABELS))
        self.assertEqual([r['status'] for r in rows], ['timeout'] + ['not_attempted'] * 3)


if __name__ == '__main__': unittest.main()
