"""Score a completed DS8/DS9 host cohort without changing frozen match logic."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import tempfile
from collections import defaultdict
from pathlib import Path


HERE = Path(__file__).resolve().parent
FROZEN_SCORE = HERE.parent / "2026_09_28_arm_boundary_fallback" / "score.py"
DATASETS = ("DS8", "DS9")
MARGIN_GATE = 0.025


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_frozen_score():
    spec = importlib.util.spec_from_file_location("frozen_boundary_score", FROZEN_SCORE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load frozen scorer: {FROZEN_SCORE}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def dataset_view(host: Path, dataset: str, destination: Path) -> list[dict]:
    manifest = json.loads((host / "manifest.json").read_text())
    if not manifest.get("complete") or manifest.get("processed_dwells") != len(manifest["selected"]):
        raise ValueError("host cohort manifest is incomplete")
    selected = [row for row in manifest["selected"] if row.get("dataset_id") == dataset]
    if not selected:
        raise ValueError(f"host cohort has no {dataset} rows")
    cases = {(row["session_id"], row["visit_index"]) for row in selected}
    records = [json.loads(line) for line in (host / "rows.jsonl").read_text().splitlines()]
    records = [row for row in records if (row["context"]["session_id"], row["context"]["visit_index"]) in cases]
    if len(records) != len(selected):
        raise ValueError(f"host rows do not cover the selected {dataset} view")
    view_manifest = dict(manifest, selected=selected, complete=True, processed_dwells=len(selected))
    destination.mkdir()
    (destination / "manifest.json").write_text(json.dumps(view_manifest, indent=2) + "\n")
    (destination / "rows.jsonl").write_text("".join(json.dumps(row) + "\n" for row in records))
    return selected


def recording_counts(selected: list[dict], baseline: dict, native: dict, audit) -> list[dict]:
    """Aggregate frozen per-dwell summaries into recording-level hit evidence."""
    grouped = defaultdict(lambda: {
        "dataset_id": None, "session_id": None, "dwells": 0, "original_hits": 0,
        "recovered_hits": 0, "original_negative_windows_now_positive": 0,
    })
    for context in selected:
        case = (context["session_id"], context["visit_index"])
        one = audit.summarize([context], baseline, {case: native[case]})["totals"]
        record = grouped[(context["dataset_id"], context["session_id"])]
        record["dataset_id"] = context["dataset_id"]
        record["session_id"] = context["session_id"]
        record["dwells"] += 1
        record["original_hits"] += one["reference_positive_hits"]
        record["recovered_hits"] += one["recovered_positive_hits"]
        for key, expected in baseline[case].items():
            actual = native[case][key]["candidates"]
            if not any(item["margin"] >= MARGIN_GATE for item in expected["candidates"]) and any(
                item["margin"] >= MARGIN_GATE for item in actual
            ):
                record["original_negative_windows_now_positive"] += 1
    result = []
    for record in grouped.values():
        denominator = record["original_hits"]
        record["recovery_fraction"] = record["recovered_hits"] / denominator if denominator else None
        record["below_90_percent_recovery"] = (
            denominator > 0 and record["recovered_hits"] / denominator < 0.9
        )
        result.append(record)
    return sorted(result, key=lambda item: (item["dataset_id"], item["session_id"]))


def summarize(host: Path, baseline: Path) -> dict:
    frozen = load_frozen_score()
    result = {"schema": "ds89-boundary-fallback-host-summary/v1", "host": str(host),
              "baseline_sha256": sha256(baseline), "frozen_scorer_sha256": sha256(FROZEN_SCORE),
              "datasets": {}}
    with tempfile.TemporaryDirectory(prefix="leo-ds89-score-") as name:
        temporary = Path(name)
        for dataset in DATASETS:
            view = temporary / dataset.lower()
            selected = dataset_view(host, dataset, view)
            score = frozen.score(view, baseline)
            native = frozen.module.load_native(view / "rows.jsonl", selected)
            references = frozen.module.audit.load_baseline(baseline)
            recordings = recording_counts(selected, references, native, frozen.module.audit)
            result["datasets"][dataset] = {
                "score": score,
                "recordings": recordings,
                "recordings_with_positive_denominator": sum(item["original_hits"] > 0 for item in recordings),
                "recordings_below_90_percent_recovery": sum(item["below_90_percent_recovery"] for item in recordings),
                "original_negative_windows_now_positive": sum(
                    item["original_negative_windows_now_positive"] for item in recordings
                ),
            }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = summarize(args.host, args.baseline)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value["score"]["totals"] for key, value in result["datasets"].items()}, indent=2))


if __name__ == "__main__":
    main()
