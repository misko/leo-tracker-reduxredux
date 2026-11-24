"""Tests for the exact cold finalist measurement boundary."""

import ctypes as ct
import gzip
import json
from pathlib import Path
from sys import path
from types import SimpleNamespace
import unittest

import numpy as np

REPORTS = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
path.insert(0, str(REPORTS))

from cold_kernel_price import Probes, output_bytes, scientific
from cold_kernel_price_readout import price


class ProbeTests(unittest.TestCase):
    def test_derivatives_share_the_model_and_base_only(self):
        probes = Probes()
        calculate = probes.calculations(lambda model, point: (model, point.tolist()), [])
        base = np.array([3., 4.])
        model = SimpleNamespace()
        calculate(model, base)

        def forward(anchor, lo, hi, step):
            for axis in range(2):
                point = anchor.copy()
                point[axis] += step
                yield axis, point, step

        for axis, point, _ in probes.points(forward)(base, None, None, 0.001):
            self.assertEqual(calculate(model, point), (model, point.tolist()))
            self.assertEqual(probes.rows[-1]["axis"], axis)
        calculate(model, base)
        calculate(SimpleNamespace(), base)
        counts = probes.counts()
        self.assertEqual(counts["calculations"], 5)
        self.assertEqual(counts["models"], 2)
        self.assertEqual(counts["exact_repeats"], 1)
        self.assertEqual(counts["derivatives_with_base"], 2)
        self.assertEqual(counts["derivative_exact_repeats"], 0)
        self.assertEqual(counts["partner_shared_coordinates"], {0: 1})

    def test_shadow_comparison_includes_all_original_outputs(self):
        n, p, k, t = 5, 4, 3, 2
        original = [(ct.c_double * size)(*range(size)) for size in (p, n, k, p, t, 2)]
        iteration = ct.c_int(30)
        rates = (ct.c_double * k)(1., 2., 3.)
        arguments = [None] * 19
        arguments[11] = t
        arguments.extend([*original, ct.byref(iteration), rates])
        before = output_bytes(arguments, (n, p, k))
        for i, array in enumerate(original):
            array[0] = 1.
            self.assertNotEqual(before[i], output_bytes(arguments, (n, p, k))[i])
        iteration.value -= 1
        rates[-1] = 4.
        after = output_bytes(arguments, (n, p, k))
        self.assertNotEqual(before[6], after[6])
        self.assertNotEqual(before[7], after[7])

    def test_science_comparison_retains_results_and_removes_only_local_clocks(self):
        self.assertEqual(scientific({3: ({"score": np.float64(0.25), "cpu_ns": 123,
                                          "owners": [[7, "predictive"]]}, np.array([2., 3.]))}),
                         {"3": [{"score": 0.25, "owners": [[7, "predictive"]]}, [2., 3.]]})

    def test_receipt_separates_optimizer_and_endpoint_repeats(self):
        with gzip.open(REPORTS / "measurements/cold-kernel-price.json.gz") as stream:
            receipt = json.load(stream)
        for case, count in (("DS30-0402", 194), ("DS30-0374", 132)):
            witness = receipt["observations"][case]
            result = price(witness["audit"])
            self.assertEqual(result, witness["derived"])
            self.assertEqual(result["original_objective_evaluations"], count)
            self.assertEqual(result["post_optimizer_endpoint_calculations"], 6)
            self.assertEqual(
                result["residual_energy_after_whole_repeat_removal_cpu_ns"]
                + result["residual_energy_already_in_repeated_calculations_cpu_ns"],
                witness["audit"]["phase_cpu_ns"]["residual_energy"],
            )


if __name__ == "__main__":
    unittest.main()
