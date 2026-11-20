"""Advance complete saved-IQ ordinary GLRT products through the locked clock/offset fit."""

import argparse
import gzip
import json
import subprocess
from pathlib import Path
from time import perf_counter

from ..__main__ import encoded, local_output, read_predictions, references, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from ..variants import clock_offset, native_lean
from . import (
    clock_chain_raw,
    clock_offset_trial,
    iq_joint_trial,
    native_clock_donor,
    native_joint_trial,
)
from .full_v5_check import _load_case, _sha

REPORT = clock_chain_raw.REPORT
CASES = iq_joint_trial.CASES
METHOD = "clock_chain"
PRIMARY = clock_offset.METHOD
BOUNDARY = "Complete saved IQ through ordinary GLRT, streaming Graph and joint clock plus offset"
ARCHIVE_BOUNDARY = (
    "Authenticated complete ordinary GLRT artifact through fresh Graph and clock plus offset"
)
CLOCK_STUDY = clock_offset_trial.REPORT / "full"
SOURCES = (Path(__file__), Path(clock_chain_raw.__file__))


def verify_deployment():
    prior = iq_joint_trial.read(iq_joint_trial.SEAL)
    if encoded(prior) != encoded(iq_joint_trial.source_lock(iq_joint_trial.joint.BUNDLE)):
        raise ValueError("The reviewed ordinary detector or native Graph source changed")


def sealed_inputs(report, sources):
    donor_lock = iq_joint_trial.verify_lock(iq_joint_trial.REPORT)
    clock_lock = iq_joint_trial.verify_lock(CLOCK_STUDY)
    frozen = iq_joint_trial.read(CLOCK_STUDY / "plan.json")
    for path in (
        clock_offset_trial.WORKER,
        Path(clock_offset.__file__),
        Path(clock_offset.offset.__file__),
    ):
        key = str(path.relative_to(clock_offset_trial.ROOT))
        if _sha(path) != frozen["implementation"][key]:
            raise ValueError(f"Frozen clock-offset implementation changed: {key}")
    archives = native_clock_donor.REPORT / "archived-controls"
    return dict(
        cases=list(CASES),
        source_sha256=sources | {"PROTOCOL.md": _sha(report / "PROTOCOL.md")},
        ordinary_parent_sha256=donor_lock,
        ordinary_source_sha256=_sha(iq_joint_trial.SEAL),
        clock_parent_sha256=clock_lock,
        clock_implementation=frozen["implementation"],
        archive_controls_sha256=iq_joint_trial.verify_lock(archives),
    )


def archived_sources(report):
    return {path.name: _sha(report / "source" / f"{path.name}.txt") for path in SOURCES}


def lock_report(report):
    verify_deployment()
    report.mkdir(parents=True, exist_ok=False)
    write(report / "PROTOCOL.md", (REPORT / "PROTOCOL.md").read_bytes())
    for source in SOURCES:
        write(report / "source" / f"{source.name}.txt", source.read_bytes())
    save_json(report / "source-lock.json", sealed_inputs(report, archived_sources(report)))


def require_current_lock(report, work):
    lock = iq_joint_trial.read(report / "source-lock.json")
    current = {path.name: _sha(path) for path in SOURCES}
    if current != archived_sources(report) or lock != sealed_inputs(report, current):
        raise ValueError("Runnable source differs from the selected report lock")
    name = Path(clock_chain_raw.__file__).name
    receipt = work / clock_chain_raw.RUNNER_RECEIPT
    if not receipt.is_file() or iq_joint_trial.read(receipt) != {name: current[name]}:
        raise ValueError("Replay was not produced by the locked raw runner")


def verify_product(case, ordinary, fresh, factor=None):
    """Keep the complete named ordinary product across the fresh numerical boundary."""
    raw = fresh["raw"]
    prior = ordinary["raw"]
    keys = (
        "detector_sha256",
        "native_input_manifest_sha256",
        "analysis_manifest_sha256",
        "native_sha256",
        "iq_bytes",
        "recording_windows",
        "processed_windows",
        "invalid_capture",
        "probe_rows",
        "candidate_rows",
        "positive_candidates",
    )
    if (
        raw["id"] != case["id"]
        or raw["raw_gate"] != "fresh whole-recording native GLRT"
        or any(raw[key] != prior[key] for key in keys)
        or (factor is not None and _sha(factor) != raw["native_sha256"])
        or raw["recording_windows"] != case["recording"]["window_count"]
        or len(fresh["raw_lanes"]) != 2
        or sum(v["decoded_visits"] for v in fresh["raw_lanes"]) != raw["recording_windows"]
        or sum(v["decoded_bytes"] for v in fresh["raw_lanes"]) != raw["iq_bytes"]
    ):
        raise ValueError("Fresh factor bytes, capture coverage or detector authority do not match")


