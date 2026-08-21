#!/usr/bin/env python3
"""Run persisted scanner replay sweeps through the production scan analyzer."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from leo.cli.scanner import write_scanner_report
from leo.scanner import (
    CapturedScannerSweep,
    ScanDecision,
    ScannerReferenceLabel,
    analyze_scan_sweep,
)
from leo.scanner.application import CapturedScanTarget
from leo.scanner.ports import ScanRadioBlock, ScanRadioIdentity
from leo.storage import PublishedScannerReplaySweep, ScannerReplayStore


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset_ids", nargs="+")
    parser.add_argument("--bulk-root", type=Path, default=Path("/srv/bulk/leo"))
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("/srv/bulk/leo/scanner-replay-evaluations"),
    )
    parser.add_argument("--evaluation-id", required=True)
    return parser.parse_args()


def _complex_frame(values: np.ndarray) -> np.ndarray:
    """Losslessly reconstruct the complex64 values seen by the live analyzer."""

    ci16 = np.asarray(values)
    if ci16.dtype != np.dtype("<i2") or ci16.ndim != 3 or ci16.shape[2] != 2:
        raise ValueError("replay frame must be little-endian sample/receiver/IQ CI16")
    output = np.empty(ci16.shape[:2], dtype=np.complex64)
    output.real = ci16[:, :, 0]
    output.imag = ci16[:, :, 1]
    output.setflags(write=False)
    return output


def _captured_sweep(
    dataset_id: str,
    sweep: PublishedScannerReplaySweep,
    values: np.ndarray,
) -> CapturedScannerSweep:
    manifest = sweep.manifest
    targets: list[CapturedScanTarget] = []
    for frame in manifest.frames:
        selected = values[frame.sample_start : frame.sample_start + frame.sample_count]
        applied = frame.source.applied_settings
        targets.append(
            CapturedScanTarget(
                target=frame.target,
                block=ScanRadioBlock(
                    samples=_complex_frame(selected),
                    requested_if_center_hz=frame.source.requested_settings.center_frequency_hz,
                    actual_if_center_hz=applied.center_frequency_hz,
                    tune_ms=0.0,
                    listen_ms=float(manifest.configuration.dwell_ms),
                    host_request_utc_ns=(0, 0),
                    host_request_monotonic_ns=(0, 0),
                ),
                error=None,
            )
        )
    return CapturedScannerSweep(
        identity=ScanRadioIdentity(
            radio_id="scanner-replay",
            serial=dataset_id,
            uri=sweep.uri,
        ),
        configuration=manifest.configuration,
        capture_elapsed_ms=0.0,
        targets=tuple(targets),
    )


def _outcome(
    label: ScannerReferenceLabel,
    decision: ScanDecision,
) -> str:
    if decision is ScanDecision.INCONCLUSIVE:
        return "inconclusive"
    detected = decision is ScanDecision.ACTIVE
    active = label is ScannerReferenceLabel.ACTIVE
    if active and detected:
        return "true_positive"
    if active:
        return "false_negative"
    if detected:
        return "false_positive"
    return "true_negative"


def _rates(counts: Counter[str]) -> dict[str, float | None]:
    tp = counts["true_positive"]
    tn = counts["true_negative"]
    fp = counts["false_positive"]
    fn = counts["false_negative"]
    conclusive = tp + tn + fp + fn
    positives = tp + fn
    negatives = tn + fp
    return {
        "accuracy": (tp + tn) / conclusive if conclusive else None,
        "recall": tp / positives if positives else None,
        "specificity": tn / negatives if negatives else None,
        "false_positive_rate": fp / negatives if negatives else None,
    }


def _evaluate_dataset(
    store: ScannerReplayStore,
    dataset_id: str,
    output: Path,
) -> dict[str, Any]:
    dataset = store.inspect(dataset_id)
    truth = {(item.sweep_id, item.target_index): item for item in dataset.truth.items}
    counts: Counter[str] = Counter()
    sweeps: list[dict[str, Any]] = []
    reports = output / dataset_id
    reports.mkdir(parents=True)
    for entry in dataset.manifest.entries:
        sweep = store.inspect_sweep(dataset_id, entry.sweep_id)
        values = store.read_ci16(sweep, verify=True)
        captured = _captured_sweep(dataset_id, sweep, values)
        scan_id = f"replay-{dataset_id}-{entry.sweep_id}"
        report = analyze_scan_sweep(captured, scan_id=scan_id)
        report_path = reports / f"{entry.sweep_id}.scanner-report.json"
        write_scanner_report(report_path, report)
        sweep_counts: Counter[str] = Counter()
        decisions: list[dict[str, Any]] = []
        frames_by_target = {frame.target_index: frame for frame in sweep.manifest.frames}
        for target_index, result in enumerate(report.results):
            reference = truth[(entry.sweep_id, target_index)]
            source = frames_by_target[target_index].source
            outcome = _outcome(reference.label, result.decision)
            sweep_counts[outcome] += 1
            counts[outcome] += 1
            decisions.append(
                {
                    "target_index": target_index,
                    "channel": result.target.channel,
                    "edge": result.target.edge.value,
                    "reference": reference.label.value,
                    "decision": result.decision.value,
                    "outcome": outcome,
                    "best_margin": result.best_margin,
                    "source": {
                        "session_id": source.session_id,
                        "stream_id": source.stream_id,
                        "sample_start": source.source_sample_start,
                    },
                }
            )
        sweeps.append(
            {
                "sweep_id": entry.sweep_id,
                "split": entry.split.value,
                "report": str(report_path.relative_to(output)),
                "analysis_elapsed_ms": report.analysis_elapsed_ms,
                "counts": dict(sorted(sweep_counts.items())),
                "decisions": decisions,
            }
        )
    return {
        "dataset_id": dataset_id,
        "dataset_manifest_sha256": dataset.manifest_sha256,
        "counts": dict(sorted(counts.items())),
        "rates": _rates(counts),
        "sweeps": sweeps,
    }


def main() -> int:
    arguments = _arguments()
    output_root = arguments.output_root.resolve(strict=False)
    if not output_root.is_absolute() or str(output_root).startswith("/mnt/qnap01"):
        raise ValueError("evaluation output must use an approved local absolute path")
    output_root.mkdir(parents=True, exist_ok=True)
    destination = output_root / arguments.evaluation_id
    if destination.exists():
        raise FileExistsError(f"evaluation already exists: {destination}")
    temporary = Path(tempfile.mkdtemp(prefix=f".{arguments.evaluation_id}.", dir=output_root))
    temporary.chmod(0o755)
    try:
        store = ScannerReplayStore(arguments.bulk_root)
        datasets = [
            _evaluate_dataset(store, dataset_id, temporary) for dataset_id in arguments.dataset_ids
        ]
        total: Counter[str] = Counter()
        for dataset in datasets:
            total.update(dataset["counts"])
        summary = {
            "schema_version": 1,
            "kind": "scanner_replay_evaluation",
            "evaluation_id": arguments.evaluation_id,
            "analyzer": "leo.scanner.analyze_scan_sweep",
            "datasets": datasets,
            "aggregate": {
                "counts": dict(sorted(total.items())),
                "rates": _rates(total),
            },
        }
        (temporary / "summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
        print(json.dumps({**summary["aggregate"], "path": str(destination)}, indent=2))
    except Exception:
        shutil.rmtree(temporary)
        raise
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
