"""Frozen, matched B7 controls for orbit-consistent protected track joins."""

import argparse
import json
import shutil
import time
from dataclasses import asdict
from functools import partial
from pathlib import Path

import numpy as np
from continuous_merge_evaluate import evaluate
from continuous_merge_positions import load_prepared
from continuous_merge_study import plain, sha, write

from leo.analysis.continuous_merge_bootstrap import (
    ContinuousBootstrapPolicy,
    bootstrap_with_continuity,
)
from leo.analysis.hard60_score import predict_orbits
from leo.application.hard60_b7 import run_b7
from leo.application.regional_position_runner import RegionalSliceExpired
from leo.cli.regional_position import configuration
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports/2026_10_12_consistent_track_merge"
LOCAL = REPORT / "local"
PREVIOUS = Path("/srv/bulk/leo-dev/leo-track-merge-study/reports/2026_10_12_continuous_track_merge")
MODES = ("baseline", "shape", "consistent")


def verify(protocol):
    for path, digest in protocol["source_bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("bound source changed: " + path)
    for path, digest in protocol["input_bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("bound input changed: " + path)
    if canonical_digest(configuration()) != protocol["configuration_sha256"]:
        raise ValueError("pipeline configuration changed")


def freeze(dataset, session_id):
    old = PREVIOUS / "local" / dataset / session_id
    case = LOCAL / dataset / session_id
    destination = case / "positions"
    if (destination / "experiment.json").exists():
        raise ValueError("consistency experiment already exists")
    census = json.loads((old / "census.json").read_bytes())
    previous = json.loads((old / "positions/experiment.json").read_bytes())
    if census["status"] != "complete":
        raise ValueError("original preparation failed")
    baseline = load_prepared(old / "baseline.json")
    merged = load_prepared(old / "replace-guard.json")
    assert baseline.candidate_ids == merged.candidate_ids
    for field in ("window_ids", "times_s", "measured_hz", "rf_hz", "receiver", "channel", "margin"):
        assert np.array_equal(
            getattr(baseline.observations, field), getattr(merged.observations, field)
        )
    inputs = (
        old / "baseline.json",
        old / "replace-guard.json",
        old / "census.json",
        old / "positions/bank.npz",
        old / "positions/experiment.json",
        PREVIOUS / "membership.json",
    )
    if sha(old / "positions/bank.npz") != previous["bank_sha256"]:
        raise ValueError("original initial bank changed")
    source_paths = sorted((ROOT / "src/leo").glob("analysis/*.py"))
    source_paths += sorted((ROOT / "src/leo").glob("application/*.py"))
    source_paths += sorted((ROOT / "src/leo").glob("contracts/*.py"))
    source_paths += [
        Path(__file__),
        ROOT / "tools/continuous_merge_positions.py",
        ROOT / "tools/continuous_merge_study.py",
    ]
    destination.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(old / "positions/bank.npz", destination / "bank.npz")
    shutil.copyfile(old / "census.json", case / "census.json")
    for mode in MODES:
        shutil.copyfile(old / "baseline.json", case / (mode + ".json"))
        (destination / mode).mkdir(exist_ok=True)
    protocol = {
        "policy": "continuous-protected-local-orbital-agreement-v2",
        "dataset": dataset,
        "session_id": session_id,
        "role": census["member"]["role"],
        "original_case": str(old),
        "source_bindings": {str(p): sha(p) for p in source_paths},
        "input_bindings": {str(p): sha(p) for p in inputs},
        "bank_sha256": sha(destination / "bank.npz"),
        "configuration": configuration(),
        "configuration_sha256": canonical_digest(configuration()),
        "policies": {m: asdict(ContinuousBootstrapPolicy(mode=m)) for m in MODES},
        "maximum_bootstrap_seconds": 5.0,
        "original_tracks": len(baseline.bootstrap_tracks),
        "proposal_pool_tracks": len(set(baseline.bootstrap_tracks) | set(merged.bootstrap_tracks)),
        "scope": (
            "All conditions profile the identical original-plus-guarded proposal pool, then "
            "recompute a seed using only their selected proposals. Original observations, initial "
            "bank, prior, 400-point search and per-stage budgets match. Original discovery "
            "candidates are preserved locally by consistent mode. No reference used. "
            "Final c=0 versus fitted-c arms share fitted-c discovery and final bank within mode."
        ),
        "reference_usage": "none",
    }
    write(destination / "experiment.json", protocol)
    print(
        json.dumps(
            {
                k: protocol[k]
                for k in ("dataset", "session_id", "original_tracks", "proposal_pool_tracks")
            }
        )
    )


def execute(case, mode, maximum_seconds):
    destination = case / "positions"
    protocol = json.loads((destination / "experiment.json").read_bytes())
    verify(protocol)
    output = destination / mode
    if (output / "terminal.json").exists():
        print("already terminal")
        return
    if sha(destination / "bank.npz") != protocol["bank_sha256"]:
        raise ValueError("bank changed")
    old = Path(protocol["original_case"])
    prepared = load_prepared(old / "baseline.json")
    merged = load_prepared(old / "replace-guard.json")
    with np.load(destination / "bank.npz") as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    policy = ContinuousBootstrapPolicy(**protocol["policies"][mode])

    def audit(receipt):
        name = canonical_digest(receipt["point"])[7:]
        write(output / "bootstrap-audits" / (name + ".json"), receipt)

    bootstrapper = partial(
        bootstrap_with_continuity,
        merged_tracks=merged.bootstrap_tracks,
        policy=policy,
        audit=audit,
    )
    binding = canonical_digest({"experiment": protocol, "mode": mode})
    store = RegionalCheckpointStore(output, protocol["session_id"], binding)
    begun = time.monotonic()
    status, result, reason = "yielded", None, None
    with store.writer():
        try:
            result = run_b7(
                prepared.observations,
                bank,
                RegionalPrior(),
                prepared.bootstrap_tracks,
                store,
                maximum_seconds=maximum_seconds,
                bootstrapper=bootstrapper,
                bootstrap_configuration={"policy": asdict(policy), "evidence": binding},
            )
            status = "complete"
        except RegionalSliceExpired as error:
            reason = str(error)
        except (ValueError, TimeoutError) as error:
            status, reason = "failed", f"{type(error).__name__}: {error}"
    receipt = {
        "status": status,
        "reason": reason,
        "elapsed_s": time.monotonic() - begun,
        "binding": binding,
    }
    write(output / "last-slice.json", receipt)
    if status != "yielded":
        write(
            output / "terminal.json",
            {
                **receipt,
                "result": plain(result),
                "reference_usage": "none",
            },
        )
    print(json.dumps({"mode": mode, **receipt}), flush=True)


def diagnose(case):
    protocol = json.loads((case / "positions/experiment.json").read_bytes())
    verify(protocol)
    old = Path(protocol["original_case"])
    prepared = load_prepared(old / "baseline.json")
    merged = load_prepared(old / "replace-guard.json")
    with np.load(case / "positions/bank.npz") as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    receipts = []
    # The second point is a previously exposed diagnostic near the reference,
    # never a seed or a search restriction. The origin is fixed by the prior.
    for point in ([0.0, 0.0], [-80.0, -80.0]):
        for mode in MODES:
            result = bootstrap_with_continuity(
                prepared.observations,
                bank,
                RegionalPrior(),
                point,
                prepared.bootstrap_tracks,
                merged_tracks=merged.bootstrap_tracks,
                policy=ContinuousBootstrapPolicy(**protocol["policies"][mode]),
                audit=receipts.append,
                maximum_seconds=5.0,
                orbit_predictor=predict_orbits,
            )
            receipts[-1]["catalogue_candidates"] = [
                int(bank.numbers[i]) for i in result.satellite_indices
            ]
            for decision in receipts[-1]["decisions"]:
                decision["joined_catalogue_candidate"] = (
                    int(bank.numbers[decision["joined_satellite_index"]])
                    if "joined_satellite_index" in decision
                    else None
                )
                decision["parent_catalogue_candidates"] = [
                    int(bank.numbers[i]) for i in decision.get("parent_satellite_indices", [])
                ]
    write(case / "positions/point-diagnosis.json", receipts)
    print(
        json.dumps(
            [
                {
                    "point": r["point"],
                    "mode": r["policy"]["mode"],
                    "joins": r["selected_joins"],
                    "bank": r["catalogue_candidates"],
                    "seconds": r["seconds"],
                }
                for r in receipts
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "execute", "diagnose", "evaluate"))
    parser.add_argument("dataset", choices=("DS20", "DS16"))
    parser.add_argument("session_id")
    parser.add_argument("--mode", choices=MODES, default="consistent")
    parser.add_argument("--maximum-seconds", type=float, default=420)
    parser.add_argument("--variants", nargs="+", choices=MODES, default=list(MODES))
    args = parser.parse_args()
    case = LOCAL / args.dataset / args.session_id
    if args.command == "freeze":
        freeze(args.dataset, args.session_id)
    elif args.command == "execute":
        execute(case, args.mode, args.maximum_seconds)
    elif args.command == "diagnose":
        diagnose(case)
    else:
        evaluate(case, args.variants)
