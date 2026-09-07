#!/usr/bin/env python3
"""Evaluation-only reveal: seals finished inference outputs before reading truth.

This tool has no estimator imports and writes only evaluation artefacts. Its
outputs must never be consumed by the search or refinement-point generator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np


def evaluate(runs, truth_path, output, polishes=()):
    if output.exists():
        raise ValueError("fresh evaluation output required")
    frozen = []
    for run in runs:
        result = json.loads((run / "result.json").read_text())
        if not result.get("complete") or result["position_truth_used"]:
            raise ValueError("only finished truth-free inference runs may be revealed")
        files = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(run.iterdir())
            if path.suffix in (".json", ".npz") and path.name != "evaluation-seal.json"
        }
        seal = run / "evaluation-seal.json"
        if seal.exists():
            if json.loads(seal.read_text()) != files:
                raise ValueError("inference changed after evaluation seal")
        else:
            seal.write_text(json.dumps(files, indent=2) + "\n")
        frozen.append((run, result, hashlib.sha256(seal.read_bytes()).hexdigest()))
    frozen_polishes = []
    for path in polishes:
        document = json.loads(path.read_text())
        if not document.get("complete") or document["position_truth_used"]:
            raise ValueError("unfinished or truth-informed local polish")
        frozen_polishes.append((path, document, hashlib.sha256(path.read_bytes()).hexdigest()))
    polish_seal = output.with_suffix(".inference-seal.json")
    if polish_seal.exists():
        raise ValueError("evaluation seal already exists")
    polish_seal.write_text(json.dumps({str(p): d for p, _, d in frozen_polishes}, indent=2) + "\n")
    # The first and only read of the user-provided answer occurs after sealing.
    truth = json.loads(truth_path.read_text())
    lat0, lon0 = np.deg2rad([truth["latitude_deg"], truth["longitude_deg"]])
    records = []
    for run, result, seal_digest in frozen:
        history = json.loads((run / "history.json").read_text())
        lat = np.deg2rad([row["latitude_deg"] for row in history])
        lon = np.deg2rad([row["longitude_deg"] for row in history])
        a = (
            np.sin((lat - lat0) / 2) ** 2
            + np.cos(lat0) * np.cos(lat) * np.sin((lon - lon0) / 2) ** 2
        )
        distances = 2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
        records.append(
            {
                "run": run.name,
                "region_km": result["region"]["width_km"],
                "seal_digest": seal_digest,
                "horizontal_error_m": float(distances[-1]),
                "history_horizontal_error_m": distances.tolist(),
                "latitude_deg": result["latitude_deg"],
                "longitude_deg": result["longitude_deg"],
                "heldout_score": result["heldout_score_at_train_best"],
                "scan_count": result["scan_count"],
                "episode_count": result["episode_count"],
            }
        )
    polish_records = []
    for path, document, seal_digest in frozen_polishes:
        for model in document["models"]:
            lat, lon = np.deg2rad([model["latitude_deg"], model["longitude_deg"]])
            a = (
                np.sin((lat - lat0) / 2) ** 2
                + np.cos(lat0) * np.cos(lat) * np.sin((lon - lon0) / 2) ** 2
            )
            polish_records.append(
                {
                    "file": path.name,
                    "parent_run": document["parent_run"],
                    "seal_digest": seal_digest,
                    "region_km": document["region"]["width_km"],
                    "horizontal_error_m": float(
                        2 * 6371008.8 * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
                    ),
                    "episode_count": document["episode_count"],
                    **model,
                }
            )
    output.write_text(
        json.dumps(
            {
                "purpose": "evaluation_only",
                "truth": truth,
                "runs": records,
                "polishes": polish_records,
            },
            indent=2,
        )
        + "\n"
    )
    for row in records:
        print(f"{row['run']}: {row['horizontal_error_m']:.1f} m horizontal error")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=Path, nargs="+", required=True)
    parser.add_argument("--truth", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--polishes", type=Path, nargs="*", default=[])
    args = parser.parse_args()
    evaluate(args.runs, args.truth, args.output, args.polishes)


if __name__ == "__main__":
    main()