def bind(case, work):
    original = iq_joint_trial.read(iq_joint_trial.REPORT / "stage-receipts.json")[case["id"]]
    folder = work / case["id"]
    raw = folder / "raw-stages.json"
    unsuccessful = work / f"{case['id']}-raw-failure.json"
    if raw.is_file():
        stage = iq_joint_trial.read(raw)
        factor = folder / "native.json"
        verify_product(case, original, stage, factor)
        scope = dict(fresh_ordinary_raw=True, fresh=stage, archive_reused=None)
    elif unsuccessful.is_file():
        factor = native_clock_donor.DONORS / case["id"] / "native.json"
        scope = dict(
            fresh_ordinary_raw=False,
            fresh=None,
            unsuccessful=iq_joint_trial.read(unsuccessful),
            archive_reused=dict(
                raw=original["raw"],
                prior_raw_envelope=original["raw_envelope"],
                prior_factor_assembly=original["factor_assembly"],
            ),
        )
    else:
        raise ValueError("No terminal fresh replay receipt or authenticated failure is available")
    digest = original["raw"]["native_sha256"]
    packet, paths = iq_joint_trial.bind_fresh(case, factor, digest)
    if (
        packet != original["native_query"]
        or packet["catalogue"]["sha256"] != case["catalog"]["sha256"]
    ):
        raise ValueError("Fresh clock request changed its causal or track authority")
    for field in ("native", "catalogue", "track_config"):
        if _sha(paths[field]) != packet[field]["sha256"]:
            raise ValueError(f"Mounted {field} differs from the authenticated packet")
    return scope, packet, paths, original


def verify_worker(result, boundary, packet, paths, parent):
    if (
        result["observation_sha256"] != parent["graph_sha256"]
        or result["counts"]["native_bytes"] != paths["native"].stat().st_size
        or result["counts"]["probes"] != parent["raw"]["probe_rows"]
        or result["address_space_limit_mib"] != native_lean.AS_LIMIT_MIB
        or set(result["models"]) != set(clock_offset.MODES)
        or any(
            "localization_v3" in path or "v5_" in path for path in result["imported_first_party"]
        )
    ):
        raise ValueError("Fresh worker changed product coverage, Graph identity or memory bound")
    assignment = set()
    for model in result["models"].values():
        validate_result(model)
        metrics = model["metrics"]
        keys = ("training_ownership", "final_ownership", "held_prefix_ownership")
        assignment.add(encoded({key: metrics[key] for key in keys}))
        if set(model["arms"]) != set(ARMS) or model["arms"]["c0"]["c_hz_per_ghz"] != 0:
            raise ValueError("Clock model changed a calibration arm")
        model["boundary"] = boundary
    if len(assignment) != 1 or packet != parent["native_query"]:
        raise ValueError("Paired fits did not share original held and training assignments")


def verify_published(report, work=None):
    prediction_sha = iq_joint_trial.verify_lock(report)
    lock = iq_joint_trial.read(report / "source-lock.json")
    if lock != sealed_inputs(report, archived_sources(report)):
        raise ValueError("Archived runner bytes or a frozen parent differ from the source lock")
    figure_lock = report / "figure-lock.json"
    if figure_lock.is_file():
        iq_joint_trial.verify_lock(report, figure_lock.name)
        figure = iq_joint_trial.read(figure_lock)
        solver = REPORT.with_name("solver-memory")
        solver_lock = iq_joint_trial.verify_lock(solver)
        solver_product = _sha(solver / "control-positions.jsonl.gz")
        if (
            figure["compact_control_parent_lock_sha256"] != solver_lock
            or figure["compact_control_parent_product_sha256"] != solver_product
        ):
            raise ValueError("Published compact comparator differs from its sealed parent")
    rows = iq_joint_trial.read(report / "stage-receipts.json")
    prior = iq_joint_trial.read(iq_joint_trial.REPORT / "stage-receipts.json")
    if set(rows) != set(CASES):
        raise ValueError("Published receipts do not contain exactly the locked two recordings")
    for ident in CASES:
        case, row, original = _load_case(ident), rows[ident], prior[ident]
        scope = row["scope"]
        packet = row["packet"]
        if (
            row["id"] != ident
            or packet != original["native_query"]
            or row["input_sha256"] != iq_joint_trial.sha256(encoded(packet)).hexdigest()
            or row["native_sha256"] != packet["native"]["sha256"]
            or row["worker"]["observation_sha256"] != original["graph_sha256"]
            or row["worker"]["counts"]["probes"] != original["raw"]["probe_rows"]
        ):
            raise ValueError(f"Published native or Graph receipt differs for {ident}")
        if scope["fresh_ordinary_raw"]:
            verify_product(case, original, scope["fresh"])
        elif scope["archive_reused"]["raw"] != original["raw"]:
            raise ValueError(f"Published archive fallback differs from authority for {ident}")
        if work is not None:
            mounted_scope, mounted_packet, paths, _ = bind(case, work)
            if (scope, packet) != (mounted_scope, mounted_packet):
                raise ValueError(f"Mounted raw receipts differ from the published run for {ident}")
            boundary = BOUNDARY if scope["fresh_ordinary_raw"] else ARCHIVE_BOUNDARY
            verify_worker(row["worker"], boundary, packet, paths, original)
    return dict(
        cases=list(CASES), prediction_sha256=prediction_sha, mounted_factors=work is not None
    )


