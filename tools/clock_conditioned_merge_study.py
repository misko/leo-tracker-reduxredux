"""Freeze matched common-drift bootstrap and fixed-point coarse c ablations."""

import argparse
import json
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import LOCAL, PREVIOUS, REPORT, ROOT
from continuous_merge_positions import load_prepared
from continuous_merge_study import plain, sha, write
from global_band_merge_study import ORIGINAL

from leo.analysis.clock_conditioned_bootstrap import (
    ClockConditioningConfiguration,
    bootstrap_with_clock_conditioning,
)
from leo.analysis.continuous_merge_bootstrap import ContinuousBootstrapPolicy
from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.lnb_band_calibration import calibrated_band_observations
from leo.analysis.regional_position_fit import fit_position
from leo.application.hard60_runner import HARD60_SCORE
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior

DESTINATION = REPORT / "local/clock-conditioned"
MODES = {
    "original-control": ("none", "baseline"),
    "joined-control": ("none", "consistent"),
    "original-conditioned": ("alternating", "baseline"),
    "joined-conditioned": ("alternating", "consistent"),
}


def verify(bindings):
    for path, digest in bindings.items():
        if sha(Path(path)) != digest:
            raise ValueError("clock-conditioned authority changed: " + path)


def freeze():
    output = DESTINATION / "protocol.json"
    if output.exists():
        raise ValueError("clock-conditioned protocol already frozen")
    selection_path = PREVIOUS / "cohort-selection.json"
    selection = json.loads(selection_path.read_bytes())
    donor_path = LOCAL / "DS20/fast-014c72ff95ab599c51ba3b3ec9b92cb8/cal-independent-fitted-c.json"
    donor = json.loads(donor_path.read_bytes())
    if not donor["fit"]["converged"] or donor["reference_usage"] != "none":
        raise ValueError("stationary reference-free donor required")
    donor_protocol_path = donor_path.parent / "protocol.json"
    donor_protocol = json.loads(donor_protocol_path.read_bytes())
    verify(donor_protocol["bindings"])
    if donor_protocol["role"] != "development":
        raise ValueError("calibration donor must be development")
    donor_source_path = ORIGINAL / "local/DS20" / donor_protocol["session_id"] / "source.json"
    donor_source = json.loads(donor_source_path.read_bytes())
    cases, paths = [], [Path(__file__), selection_path, donor_path, ORIGINAL / "membership.json"]
    paths += [donor_protocol_path, donor_source_path]
    paths += sorted((ROOT / "src/leo/analysis").glob("*.py"))
    paths += sorted((ROOT / "src/leo/application").glob("*.py"))
    paths += sorted((ROOT / "src/leo/contracts").glob("*.py"))
    paths += [
        ROOT / "tools/continuous_merge_positions.py",
        ROOT / "tools/continuous_merge_study.py",
    ]
    for member in selection["members"]:
        old = ORIGINAL / "local" / member["dataset"] / member["session_id"]
        terminal_path = (
            PREVIOUS
            / "local"
            / member["dataset"]
            / member["session_id"]
            / "positions/baseline/terminal.json"
        )
        terminal = json.loads(terminal_path.read_bytes())
        if terminal["status"] != "complete":
            raise ValueError("old baseline incomplete")
        final = next(f for f in terminal["result"]["finals"] if f["arm"] == "fitted-c")
        point = tuple(float(v) for v in final["basin"].split(":")[-2:])
        prepared = load_prepared(old / "baseline.json")
        high = int(sum(prepared.observations.channel >= 5))
        source = json.loads((old / "source.json").read_bytes())
        if high and source["radio_id"] != donor_source["radio_id"]:
            raise ValueError("same-radio calibration donor required")
        paths += [terminal_path]
        paths += [
            old / name
            for name in (
                "baseline.json",
                "replace-guard.json",
                "census.json",
                "source.json",
                "positions/experiment.json",
                "positions/bank.npz",
            )
        ]
        old_protocol = json.loads((old / "positions/experiment.json").read_bytes())
        if sha(old / "positions/bank.npz") != old_protocol["bank_sha256"]:
            raise ValueError("initial bank changed")
        cases.append(
            {
                "dataset": member["dataset"],
                "session_id": member["session_id"],
                "role": member["role"],
                "original_case": str(old),
                "point": point,
                "point_source": str(terminal_path),
                "high_band_rows": high,
                "calibrations": ["raw", "cal"] if high else ["raw"],
            }
        )
    write(
        output,
        {
            "cases": cases,
            "bindings": {str(p): sha(p) for p in paths},
            "modes": MODES,
            "configuration": asdict(ClockConditioningConfiguration()),
            "fixed_band_offsets_hz": donor["band_offsets_hz"],
            "bootstrap_seconds": 120,
            "coarse_seconds": 20,
            "coarse_iterations": 600,
            "reference_usage": "none in freeze/execute",
            "scope": (
                "Fixed eight-member development selection. One common raw-baseline data-selected "
                "point per recording, initial catalogue and original/joined pool. Four modes cross "
                "conditioning and protected joins; all use three starts times three passes and one "
                "120s initializer bound. Branch selection uses fixed original supports/weights and "
                "physical common-clock coherence; no per-track free constant in this selection. "
                "Raw versus fixed donor correction on DS20; no redundant correction "
                "for no-high DS16. Both c arms use identical observations, returned bank, seed, "
                "priors, fixed point, 20s/600iter coarse bounds. Conditional initializer/coarse "
                "diagnostic only, not a full search, final B7 result or geographic validation."
            ),
        },
    )
    print(json.dumps({"cases": len(cases), "protocol_sha256": sha(output)}), flush=True)


