#!/usr/bin/env python3
"""Run the source-bound Doppler analyzer sequentially over a frozen dwell cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from tools.analyze_raw_dwell_doppler import analyze_raw_dwell
except ModuleNotFoundError:  # Direct ``python tools/...`` invocation.
    from analyze_raw_dwell_doppler import analyze_raw_dwell

DEFAULT_BULK_ROOT = Path("/srv/bulk/leo")
DEFAULT_INPUTS = Path("reports/figures/2026_08_24_recent_50_doppler/inputs.json")
DEFAULT_OUTPUT_ROOT = Path("reports/figures/2026_08_24_recent_50_doppler/results")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bulk-root", type=Path, default=DEFAULT_BULK_ROOT)
    parser.add_argument("--inputs", type=Path, default=DEFAULT_INPUTS)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--maximum-track-attempts", type=int, default=4)
    parser.add_argument("--only-label")
    parser.add_argument("--maximum-dwells", type=int)
    parser.add_argument("--resume", action="store_true")
    return parser.parse_args()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected one JSON object: {path}")
    return value


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def validated_dwells(path: Path) -> tuple[dict[str, Any], ...]:
    document = _load(path)
    if document.get("schema") != "org.leo.research.recent-raw-doppler-inputs/v1":
        raise ValueError("unexpected recent raw-Doppler input schema")
    rows = tuple(document.get("dwells", ()))
    if document.get("selected_dwell_count") != len(rows) or len(rows) < 50:
        raise ValueError("recent raw-Doppler cohort must contain at least 50 dwells")
    identities = {(row.get("session_id"), row.get("run_id")) for row in rows}
    labels = {row.get("label") for row in rows}
    if len(identities) != len(rows) or len(labels) != len(rows):
        raise ValueError("recent raw-Doppler cohort identities and labels must be unique")
    return rows


def _output_path(root: Path, row: dict[str, Any]) -> Path:
    return root / f"{row['label']}-{str(row['session_id']).rsplit('-', 1)[-1]}.json"


def _is_reusable(path: Path, row: dict[str, Any]) -> bool:
    if not path.is_file():
        return False
    try:
        document = _load(path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return bool(
        document.get("schema") == "org.leo.research.raw-dwell-doppler/v1"
        and document.get("session_id") == row["session_id"]
        and document.get("run_id") == row["run_id"]
        and document.get("analysis_manifest_digest") == row["analysis_manifest_digest"]
        and document.get("recording_manifest_digest") == row["recording_manifest_digest"]
    )


def _atomic_json(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _index_document(
    *, inputs_path: Path, rows: tuple[dict[str, Any], ...], output_root: Path
) -> dict[str, Any]:
    results = []
    for row in rows:
        path = _output_path(output_root, row)
        if not path.is_file():
            results.append(
                {"label": row["label"], "session_id": row["session_id"], "status": "pending"}
            )
            continue
        document = _load(path)
        results.append(
            {
                "label": row["label"],
                "session_id": row["session_id"],
                "run_id": row["run_id"],
                "status": document.get("status", "execution_error"),
                "result_path": str(path),
                "result_digest": _digest(path),
            }
        )
    return {
        "schema": "org.leo.research.raw-doppler-cohort-index/v1",
        "inputs_path": str(inputs_path),
        "inputs_digest": _digest(inputs_path),
        "dwell_count": len(rows),
        "completed_result_count": sum(item["status"] != "pending" for item in results),
        "results": results,
    }


def run_cohort(
    *,
    bulk_root: Path,
    inputs_path: Path,
    output_root: Path,
    maximum_track_attempts: int,
    only_label: str | None,
    maximum_dwells: int | None,
    resume: bool,
) -> None:
    rows = validated_dwells(inputs_path)
    selected = tuple(row for row in rows if only_label is None or row["label"] == only_label)
    if only_label is not None and not selected:
        raise ValueError(f"cohort label is absent: {only_label}")
    if maximum_dwells is not None:
        if maximum_dwells < 1:
            raise ValueError("maximum dwells must be positive")
        selected = selected[:maximum_dwells]
    output_root.mkdir(parents=True, exist_ok=True)
    for position, row in enumerate(selected, start=1):
        path = _output_path(output_root, row)
        if resume and _is_reusable(path, row):
            print(f"{row['label']} {position}/{len(selected)}: reuse {path}", flush=True)
            continue
        print(
            f"{row['label']} {position}/{len(selected)}: analyze {row['session_id']}",
            flush=True,
        )
        try:
            result = analyze_raw_dwell(
                bulk_root=bulk_root,
                session_id=str(row["session_id"]),
                run_id=str(row["run_id"]),
                maximum_track_attempts=maximum_track_attempts,
                include_frames=False,
            )
        except Exception as error:  # Cohort inventory must survive one failed dwell.
            result = {
                "schema": "org.leo.research.raw-dwell-doppler-execution-error/v1",
                "session_id": row["session_id"],
                "run_id": row["run_id"],
                "status": "execution_error",
                "error_type": type(error).__name__,
                "error": str(error),
                "candidate_only": True,
            }
        _atomic_json(path, result)
        _atomic_json(
            output_root / "index.json",
            _index_document(inputs_path=inputs_path, rows=rows, output_root=output_root),
        )
    _atomic_json(
        output_root / "index.json",
        _index_document(inputs_path=inputs_path, rows=rows, output_root=output_root),
    )


def main() -> None:
    arguments = _arguments()
    run_cohort(
        bulk_root=arguments.bulk_root,
        inputs_path=arguments.inputs,
        output_root=arguments.output_root,
        maximum_track_attempts=arguments.maximum_track_attempts,
        only_label=arguments.only_label,
        maximum_dwells=arguments.maximum_dwells,
        resume=arguments.resume,
    )


if __name__ == "__main__":
    main()
