"""Code-family comparisons must preserve measured bits and reject missing ones."""

import unittest

from summarize import family, same_acquisition


class FamilyTests(unittest.TestCase):
    def test_binding_ignores_only_duplicate_rank(self):
        a = dict(probe=dict(visit=3, rx=1), candidate=dict(candidate_rank=0, cfo=100, epoch=25))
        b = dict(probe=dict(visit=3, rx=1), candidate=dict(candidate_rank=1, cfo=100, epoch=25))
        self.assertTrue(same_acquisition(a, b))
        b["candidate"]["epoch"] = 26
        self.assertFalse(same_acquisition(a, b))
        b["candidate"]["epoch"] = 25
        b["probe"]["visit"] = 4
        self.assertFalse(same_acquisition(a, b))

    def test_rotation_and_polarity(self):
        word = "011001100110101101001110001010010011100011110101001001100101"
        for i in range(60):
            rotated = word[i:] + word[:i]
            self.assertEqual(family(word), family(rotated))
            self.assertEqual(family(word), family(rotated.translate(str.maketrans("01", "10"))))

    def test_missing_bits_cannot_be_full_family(self):
        for word in ("0" * 59, "0" * 59 + "?", "0" * 59 + "2"):
            with self.assertRaises(ValueError):
                family(word)

    def test_distinct_words_remain_distinct(self):
        self.assertNotEqual(family("0" * 60), family("1" + "0" * 59))


if __name__ == "__main__":
    unittest.main()
