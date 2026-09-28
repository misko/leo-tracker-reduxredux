"""Owned contract tests for the DS8/DS9 frozen-cohort wrapper."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("run_candidate", HERE / "run_candidate.py")
runner = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(runner)


def make_inputs(tmp_path: Path) -> tuple[Path, list[dict]]:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    rows = []
    for index in range(680):
        dataset = "DS8" if index < 260 else "DS9"
        name = f"{index}.npy"
        (inputs / name).touch()
        rows.append({
            "dataset_id": dataset, "session_id": f"session-{index}", "visit_index": index,
            "rate_hz": 2_500_000, "shape": [300000, 2, 2], "dtype": "int16",
            "file": name, "sha256": hashlib.sha256(b"").hexdigest(),
        })
    (inputs / "inputs.json").write_text(json.dumps({
        "schema": "ds7-large-arm-inputs/v1", "complete": True, "rows": rows,
    }))
    return inputs, rows


def make_baseline(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "baseline.jsonl"
    path.write_text("".join(json.dumps({
        "method": "original", "repeat": 0, "status": "ok",
        "context": {"session_id": row["session_id"], "visit_index": row["visit_index"], "sha256": row["sha256"]},
    }) + "\n" for row in rows))
    return path


class RunCandidateTest(unittest.TestCase):
    def test_run_delegates_all_680_rows_to_frozen_cohort(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            tmp_path = Path(name)
            inputs, rows = make_inputs(tmp_path)
            baseline = make_baseline(tmp_path, rows)
            binary = runner.DEFAULT_BINARY
            calls = []

            class Frozen:
                def run(self, *args, **kwargs):
                    calls.append((args, kwargs, self.INPUTS, self.BASELINE))

            frozen = Frozen()
            with patch.object(runner, "load_frozen_cohort", return_value=frozen):
                runner.run(inputs, baseline, tmp_path / "out", binary, workers=3)
            self.assertEqual(calls, [
                ((binary, tmp_path / "out"), {"workers": 3, "all_sealed": True}, inputs, baseline)
            ])

    def test_rejects_incomplete_or_wrong_dataset_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            tmp_path = Path(name)
            inputs, rows = make_inputs(tmp_path)
            rows[679]["dataset_id"] = "DS8"
            (inputs / "inputs.json").write_text(json.dumps({
                "schema": "ds7-large-arm-inputs/v1", "complete": True, "rows": rows,
            }))
            with self.assertRaisesRegex(ValueError, "260 DS8 and 420 DS9"):
                runner.validate_inputs(inputs)


if __name__ == "__main__":
    unittest.main()
