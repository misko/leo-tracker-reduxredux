"""Score the capped row-major replay from sealed attempts and the historical timing pair."""

import argparse
import csv
import gzip
import json
import re
from collections import Counter
from statistics import median

from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import row_memory_replay as trial
from . import same_core_baseline as baseline
from .full_receiver_comparison import read, require_fields, roster_matches, seal, sha
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

CHART = "v5_recovery_reads-roof4-capture-era"
ATTEMPTS = "attempts.jsonl.gz"
EXECUTED = "as-executed-launcher.py"
CAPTURE = "capped-positions.jsonl.gz"
COMPACT = "compact-positions.jsonl.gz"
ORIGINAL = "original-positions.jsonl.gz"


def counters(raw):
    return {key: int(value) for key, value in map(str.split, raw.splitlines())}


def systemd_seconds(raw):
    if raw is None:
        return None
    scales = {"min": 60, "s": 1, "ms": 0.001, "us": 0.000001}
    return sum(
        float(n) * scales[unit] for n, unit in re.findall(r"(\d+(?:\.\d+)?)(min|ms|us|s)", raw)
    )


def terminal_evidence(attempt):
    log = attempt.get("preserved_worker_log")
    if log is None:
        return {}
    from ..corpus import _sha

    if _sha(log.encode()) != attempt["worker_log_sha256"]:
        raise ValueError("preserved service log differs from the original attempt")
    lines = log.splitlines()
    marker = re.compile(r"^stage: (enter|leave) (.+)$")
    stage_rows = [m.groups() for line in lines if (m := marker.fullmatch(line))]
    stage_counts = Counter(
        stage
        for change, label in stage_rows
        for stage in (label.split("#")[0],)
        if change == "leave"
    )
    log_fields = {
        k: v.strip()
        for line in lines
        if ":" in (stripped := line.strip()) and not stripped.startswith("stage:")
        for k, v in (stripped.split(":", 1),)
    }
    if (
        (unit := attempt.get("unit"))
        and not any(line.startswith(f"Running as unit: {unit}.service") for line in lines)
        and trial.terminal_result(log) in ("oom-kill", "timeout")
    ):
        raise ValueError("systemd terminal log has a different transient unit")
    return dict(
        result=trial.terminal_result(log),
        peak_and_swap=log_fields.get("Memory peak"),
        cpu_s=systemd_seconds(log_fields.get("CPU time consumed")),
        runtime_s=systemd_seconds(log_fields.get("Service runtime")),
        last_stage=" ".join(stage_rows[-1]) if stage_rows else None,
        entered=sorted(
            {label for change, label in stage_rows if change == "enter" and "#" not in label}
        ),
        completed=stage_counts,
    )


def audit_snapshots(samples, unit, cpu):
    if not samples:
        return {}
    if (
        len({item["pid"] for item in samples}) != 1
        or len({item["cgroup"] for item in samples}) != 1
        or not samples[0]["cgroup"].endswith(f"/{unit}.service")
    ):
        raise ValueError("sampling changed its transient worker or cgroup")
    for item in samples:
        require_fields(
            item,
            {
                "affinity": [cpu],
                "memory.max": str(trial.MEMORY),
                "memory.swap.max": "0",
                "memory.swap.current": "0",
            },
        )
        if item["nice"] < trial.NICE or int(item["process"]["Threads"]) != 1:
            raise ValueError("the worker used the wrong priority or thread count")
    last = samples[-1]
    return dict(
        count=len(samples),
        cgroup_peak_bytes=max(int(row["memory.peak"]) for row in samples),
        cpu_sample_s=counters(last["cpu.stat"])["usage_usec"] / 1e6,
        process_io_sample=last["process_io"],
        cgroup_io_sample=last["io.stat"],
        memory_events_sample=counters(last["memory.events"]),
        sampled_interval_s=(last["observed_ns"] - samples[0]["observed_ns"]) / 1e9,
    )


