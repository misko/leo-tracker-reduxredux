from pathlib import Path
import unittest
from unittest.mock import patch

from reports.ALGO08.v3 import adaptive_raw_trial as trial


class AdaptiveRawTrialTests(unittest.TestCase):
    def test_switch_changes_only_checkout_output_and_opt_in(self):
        command = ["timeout", "--kill-after=2s", "90s", "python", "-IB", "/old/combined_raw_research.py",
                   "--eight-ms-native-history", "--catalogue-block-rank", "--portable-orbit-index", "/idx",
                   "--grid-feature-projection-library", "/lib", "--one-pass-web-png", "--named-survivor-finish",
                   "--direct-orbit-figures", "--direct-residual-figures", "--region", "/offer", "--output", "/old"]
        candidate = trial.adaptive_command(command, Path("/dev/shm/fresh"))
        self.assertEqual(candidate[-1], trial.FLAG)
        self.assertNotIn(trial.FLAG, command)
        for index, arg in enumerate(candidate[:-1]):
            if index not in (5, command.index("--output") + 1):
                self.assertEqual(arg, command[index])
        with self.assertRaisesRegex(ValueError, "two-scan"):
            trial.adaptive_command([*command, "--full-anchor-primary-library", "extra"], Path("/dev/shm/fresh"))

    def test_research_layout_restores_isolated_import_path(self):
        import sys
        from contextlib import contextmanager

        from reports.ALGO08.v3 import live_adaptive_grid_entry as adapter, unified_short_bootstrap as boot

        original = sys.path

        @contextmanager
        def active(output):
            self.assertEqual(output, Path("/dev/shm/example"))
            self.assertIn(str(trial.CHECKOUT), sys.path)
            yield

        with patch.object(adapter, "research_layout", active), boot.adaptive_map_layout(Path("/dev/shm/example")):
            self.assertIsNot(sys.path, original)
        self.assertIs(sys.path, original)

    def test_excluded_low_points_are_relative_to_each_arm(self):
        points = [dict(east_km=i, north_km=0.0, latlon=[0.0, float(i)], scores={"c0": a, "fitted_c": b})
                  for i, (a, b) in enumerate(((0.0, 10.0), (4.5, 15.0), (4.6, 14.0), (None, 9.7)))]
        lost = trial.missed_low_points(dict(points=points[:1]), dict(points=points))
        self.assertEqual([point["east_km"] for point in lost["c0"]], [1])
        self.assertEqual([point["east_km"] for point in lost["fitted_c"]], [2, 3])
        self.assertEqual(lost["fitted_c"][-1]["excess_loss"], 0.0)

    def test_passive_cache_comparison_ignores_query_timestamps(self):
        row = dict(members=19, observed_members=19, cached_pages=50, observed_file_pages=50, unavailable={})
        self.assertTrue(trial.same_page_counts({"payload": dict(row, started_unix_ns=1)},
                                               {"payload": dict(row, started_unix_ns=2)}))
        self.assertFalse(trial.same_page_counts({"payload": row}, {"payload": dict(row, cached_pages=49)}))