def execute(dataset):
    protocol_path = DESTINATION / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol["bindings"])
    for case in protocol["cases"]:
        if case["dataset"] != dataset:
            continue
        old = Path(case["original_case"])
        prepared, merged = (
            load_prepared(old / name) for name in ("baseline.json", "replace-guard.json")
        )
        with np.load(old / "positions/bank.npz") as z:
            bank = PositionOrbitBank(**{key: z[key] for key in z.files})
        for calibration in case["calibrations"]:
            offsets = protocol["fixed_band_offsets_hz"] if calibration == "cal" else [0.0, 0.0]
            observations, _ = calibrated_band_observations(prepared.observations, offsets)
            for mode, (conditioning, merge_policy) in protocol["modes"].items():
                output = (
                    DESTINATION
                    / dataset
                    / case["session_id"]
                    / (calibration + "-" + mode + ".json")
                )
                if output.exists():
                    continue
                began, audit = time.monotonic(), []
                result = {
                    "case": case,
                    "calibration": calibration,
                    "mode": mode,
                    "protocol_sha256": sha(protocol_path),
                    "status": "failed",
                    "reason": None,
                    "reference_usage": "none",
                }
                try:
                    seed = bootstrap_with_clock_conditioning(
                        observations,
                        bank,
                        RegionalPrior(),
                        case["point"],
                        prepared.bootstrap_tracks,
                        merged_tracks=merged.bootstrap_tracks,
                        configuration=ClockConditioningConfiguration(
                            **{**protocol["configuration"], "conditioning": conditioning}
                        ),
                        policy=ContinuousBootstrapPolicy(mode=merge_policy),
                        maximum_seconds=protocol["bootstrap_seconds"],
                        orbit_predictor=predict_orbits,
                        audit=audit.append,
                    )
                    model = Hard60Objective(
                        observations,
                        bank.select(list(seed.satellite_indices)),
                        RegionalPrior(),
                        HARD60_SCORE,
                    )
                    fits = {}
                    for arm in ("fitted-c", "zero-c"):
                        fits[arm] = plain(
                            fit_position(
                                model,
                                seed.vector,
                                rf_arm=arm,
                                fixed_position=True,
                                maximum_seconds=protocol["coarse_seconds"],
                                maximum_iterations=protocol["coarse_iterations"],
                                slope_half_width_hz_s=60,
                            )
                        )
                    result.update(
                        status="complete",
                        seed=plain(seed),
                        audit=audit[0],
                        fits=fits,
                        catalogue_numbers=bank.numbers[list(seed.satellite_indices)].tolist(),
                    )
                except (ValueError, TimeoutError) as error:
                    result["reason"] = f"{type(error).__name__}: {error}"
                result["elapsed_s"] = time.monotonic() - began
                write(output, result)
                print(
                    json.dumps(
                        {
                            "sid": case["session_id"],
                            "calibration": calibration,
                            "mode": mode,
                            "status": result["status"],
                            "reason": result["reason"],
                            "elapsed_s": result["elapsed_s"],
                        }
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "execute"))
    parser.add_argument("--dataset", choices=("DS20", "DS16"), default="DS20")
    args = parser.parse_args()
    if args.operation == "freeze":
        freeze()
    else:
        execute(args.dataset)