def validate_attempt(attempt, plan):
    ident = attempt["id"]
    expected = plan["source"]
    cpu = expected["cpu_by_case"][ident]
    require_fields(attempt, dict(cpu=cpu))
    result = attempt["result"]
    validate_result(result)
    roster_matches(result["arms"], ARMS, f"{ident} outcomes")
    measurements = audit_snapshots(attempt["snapshots"], attempt.get("unit"), cpu)
    terminal = terminal_evidence(attempt)
    if measurements.get("cgroup_peak_bytes", 0) > trial.MEMORY:
        raise ValueError(f"{ident} observed a cgroup above the memory cap")
    proof = attempt.get("request_proof")
    if (
        measurements
        or result["status"] == "ok"
        or terminal.get("result") in ("oom-kill", "timeout")
    ) and (not proof or not 180 <= attempt["runtime_limit_s"] <= 210):
        raise ValueError(f"{ident} ran without a bound request and runtime limit")
    if result["status"] == "ok" and not measurements:
        raise ValueError(f"{ident} completed without observing its live cap")
    if proof:
        require_fields(
            proof,
            {
                k: expected["inputs"][ident][k]
                for k in ("resolved_request_sha256", "scientific_request_sha256")
            },
        )
    lock_start = plan["locked_ns"]
    if (
        not lock_start
        <= attempt["started_ns"]
        <= attempt["finished_ns"]
        <= (lock_start + trial.PANEL_S * 1_000_000_000)
    ):
        raise ValueError(f"{ident} attempt exceeds its time window")
    return measurements, terminal


def precedes_retry(row, terminal):
    return (
        row["result"]["status"] == "unavailable"
        and not row["snapshots"]
        and terminal.get("last_stage") is None
        and terminal.get("result") not in ("oom-kill", "timeout")
    )


def collect(attempts, plan):
    groups = {ident: [] for ident in plan["source"]["roster"]}
    positions = []
    for item in attempts:
        observed, terminal = validate_attempt(item, plan)
        groups[item["id"]].append((item, observed, terminal))
    for ident, group in groups.items():
        ordered = sorted(group, key=lambda x: x[0]["started_ns"])
        if not 1 <= len(ordered) <= 2:
            raise ValueError(f"{ident} lacks its one or two scheduled receipts")
        if len(ordered) == 2 and (
            not precedes_retry(ordered[0][0], ordered[0][2])
            or ordered[0][0]["finished_ns"] > ordered[1][0]["started_ns"]
        ):
            raise ValueError(f"{ident} retried an observed worker")
        final, observed, terminal = ordered[-1]
        result = final["result"]
        if terminal.get("result") in ("oom-kill", "timeout"):
            status = "timed_out" if terminal["result"] == "timeout" else "failed"
            result = dict(
                result,
                status=status,
                reason=terminal["result"],
                metrics=dict(result["metrics"], position_attempted=bool(terminal["last_stage"])),
            )
        validate_result(result)
        positions.append(
            dict(
                plan["source"]["inputs"][ident],
                method=trial.NAME,
                cpu=final["cpu"],
                mode="memory-cap",
                result=result,
                raw_launcher_status=final["result"]["status"],
                live_cap=observed,
                terminal=terminal,
                attempts=len(ordered),
                worker_wall_s=final.get("worker_wall_s"),
            )
        )
    return positions


def delta(left, right):
    return left - right if left is not None and right is not None else None


def point_arm(row, arm):
    result = row["result"]
    a = result["arms"][arm]
    rf = a.get("rf_rms_hz", result["metrics"].get(f"{arm}_conditional_rms_hz"))
    return a["latlon"], rf, result["metrics"].get(f"{arm}_associated_observations")


def score_positions(active, controls):
    refs, _ = _frozen_roof()
    for row in active:
        ident = row["id"]
        truth = refs[ident]["truth"]
        for arm in ARMS:
            point, rf, observations = point_arm(row, arm)
            compact, compact_rf, compact_count = point_arm(controls[baseline.COMPACT][ident], arm)
            original, original_rf, original_count = point_arm(
                controls[baseline.ORIGINAL][ident], arm
            )
            to_compact, to_original = distance_km(point, compact), distance_km(point, original)
            yield dict(
                id=ident,
                cpu=row["cpu"],
                arm=arm,
                cap_status=row["result"]["status"],
                capped_error_km=distance_km(point, truth),
                compact_error_km=distance_km(compact, truth),
                original_error_km=distance_km(original, truth),
                cap_to_compact_m=1000 * to_compact if to_compact is not None else None,
                cap_to_original_m=1000 * to_original if to_original is not None else None,
                capped_conditional_rms_hz=rf,
                compact_conditional_rms_hz=compact_rf,
                original_conditional_rms_hz=original_rf,
                cap_minus_compact_hz=delta(rf, compact_rf),
                cap_minus_original_hz=delta(rf, original_rf),
                capped_associated_observations=observations,
                compact_associated_observations=compact_count,
                original_associated_observations=original_count,
            )


def timing_fields(prefix, row):
    keys = (
        "launcher_wall_s",
        "child_cpu_s",
        "peak_child_rss_kib",
        "common_through_cavity_s",
        "numerical_published_boundary_s",
        "original_full_late_s",
        "original_render_s",
    )
    return {f"{prefix}_{key}": row[key] for key in keys}


