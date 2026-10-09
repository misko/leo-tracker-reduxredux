"""Metadata scheduling and terminal-controller tests without worker launches."""

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("batch107_test", HERE / "batch.py")
batch = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(batch)


class BatchTest(unittest.TestCase):
    def test_metadata_interleaving(self):
        members = []
        for dataset, count in zip(batch.DATASETS, (3, 2, 2, 2), strict=True):
            for i in range(count):
                members.append(
                    dict(member={"dataset": dataset, "inventory_label": f"{dataset}-{i}"})
                )
        labels = [batch.label(m) for m in batch.interleave(list(reversed(members)))]
        self.assertEqual(labels[:4], [name + "-0" for name in batch.DATASETS])
        self.assertEqual(labels[-1], "DS16-2")
        self.assertEqual(len(labels), len(set(labels)))

    def test_two_disjoint_shards_and_member_cap(self):
        plan = dict(labels=[str(i) for i in range(7)], maximum_workers=2)
        def invoke(label, **kwargs):
            return {"baseline": "failed"}
        first = batch.run_shard(plan, 0, invoke=invoke)
        second = batch.run_shard(plan, 1, invoke=invoke)
        self.assertEqual(
            {r["label"] for r in first} | {r["label"] for r in second}, set(plan["labels"])
        )
        self.assertFalse({r["label"] for r in first} & {r["label"] for r in second})
        self.assertEqual(len(batch.run_shard(plan, 0, maximum_members=1, invoke=invoke)), 1)
        with self.assertRaises(ValueError):
            batch.run_shard(plan, 0, maximum_members=-1)

    def test_failed_baseline_skips_candidate_without_excluding_member(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "protocol.json").write_text("{}")
            digest = hashlib.sha256((root / "protocol.json").read_bytes()).hexdigest()
            directory = root / "results" / "member"
            directory.mkdir(parents=True)
            (directory / "baseline.json").write_text(
                json.dumps(dict(protocol_sha256=digest, status="failed"))
            )

            def forbidden(*args, **kwargs):
                raise AssertionError("No numerical child should run")

            outcome = batch.CONTROLLER.CONTROLLER.run_member("member", here=root, invoke=forbidden)
            self.assertEqual(outcome, {"baseline": "failed"})
            self.assertFalse((directory / "candidate.json").exists())


if __name__ == "__main__":
    unittest.main()
