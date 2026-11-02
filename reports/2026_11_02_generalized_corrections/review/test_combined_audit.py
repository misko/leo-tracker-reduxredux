from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from audit_combined import expected_next_cases, merge_authoritative, was_started


class CombinedAuditTests(unittest.TestCase):
    def test_temporary_or_empty_engine_artifact_forbids_a_retry(self):
        row = dict(status="total_deadline_fallback")
        with TemporaryDirectory() as temp:
            folder = Path(temp)
            (folder/"result.json").write_text("{}")
            self.assertFalse(was_started(row, folder))
            (folder/"result.json.tmp").write_text("{}")
            self.assertTrue(was_started(row, folder))
            (folder/"result.json.tmp").unlink()
            (folder/"engine").mkdir()
            self.assertTrue(was_started(row, folder))

    def test_partial_A_metadata_excludes_queue_only_replacement(self):
        with TemporaryDirectory() as temp:
            path = Path(temp)/"results.json"
            row = dict(status="total_deadline_fallback", numerical_trigger_diagnostics={})
            self.assertEqual(expected_next_cases({"X":{}}, [(path, {"X":row})]), set())

    def test_a_started_source_row_cannot_be_replaced(self):
        with TemporaryDirectory() as temp:
            first, later = Path(temp)/"first/results.json", Path(temp)/"later/results.json"
            with self.assertRaisesRegex(ValueError, "retried or replaced"):
                merge_authoritative({"X":{}}, [(first, {"X":dict(status="complete")}),
                    (later, {"X":dict(status="complete")})])

    def test_latest_queue_placeholder_then_first_started_row_is_authoritative(self):
        with TemporaryDirectory() as temp:
            paths = [Path(temp)/str(i)/"results.json" for i in range(3)]
            rows = [dict(status="total_deadline_fallback", marker=0),
                    dict(status="total_deadline_fallback", marker=1),
                    dict(status="complete", marker=2)]
            chosen, source = merge_authoritative({"X":{}}, [(p, {"X":r}) for p, r in zip(paths, rows)])
            self.assertEqual(chosen["X"], rows[2])
            self.assertEqual(source["X"], paths[2])


if __name__ == "__main__":
    unittest.main()
