#!/usr/bin/env python3
"""Measured full-dwell screening plus blind/seeded fractional confirmation."""

from __future__ import annotations

import argparse
import json
from contextlib import ExitStack
from pathlib import Path

import numpy as np

from tools.evaluate_native_presence_budgets import associated
from tools.evaluate_presence_window_rank import load_dwells
from tools.native_presence import ROOT, build_dwell_presence
from tools.presence_dwell import NativeDwell, unpack
from tools.presence_fftw import fftw_identity, fftw_options
from tools.qualify_native_presence import digest, write_json
from tools.qualify_presence_worker import compare_values


def summarize(rows):
    summary = {}

    def identity(row):
        return row["rate_hz"], row["bins"], row.get("timing_bins", 0), row["mode"]

    for rate, bins, timing_bins, mode in sorted({identity(r) for r in rows}):
        subset = [r for r in rows if identity(r) == (rate, bins, timing_bins, mode)]
        policies = {}
        for k in (1, 2, 3, 6):
            policies[str(k)] = {
                "reference_selected": sum(
                    any(r["reference_positive"][i] for i in r["result"]["rank"]["order"][:k])
                    for r in subset
                ),
                "associated": sum(
                    any(o["associated"] for o in r["observations"][:k]) for r in subset
                ),
                "flagged_without_association": sum(
                    any(o["detected"] for o in r["observations"][:k])
                    and not any(o["associated"] for o in r["observations"][:k])
                    for r in subset
                ),
                "desktop_prefix_cpu_p50_p99_max_ms": np.percentile(
                    [r["result"]["prefix_cpu_ms"][k - 1] for r in subset], [50, 99, 100]
                ).tolist(),
            }
        label = f"{rate}:{bins}:{timing_bins}:{mode}" if timing_bins else f"{rate}:{bins}:{mode}"
        summary[label] = {
            "visits": len(subset),
            "reference_positive_visits": sum(any(r["reference_positive"]) for r in subset),
            "policies": policies,
        }
    return summary


