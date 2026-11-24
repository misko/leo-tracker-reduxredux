import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from first_member_scout import splice


def lane(visit, factor):
    return dict(visit_index=visit, receiver_id=0, candidates=[factor] if factor else [])


def factor(score):
    return dict(fractional_margin=score, fractional_exact_score=score + 0.1,
                fractional_control_score=0.1, fractional_tracking_cfo_hz=-873.5,
                integer_epoch_sample=25, fractional_epoch_offset_samples=0.2,
                candidate_rank=0, passed_fractional_margin_gate=True)


class SavedFirstMember(unittest.TestCase):
    def test_splice_uses_measured_empty_and_keeps_unaffected_rows(self):
        original = [lane(0, factor(0.5)), lane(1, factor(0.7))]
        ordinary = [lane(0, factor(0.5 + 1e-13)), lane(1, factor(0.7))]
        shorter = [ordinary[0], lane(1, None)]
        rows, dropped, peaks = splice(original, ordinary, shorter, {(0, 0)})
        self.assertIs(rows[0], original[0])
        self.assertEqual(rows[1], shorter[1])
        self.assertEqual(dropped, original[1:])
        self.assertGreater(peaks["fractional_margin"], 0)

    def test_rejects_nonroundoff_cfo_score_or_clock_changes(self):
        original = [lane(0, factor(0.5))]
        for member, message in (
            (lane(0, dict(factor(0.5), fractional_tracking_cfo_hz=-873.49)), "signed"),
            (lane(0, factor(0.500001)), "certificate"),
            (lane(1, factor(0.5)), "chronological"),
        ):
            with self.assertRaisesRegex(ValueError, message):
                splice(original, [member], [member], set())

    def test_rejects_anchor_omission_and_unmeasured_replacement(self):
        original = [lane(0, factor(0.5))]
        with self.assertRaisesRegex(ValueError, "short-lane omissions"):
            splice(original, original, [lane(0, None)], {(0, 0)})
        with self.assertRaisesRegex(ValueError, "short-lane omissions"):
            splice(original, original, [lane(0, factor(0.6))], set())


if __name__ == "__main__":
    unittest.main()
