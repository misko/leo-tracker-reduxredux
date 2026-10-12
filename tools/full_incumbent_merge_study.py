"""Bounded full B7 comparison of frozen incumbent initialization policies.

Reuse the pinned development panel, never its earlier selected fixed points.
All geographic references are excluded from protocol creation and inference.
"""

import argparse
import json
import time
from dataclasses import asdict
from functools import partial
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import REPORT, ROOT
from clock_conditioned_merge_study import verify
from continuous_merge_positions import load_prepared
from continuous_merge_study import plain, sha, write
from incumbent_clock_merge_study import OUTPUT as PARENT

from leo.analysis.clock_conditioned_bootstrap import ClockConditioningConfiguration
from leo.analysis.continuous_merge_bootstrap import ContinuousBootstrapPolicy
from leo.analysis.incumbent_clock_bootstrap import bootstrap_with_clock_incumbents
from leo.analysis.lnb_band_calibration import calibrated_band_observations
from leo.application.hard60_b7 import B7_POLICY, run_b7
from leo.application.regional_position_runner import RegionalSliceExpired
from leo.cli.regional_position import configuration
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore

OUTPUT = REPORT / "local/full-incumbent"


def compact_audit(receipt, bank):
    """Keep selected seed identity and every event without duplicating support rows."""
    result = {k: v for k, v in receipt.items() if k != "candidate_packets"}
    selected = receipt["candidate_packets"][receipt["selected"]]
    result["selected_satellites"] = bank.numbers[list(selected.satellite_indices)].tolist()
    result["selected_vector"] = selected.vector.tolist()
    return result


def matched_observations(original, joined):
    if original.candidate_ids != joined.candidate_ids:
        raise ValueError("join changed candidate inventory")
    for field in asdict(original.observations):
        if not np.array_equal(
            getattr(original.observations, field), getattr(joined.observations, field)
        ):
            raise ValueError("join changed observation field: " + field)


def freeze():
    path = OUTPUT / "protocol.json"
    if path.exists():
        raise ValueError("full incumbent protocol already frozen")
    parent_path = PARENT / "protocol.json"
    parent = json.loads(parent_path.read_bytes())
    verify(parent["bindings"])
    paths = [parent_path, Path(__file__)]
    paths += sorted((ROOT / "src/leo/analysis").glob("*.py"))
    paths += sorted((ROOT / "src/leo/application").glob("*.py"))
    paths += sorted((ROOT / "src/leo/contracts").glob("*.py"))
    paths += [
        ROOT / "tools" / name
        for name in (
            "continuous_merge_positions.py",
            "continuous_merge_study.py",
            "clock_conditioned_merge_study.py",
            "incumbent_clock_merge_study.py",
            "band_calibrated_merge_study.py",
        )
    ]
    cases = []
    for case in parent["cases"]:
        old = Path(case["original_case"])
        original, joined = (
            load_prepared(old / name)
            for name in (
                "baseline.json",
                "replace-guard.json",
            )
        )
        matched_observations(original, joined)
        census = json.loads((old / "census.json").read_bytes())
        experiment = json.loads((old / "positions/experiment.json").read_bytes())
        if census["member"]["role"] != "development":
            raise ValueError("development panel role changed")
        bank_path = old / "positions/bank.npz"
        if sha(bank_path) != experiment["bank_sha256"]:
            raise ValueError("original initial catalogue changed")
        paths += [
            old / name
            for name in (
                "baseline.json",
                "replace-guard.json",
                "census.json",
                "positions/experiment.json",
                "positions/bank.npz",
            )
        ]
        # Deliberately exclude the parent's data-selected fixed point.
        cases.append(
            {
                k: case[k]
                for k in (
                    "dataset",
                    "session_id",
                    "original_case",
                    "calibrations",
                )
            }
            | {"role": "development", "bank_path": str(bank_path)}
        )
    write(
        path,
        {
            "parent_protocol": str(parent_path),
            "bindings": {str(p): sha(p) for p in paths},
            "cases": cases,
            "modes": parent["modes"],
            "clock_configuration": parent["configuration"],
            "fixed_band_offsets_hz": parent["fixed_band_offsets_hz"],
            "configuration": configuration(),
            "configuration_sha256": canonical_digest(configuration()),
            "b7_policy": B7_POLICY,
            "reference_usage": "none in freeze or execute; evaluate only after sealing terminals",
            "scope": (
                "Same eight pinned development recordings and whole-recording roles. "
                "Four original/joined by unconditioned/conditioned incumbent modes; raw and "
                "fixed-development-donor calibration states as in the parent protocol. "
                "Original observations, initial catalogue, prior and full 400-point B7 search "
                "policy match. Bootstrap uses the existing five-second per-point bound. "
                "No earlier selected point is used. c=0 and fitted-c finals share fitted-c "
                "discovery, final bank and fitting budgets within each mode. This conditional "
                "ablation does not refit upstream discovery with c=0. Candidate banks may "
                "change across modes as intervention effects. No hardware or default changes."
            ),
        },
    )
    print(json.dumps({"cases": len(cases), "protocol_sha256": sha(path)}), flush=True)