def run_fit(ident, work, cap, cpu):
    case = _load_case(ident)
    scope, packet, paths, prior = bind(case, work)
    args = clock_offset_trial.command(cpu, paths, native_joint_trial.BUNDLE)
    began = perf_counter()
    run = subprocess.run(args, input=encoded(packet), capture_output=True, check=True, timeout=cap)
    out = json.loads(run.stdout)
    boundary = BOUNDARY if scope["fresh_ordinary_raw"] else ARCHIVE_BOUNDARY
    verify_worker(out, boundary, packet, paths, prior)
    row = dict(
        id=ident,
        method=METHOD,
        native_sha256=packet["native"]["sha256"],
        capture_era_native_sha256=case["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
        input_sha256=iq_joint_trial.sha256(encoded(packet)).hexdigest(),
        tile=packet["offer"],
        worker_wall_s=perf_counter() - began,
        scope=scope,
        worker=out,
        packet=packet,
    )
    save_json(work / f"{ident}-fit.json", row)


def _errors(ident, result):
    panel = "ds26-common127" if ident.startswith("DS26") else "roof16"
    _, (site,) = references(panel, [ident])
    return {arm: distance_km(result["arms"][arm]["latlon"], site["truth"]) for arm in ARMS}


def archive_options():
    archive = native_clock_donor.REPORT / "archived-controls"
    entries = []
    for role in ROLES:
        rows = read_predictions(archive / f"{role}.jsonl.gz")
        for ident in CASES:
            row, case = rows[ident], _load_case(ident)
            if row["native_sha256"] != case["native"]["sha256"] or (
                row["catalog_sha256"] != case["catalog"]["sha256"]
            ):
                raise ValueError("Original v5 option does not match the roof capture and catalogue")
            entries.append(dict(row, variant=role, position_error_km=_errors(ident, row["result"])))
    return entries


def _gzip(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def package(report, work):
    if (report / "prediction-lock.json").exists():
        raise ValueError("The selected report already contains sealed predictions")
    require_current_lock(report, work)
    fits = [iq_joint_trial.read(work / f"{ident}-fit.json") for ident in CASES]
    models = []
    for fit in fits:
        for variant, result in fit["worker"]["models"].items():
            row = {k: v for k, v in fit.items() if k not in {"scope", "worker", "packet"}}
            models.append(
                dict(
                    row,
                    variant=variant,
                    result=result,
                    observation_sha256=fit["worker"]["observation_sha256"],
                    position_error_km=_errors(fit["id"], result),
                )
            )
    controls = archive_options()
    _gzip(report / "positions.jsonl.gz", models)
    _gzip(report / "v5-options.jsonl.gz", controls)
    save_json(report / "stage-receipts.json", {row["id"]: row for row in fits})
    summary = {
        variant: {
            arm: distribution(
                row["position_error_km"][arm]
                for row in models + controls
                if row["variant"] == variant
            )
            for arm in ARMS
        }
        for variant in (*clock_offset.MODES, *ROLES)
    }
    save_json(report / "summary.json", summary)
    names = (
        "PROTOCOL.md",
        "source-lock.json",
        "positions.jsonl.gz",
        "v5-options.jsonl.gz",
        "stage-receipts.json",
        "summary.json",
        *(f"source/{path.name}.txt" for path in SOURCES),
    )
    save_json(
        report / "prediction-lock.json",
        dict(cases=list(CASES), files={name: _sha(report / name) for name in names}),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("lock", "fit", "package", "verify"))
    parser.add_argument("--work", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--case", choices=CASES)
    parser.add_argument("--cap", type=int, default=25)
    opts = parser.parse_args()
    if opts.action != "verify" and opts.report is None:
        parser.error("select a separate --report directory for a new replay")
    report = local_output(opts.report or REPORT)
    work = local_output(opts.work) if opts.work is not None else None
    if opts.action == "lock":
        lock_report(report)
        return
    if opts.action == "verify":
        print(json.dumps(verify_published(report, work), indent=2))
        return
    if work is None:
        parser.error("supply the matching raw replay --work directory")
    if opts.action == "fit":
        if opts.case is None:
            parser.error("select the recording with --case")
        require_current_lock(report, work)
        verify_deployment()
        run_fit(opts.case, work, opts.cap, clock_chain_raw.CPUS[CASES.index(opts.case)])
    else:
        package(report, work)


if __name__ == "__main__":
    main()
