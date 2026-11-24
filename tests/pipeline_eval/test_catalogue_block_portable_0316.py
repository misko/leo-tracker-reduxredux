"""Check complete rank activation and scientific compatibility for the paired worker."""

import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from catalogue_block_portable_0316 import PINS, PORT_SOURCE, RANK_SHA, exact_rank, standard_native, verified_port


def active_receipt():
    work = dict(admitted_ranks=1, original_ranks=0, calls=624, compact_calls=624,
                rows_saved=892716, rows_retained=25812, original_rows=918528)
    return dict(port_commit=PORT_SOURCE, source_sha256=PINS, work=work,
                evaluations=[dict(digest=RANK_SHA, nodes=6, rank={"cpu_ns": 200})])


class CombinedRankTests(unittest.TestCase):
    def test_uses_exact_frozen_modules_and_exercised_rank(self):
        verified_port()
        receipt = active_receipt()
        self.assertEqual(exact_rank(receipt), receipt["evaluations"][0])

    def test_rejects_fallback_or_missing_curves_after_a_successful_publication(self):
        for field, value in (("admitted_ranks", 0), ("original_ranks", 1), ("full_fallback", 1),
                             ("compact_calls", 623), ("rows_saved", 892715)):
            receipt = active_receipt()
            receipt["work"][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                exact_rank(receipt)

    def test_rejects_a_changed_ordered_rank_even_when_work_matches(self):
        receipt = active_receipt()
        changed = copy.deepcopy(receipt)
        changed["evaluations"][0]["digest"] = "different rank"
        with self.assertRaises(ValueError):
            exact_rank(changed)

    def test_rejects_native_grid_or_verified_png_fallback(self):
        posterior = dict(arithmetic="permuted native posterior factor", factor_calls=356, prediction_calls=356)
        png = dict(fallbacks=0, verified=8, reused=8)
        trace = {"receipt": {"posterior_grid_handoff": posterior}}
        self.assertEqual(standard_native(trace, {"png_readback": png}),
                         dict(posterior_grid=posterior, png_readback=png))
        png["fallbacks"] = 1
        with self.assertRaises(ValueError):
            standard_native(trace, {"png_readback": png})
        png["fallbacks"], posterior["factor_calls"] = 0, 355
        with self.assertRaises(ValueError):
            standard_native(trace, {"png_readback": png})


if __name__ == "__main__":
    unittest.main()
