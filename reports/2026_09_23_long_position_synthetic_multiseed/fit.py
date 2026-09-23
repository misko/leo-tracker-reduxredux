#!/usr/bin/env python3
"""Run blinded fixed-setting fits for the frozen multi-seed control."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import numpy as np

CASES = ("gaussian_300hz", "gaussian_300hz_satellite_epoch_0p3s")
PRIORS = ("sacramento", "reno")


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_module(path: Path):
    spec = importlib.util.spec_from_file_location("multiseed_fixed_fitter", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(args):
    if args.output.exists():
        raise FileExistsError("fresh output required")
    fixed = load_module(args.fixed_fitter)
    archive = np.load(args.materialized, allow_pickle=False)
    arrays = {key: archive[key] for key in archive.files}
    archive.close()
    started = time.monotonic()
    fits = []
    for seed_index, seed in enumerate(arrays["seeds"]):
        for case in CASES:
            measured = arrays[f"{case}_hz"][seed_index]
            for prior in PRIORS:
                row = fixed.fit_one(arrays, measured, prior)
                row.pop("track_training")
                fits.append({"seed": int(seed), "case": case, **row})
    inference = {
        "schema": "long-position-synthetic-multiseed-inference/v1",
        "control_only": True,
        "generator_coordinate_available_to_fit": False,
        "geographic_or_held_selection": False,
        "seeds": arrays["seeds"].tolist(),
        "cases": CASES,
        "priors": PRIORS,
        "fits": fits,
        "runtime_s": time.monotonic() - started,
        "bindings": {
            "protocol": digest(Path(__file__).with_name("PROTOCOL.md")),
            "materialized_npz": digest(args.materialized),
            "fixed_fitter": digest(args.fixed_fitter),
            "tool": digest(Path(__file__)),
        },
    }
    args.output.mkdir(parents=True)
    payload = json.dumps(inference, indent=2, sort_keys=True) + "\n"
    (args.output / "inference.json").write_text(payload)
    (args.output / "inference.sha256").write_text(
        hashlib.sha256(payload.encode()).hexdigest() + "\n"
    )

    generation = json.loads(args.materialization_receipt.read_text())
    truth = generation["generator"]
    results = json.loads(payload)
    for row in results["fits"]:
        seed_index = int(np.flatnonzero(arrays["seeds"] == row["seed"])[0])
        measured = arrays[f"{row['case']}_hz"][seed_index]
        _unused, details = fixed.residual_rows(
            arrays, measured, (row["latitude_deg"], row["longitude_deg"]), False
        )
        held_capped, held_uncapped = fixed.summarize(details, "held_rms_hz")
        row["held_capped800_rmse_hz"] = held_capped
        row["held_uncapped_rmse_hz"] = held_uncapped
        row["postseal_error_km"] = fixed.haversine_km(
            (row["latitude_deg"], row["longitude_deg"]),
            (truth["latitude_deg"], truth["longitude_deg"]),
        )
    summaries = []
    for case in CASES:
        for prior in PRIORS:
            rows = [
                row for row in results["fits"]
                if row["case"] == case and row["prior"] == prior
            ]
            errors = np.asarray([row["postseal_error_km"] for row in rows])
            summaries.append({
                "case": case,
                "prior": prior,
                "fit_count": len(rows),
                "optimizer_success_count": sum(row["optimizer_success"] for row in rows),
                "median_error_km": float(np.median(errors)),
                "p90_error_km": float(np.percentile(errors, 90)),
                "fraction_below_0p300_km": float(np.mean(errors < 0.300)),
                "maximum_error_km": float(np.max(errors)),
                "median_training_uncapped_rmse_hz": float(np.median(
                    [row["training_uncapped_rmse_hz"] for row in rows]
                )),
                "median_held_uncapped_rmse_hz": float(np.median(
                    [row["held_uncapped_rmse_hz"] for row in rows]
                )),
            })
    results["postseal_generator"] = truth
    results["postseal_summaries"] = summaries
    results["bindings"]["materialization_receipt"] = digest(args.materialization_receipt)
    result_payload = json.dumps(results, indent=2, sort_keys=True) + "\n"
    (args.output / "results.json").write_text(result_payload)
    (args.output / "results.sha256").write_text(
        hashlib.sha256(result_payload.encode()).hexdigest() + "\n"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--materialized", type=Path, required=True)
    parser.add_argument("--materialization-receipt", type=Path, required=True)
    parser.add_argument("--fixed-fitter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