def score_resources(active):
    path = trial.baseline.REPORT / "timings.csv"
    with path.open(newline="") as stream:
        historic = {(row["id"], row["method"]): row for row in csv.DictReader(stream)}
    for row in active:
        ident, cpu = row["id"], row["cpu"]
        a, b = (historic[ident, name] for name in (baseline.COMPACT, baseline.ORIGINAL))
        for item in (a, b):
            if int(item["cpu"]) != cpu:
                raise ValueError("historical timing rows changed their CPU binding")
        metrics = row["result"]["metrics"]
        measurement = metrics.get("composed_memory_measurement", {})
        live = row["live_cap"]
        terminal = row["terminal"]
        io = metrics.get("recovery_reads", {})
        physical = io.get("worker_io", live.get("process_io_sample", {}))
        sweeps = io.get("sweeps", [])
        yield dict(
            id=ident,
            cpu=cpu,
            status=row["result"]["status"],
            raw_launcher_status=row["raw_launcher_status"],
            attempts=row["attempts"],
            reason=row["result"].get("reason"),
            systemd_result=terminal.get("result"),
            last_stage=terminal.get("last_stage"),
            systemd_cpu_s=terminal.get("cpu_s"),
            systemd_runtime_s=terminal.get("runtime_s"),
            systemd_reported_memory_peak_swap=terminal.get("peak_and_swap"),
            nomination_coarse_sweeps=terminal.get("completed", {}).get("nomination.coarse", 0),
            completed_residual_screens=terminal.get("completed", {}).get("screen_candidates", 0),
            capped_service_wall_s=row["worker_wall_s"],
            capped_worker_cpu_s=measurement.get("cpu_s"),
            capped_internal_wall_s=measurement.get("wall_s"),
            capped_process_peak_rss_kib=measurement.get("after", {}).get("peak_rss_kib"),
            capped_observed_cgroup_peak_bytes=live.get("cgroup_peak_bytes"),
            last_sampled_cgroup_cpu_s=live.get("cpu_sample_s"),
            last_sampled_oom=live.get("memory_events_sample", {}).get("oom"),
            last_sampled_oom_kill=live.get("memory_events_sample", {}).get("oom_kill"),
            measured_io_scope="completed worker" if io else "last sample" if live else None,
            capped_physical_read_bytes=physical.get("read_bytes"),
            capped_physical_write_bytes=physical.get("write_bytes"),
            capped_logical_coarse_read_bytes=sum(s["state_bytes"] for s in sweeps)
            if sweeps
            else None,
            historic_layout_equivalent_coarse_read_bytes=(
                sum(s["phase_major_state_bytes"] for s in sweeps) if sweeps else None
            ),
            capped_logical_bank_write_bytes=(
                sum(
                    s["scratch_bytes"]
                    for k in ("ecef", "audit")
                    for s in metrics.get("bounded_recovery_rows", {}).get(k, ())
                )
                if io
                else None
            ),
            **timing_fields("compact", a),
            **timing_fields("original", b),
        )


def pack(path, rows):
    write(path, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))


