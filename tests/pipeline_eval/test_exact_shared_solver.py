from collections import Counter
from contextlib import contextmanager
import ctypes as ct
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from reports.ALGO08.v3.profiled_grid_export import (
    ILL_CONDITIONED, STOCK_PREFIX_REFUSAL, exported, handoff, profiled_exports, profiled_grid,
)
from reports.ALGO08.v3.profiled_grid_export_0008 import calibration
from reports.ALGO08.v3 import profiled_grid_export_admission as admission


class ProfiledPosteriorTest(TestCase):
    def test_corrupt_permutation_refuses_native_factor(self):
        capture = handoff.Capture(2)
        capture.exported.value = 1
        capture.lower[:] = np.eye(2)
        capture.order[:] = 1, 0
        self.assertTrue(exported(capture))
        capture.order[:] = 1, 1
        self.assertFalse(exported(capture))
        capture.order[:] = 1, 0
        capture.lower[1, 1] = np.nan
        self.assertFalse(exported(capture))
        capture.lower[1, 1] = 0.0
        self.assertFalse(exported(capture))

    def test_incompatible_binary_leaves_the_stock_hook_untouched(self):
        stock = handoff.Capture.run
        audit = Counter()
        with profiled_exports(Path("/nonexistent-profiled-grid-so"), "unused", audit):
            self.assertIs(stock, handoff.Capture.run)
        self.assertEqual(audit, {"unsupported_library": 1})

    def test_profiled_export_replays_stock_only_on_refusal_or_bad_factor(self):
        for issue in ("status", "factor", None):
            with self.subTest(issue=issue):
                seen = []
                capture = handoff.Capture(2)
                owner = SimpleNamespace(counts=Counter())

                def stock(*args):
                    seen.append("stock")
                    capture.exported.value = 1
                    capture.lower[:] = np.eye(2)
                    capture.order[:] = 0, 1
                    return 0

                stock.argtypes, stock.restype = [], int

                def profile(*args):
                    seen.append("profile")
                    capture.exported.value = 1
                    capture.lower[:] = np.eye(2)
                    capture.order[:] = (0, 0) if issue == "factor" else (0, 1)
                    return 1 if issue == "status" else 0

                with TemporaryDirectory() as temp:
                    binary = Path(temp)/"stub.so"
                    body = b"stub approved by the test"
                    binary.write_bytes(body)
                    audit = Counter()
                    with (patch("reports.ALGO08.v3.profiled_grid_export.ct.CDLL",
                                return_value=SimpleNamespace(nb_profiled_posterior=profile)),
                          profiled_exports(binary, sha256(body).hexdigest(), audit)):
                        self.assertEqual(capture.run(owner, stock, ()), 0)
                self.assertEqual(seen, ["profile", "stock"] if issue else ["profile"])
                self.assertEqual(audit, {"attempted": 1, "stock_replay" if issue else "profiled_completed": 1})
                self.assertTrue(exported(capture))

    def test_stock_refusal_requires_tag_exact_symbol_and_condition_status(self):
        callback = ct.CFUNCTYPE(ct.c_int)
        entered = []
        stock = callback(lambda: entered.append("stock") or ILL_CONDITIONED)
        other = callback(lambda: entered.append("different") or ILL_CONDITIONED)
        for symbol, marker, status, proved in (
            (stock, STOCK_PREFIX_REFUSAL, ILL_CONDITIONED, True),
            (other, STOCK_PREFIX_REFUSAL, ILL_CONDITIONED, False),
            (stock, 0, ILL_CONDITIONED, False),
            (stock, STOCK_PREFIX_REFUSAL, 2, False),
        ):
            with self.subTest(marker=marker, status=status, proved=proved):
                entered.clear()
                audit = Counter()
                capture = handoff.Capture(2)

                def profile(*args):
                    capture.exported.value = marker
                    return status

                def run(self, owner, operation, args):
                    result = operation()
                    if operation is stock:
                        self.exported.value = 0
                    return result

                target = "reports.ALGO08.v3.profiled_grid_export.checked_symbol"
                with (patch(target, side_effect=(profile, symbol)),
                      patch.object(handoff.Capture, "run", run),
                      profiled_exports("profiled", "approved-sha", audit, proof_stock="stock")):
                    self.assertEqual(capture.run(None, stock, ()), ILL_CONDITIONED)
                self.assertEqual(audit, {"attempted": 1, "certified_stock_refusal" if proved else "stock_replay": 1})
                self.assertEqual(entered, [] if proved else ["stock"])
                self.assertEqual(capture.exported.value, 0)

    def test_the_opt_in_port_uses_the_grid_dispatchers_stock_asset(self):
        calls, counts, audit = [], Counter(), Counter()

        @contextmanager
        def original(port, library, in_grid):
            calls.append((port, library, in_grid))
            yield counts

        @contextmanager
        def candidate(binary, pin, observed, *, proof_stock):
            calls.append((binary, pin, observed, proof_stock))
            yield

        with (patch.object(handoff, "grid_handoff", original),
              patch("reports.ALGO08.v3.profiled_grid_export.profiled_exports", candidate),
              profiled_grid("new.so", "digest", audit, proof=True)):
            with handoff.grid_handoff("publication-port", "durable-asset.so", False) as result:
                self.assertIs(result, counts)
        self.assertEqual(calls, [("publication-port", "durable-asset.so", False),
                                 ("new.so", "digest", audit, "durable-asset.so")])

    def test_radio_two_coefficients_distinguish_fitted_arm(self):
        original = np.zeros((2, 243))
        original[0, [0, 8]] = 1
        original[1, 2] = 1
        self.assertEqual(calibration(original)["arm"], "unclassified")
        original[1, 8] = -1
        self.assertEqual(calibration(original), dict(arm="fitted_c", radio2_rows=1, radio1_rows=1,
                                                    radio2_nonzero_column8=1))
        original[1, 1] = 1
        with self.assertRaisesRegex(ValueError, "radio intercept"):
            calibration(original)

    def test_the_watch_ignores_a_fresh_deferral_from_another_case(self):
        events = [{"case": "DS30-0211", "unix_ns": 80}, {"case": "DS30-0277", "unix_ns": 90}]
        library = SimpleNamespace(inotify_init1=lambda *_: 17, inotify_add_watch=lambda *_: 0)
        with (TemporaryDirectory() as temp,
              patch.object(admission.ctypes, "CDLL", return_value=library),
              patch.object(admission.os, "read", return_value=b"notification"),
              patch.object(admission.os, "close"),
              patch.object(admission.select, "select", return_value=([17], [], [])),
              patch.object(admission, "replaced_export", return_value=True),
              patch.object(admission, "time_ns", return_value=100),
              patch.object(admission, "recent_deferral", side_effect=events),
              patch.object(admission, "launch", return_value={"returncode": 0}) as launch):
            binary = Path(temp)/"ready.so"
            binary.touch()
            result = admission.watch(binary, "digest", proof=False, physical=None, official_case="DS30-0277")
        launch.assert_called_once_with(events[1], binary, "digest", proof=False, physical=None)
        self.assertEqual((result["exports"], result["attempts"]), (2, 1))
