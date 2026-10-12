"""Seal full-search terminals before evaluation; retain the entire planned panel."""

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from band_calibrated_merge_study import PREVIOUS, REPORT
from clock_conditioned_merge_study import verify
from continuous_merge_positions import load_prepared
from continuous_merge_study import sha, write
from full_incumbent_merge_study import OUTPUT

from leo.analysis.regional_position_score import coordinates
from leo.application.regional_position_report import regional_position_document
from leo.contracts.digests import canonical_digest
from leo.contracts.regional_position import RegionalPrior
from leo.storage.regional_position_v2 import Hard60Store
from leo.storage.regional_position_v3 import B7Store

PUBLIC = REPORT / "full-incumbent"
STAGES = ("B7", "C6", "B5", "B4W", "B4", "B3")


def latest_common_stage(attempts):
    """Select by convergence and frozen stage order, never reference accuracy."""
    for stage in STAGES:
        rows = attempts.get(stage, {})
        fits = [rows.get(arm) for arm in ("fitted-c", "zero-c")]
        if all(f is not None and f["converged"] for f in fits):
            if len(fits[0]["vector"]) != len(fits[1]["vector"]):
                raise ValueError("paired stage parameter inventories differ")
            if abs(fits[1]["vector"][6]) > 1e-10:
                raise ValueError("zero-c stage did not lock the RF coefficient")
            if any(abs(v) > 1e-10 for v in fits[1].get("rf_drift_coefficients", ())):
                raise ValueError("zero-c stage did not lock RF drift coefficients")
            return stage
    return None


def error_m(point, reference):
    latitude, longitude = coordinates(RegionalPrior(), point)
    lat, lon, ref_lat, ref_lon = map(math.radians, (latitude, longitude, *reference))
    h = math.sin((lat - ref_lat) / 2) ** 2
    h += math.cos(lat) * math.cos(ref_lat) * math.sin((lon - ref_lon) / 2) ** 2
    return 2 * 6371008.8 * math.asin(math.sqrt(min(1, max(0, h))))


def seal_terminals(path, protocol_path, terminals):
    previous = (
        json.loads(path.read_bytes())
        if path.exists()
        else {
            "protocol_sha256": sha(protocol_path),
            "terminals": {},
        }
    )
    if previous["protocol_sha256"] != sha(protocol_path):
        raise ValueError("full numerical protocol changed")
    for source, digest in previous["terminals"].items():
        if sha(Path(source)) != digest:
            raise ValueError("previously sealed terminal changed: " + source)
    updated = dict(previous["terminals"])
    updated.update({str(p): sha(p) for p in terminals})
    write(path, {"protocol_sha256": sha(protocol_path), "terminals": updated})


def evaluate(case, calibration, mode, protocol, terminal, reference_root):
    published = B7Store(reference_root).status(case["session_id"]).manifest
    if published is None:
        published = Hard60Store(reference_root).status(case["session_id"]).manifest
    if published is None:
        raise ValueError("reference authority unavailable")
    old = Path(case["original_case"])
    census = json.loads((old / "census.json").read_bytes())
    document = published.document
    if document.input_manifest_sha256 != census["input_manifest_sha256"]:
        raise ValueError("reference authority belongs to another recording")
    reference = (document.reference_latitude_deg, document.reference_longitude_deg)
    prepared = load_prepared(old / "baseline.json")
    result = terminal["result"]
    evaluation = regional_position_document(
        result,
        session_id=case["session_id"],
        input_digest=census["input_manifest_sha256"],
        analysis_digest=census["analysis_manifest_sha256"],
        evidence_digest=prepared.evidence_sha256,
        configuration=protocol["configuration"],
        windows=census["windows"],
        reference=reference,
        reference_evidence=document.reference_evidence,
    )
    rows = []
    for arm in next(m for m in evaluation.methods if m.name == "V16").arms:
        selected = arm.selected
        row = {"arm": arm.name, "selected": selected is not None, "reasons": arm.reasons}
        if selected is not None:
            row.update(
                {
                    k: getattr(selected, k)
                    for k in (
                        "latitude_deg",
                        "longitude_deg",
                        "horizontal_error_m",
                        "objective",
                        "selection_score",
                        "posterior_rms_hz",
                        "stationarity",
                        "converged",
                        "coefficient_hz_per_ghz",
                        "accepted_stage",
                        "satellites",
                    )
                }
            )
            state = selected.joint_state
            row["likelihood_nll"] = state.likelihood_nll if state is not None else None
        rows.append(row)
    a, b = rows
    operational_pair = {
        "both_selected": a["selected"] and b["selected"],
        "common_bank": a.get("satellites") == b.get("satellites")
        if a["selected"] and b["selected"]
        else False,
        "common_stage": a.get("accepted_stage") == b.get("accepted_stage")
        if a["selected"] and b["selected"]
        else False,
    }
    attempts = result.get("b7", {}).get("attempts", {})
    stage = latest_common_stage(attempts)
    common_rows = []
    if stage is not None:
        for arm in ("fitted-c", "zero-c"):
            fit = attempts[stage][arm]
            common_rows.append(
                {
                    "arm": arm,
                    "stage": stage,
                    "reference_error_m": error_m(fit["vector"][:2], reference),
                    "objective": fit["objective"],
                    "likelihood_nll": fit["joint_state"]["likelihood_nll"],
                    "stationarity": fit["stationarity"],
                    "converged": fit["converged"],
                    "coefficient_hz_per_ghz": fit["vector"][6],
                    "bank_count": len(fit["vector"]) - 7,
                }
            )
    return {
        "dataset": case["dataset"],
        "session_id": case["session_id"],
        "calibration": calibration,
        "mode": mode,
        "role": case["role"],
        "rows": rows,
        "operational_pair": operational_pair,
        "latest_common_stage": stage,
        "common_stage_rows": common_rows,
        "same_stage_bank_basis": "Same frozen run_joint_stages model in both arms",
        "reference": reference,
        "reference_evidence": document.reference_evidence,
        "reference_products": str(reference_root),
        "reference_document_sha256": canonical_digest(document.model_dump(mode="json")),
        "scope": (
            "Operational selected arms and latest stationary common stage; "
            "no reference in selection"
        ),
    }


