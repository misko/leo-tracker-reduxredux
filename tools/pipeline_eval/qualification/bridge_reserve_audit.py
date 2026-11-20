"""Compare saved curved support with original v5 on the largest reserve regression."""

import argparse
from math import dist
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json
from ..scoring import ARMS
from ..variants import bridge_support
from . import bridge_reserve_results as trial
from . import full_receiver_comparison as common
from .bridge_cavity_diagnostic import retained


def by_component(rows):
    items = {row["component"]: row for row in rows}
    if len(items) != len(rows):
        raise ValueError("final curved components not unique")
    return items


def compare(candidate, original):
    a, b = by_component(candidate), by_component(original)
    return dict(
        bridge_points=sum(r["points"] for r in a.values()),
        original_points=sum(r["points"] for r in b.values()),
        shared_components=len(a.keys() & b.keys()),
        absent_from_bridge=[b[k] for k in sorted(b.keys() - a.keys())],
        unique_to_bridge=[a[k] for k in sorted(a.keys() - b.keys())],
        changed_identity=[
            dict(component=k, bridge=a[k], original=b[k])
            for k in sorted(a.keys() & b.keys())
            if a[k]["norad"] != b[k]["norad"]
        ],
    )


def original(ident, binding, execution_seal):
    import evaluate_accuracy_repair as runner

    case = trial.trial.frozen_inputs()[ident]
    request_path = Path("/srv/bulk") / case["request"]["path"]
    execution_path = request_path.parents[1] / "baseline-execution.json"
    execution = common.read(execution_path)
    request = common.read(request_path)
    worker = execution["worker"]
    archive = Path(worker["artifact"]["path"])
    if (
        common.sha(request_path) != binding["frozen_request_sha256"]
        or common.sha(execution_path) != execution_seal["execution_sha256"].removeprefix("sha256:")
        or runner.ev.digest(request) != execution_seal["request_sha256"]
        or runner.ev.file_digest(archive) != worker["artifact"]["sha256"]
    ):
        raise ValueError("original regression archive differs from the execution seal")
    codec = runner.ev.owned_import("leo.storage.localization_v3_codec", request["source"])
    payload, _ = codec.unpack(archive.read_bytes())
    if payload["request"] != request or payload["request_sha256"] != runner.ev.digest(request):
        raise ValueError("original regression archive has another scientific request")
    audit = payload["audit"]
    cavity = audit["cavity_policy"] or {}
    arms = cavity.get("policy_arms") or audit["signed_policy"]["arms"]
    initial = audit["initial"]
    selected = next(
        r for r in initial["choices"] if r["hypothesis"] == initial["selected_hypothesis"]
    )
    start = {
        a: dict(
            xy=list(map(float, r["fit"]["parameters"])),
            gate_points=int(r["metrics"]["accepted_points"]),
            gate_tracks=int(r["metrics"]["accepted_tracks"]),
        )
        for a, r in selected["arms"].items()
    }
    return (
        bridge_support.support(arms),
        retained(audit["recovery"]),
        {a: list(arms[a]["endpoint_latlon"]) for a in ARMS},
        worker["artifact"]["sha256"],
        start,
        initial["box_width_km"] / 2,
    )


def audit(output):
    lock = common.seal(output, "roof-lock.json", (trial.POSITIONS, trial.CONTROLS, "tails.json"))
    risk = common.read(output / "tails.json")["audit"]
    if risk is None:
        return
    ident = risk["id"]
    if ident not in lock["cases"]:
        raise ValueError("regression outside the established reserve")
    plan = common.read(output / "source-lock.json")
    artifact = common.secant_full.REPORT / "original-v5-inputs.json"
    if common.sha(artifact) != plan["compact_ledger"]["files"][artifact.name]:
        raise ValueError("original binding archive changed")
    bound = common.read(artifact)[ident]["baseline"]
    saved, conservative, points, arch, start, bound_km = original(
        ident, plan["bindings"][ident], bound
    )
    records = read_predictions(output / trial.POSITIONS)
    all_metrics = records[ident]["result"]["metrics"]
    metrics = all_metrics["bridge_support"]
    same_boundary_cases = [
        i
        for i, row in records.items()
        if row["result"]["status"] == "ok"
        and max(map(abs, row["result"]["metrics"]["center_bridge"]["start_xy"])) >= bound_km
    ]
    report = dict(
        id=ident,
        input_sha256=records[ident]["input_sha256"],
        roof_lock_sha256=common.sha(output / "roof-lock.json"),
        original_archive_sha256=arch,
        original_execution=bound,
        selected_after_freeze=risk,
        original_initial=start,
        bridge_seed=dict(
            **{
                k: all_metrics["center_bridge"][k]
                for k in ("first_xy", "start_xy", "seed_gate_points", "seed_gate_tracks")
            },
            original_c0_initial_distance_km=dist(
                all_metrics["center_bridge"]["start_xy"], start["c0"]["xy"]
            ),
            regional_half_width_km=bound_km,
            completed_cases_at_boundary=sorted(same_boundary_cases),
        ),
        original_cavity_coordinates=points,
        original_conservative={
            a: dict(
                points=sum(r["points"] for r in info["owners"].values()),
                tracks=len(info["owners"]),
                xy=info["xy"],
            )
            for a, info in conservative.items()
        },
        bridge_reclassification={k: metrics[k] for k in ("readmitted", "reassigned")},
        cavity_support={
            a: dict(
                compare(metrics["final_support"][a]["curved"], saved[a]["curved"]),
                bridge_predictive_points=metrics["final_support"][a]["predictive_points"],
                original_predictive_points=saved[a]["predictive_points"],
            )
            for a in ARMS
        },
    )
    save_json(output / "regression-audit.json", report)
    save_json(
        output / "regression-audit-receipt.json",
        dict(
            id=ident,
            roof_lock_sha256=report["roof_lock_sha256"],
            files={"regression-audit.json": common.sha(output / "regression-audit.json")},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=trial.REPORT)
    audit(local_output(parser.parse_args().out))