def evaluate(
    directory: Path,
    output: Path,
    *,
    multires=False,
    integer_fold=False,
    fftw_prefix: Path | None = None,
    area_screen: bool = False,
    hybrid_screen: bool = False,
):
    if area_screen and hybrid_screen:
        raise ValueError("choose either area-only or hybrid screen")
    if integer_fold and not multires:
        raise ValueError("integer folding experiment requires the frozen multires protocol")
    directory, output = directory.resolve(), output.resolve()
    fft_options = fftw_options(fftw_prefix) if fftw_prefix is not None else None
    if any(
        output.is_relative_to(p) for p in (directory, Path("/mnt/qnap01"), Path("/srv/bulk/leo"))
    ):
        raise ValueError("output must be separate from source/archive")
    protocol_path = (
        ROOT
        / "config/analysis"
        / ("arm-presence-multires-v1.json" if multires else "arm-presence-proposal-reuse-v1.json")
    )
    protocol = json.loads(protocol_path.read_text())
    optimization = None
    if integer_fold:
        optimization_path = ROOT / "config/analysis/arm-presence-fold-ci16-v1.json"
        optimization = json.loads(optimization_path.read_text())
        if optimization["base_protocol"] != str(protocol_path.relative_to(ROOT)) or optimization[
            "extra_defines"
        ] != {"DIFFERENTIAL_CI16": 1}:
            raise ValueError("unreviewed integer folding configuration")
    if (
        protocol["maximum_confirmations"] != 6
        or protocol["research_margin"] != 0.025
        or protocol["receiver"] != 1
    ):
        raise ValueError("unreviewed confirmation policy")
    detector_path = ROOT / protocol["detector_protocol"]
    detector = json.loads(detector_path.read_text())
    output.mkdir(parents=True, exist_ok=False)
    write_json(
        output / "freeze.json",
        {
            "schema": "org.leo.research.presence-dwell-freeze/v1",
            "state": "configuration_frozen_before_execution_existing_cohort_is_development",
            "protocol": protocol,
            "protocol_sha256": digest(protocol_path),
            "detector_protocol_sha256": digest(detector_path),
            "inputs_sha256": digest(directory / "inputs.json"),
            "prior_results_sha256": digest(directory / "results.json"),
            "evaluation_tool_sha256": digest(Path(__file__)),
            "optimization": optimization,
            "optimization_sha256": digest(optimization_path) if optimization else None,
            "fft_backend": fftw_identity(fft_options) if fft_options else "builtin_fp64",
            "screen_projection": "hybrid_max_second_ratio"
            if hybrid_screen
            else ("area_average" if area_screen else "point_interpolation"),
        },
    )
    flags = tuple(detector["common_flags"]) + tuple(
        f"-DLEO_PRESENCE_{k}={v}" for k, v in detector["variants"][0]["defines"].items()
    )
    if optimization:
        flags += tuple(f"-DLEO_PRESENCE_{k}={v}" for k, v in optimization["extra_defines"].items())
    if area_screen:
        flags += ("-DLEO_PRESENCE_RANK_AREA_PROJECTION=1",)
    if hybrid_screen:
        flags += ("-DLEO_PRESENCE_RANK_HYBRID_PROJECTION=1",)
    library = build_dwell_presence(
        output / "dwell.so",
        cflags=flags + (fft_options["cflags"] if fft_options else ()),
        ldflags=fft_options["ldflags"] if fft_options else (),
        dependencies=fft_options["dependencies"] if fft_options else (),
    )
    inputs = {r["file"]: r for r in json.loads((directory / "inputs.json").read_text())}
    priors = {r["probe"]: r for r in json.loads((directory / "results.json").read_text())}
    rows, blind_parity = [], 0
    with ExitStack() as stack, (output / "results.jsonl").open("x") as stream:
        workspaces = {}
        for metadata, iq in load_dwells(directory):
            rate = metadata["rate_hz"]
            grids = [
                (bins, timing)
                for bins in protocol["grids_by_rate"][str(rate)]
                for timing in protocol.get("timing_grids_by_rate", {}).get(str(rate), [None])
            ]
            for bins, timing in grids:
                key = (rate, metadata["edge"], bins, timing)
                if key not in workspaces:
                    workspaces[key] = stack.enter_context(NativeDwell(library, *key))
                for mode in protocol["modes"]:
                    result = unpack(workspaces[key].run(iq, seeded=mode == "seeded"))
                    result["screen_diagnostics"] = unpack(workspaces[key].screens())
                    observations = []
                    for position, window in enumerate(result["rank"]["order"]):
                        source = metadata["source_files"][window]
                        confirmation = result["confirmations"][position]
                        candidates = confirmation["candidates"][: confirmation["candidate_count"]]
                        positive = [
                            c
                            for c in inputs[source]["oracle_candidates"]
                            if c["margin"] >= protocol["research_margin"]
                        ]
                        detected = [
                            c
                            for c in candidates
                            if c["fractional_complete"]
                            and c["margin"] >= protocol["research_margin"]
                        ]
                        matched = any(
                            associated(a, b, rate, protocol["reference_association"])
                            for a in detected
                            for b in positive
                        )
                        if mode == "blind":
                            expected = priors[source]["result"]["candidates"]
                            if len(expected) != len(candidates):
                                raise ValueError("blind comparator changed candidate count")
                            for actual, reference in zip(candidates, expected, strict=True):
                                # The archived CLI persisted eight candidate fields;
                                # the in-process structure also has diagnostic grids.
                                # Compare every persisted field with its old tolerance.
                                compare_values({key: actual[key] for key in reference}, reference)
                            blind_parity += 1
                        observations.append(
                            {"window": window, "detected": bool(detected), "associated": matched}
                        )
                    row = {
                        **metadata,
                        "bins": bins,
                        "timing_bins": timing or 0,
                        "mode": mode,
                        "result": result,
                        "observations": observations,
                    }
                    rows.append(row)
                    stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
    result = {
        "schema": "org.leo.research.presence-dwell-results/v1",
        "status": "development_only_no_live_or_absence_claim",
        "binary_sha256": digest(library),
        "blind_windows_matching_frozen_outputs": blind_parity,
        "results": summarize(rows),
    }
    write_json(output / "summary.json", result)
    print(json.dumps(result, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--multires", action="store_true")
    parser.add_argument("--integer-fold", action="store_true")
    parser.add_argument("--fftw-prefix", type=Path)
    parser.add_argument("--area-screen", action="store_true")
    parser.add_argument("--hybrid-screen", action="store_true")
    args = parser.parse_args()
    evaluate(
        args.directory,
        args.output,
        multires=args.multires,
        integer_fold=args.integer_fold,
        fftw_prefix=args.fftw_prefix,
        area_screen=args.area_screen,
        hybrid_screen=args.hybrid_screen,
    )


if __name__ == "__main__":
    main()
