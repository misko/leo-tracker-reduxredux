"""Frozen full-search calibration transfer versus protected continuity joins.

Learn the fixed band correction from a development recording's reference-free
fit, then apply it through the observation port before any discovery stage.
Raw evidence, initial catalogue, priors and work budgets remain matched.
"""

import argparse
import json
import time
from dataclasses import asdict
from functools import partial
from pathlib import Path

import numpy as np
from band_calibrated_merge_study import LOCAL, ROOT
from continuous_merge_positions import load_prepared
from continuous_merge_study import plain, sha, write

from leo.analysis.continuous_merge_bootstrap import (
    ContinuousBootstrapPolicy,
    bootstrap_with_continuity,
)
from leo.analysis.lnb_band_calibration import calibrated_band_observations
from leo.application.hard60_b7 import B7_POLICY, run_b7
from leo.application.regional_position_report import regional_position_document
from leo.application.regional_position_runner import RegionalSliceExpired
from leo.cli.regional_position import configuration
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import PositionOrbitBank, RegionalPrior
from leo.storage.regional_position_checkpoints import RegionalCheckpointStore
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store

ORIGINAL = Path("/srv/bulk/leo-dev/leo-track-merge-study/reports/2026_10_12_continuous_track_merge")
DONOR = LOCAL / "DS20/fast-014c72ff95ab599c51ba3b3ec9b92cb8"
MODES = {
    "raw-original": (False, "baseline"),
    "raw-joined": (False, "consistent"),
    "cal-original": (True, "baseline"),
    "cal-joined": (True, "consistent"),
}