def control_oracle(case, output):
    """Compare raw original seed receipts at shared points to the prior full control."""
    previous = PREVIOUS / "local" / case["dataset"] / case["session_id"] / "positions"
    terminal_path = previous / "baseline/terminal.json"
    bank_path = previous / "bank.npz"
    experiment_path = previous / "experiment.json"
    experiment = json.loads(experiment_path.read_bytes())
    if experiment["original_case"] != case["original_case"]:
        raise ValueError("control oracle observation authority differs")
    previous_terminal = json.loads(terminal_path.read_bytes())
    if previous_terminal["status"] != "complete":
        raise ValueError("prior control is incomplete")
    with np.load(bank_path) as z:
        numbers = z["numbers"]
    points = previous_terminal["result"]["points"]
    counts = {
        "audits": 0,
        "shared_points": 0,
        "prior_failed": 0,
        "different_bank": 0,
        "different_vector": 0,
    }
    largest = 0.0
    inputs = {str(p): sha(p) for p in (terminal_path, bank_path, experiment_path)}
    for path in sorted((output / "bootstrap-audits").glob("*.json")):
        inputs[str(path)] = sha(path)
        audit = json.loads(path.read_bytes())
        counts["audits"] += 1
        e, n = audit["point"]
        key = f"point:{e:g}:{n:g}"
        if key not in points:
            continue
        counts["shared_points"] += 1
        if points[key]["result"] is None:
            counts["prior_failed"] += 1
            continue
        seed = points[key]["result"]["bootstrap"]
        if audit["selected_satellites"] != numbers[seed["satellite_indices"]].tolist():
            counts["different_bank"] += 1
            continue
        a, b = np.array(audit["selected_vector"]), np.array(seed["vector"])
        if a.shape != b.shape:
            raise ValueError("same-bank control parameter inventory differs")
        difference = float(np.max(np.abs(a - b)))
        largest = max(largest, difference)
        counts["different_vector"] += int(difference > 1e-7)
    return {
        **counts,
        "maximum_shared_vector_difference": largest,
        "input_bindings": inputs,
        "scope": "Raw original controls at shared search points; numeric equivalence, not accuracy",
    }


