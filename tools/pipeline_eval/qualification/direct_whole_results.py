"""Publish measured whole-IQ direct slim receiver endpoints and factor authority."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import direct_whole_trial as trial
from . import full_receiver_comparison as common
from . import whole_fractional as earlier
from . import whole_memory_chain as apparatus
from . import whole_pair
from .direct_lifetime_results import whole_cpu
from .iq_schedule import native_durations
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

METHODS = {
    trial.METHOD: ("positions.jsonl.gz", "one", "Direct slim"),
    "whole_fractional": ("prepared-positions.jsonl.gz", "one_native_factors", "Prior prepared"),
    "whole_cavity": ("stock-positions.jsonl.gz", "stock", "Ordinary stock"),
}


def validate_stage_receipt(begin, position):
    if position["evaluator_modules"] or not Path(position["entry"]).is_relative_to(trial.SLIM):
        raise ValueError("position backend differs from the explicit slim source contract")
    for marker in (position["start"], position["end"]):
        expected = dict(pid=begin["pid"], cgroup=begin["cgroup"], cpus=[18]) | {
            "memory.max": trial.CHAIN.MEMORY,
            "memory.swap.max": 0,
            "memory.swap.current": 0,
            "memory.events.oom_kill": 0,
        }
        common.require_fields(marker, expected)
    if position["end"]["monotonic_s"] <= position["start"]["monotonic_s"]:
        raise ValueError("position timestamps do not bound a completed fit")


def archived(source, name):
    return read_predictions(apparatus.sealed(source, name))[trial.IDENT]


def optional(path):
    return common.read(path) if path.is_file() else None


def summarize(work):
    lock = work / "plan.json"
    pin = common.read(lock)
    if trial.plan() != pin:
        raise ValueError("whole replay inputs or exact package changed after lock")
    ident = trial.IDENT
    folder = work / ident
    service = common.read(work / f"{ident}-service.json")
    log_file = work / f"{ident}-systemd.log"
    if common.sha(log_file) != service["log_sha256"]:
        raise ValueError("systemd log differs from the service receipt")
    log = log_file.read_text()
    begin = optional(work / f"{ident}-begin.json")
    start = None if begin is None else begin["start"]
    raw = optional(folder / "raw-stages.json")
    position = optional(folder / "position-stages.json")
    complete = position is not None and "end" in position and service["code"] == 0
    fresh = folder / "native.json"
    observed = common.sha(fresh) if fresh.is_file() else None
    prepared = archived(earlier.REPORT, "positions.jsonl.gz")
    ordinary = archived(earlier.REPORT, "control-positions.jsonl.gz")
    measured_binding = pin["binding"]
    for row in (prepared, ordinary):
        common.require_fields(row, {k: measured_binding[k] for k in ("catalog_sha256", "tile")})
    if complete:
        validate_stage_receipt(start, position)
        if (
            observed != pin["prepared_native_sha256"]
            or observed != raw["native_sha256"]
            or not raw["request_parity"]
            or not raw["factor_parity"]["complete_native_science_exact"]
            or raw["lane_parity"] != {"lanes": 2, "segments": 14, "visits": 6772}
            or not service["samples"]
        ):
            raise ValueError("published position lacks exact complete prepared GLRT authority")
        result = common.read(folder / "position/result.json")
    else:
        result = dict(
            status="timed_out" if service["systemd"].get("Result") == "timeout" else "failed",
            reason=service["systemd"].get("Result", "Worker did not finish"),
            arms={a: {"latlon": None} for a in ARMS},
            metrics={"position_attempted": position is not None},
        )
    result["boundary"] = trial.BOUNDARY
    validate_result(result)
    trace = dict(
        service=service,
        start=start,
        raw=raw,
        position=position,
        service_log=log,
        exact_prepared_sha256=observed == pin["prepared_native_sha256"],
    )
    return (
        dict(
            id=ident,
            method=trial.METHOD,
            detector="ordinary",
            mode="matched-tile",
            input_sha256=observed,
            native_sha256=observed,
            origin_native_sha256=pin["ordinary_native_sha256"],
            catalog_sha256=measured_binding["catalog_sha256"],
            tile=measured_binding["tile"],
            worker_wall_s=(
                position["end"]["monotonic_s"] - start["monotonic_s"]
                if complete
                else service["elapsed_s"]
            ),
            result=result,
        ),
        prepared,
        ordinary,
        trace,
    )


def stages_for(trace):
    raw, start, position = (trace[k] for k in ("raw", "start", "position"))
    result = {
        "supervisor_wall_s": trace["service"]["elapsed_s"],
        "systemd_cpu_s": whole_cpu(trace["service_log"]),
    }
    if raw and start:
        raw_last = raw["raw_complete"]
        assembly = raw["assembly_complete"]
        result.update(
            raw_wall_s=raw_last["monotonic_s"] - start["monotonic_s"],
            raw_cpu_s=(raw_last["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6,
            assembly_wall_s=assembly["monotonic_s"] - raw_last["monotonic_s"],
            acquisition_seconds=raw["capture_seconds"],
        )
    if position and "end" in position:
        entry, exit = position["start"], position["end"]
        result.update(
            handoff_wall_s=entry["monotonic_s"] - raw["assembly_complete"]["monotonic_s"],
            position_wall_s=exit["monotonic_s"] - entry["monotonic_s"],
            position_cpu_s=(exit["cpu.stat.usage_usec"] - entry["cpu.stat.usage_usec"]) / 1e6,
            position_peak_rss_kib=exit["rss_peak_kib"],
            memory_peak_bytes=exit["memory.peak"],
            full_replay_wall_s=exit["monotonic_s"] - start["monotonic_s"],
            full_replay_cpu_s=(exit["cpu.stat.usage_usec"] - start["cpu.stat.usage_usec"]) / 1e6,
            oom_kills=exit["memory.events.oom_kill"],
            swap_bytes=exit["memory.swap.current"],
        )
    return result


def stage_source(report):
    path = apparatus.sealed(report, "stages.json.gz")
    return json.loads(gzip.decompress(path.read_bytes()))[trial.IDENT]


def seal(work, out):
    ident = trial.IDENT
    measured, prepared, ordinary, trace = summarize(work)
    rows = {r["method"]: r for r in (measured, prepared, ordinary)}
    all_traces = {
        trial.METHOD: trace,
        "whole_fractional": stage_source(earlier.REPORT),
        "whole_cavity": stage_source(whole_pair.REPORT),
    }
    out.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for method, (name, _, _) in METHODS.items():
        pack(out / name, [rows[method]])
        artifacts.append(name)
    for name, data in (
        ("stages.json.gz", gzip.compress(encoded(trace), mtime=0)),
        ("source-lock.json", (work / "plan.json").read_bytes()),
    ):
        write(out / name, data)
        artifacts.append(name)
    native = work / ident / "native.json"
    if native.is_file():
        write(out / "native.json.gz", gzip.compress(native.read_bytes(), mtime=0))
        artifacts.append("native.json.gz")
    phase = [dict(method=method, **stages_for(t)) for method, t in all_traces.items()]
    timing_fields = tuple(dict.fromkeys(key for row in phase for key in row))
    csv_file(out / "timings.csv", [{k: r.get(k) for k in timing_fields} for r in phase])
    comparison = {}
    for method, row in rows.items():
        result = row["result"]
        audit = all_traces[method]
        comparable = result["status"] == measured["result"]["status"] == "ok"
        raw = audit["raw"]
        comparison[method] = dict(
            completed=result["status"] == "ok",
            raw_counts=raw["raw_counts"] if raw else None,
            native_calls=native_durations(audit)
            if raw and (not audit["position"] or "end" in audit["position"])
            else None,
            exact_position_and_rms=result["arms"] == measured["result"]["arms"]
            if comparable
            else None,
            numerical_counts={
                k: v
                for k, v in result["metrics"].items()
                if k
                in (
                    "observations",
                    "tracks",
                    "initial_branches",
                    "initial_arm_fits",
                    "cavity_offered",
                    "compact_projections",
                )
            },
        )
    save_json(out / "comparison.json", comparison)
    artifacts.extend(("comparison.json", "timings.csv"))
    public = dict(
        cases=[ident],
        input_sha256=measured["native_sha256"],
        source_lock_sha256=common.sha(out / "source-lock.json"),
        files={k: common.sha(out / k) for k in artifacts},
    )
    save_json(out / "receipt.json", public)
    return rows, public


def score(rows, out, receipt):
    ref, _ = _frozen_roof()
    csv_file(
        out / "scores.csv",
        [
            dict(
                id=row["id"],
                method=method,
                status=row["result"]["status"],
                arm=a,
                error_km=distance_km(row["result"]["arms"][a]["latlon"], ref[row["id"]]["truth"]),
                conditional_rms_hz=row["result"]["arms"][a].get("rf_rms_hz"),
            )
            for method, row in rows.items()
            for a in ARMS
        ],
    )
    lock = dict(receipt, files={**receipt["files"], "scores.csv": common.sha(out / "scores.csv")})
    save_json(out / "figure-lock.json", lock)
    save_json(
        out / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="direct-whole-prepared-slim",
                    method=trial.METHOD,
                    cases=receipt["cases"],
                    scope="roof",
                    seal="figure-lock.json",
                    title="Full saved IQ through the slim direct receiver",
                    caption="A full ordinary recording under 512 MiB. Controls use the same "
                    "saved visits. Original v5 roles use capture-era factors.",
                    source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                    provenance=["comparison.json", "timings.csv", "scores.csv"],
                    series=[
                        dict(
                            key=key,
                            file=name,
                            value=method,
                            label=label,
                            native_authority="ordinary",
                            native_field="native_sha256"
                            if key == "stock"
                            else "origin_native_sha256",
                            **({"match": ["tile", "catalog_sha256"]} if key != "one" else {}),
                        )
                        for method, (name, key, label) in METHODS.items()
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=trial.REPORT)
    a = p.parse_args()
    output = local_output(a.out)
    measured, receipt = seal(a.work, output)
    score(measured, output, receipt)