def verify(protocol):
    for path, digest in protocol["bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("global band study authority changed: " + path)
    if canonical_digest(configuration()) != protocol["configuration_sha256"]:
        raise ValueError("global band configuration changed")


def freeze(dataset, sid):
    case = LOCAL / dataset / sid / "global-transfer"
    if (case / "protocol.json").exists():
        raise ValueError("global transfer protocol already frozen")
    old = ORIGINAL / "local" / dataset / sid
    census = json.loads((old / "census.json").read_bytes())
    donor_protocol = json.loads((DONOR / "protocol.json").read_bytes())
    if donor_protocol["role"] != "development":
        raise ValueError("calibration donor must belong to the fixed development split")
    for path, digest in donor_protocol["bindings"].items():
        if sha(Path(path)) != digest:
            raise ValueError("calibration donor authority changed: " + path)
    donor_fit_path = DONOR / "cal-independent-fitted-c.json"
    donor = json.loads(donor_fit_path.read_bytes())
    if not donor["fit"]["converged"] or donor["reference_usage"] != "none":
        raise ValueError("stationary reference-free calibration donor required")
    donor_old = ORIGINAL / "local/DS20" / donor_protocol["session_id"]
    donor_source = json.loads((donor_old / "source.json").read_bytes())
    source = json.loads((old / "source.json").read_bytes())
    prepared = load_prepared(old / "baseline.json")
    merged = load_prepared(old / "replace-guard.json")
    if prepared.candidate_ids != merged.candidate_ids:
        raise ValueError("merge changed candidate inventory")
    for field in asdict(prepared.observations):
        if not np.array_equal(
            getattr(prepared.observations, field), getattr(merged.observations, field)
        ):
            raise ValueError("merge changed raw observation field: " + field)
    high_count = int(np.sum(prepared.observations.channel >= 5))
    if high_count and source["radio_id"] != donor_source["radio_id"]:
        raise ValueError("high-band calibration transfer requires the same radio")
    offsets = donor["band_offsets_hz"] if high_count else [0.0, 0.0]
    derived, correction = calibrated_band_observations(prepared.observations, offsets)
    bank_path = old / "positions/bank.npz"
    old_protocol = json.loads((old / "positions/experiment.json").read_bytes())
    if sha(bank_path) != old_protocol["bank_sha256"]:
        raise ValueError("original catalogue changed")
    paths = [
        old / name
        for name in (
            "baseline.json",
            "replace-guard.json",
            "source.json",
            "census.json",
            "positions/experiment.json",
        )
    ]
    paths += [
        bank_path,
        ORIGINAL / "membership.json",
        donor_fit_path,
        DONOR / "protocol.json",
        donor_old / "source.json",
    ]
    paths += sorted((ROOT / "src/leo/analysis").glob("*.py"))
    paths += sorted((ROOT / "src/leo/application").glob("*.py"))
    paths += sorted((ROOT / "src/leo/contracts").glob("*.py"))
    paths += [
        Path(__file__),
        ROOT / "tools/band_calibrated_merge_study.py",
        ROOT / "tools/continuous_merge_positions.py",
        ROOT / "tools/continuous_merge_study.py",
    ]
    protocol = {
        "dataset": dataset,
        "session_id": sid,
        "role": census["member"]["role"],
        "original_case": str(old),
        "bank_path": str(bank_path),
        "bindings": {str(path): sha(path) for path in paths},
        "configuration": configuration(),
        "configuration_sha256": canonical_digest(configuration()),
        "b7_policy": B7_POLICY,
        "modes": MODES,
        "policies": {
            name: asdict(ContinuousBootstrapPolicy(mode=policy))
            for name, (_, policy) in MODES.items()
        },
        "fixed_band_offsets_hz": offsets,
        "donor_session_id": donor_protocol["session_id"],
        "donor_role": donor_protocol["role"],
        "donor_radio_id": donor_source["radio_id"],
        "target_radio_id": source["radio_id"],
        "high_band_observations": high_count,
        "raw_observations_sha256": canonical_digest(plain(prepared.observations)),
        "calibrated_observations_sha256": canonical_digest(plain(derived)),
        "correction_range_hz": [float(correction.min()), float(correction.max())],
        "rf_inventory": sorted(
            set(
                (int(rx), int(ch), float(rf))
                for rx, ch, rf in zip(
                    prepared.observations.receiver,
                    prepared.observations.channel,
                    prepared.observations.rf_hz,
                    strict=True,
                )
            )
        ),
        "calibration_assumption": (
            "Same radio and RX/LNB wiring; time-invariant band correction transferred from an "
            "exposed development recording. Physical stability is a testable assumption, "
            "not established by radio ID."
        ),
        "scope": (
            "Four full 400-point B7 searches: fixed donor calibration on/off crossed with "
            "protected joins on/off. All raw windows, alternatives, RF carriers, initial "
            "catalogue, priors and per-stage budgets match. Derived CFO equals raw minus gamma "
            "for CH5-8; raw persisted products are untouched. c=0 and fitted-c finals share "
            "fitted-c discovery and the final bank within mode; this is a conditional c "
            "ablation. Candidate sets may change between modes as an intervention consequence. "
            "No reference in inference."
        ),
        "reference_usage": "none in freeze or execute",
    }
    write(case / "protocol.json", protocol)
    for mode in MODES:
        (case / mode).mkdir(exist_ok=True)
    print(
        json.dumps(
            {
                k: protocol[k]
                for k in (
                    "dataset",
                    "session_id",
                    "role",
                    "fixed_band_offsets_hz",
                    "high_band_observations",
                )
            }
        )
    )


def execute(case, mode, maximum_seconds):
    protocol = json.loads((case / "protocol.json").read_bytes())
    verify(protocol)
    output = case / mode
    if (output / "terminal.json").exists():
        print("already terminal")
        return
    old = Path(protocol["original_case"])
    prepared, merged = (
        load_prepared(old / "baseline.json"),
        load_prepared(old / "replace-guard.json"),
    )
    enabled, _ = protocol["modes"][mode]
    offsets = protocol["fixed_band_offsets_hz"] if enabled else [0.0, 0.0]
    observations, _ = calibrated_band_observations(prepared.observations, offsets)
    expected = protocol["calibrated_observations_sha256" if enabled else "raw_observations_sha256"]
    if canonical_digest(plain(observations)) != expected:
        raise ValueError("derived observation inventory changed")
    with np.load(protocol["bank_path"]) as z:
        bank = PositionOrbitBank(**{key: z[key] for key in z.files})
    policy = ContinuousBootstrapPolicy(**protocol["policies"][mode])

    def audit(receipt):
        write(
            output / "bootstrap-audits" / (canonical_digest(receipt["point"])[7:] + ".json"),
            receipt,
        )

    bootstrapper = partial(
        bootstrap_with_continuity, merged_tracks=merged.bootstrap_tracks, policy=policy, audit=audit
    )
    binding = canonical_digest({"experiment": protocol, "mode": mode})
    store = RegionalCheckpointStore(output, protocol["session_id"], binding)
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
            {**receipt, "result": plain(result), "reference_usage": "none"},
        )
    print(json.dumps({"mode": mode, **receipt}), flush=True)