def publish(plan_path, attempts, output):
    plan = read(plan_path)
    historic, controls = trial.controls()
    source = plan["source"]
    executed = plan_path.with_name(EXECUTED)
    if not executed.exists():
        from pathlib import Path

        executed = Path(trial.__file__)
    require_fields(source, dict(launcher_sha256=sha(executed)))
    require_fields(
        source,
        dict(
            roster=historic["cases"],
            inputs=historic["bindings"],
            baseline_receipt_sha256=sha(baseline.REPORT / "receipt.json"),
            baseline_roof_receipt_sha256=sha(baseline.REPORT / "roof-lock.json"),
            deployed_rows_source_sha256=sha(trial.worker.REPORT / "source-lock.json"),
            deployed_rows_worker_sha256=sha(trial.worker.WORKER),
        ),
    )
    active = collect(attempts, plan)
    csv_file(output / "scores.csv", list(score_positions(active, controls)))
    resources = list(score_resources(active))
    prior = trial.worker.REPORT
    seeded_name = "capped-positions.jsonl.gz"
    seeded_lock = seal(prior, "prediction-lock.json", (seeded_name,))
    require_fields(
        seeded_lock, dict(cases=["DS29-0082"], source_lock_sha256=sha(prior / "source-lock.json"))
    )
    seeded = read_predictions(prior / seeded_name)["DS29-0082"]
    m = seeded["result"]["metrics"]
    workloads = [
        dict(
            id=row["id"],
            source="capture-era compact cavity track inventory",
            observations=row["result"]["metrics"]["observations"],
            tracks=row["result"]["metrics"]["tracks"],
            observed_nomination_coarse_passes=next(
                r["nomination_coarse_sweeps"] for r in resources if r["id"] == row["id"]
            ),
            full_nomination_possible=next(
                bool(row2["terminal"].get("completed", {}).get("nominate_families"))
                for row2 in active
                if row2["id"] == row["id"]
            ),
        )
        for row in controls[baseline.COMPACT].values()
    ]
    workloads.append(
        dict(
            id="DS29-0082",
            source="completed ordinary row-major worker",
            observations=m["observations"],
            tracks=m["tracks"],
            observed_nomination_coarse_passes=len(m["nomination_memory"]["coarse"]),
            full_nomination_possible=True,
            regional_nomination_satellite_counts=sorted(
                {r["rows"] for r in m["nomination_memory"]["coarse"]}
            ),
            completed_usable_ecef_rows=[r["rows"] for r in m["bounded_recovery_rows"]["ecef"]],
        )
    )
    save_json(output / "workload.json", workloads)
    csv_file(output / "resources.csv", resources)
    complete = [row for row in resources if row["status"] == "ok"]
    save_json(
        output / "summary.json",
        dict(
            scheduled=len(active),
            completed_fixes=len(complete),
            statuses={
                status: sum(r["status"] == status for r in resources)
                for status in sorted({r["status"] for r in resources})
            },
            measured_wall_median_s=median(r["capped_service_wall_s"] for r in complete)
            if complete
            else None,
            attempted_workers=len(attempts),
            recording_resources=resources,
        ),
    )
    pack(output / ATTEMPTS, attempts)
    pack(output / CAPTURE, active)
    for filename, method in ((COMPACT, baseline.COMPACT), (ORIGINAL, baseline.ORIGINAL)):
        pack(output / filename, (controls[method][ident] for ident in source["roster"]))
    write(output / "source-lock.json", plan_path.read_bytes())
    write(output / EXECUTED, executed.read_bytes())
    files = (
        CAPTURE,
        COMPACT,
        ORIGINAL,
        ATTEMPTS,
        EXECUTED,
        "scores.csv",
        "resources.csv",
        "summary.json",
        "workload.json",
    )
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=source["roster"],
            files={name: sha(output / name) for name in files},
            source_lock_sha256=sha(output / "source-lock.json"),
        ),
    )
    oom = sum(row["reason"] == "oom-kill" for row in resources)
    caption = (
        f"Four capture-era GLRT inputs on the historical cores. {len(complete)}/4 capped fixes. "
        f"{oom} memory kills. "
        "The historical compact worker ends at cavity. Row-major and original run late work."
    )
    series = [
        dict(
            key=key,
            file=file,
            value=method,
            label=label,
            match=[
                "input_sha256",
                "native_sha256",
                "catalog_sha256",
                "tile",
                "resolved_request_sha256",
            ],
        )
        for key, file, method, label in (
            (
                "one",
                CAPTURE,
                trial.NAME,
                "512 MiB cap (OOM)" if oom == len(active) else "Row-major at 512 MiB",
            ),
            ("stock", COMPACT, baseline.COMPACT, "Compact cavity on same core"),
            ("all_visits", ORIGINAL, baseline.ORIGINAL, "Full original on same core"),
        )
    ]
    save_json(
        output / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id=CHART,
                    method=trial.NAME,
                    scope="roof",
                    title="Row-major v5 at 512 MiB · four roofs",
                    cases=source["roster"],
                    caption=caption,
                    seal="prediction-lock.json",
                    series=series,
                    provenance=["scores.csv", "resources.csv", "summary.json", "workload.json"],
                    source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                )
            ],
        ),
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=local_output, default=trial.REPORT)
    parser.add_argument("--runs", type=local_output, default=trial.RUNS)
    parser.add_argument("--published", action="store_true")
    parser.add_argument("--out", type=local_output)
    args = parser.parse_args()
    plan = args.report / "source-lock.json"
    if args.published:
        lock = read(args.report / "prediction-lock.json")
        path = args.report / ATTEMPTS
        require_fields(lock, dict(source_lock_sha256=sha(plan)))
        if lock["files"][ATTEMPTS] != sha(path):
            raise ValueError("published attempts changed")
        attempts = list(map(json.loads, gzip.decompress(path.read_bytes()).splitlines()))
    else:
        attempts = []
        for path in sorted(args.runs.glob(f"*/attempt-*/{trial.FILE}")):
            item = read(path)
            log = path.with_name("worker.log")
            if log.exists() and item.get("worker_log_sha256"):
                item["preserved_worker_log"] = log.read_bytes().decode()
            attempts.append(item)
    publish(plan, attempts, args.out or args.report)


if __name__ == "__main__":
    main()
