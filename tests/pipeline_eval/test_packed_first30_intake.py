from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from packed_first30_intake import FULL, MEMBER_FIELDS, SHORT, case_budget, footprint, prospective, saved, scenario


def signed_members(extents):
    rows = [dict(chunk_index=i, first_sequence=sum(n for n, _ in extents[:i]), window_count=count,
                 compressed_bytes=decoded//2, uncompressed_bytes=decoded, compressed_sha256=f"encoded-{i}",
                 uncompressed_sha256=f"decoded-{i}", index_sha256=f"index-{i}")
            for i, (count, decoded) in enumerate(extents)]
    return rows, [dict({v: row[k] for k, v in MEMBER_FIELDS.items()}, complete_encoded_auth=True,
                       largest_sample_window_bytes=min(row["uncompressed_bytes"], FULL)) for row in rows]


class PackedFirst30IntakeTest(unittest.TestCase):
    def test_exact_partial_bytes_and_signed_authority(self):
        signed, paid = signed_members([(64, 64*FULL), (4, 4*FULL-412)])
        amount, final = footprint(signed, paid)
        self.assertEqual(dict(visits=4, decoded=4*FULL-412, encoded=(4*FULL-412)//2), final)
        self.assertEqual(68*FULL-412, amount["decoded"])
        self.assertEqual(1, amount["final_partial_variable"])
        altered = deepcopy(paid)
        altered[1]["raw_sha256"] = "different"
        with self.assertRaisesRegex(ValueError, "signed manifest"):
            footprint(signed, altered)
        with self.assertRaises(ValueError):
            footprint(signed, paid[:1])

    def test_aperture_counts_can_have_no_short_calls(self):
        case = dict(admitted=1, issued=2, modes={"full": dict(visits=1, elapsed_ns=7),
                                                "short_primary": dict(elapsed_ns=0)},
                    acquisition={"elapsed_s": 4}, paid_candidate_s=5)
        self.assertEqual(FULL, case_budget(case, dict(visits=2, decoded=FULL))["requested_decoded"])
        case["modes"]["short_primary"]["visits"] = 1
        case["admitted"] = 2
        budget = case_budget(case, dict(visits=2, decoded=2*FULL))
        self.assertEqual(FULL-SHORT, budget["skipped_decoded"])
        self.assertTrue(budget["direct_geometry"])
        self.assertFalse(case_budget(case, dict(visits=2, decoded=2*FULL-1, variable=1))["direct_geometry"])
        with self.assertRaisesRegex(ValueError, "apertures"):
            case_budget(case, dict(visits=2, decoded=FULL))

    def test_whole_gate_uses_all_cases_caps_local_and_keeps_migration_penalty(self):
        cases = [dict(paid_installed_s=10, paid_candidate_s=6, outer_acquisition_s=2),
                 dict(paid_installed_s=30, paid_candidate_s=18, outer_acquisition_s=2)]
        result = scenario(cases, [9, -1])
        self.assertEqual(1, result["saved_s"])
        self.assertEqual(1, result["capped_cases"])
        self.assertEqual(3, result["gap_to_half_total_s"])
        self.assertAlmostEqual(.575, result["summed_ratio"])
        self.assertAlmostEqual((.4 + 19/30)/2, result["paired_median_ratio"])

    def test_clean_descriptor_substitution_pays_full_pack_verification_and_no_writer(self):
        dense = saved("eight-first-use.json.gz")
        held = saved("eight-first-use-held.json.gz")["data"]["held"]
        seekable = saved("seekable-eight-raw.json.gz")
        clocks = [row["clocks"]["wall_ns"] for row in prospective(dense, held, seekable)]
        self.assertEqual([502823, -2775324, 6077349, 18033141], [c["normalized_acquire_saving"] for c in clocks])
        self.assertTrue(all(c["joint_saving"] > c["normalized_acquire_saving"] for c in clocks))
        dense["result"]["arms"][0]["packed8"]["acquisition"]["reads"]["encoded_blocks_preverified"] -= 1
        with self.assertRaisesRegex(ValueError, "both apertures"):
            prospective(dense, held, seekable)


if __name__ == "__main__":
    unittest.main()