def evaluate(case, reference_root):
    protocol = json.loads((case / "protocol.json").read_bytes())
    verify(protocol)
    paths = {m: case / m / "terminal.json" for m in MODES}
    results = {m: json.loads(p.read_bytes()) for m, p in paths.items()}
    if any(r["status"] != "complete" for r in results.values()):
        raise ValueError("all four global searches must be sealed and complete first")
    seal = {str(path): sha(path) for path in paths.values()}
    seal_path = case / "evaluation-seal.json"
    if seal_path.exists() and json.loads(seal_path.read_bytes()) != seal:
        raise ValueError("global transfer evaluation seal changed")
    write(seal_path, seal)
    published = B7Store(reference_root).status(protocol["session_id"]).manifest
    if published is None:
        published = Hard60Store(reference_root).status(protocol["session_id"]).manifest
    if published is None:
        raise ValueError("reference authority unavailable")
    census = json.loads((Path(protocol["original_case"]) / "census.json").read_bytes())
    if published.document.input_manifest_sha256 != census["input_manifest_sha256"]:
        raise ValueError("reference belongs to another recording")
    reference = (
        published.document.reference_latitude_deg,
        published.document.reference_longitude_deg,
    )
    prepared = load_prepared(Path(protocol["original_case"]) / "baseline.json")
    rows = []
    for mode, result in results.items():
        document = regional_position_document(
            result["result"],
            session_id=protocol["session_id"],
            input_digest=census["input_manifest_sha256"],
            analysis_digest=census["analysis_manifest_sha256"],
            evidence_digest=prepared.evidence_sha256,
            configuration=protocol["configuration"],
            windows=census["windows"],
            reference=reference,
            reference_evidence=published.document.reference_evidence,
        )
        for arm in next(m for m in document.methods if m.name == "V16").arms:
            selected = arm.selected
            final = next((r for r in result["result"]["finals"] if r["arm"] == arm.name), None)
            state = ((final or {}).get("fit") or {}).get("joint_state", {})
            rows.append(
                {
                    "mode": mode,
                    "arm": arm.name,
                    "reference_error_m": selected.horizontal_error_m if selected else None,
                    "objective": selected.objective if selected else None,
                    "posterior_rms_hz": selected.posterior_rms_hz if selected else None,
                    "likelihood_nll": state.get("likelihood_nll"),
                    "accepted_stage": (final or {}).get("accepted_stage"),
                    "satellites": (final or {}).get("satellites"),
                }
            )
    write(
        case / "evaluation.json",
        {
            "rows": rows,
            "reference": reference,
            "reference_evidence": published.document.reference_evidence,
            "reference_root": str(reference_root),
            "reference_document_sha256": canonical_digest(
                published.document.model_dump(mode="json")
            ),
            "seal_sha256": sha(seal_path),
            "protocol_sha256": sha(case / "protocol.json"),
        },
    )
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("freeze", "execute", "evaluate"))
    parser.add_argument("dataset", choices=("DS20", "DS16"))
    parser.add_argument("session_id")
    parser.add_argument("--mode", choices=MODES, default="cal-original")
    parser.add_argument("--maximum-seconds", type=float, default=420)
    parser.add_argument("--reference-products", type=Path, default=Path("/srv/bulk/leo"))
    args = parser.parse_args()
    case = LOCAL / args.dataset / args.session_id / "global-transfer"
    if args.command == "freeze":
        freeze(args.dataset, args.session_id)
    elif args.command == "execute":
        execute(case, args.mode, args.maximum_seconds)
    else:
        evaluate(case, args.reference_products)