def main(reference_root):
    protocol_path = OUTPUT / "protocol.json"
    protocol = json.loads(protocol_path.read_bytes())
    verify(protocol["bindings"])
    PUBLIC.mkdir(parents=True, exist_ok=True)
    conditions, terminals = [], []
    for case in protocol["cases"]:
        for calibration in case["calibrations"]:
            for mode in protocol["modes"]:
                path = OUTPUT / case["dataset"] / case["session_id"] / (calibration + "-" + mode)
                record = {
                    "dataset": case["dataset"],
                    "session_id": case["session_id"],
                    "role": case["role"],
                    "calibration": calibration,
                    "mode": mode,
                    "terminal_status": "pending",
                    "last_recorded_slice": None,
                    "evaluation": None,
                    "evaluation_reason": None,
                }
                if (path / "last-slice.json").exists():
                    record["last_recorded_slice"] = json.loads(
                        (path / "last-slice.json").read_bytes()
                    )
                source = path / "terminal.json"
                if source.exists():
                    terminal = json.loads(source.read_bytes())
                    binding = canonical_digest(
                        {
                            "protocol_sha256": sha(protocol_path),
                            "case": case,
                            "calibration": calibration,
                            "mode": mode,
                        }
                    )
                    if terminal["binding"] != binding or terminal["reference_usage"] != "none":
                        raise ValueError("full terminal binding or reference use differs")
                    if terminal["status"] not in ("complete", "failed"):
                        raise ValueError("nonterminal receipt in terminal.json")
                    record["terminal_status"] = terminal["status"]
                    record["terminal_sha256"] = sha(source)
                    record["terminal_path"] = str(source)
                    terminals.append(source)
                conditions.append(record)
    seal_path = PUBLIC / "numerical-seal.json"
    # Every completed or failed terminal is sealed BEFORE reading reference stores.
    seal_terminals(seal_path, protocol_path, terminals)
    cases = {(c["dataset"], c["session_id"]): c for c in protocol["cases"]}
    for record in conditions:
        if record["terminal_status"] != "complete":
            continue
        terminal = json.loads(Path(record["terminal_path"]).read_bytes())
        if record["calibration"] == "raw" and record["mode"] == "original-control":
            record["control_oracle"] = control_oracle(
                cases[record["dataset"], record["session_id"]],
                Path(record["terminal_path"]).parent,
            )
        try:
            record["evaluation"] = evaluate(
                cases[record["dataset"], record["session_id"]],
                record["calibration"],
                record["mode"],
                protocol,
                terminal,
                reference_root,
            )
        except ValueError as error:
            record["evaluation_reason"] = str(error)
    write(
        PUBLIC / "progress.json",
        {
            "conditions": conditions,
            "protocol_sha256": sha(protocol_path),
            "seal_sha256": sha(seal_path),
            "script_sha256": sha(Path(__file__)),
            "scope": (
                "Entire frozen panel, including pending and failed modes; "
                "last slice is not worker liveness"
            ),
        },
    )
    rows = []
    for record in conditions:
        if record["evaluation"] is not None:
            for row in record["evaluation"]["rows"]:
                if row["selected"]:
                    rows.append({**record, **row})
    if rows:
        fig, axes = plt.subplots(1, 2, figsize=(13, 5), constrained_layout=True)
        x = np.arange(len(rows))
        labels = [
            r["session_id"][:13] + "\n" + r["calibration"] + " " + r["mode"] + "\n" + r["arm"]
            for r in rows
        ]
        colors = ["tab:blue" if r["arm"] == "fitted-c" else "tab:orange" for r in rows]
        axes[0].bar(x, [r["horizontal_error_m"] / 1000 for r in rows], color=colors)
        axes[0].set_ylabel("Error to configured reference (km)")
        baselines = {
            (r["dataset"], r["session_id"], r["calibration"]): r["likelihood_nll"]
            for r in rows
            if r["mode"] == "original-control"
            and r["arm"] == "fitted-c"
            and r["likelihood_nll"] is not None
        }
        frequency = [
            (i, r["likelihood_nll"] - baselines[key])
            for i, r in enumerate(rows)
            if r["likelihood_nll"] is not None
            and (key := (r["dataset"], r["session_id"], r["calibration"])) in baselines
        ]
        axes[1].bar(
            [v[0] for v in frequency],
            [v[1] for v in frequency],
            color=[colors[v[0]] for v in frequency],
        )
        axes[1].set_ylabel(
            "Frequency NLL − fitted-c original control\n"
            "same recording and calibration; lower is better"
        )
        axes[1].axhline(0, color="black", lw=1)
        for axis in axes:
            axis.set_xticks(x, labels, rotation=25, ha="right", fontsize=7)
            axis.grid(axis="y", alpha=0.2)
        fig.suptitle(
            "Full incumbent B7 search · completed operational arms only\n"
            "Candidate banks/stages may differ; incomplete modes stay in the progress receipt"
        )
        fig.savefig(PUBLIC / "position-and-frequency.png", dpi=160)
        plt.close(fig)
    print(
        json.dumps(
            {
                "planned": len(conditions),
                "complete": sum(r["terminal_status"] == "complete" for r in conditions),
                "failed": sum(r["terminal_status"] == "failed" for r in conditions),
                "evaluated": sum(r["evaluation"] is not None for r in conditions),
            },
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference-products", type=Path, default=Path("/srv/bulk/leo"))
    main(parser.parse_args().reference_products)
