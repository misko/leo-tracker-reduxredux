"""Frozen serial runtime, seed equivalence and paired coarse tests for incumbents."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import REPORT, ROOT
from clock_conditioned_merge_study import DESTINATION as OLD
from clock_conditioned_merge_study import verify
from continuous_merge_positions import load_prepared
from continuous_merge_study import plain, sha, write

from leo.analysis.clock_conditioned_bootstrap import ClockConditioningConfiguration
from leo.analysis.continuous_merge_bootstrap import ContinuousBootstrapPolicy
from leo.analysis.hard60_score import Hard60Objective, predict_orbits
from leo.analysis.incumbent_clock_bootstrap import bootstrap_with_clock_incumbents
from leo.analysis.lnb_band_calibration import calibrated_band_observations
from leo.analysis.regional_position_bootstrap import BootstrapMatch, PositionBootstrap
from leo.analysis.regional_position_fit import fit_position
from leo.application.hard60_runner import HARD60_SCORE
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior

OUTPUT = REPORT / "local/incumbent-clock"
BUDGETS = {"generous": 120.0, "field": 5.0}


def restore(packet):
    return PositionBootstrap(
        tuple(packet["satellite_indices"]),
        np.array(packet["vector"]),
        tuple(BootstrapMatch(**{**m, "rows": tuple(m["rows"])}) for m in packet["matches"]),
    )


def final_choice(candidates, passes):
    choices = [i for i, c in enumerate(candidates) if c["source"]["pass"] == passes - 1]
    if not choices:
        choices = [i for i, c in enumerate(candidates) if c["source"]["kind"] == "original"]
    if not choices:
        raise ValueError("no completed final-pass or original seed")
    selected = choices[0]
    for index in choices[1:]:
        if candidates[index]["score"] < candidates[selected]["score"] - 1e-9:
            selected = index
    return selected


def freeze():
    path = OUTPUT / "protocol.json"
    if path.exists():
        raise ValueError("incumbent-clock protocol already frozen")
    old_path = OLD / "protocol.json"
    old = json.loads(old_path.read_bytes())
    verify(old["bindings"])
    paths = [
        old_path,
        Path(__file__),
        ROOT / "tools/clock_conditioned_merge_study.py",
        ROOT / "tools/continuous_merge_positions.py",
        ROOT / "tools/continuous_merge_study.py",
    ]
    paths += sorted((ROOT / "src/leo/analysis").glob("*.py"))
    paths += sorted((ROOT / "src/leo/application").glob("*.py"))
    paths += sorted((ROOT / "src/leo/contracts").glob("*.py"))
    for case in old["cases"]:
        for cal in case["calibrations"]:
            for mode in old["modes"]:
                source = OLD / case["dataset"] / case["session_id"] / (cal + "-" + mode + ".json")
                if json.loads(source.read_bytes())["status"] != "complete":
                    raise ValueError("complete original numerical authority required")
                paths.append(source)
    write(
        path,
        {
            "parent_protocol": str(old_path),
            "bindings": {str(p): sha(p) for p in paths},
            "budgets": BUDGETS,
            "cases": old["cases"],
            "modes": old["modes"],
            "configuration": old["configuration"],
            "fixed_band_offsets_hz": old["fixed_band_offsets_hz"],
            "coarse_seconds": old["coarse_seconds"],
            "coarse_iterations": old["coarse_iterations"],
            "reference_usage": "none in freeze/execute",
            "scope": (
                "Same fixed eight development cases, points, initial banks and common pools. "
                "New profiled seed builder reuses matches; zero unmerged seed and every complete "
                "pass enter incumbent selection. Identical slopes reuse complete passes. "
                "Serial timing at120s and5s; budget-induced interruptions retained explicitly. "
                "Final and incumbent choices use ONE realized path before either c fit; both "
                "arms share their chosen bank/seed/priors/20s600iter bound. Exactly identical "
                "coarse inputs reuse their paired outputs within a condition. No full B7 search "
                "or geographic validation. Controls compare old no-conditioning seed fields."
            ),
        },
    )
    print(json.dumps({"cases": len(old["cases"]), "protocol_sha256": sha(path)}), flush=True)


def execute(budget, dataset, limit):
    protocol_path = OUTPUT / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol["bindings"])
    parent = json.loads(Path(protocol["parent_protocol"]).read_bytes())
    verify(parent["bindings"])
    processed = 0
    for case in protocol["cases"]:
        if dataset != "all" and case["dataset"] != dataset:
            continue
        old = Path(case["original_case"])
        prepared, merged = (
            load_prepared(old / name) for name in ("baseline.json", "replace-guard.json")
        )
        with np.load(old / "positions/bank.npz") as z:
            bank = PositionOrbitBank(**{key: z[key] for key in z.files})
        for cal in case["calibrations"]:
            obs, _ = calibrated_band_observations(
                prepared.observations, protocol["fixed_band_offsets_hz"] if cal == "cal" else [0, 0]
            )
            for mode, (conditioning, merge_policy) in protocol["modes"].items():
                path = (
                    OUTPUT
                    / budget
                    / case["dataset"]
                    / case["session_id"]
                    / (cal + "-" + mode + ".json")
                )
                if path.exists():
                    continue
                if processed >= limit:
                    return
                old_path = OLD / case["dataset"] / case["session_id"] / (cal + "-" + mode + ".json")
                old_result = json.loads(old_path.read_bytes())
                result = {
                    "case": case,
                    "budget": budget,
                    "calibration": cal,
                    "mode": mode,
                    "protocol_sha256": sha(protocol_path),
                    "status": "failed",
                    "reason": None,
                    "reference_usage": "none",
                }
                began, audits = time.monotonic(), []
                try:
                    seed = bootstrap_with_clock_incumbents(
                        obs,
                        bank,
                        RegionalPrior(),
                        case["point"],
                        prepared.bootstrap_tracks,
                        merged_tracks=merged.bootstrap_tracks,
                        policy=ContinuousBootstrapPolicy(mode=merge_policy),
                        configuration=ClockConditioningConfiguration(
                            **{**protocol["configuration"], "conditioning": conditioning}
                        ),
                        maximum_seconds=protocol["budgets"][budget],
                        orbit_predictor=predict_orbits,
                        audit=audits.append,
                    )
                    audit = audits[0]
                    final = final_choice(audit["candidates"], protocol["configuration"]["passes"])
                    selected = {"incumbent": audit["selected"], "final": final}
                    fits, fit_cache, reuse = {}, {}, {}
                    for selection, index in selected.items():
                        packet = audit["candidate_packets"][index]
                        key = (packet.satellite_indices, tuple(packet.vector))
                        if key in fit_cache:
                            fits[selection] = fits[fit_cache[key]]
                            reuse[selection] = fit_cache[key]
                            continue
                        model = Hard60Objective(
                            obs,
                            bank.select(list(packet.satellite_indices)),
                            RegionalPrior(),
                            HARD60_SCORE,
                        )
                        fits[selection] = {
                            arm: plain(
                                fit_position(
                                    model,
                                    packet.vector,
                                    rf_arm=arm,
                                    fixed_position=True,
                                    maximum_seconds=protocol["coarse_seconds"],
                                    maximum_iterations=protocol["coarse_iterations"],
                                    slope_half_width_hz_s=60,
                                )
                            )
                            for arm in ("fitted-c", "zero-c")
                        }
                        fit_cache[key] = selection
                    packets = audit["candidate_packets"]
                    witness = next(
                        (
                            i
                            for i, c in enumerate(audit["candidates"])
                            if c["source"]["kind"] == "original"
                        ),
                        None,
                    )
                    if witness is not None:
                        assert (
                            audit["candidates"][audit["selected"]]["score"]
                            <= audit["candidates"][witness]["score"] + 1e-9
                        )
                    oracle = None
                    if conditioning == "none" and audit["complete_path"]:
                        old_seed = restore(old_result["seed"])
                        new_seed = packets[final]
                        if old_seed.satellite_indices != new_seed.satellite_indices:
                            raise ValueError("fast control changed oracle catalogue")
                        np.testing.assert_allclose(
                            new_seed.vector, old_seed.vector, atol=1e-7, rtol=0
                        )
                        for new, reference in zip(new_seed.matches, old_seed.matches, strict=True):
                            assert (
                                new.rows == reference.rows
                                and new.satellite_index == reference.satellite_index
                            )
                            np.testing.assert_allclose(
                                [new.timing_s, new.shape_rms_hz, new.shape_cost],
                                [reference.timing_s, reference.shape_rms_hz, reference.shape_cost],
                                atol=1e-7,
                                rtol=0,
                            )
                        oracle = {
                            "max_vector_difference": float(
                                np.max(abs(new_seed.vector - old_seed.vector))
                            ),
                            "source_sha256": sha(old_path),
                            "matches_equivalent": True,
                        }
                    result.update(
                        status="complete",
                        seed=plain(seed),
                        audit=plain(audit),
                        selected=selected,
                        fits=fits,
                        exact_fit_reuse=reuse,
                        oracle=oracle,
                        catalogue_numbers={
                            name: bank.numbers[list(packets[index].satellite_indices)].tolist()
                            for name, index in selected.items()
                        },
                    )
                except (ValueError, TimeoutError, AssertionError) as error:
                    result["reason"] = f"{type(error).__name__}: {error}"
                result["elapsed_s"] = time.monotonic() - began
                write(path, result)
                processed += 1
                print(
                    json.dumps(
                        {
                            "sid": case["session_id"],
                            "calibration": cal,
                            "mode": mode,
                            "budget": budget,
                            "status": result["status"],
                            "reason": result["reason"],
                            "bootstrap_seconds": (result.get("audit") or {}).get("seconds"),
                            "complete_path": (result.get("audit") or {}).get("complete_path"),
                        }
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("freeze", "execute"))
    parser.add_argument("--budget", choices=tuple(BUDGETS), default="generous")
    parser.add_argument("--dataset", choices=("all", "DS20", "DS16"), default="all")
    parser.add_argument("--limit", type=int, default=96)
    args = parser.parse_args()
    if args.operation == "freeze":
        freeze()
    else:
        execute(args.budget, args.dataset, args.limit)
