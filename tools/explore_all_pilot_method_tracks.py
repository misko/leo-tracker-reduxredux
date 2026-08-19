#!/usr/bin/env python3
"""Render the same CFO-linking experiment for every pilot/QAM metric family.

This diagnostic reuses the deterministic linkers in ``explore_glrt64_tracks``
and maps each method's score and residual-CFO columns into the common candidate
shape.  It writes one four-panel PNG per detector plus the individual linker
panels and JSON provenance.  It does not alter the Standard pipeline.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

DEFAULT_INPUT = Path(
    "artifacts/production-24h-20260819-01-trial-00000132-stream-0-rx0-pilot-methods.csv"
)


@dataclass(frozen=True, slots=True)
class MethodSpec:
    key: str
    label: str
    score_field: str
    control_field: str | None
    selection_field: str
    residual_field: str | None
    minimum_selection: float
    selection_label: str = "exact − control margin"


METHODS = (
    MethodSpec(
        "anchor8",
        "Anchor-8",
        "anchor8_score",
        "anchor8_control_score",
        "anchor8_margin",
        None,
        0.40,
    ),
    MethodSpec(
        "differential16",
        "Differential-16",
        "differential16_score",
        "differential16_control_score",
        "differential16_margin",
        "differential16_residual_cfo_hz",
        0.40,
    ),
    MethodSpec(
        "differential32",
        "Differential-32",
        "differential32_score",
        "differential32_control_score",
        "differential32_margin",
        "differential32_residual_cfo_hz",
        0.40,
    ),
    MethodSpec(
        "glrt32",
        "GLRT-32",
        "glrt32_score",
        "glrt32_control_score",
        "glrt32_margin",
        "glrt32_residual_cfo_hz",
        0.40,
    ),
    MethodSpec(
        "glrt64",
        "GLRT-64",
        "glrt64_score",
        "glrt64_control_score",
        "glrt64_margin",
        "glrt64_residual_cfo_hz",
        0.40,
    ),
    MethodSpec(
        "edge_tracker",
        "Legacy edge tracker",
        "edge_tracker_score",
        "edge_tracker_control_score",
        "edge_tracker_margin",
        None,
        0.05,
    ),
    MethodSpec(
        "symbolwise",
        "Current symbolwise",
        "symbolwise_margin",
        None,
        "symbolwise_margin",
        None,
        0.05,
    ),
    MethodSpec(
        "qam_accuracy",
        "Known-symbol QAM",
        "qam_accuracy",
        None,
        "qam_accuracy",
        None,
        0.60,
        "hard-symbol accuracy",
    ),
)


def _tracker():
    path = Path(__file__).with_name("explore_glrt64_tracks.py")
    spec = importlib.util.spec_from_file_location("explore_glrt64_tracks_shared", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load shared track-linking diagnostic")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-directory", type=Path, default=Path("artifacts"))
    parser.add_argument(
        "--method",
        action="append",
        choices=tuple(spec.key for spec in METHODS),
        help="render only the selected method; repeatable (default: all)",
    )
    return parser.parse_args()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while block := source.read(1024 * 1024):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def _value(row: dict[str, str], field: str | None, default: float = 0.0) -> float:
    if field is None:
        return default
    value = row.get(field, "")
    if not value:
        raise ValueError(f"required column {field!r} is absent or empty")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"required column {field!r} is not finite")
    return result


def _candidates(tracker, rows: tuple[dict[str, str], ...], method: MethodSpec):
    candidates = []
    for row in rows:
        if not row.get("acquired_cfo_hz") or not row.get(method.selection_field):
            continue
        acquired = _value(row, "acquired_cfo_hz")
        residual = _value(row, method.residual_field)
        selection = _value(row, method.selection_field)
        candidates.append(
            tracker.Candidate(
                index=int(row["index"]),
                time_s=_value(row, "time_s"),
                acquired_cfo_hz=acquired,
                residual_cfo_hz=residual,
                refined_cfo_hz=acquired + residual,
                glrt64_score=_value(row, method.score_field),
                glrt64_control_score=_value(row, method.control_field),
                glrt64_margin=selection,
                qam_accuracy=float(row["qam_accuracy"]) if row.get("qam_accuracy") else None,
            )
        )
    if not candidates:
        raise ValueError(f"no complete {method.key} candidates")
    return tuple(candidates)


def _output_path(directory: Path, input_path: Path, method: MethodSpec) -> Path:
    stem = input_path.stem
    if stem.endswith("-pilot-methods"):
        stem = stem.removesuffix("-pilot-methods")
    return directory / f"{stem}-{method.key}-tracks.png"


def main() -> int:
    args = _arguments()
    tracker = _tracker()
    with args.input.open("r", encoding="utf-8", newline="") as source:
        rows = tuple(csv.DictReader(source))
    requested = set(args.method or ())
    methods = tuple(spec for spec in METHODS if not requested or spec.key in requested)
    args.output_directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    for method in methods:
        candidates = _candidates(tracker, rows, method)
        selected = np.asarray(
            [item.glrt64_margin >= method.minimum_selection for item in candidates],
            dtype=bool,
        )
        approaches = (
            ("continuity", tracker.continuity_tracks(candidates, selected)),
            ("predictive", tracker.predictive_tracks(candidates, selected)),
            ("robust_quadratic", tracker.robust_quadratic_tracks(candidates, selected)),
            (
                "stitched_predictive",
                tracker.stitched_predictive_tracks(candidates, selected),
            ),
        )
        output = _output_path(args.output_directory, args.input, method)
        plots = tracker._render(
            output,
            candidates,
            selected,
            approaches,
            method.minimum_selection,
            method_label=method.label,
            selection_label=method.selection_label,
        )
        document = {
            "method": asdict(method),
            "input": str(args.input.resolve()),
            "input_sha256": _sha256(args.input),
            "candidate_count": len(candidates),
            "selected_count": int(np.count_nonzero(selected)),
            "one_candidate_per_timestamp_limitation": True,
            "production_calibrated": False,
            "approaches": {
                name: [asdict(track) for track in tracks] for name, tracks in approaches
            },
            "plots": [
                {"path": str(path.resolve()), "sha256": _sha256(path)} for path in (output, *plots)
            ],
        }
        metadata = output.with_suffix(".json")
        metadata.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        outputs.append(
            {
                "method": method.key,
                "png": str(output.resolve()),
                "metadata": str(metadata.resolve()),
                "selected": int(np.count_nonzero(selected)),
                "tracks": {name: len(tracks) for name, tracks in approaches},
            }
        )
    print(json.dumps({"outputs": outputs}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
