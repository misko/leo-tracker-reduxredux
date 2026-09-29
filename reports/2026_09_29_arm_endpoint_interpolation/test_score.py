import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("endpoint_score", HERE / "score.py")
score = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(score)


def context():
    return {"session_id": "test", "visit_index": 1, "sha256": "input", "rate_hz": 2_500_000}


def candidate(epoch=100, cfo=1_000.0, margin=.03):
    return {"epoch": epoch, "refined_epoch": epoch, "tracking_cfo_hz": cfo, "margin": margin}


def rows():
    return [
        {"receiver_id": receiver, "probe_index": probe, "candidate_count": 0,
         "candidates": [], "instrumentation": {"kernel_calls": 0}}
        for receiver, probe in sorted(score.audit.WINDOW_KEYS)
    ]


class EndpointScoreTests(unittest.TestCase):
    def test_variable_candidate_entries_and_explicit_kernel_attempts(self):
        payload = rows()
        payload[0].update(candidate_count=2, candidates=[candidate(), candidate(200, margin=.01)])
        payload[0]["instrumentation"]["kernel_calls"] = 7
        payload[0]["instrumentation"].update(anchor_search_count=1, middle_glrt_kernel_attempts=3)
        payload[0]["timings_ms"] = {"total_cpu": 2.5}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            path.write_text(json.dumps({"context": context(), "rows": payload}) + "\n")
            loaded = score.load_native(path, [context()])
        window = loaded[("test", 1)][(0, 0)]
        self.assertEqual(len(window["candidates"]), 2)
        self.assertEqual(window["kernel_calls"], 7)
        self.assertEqual(window["anchor_search_count"], 1)
        self.assertEqual(window["total_cpu_ms"], 2.5)

    def test_missing_extra_and_candidate_inventory_are_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "rows.jsonl"
            bad = rows()[:-1]
            path.write_text(json.dumps({"context": context(), "rows": bad}) + "\n")
            with self.assertRaisesRegex(ValueError, "missing native windows"):
                score.load_native(path, [context()])
            bad = rows()
            bad.append({"receiver_id": 9, "probe_index": 9, "candidate_count": 0,
                        "candidates": [], "instrumentation": {"kernel_calls": 0}})
            path.write_text(json.dumps({"context": context(), "rows": bad}) + "\n")
            with self.assertRaisesRegex(ValueError, "extra native window"):
                score.load_native(path, [context()])
            bad = rows()
            bad[0].update(candidate_count=17, candidates=[candidate()] * 17)
            path.write_text(json.dumps({"context": context(), "rows": bad}) + "\n")
            with self.assertRaisesRegex(ValueError, "0..16"):
                score.load_native(path, [context()])

    def test_maximum_matching_prevents_double_credit(self):
        reference = [{"epoch_sample": value, "tracking_cfo_hz": 0} for value in (0, 3)]
        native = [{"epoch": value, "tracking_cfo_hz": 0} for value in (2, -2)]
        self.assertEqual(score.audit.maximum_matches(reference, native), 2)
        self.assertEqual(score.audit.maximum_matches(reference, native[:1]), 1)

    def test_work_window_and_cpu_counters_do_not_use_candidate_count(self):
        counts = score._counts()
        row = {
            "kernel_calls": 0,
            "anchor_search_count": 1,
            "middle_glrt_kernel_attempts": 0,
            "fallback_used": True,
            "total_cpu_ms": 3.25,
        }
        score._add(counts, [], [], row)
        self.assertEqual(counts["windows_with_glrt_attempts"], 0)
        self.assertEqual(counts["windows_without_glrt_attempts"], 1)
        self.assertEqual(counts["full_search_windows"], 2)
        self.assertEqual(counts["local_search_windows"], 0)
        self.assertEqual(counts["actual_glrt_kernel_attempts"], 0)
        self.assertEqual(counts["total_cpu_ms"], 3.25)


if __name__ == "__main__":
    unittest.main()
