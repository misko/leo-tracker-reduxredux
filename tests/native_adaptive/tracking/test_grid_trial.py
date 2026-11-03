"""Research CLI contract checks; run with GRID_TRIAL pointing to its build."""
import os
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


class GridTrialTests(unittest.TestCase):
    def run_grid(self, text, *args):
        executable = os.environ["GRID_TRIAL"]
        with tempfile.TemporaryDirectory(dir="/var/tmp") as directory:
            path = Path(directory) / "input.tsv"
            path.write_text(text)
            return subprocess.run([executable, str(path), *args],
                                  capture_output=True, text=True, timeout=10)

    def test_rejects_unbounded_grid(self):
        result = self.run_grid("", "999999999", "64", "512")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outside bounded range", result.stderr)

    def test_rejects_wrong_header(self):
        result = self.run_grid("wrong\n", "301", "16", "512")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsupported input header", result.stderr)

    def test_recovers_aliased_linear_track(self):
        header = ("candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\t"
                  "support_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\t"
                  "measured_cfo_hz\texact_score\tcontrol_score\tmargin\n")
        rows = []
        for i in range(24):
            time = 1_700_000_000_000_000_000 + i * 500_000_000
            frequency = 100000 + 500 * i + (i % 3 - 1) / 4.4e-6
            candidate = "sha256:" + hashlib.sha256(f"c{i}".encode()).hexdigest()
            source = "sha256:" + hashlib.sha256(f"s{i}".encode()).hexdigest()
            rows.append(f"{candidate}\t{source}\t0\t1\tlower\t11200000000\t{time-1000}\t"
                        f"{time}\t{time+1000}\t{frequency:.17g}\t0.6\t0.05\t0.55\n")
        result = self.run_grid(header + "".join(rows), "301", "16", "512")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SUMMARY\t24\t24\t1", result.stdout)
        track = next(row.split("\t") for row in result.stdout.splitlines()
                     if row.startswith("TRACK\t"))
        self.assertAlmostEqual(float(track[11]), 1000, places=6)
        self.assertEqual(int(track[16]), 24)


if __name__ == "__main__":
    unittest.main()