def execute(dataset, session_id, calibration, mode, maximum_seconds):
    if not np.isfinite(maximum_seconds) or not 30 <= maximum_seconds <= 600:
        raise ValueError("full analysis slice must be between 30 and 600 seconds")
    path = OUTPUT / "protocol.json"
    protocol = json.loads(path.read_bytes())
    verify(protocol["bindings"])
    if canonical_digest(configuration()) != protocol["configuration_sha256"]:
        raise ValueError("pipeline configuration changed")
    case = next(
        c for c in protocol["cases"] if (c["dataset"], c["session_id"]) == (dataset, session_id)
    )
    if calibration not in case["calibrations"] or mode not in protocol["modes"]:
        raise ValueError("condition outside frozen panel")
    output = OUTPUT / dataset / session_id / (calibration + "-" + mode)
    output.mkdir(parents=True, exist_ok=True)
    if (output / "terminal.json").exists():
        print("already terminal", flush=True)
        return
    old = Path(case["original_case"])
    prepared, joined = (
        load_prepared(old / name)
        for name in (
            "baseline.json",
            "replace-guard.json",
        )
    )
    matched_observations(prepared, joined)
    observations, _ = calibrated_band_observations(
        prepared.observations,
        protocol["fixed_band_offsets_hz"] if calibration == "cal" else [0.0, 0.0],
    )
    with np.load(case["bank_path"]) as z:
        bank = PositionOrbitBank(**{k: z[k] for k in z.files})
    conditioning, policy = protocol["modes"][mode]
    clock = ClockConditioningConfiguration(
        **{
            **protocol["clock_configuration"],
            "conditioning": conditioning,
        }
    )
    merge = ContinuousBootstrapPolicy(mode=policy)

    def audit(receipt):
        value = compact_audit(receipt, bank)
        write(
            output / "bootstrap-audits" / (canonical_digest(receipt["point"])[7:] + ".json"), value
        )

    bootstrapper = partial(
        bootstrap_with_clock_incumbents,
        merged_tracks=joined.bootstrap_tracks,
        policy=merge,
        configuration=clock,
        selection="incumbent",
        audit=audit,
    )
    binding = canonical_digest(
        {"protocol_sha256": sha(path), "case": case, "calibration": calibration, "mode": mode}
    )
    store = RegionalCheckpointStore(output, session_id, binding)
    begun, status, result, reason = time.monotonic(), "yielded", None, None
    with store.writer():
        try:
            result = run_b7(
                observations,
                bank,
                RegionalPrior(),
                prepared.bootstrap_tracks,
                store,
                maximum_seconds=maximum_seconds,
                bootstrapper=bootstrapper,
                bootstrap_configuration={
                    "policy": asdict(merge),
                    "clock": asdict(clock),
                    "selection": "incumbent",
                    "evidence": binding,
                },
            )
            status = "complete"
        except RegionalSliceExpired as error:
            reason = str(error)
        except (ValueError, TimeoutError) as error:
            status, reason = "failed", f"{type(error).__name__}: {error}"
    receipt = {
        "status": status,
        "reason": reason,
        "binding": binding,
        "elapsed_s": time.monotonic() - begun,
        "reference_usage": "none",
    }
    write(output / "last-slice.json", receipt)
    if status != "yielded":
        write(output / "terminal.json", {**receipt, "result": plain(result)})
    print(json.dumps({"condition": str(output), **receipt}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "execute"))
    parser.add_argument("--dataset", choices=("DS20", "DS16"), default="DS20")
    parser.add_argument("--session-id")
    parser.add_argument("--calibration", choices=("raw", "cal"), default="raw")
    parser.add_argument("--mode", default="original-control")
    parser.add_argument("--maximum-seconds", type=float, default=300)
    args = parser.parse_args()
    if args.command == "freeze":
        freeze()
    else:
        execute(args.dataset, args.session_id, args.calibration, args.mode, args.maximum_seconds)
