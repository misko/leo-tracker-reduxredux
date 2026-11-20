"""Preserve the primary pairs and separate line tracing for the compact entry."""

import argparse
import gzip
import json
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from ..variants import v5_lean
from . import compact_entry_trial as trial
from . import full_receiver_comparison as common
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

REPORT, CONTROL, RECEIVER = trial.REPORT, trial.CONTROL, trial.RECEIVER
ARCHIVES = {RECEIVER: "positions.jsonl.gz", CONTROL: "stock-positions.jsonl.gz"}
RETRY = "retry-control-positions.jsonl.gz"
DECISIONS = (
    "initial_branches",
    "initial_arm_fits",
    "cavity_offered",
    "observations",
    "native_observations",
    "tracks",
    "residual_targets",
    "addition_status",
    "reassociation_admitted",
    "reassociation_targets",
    "reassociation_selected",
    "compact_projections",
    "optimizer_stops",
)
ENDPOINT_METRICS = ("conditional_rms_hz", "frequency_score", "associated_observations")
SCIENTIFIC = (*DECISIONS, *(f"{a}_{m}" for a in ARMS for m in ENDPOINT_METRICS))


def parity(before, after):
    common.require_fields(after, {k: before[k] for k in trial.MATCH})
    a, b = before["result"], after["result"]
    check = dict(control_status=a["status"], receiver_status=b["status"])
    if a["status"] == b["status"] == "ok":
        left, right = a["metrics"], b["metrics"]
        missing_rms = [
            key
            for arm in ARMS
            if (key := f"{arm}_conditional_rms_hz") not in left and key not in right
        ]
        equal = {
            key: key in left and key in right and left[key] == right[key]
            for key in SCIENTIFIC
            if key not in missing_rms
        }
        equal.update(
            endpoints=a["arms"] == b["arms"],
            position_optimizer={
                k: v for k, v in left["position_optimizer"].items() if k != "wall_s"
            }
            == right["position_optimizer"],
            salvage_counters=left["tiled_salvage"]["counters"] == right["salvage_work"],
        )
        check.update(
            equal=equal,
            missing_in_both=missing_rms,
            all_reported_fields_match=all(equal.values()),
            exact=not missing_rms and all(equal.values()),
        )
    return check


def seal(plan_path, work, output):
    plan = common.read(plan_path)
    if plan["source"] != trial.source():
        raise ValueError("direct or historical row-major source changed")
    records = {m: [] for m in ARCHIVES}
    end_ns = []
    lock_sha = common.sha(plan_path)
    for pin, (key, methods) in plan["schedule"].items():
        for i, method in enumerate(methods):
            folder = work / "runs" / key / method
            path = folder / "measurement.json"
            binding = plan["bindings"][key]
            if not path.is_file():
                status = "failed" if (folder / "request.json").is_file() else "missing"
                row = dict(
                    binding,
                    method=method,
                    key=key,
                    cpu=int(pin),
                    order=i,
                    files={},
                    resources={},
                    result=v5_lean._no_fix("No sealed worker receipt", status=status),
                )
            else:
                row = common.read(path)
                common.require_fields(
                    row,
                    dict(
                        binding,
                        method=method,
                        key=key,
                        cpu=int(pin),
                        order=i,
                        source_lock_sha256=lock_sha,
                    ),
                )
                end_ns.append(path.stat().st_mtime_ns)
            validate_result(row["result"])
            records[method].append(row)
    for method, rows in records.items():
        pack(output / ARCHIVES[method], rows)
    files = list(ARCHIVES.values())
    retry = work / "retry" / "ordinary-DS29-0082" / CONTROL / "measurement.json"
    if retry.is_file():
        row = common.read(retry)
        binding = plan["bindings"]["ordinary-DS29-0082"]
        common.require_fields(
            row, dict(binding, method=CONTROL, cpu=12, source_lock_sha256=lock_sha)
        )
        validate_result(row["result"])
        pack(output / RETRY, [dict(row, attempt="same_pin_retry_after_short_write")])
        files.append(RETRY)
    write(output / "source-lock.json", plan_path.read_bytes())
    save_json(
        output / "receipt.json",
        dict(
            cases=[r["id"] for r in records[RECEIVER]],
            source_lock_sha256=lock_sha,
            files={name: common.sha(output / name) for name in files},
            elapsed_s=(max(end_ns, default=plan["locked_ns"]) - plan["locked_ns"]) / 1e9,
        ),
    )


def timing(row):
    stats = row["resources"]
    stages = row["result"]["metrics"].get("stage_s", {})
    return dict(
        id=row["id"],
        detector=row["detector"],
        method=row["method"],
        attempt=row.get("attempt", "primary"),
        cpu=row["cpu"],
        status=row["result"]["status"],
        wall_s=stats.get("wall_s"),
        cpu_s=stats.get("cpu_s"),
        peak_rss_kib=stats.get("child_peak_rss_kib"),
        output_bytes=row["files"].get("result.json"),
        log_bytes=row["files"].get("worker.log"),
        logged_stage_s=sum(stages.values()) if stages else None,
        **{f"{k}_s": v for k, v in stages.items()},
    )


def scores(output):
    seal = common.seal(output, "receipt.json", ARCHIVES.values())
    data = {m: read_predictions(output / file) for m, file in ARCHIVES.items()}
    refs, _ = _frozen_roof()
    scored, calls, paired = [], [], {}
    for ident in seal["cases"]:
        before, after = (data[m][ident] for m in (CONTROL, RECEIVER))
        paired[ident] = parity(before, after)
        for row in (before, after):
            calls.append(timing(row))
            result = row["result"]
            for a in ARMS:
                scored.append(
                    dict(
                        id=ident,
                        detector=row["detector"],
                        method=row["method"],
                        arm=a,
                        status=result["status"],
                        error_km=distance_km(result["arms"][a]["latlon"], refs[ident]["truth"]),
                        **{m: result["metrics"].get(f"{a}_{m}") for m in ENDPOINT_METRICS},
                    )
                )
    retry_archive = output / RETRY
    if RETRY in seal["files"]:
        retry = read_predictions(retry_archive)["DS29-0082"]
        calls.append(timing(retry))
        paired["ordinary_retry"] = parity(retry, data[RECEIVER]["DS29-0082"])
    all_keys = list(dict.fromkeys(k for row in calls for k in row))
    csv_file(output / "timings.csv", [{k: row.get(k) for k in all_keys} for row in calls])
    csv_file(output / "scores.csv", scored)
    save_json(output / "parity.json", paired)
    scores = ("timings.csv", "scores.csv", "parity.json")
    manifests = []
    for cohort in ("ordinary", "capture-era"):
        selected = [i for i in seal["cases"] if data[RECEIVER][i]["detector"] == cohort]
        name = f"{cohort}-lock.json"
        save_json(
            output / name,
            dict(
                cases=selected,
                source_lock_sha256=seal["source_lock_sha256"],
                files={**seal["files"], **{f: common.sha(output / f) for f in scores}},
            ),
        )
        manifests.append(
            dict(
                id=f"compact-entry-{cohort}",
                method=RECEIVER,
                scope="roof",
                seal=name,
                cases=selected,
                title=f"Direct row-major compact v5 entry · {cohort}",
                caption=(
                    "Fresh same-core pairs use the same native factors and scientific request. "
                    "The control includes the previous qualification instrumentation."
                ),
                provenance=list(scores),
                source_lock=dict(file="source-lock.json", digest_key="source_lock_sha256"),
                series=[
                    dict(
                        key=key,
                        label=label,
                        file=ARCHIVES[m],
                        value=m,
                        where={"detector": cohort},
                        native_authority="ordinary" if cohort == "ordinary" else "frozen",
                        **({"match": list(trial.MATCH)} if m == CONTROL else {}),
                    )
                    for m, key, label in (
                        (RECEIVER, "one", "Direct numerical entry"),
                        (CONTROL, "stock", "Instrumented prior entry"),
                    )
                ],
            )
        )
    if RETRY in seal["files"]:
        ordinary, *_ = manifests
        manifests.append(
            dict(
                ordinary,
                id="compact-entry-ordinary-retry",
                title="Direct row-major compact v5 entry · ordinary control retry",
                caption=(
                    "Same direct run and bound input. The fresh control retry follows the "
                    "primary control’s scratch write failure."
                ),
                series=[
                    ordinary["series"][0],
                    dict(ordinary["series"][1], file=RETRY, label="Same-core control retry"),
                ],
            )
        )
    save_json(output / "figures.json", dict(version=1, charts=manifests))


def traces(output, trace):
    follow, inventory, costs = {}, {}, {}
    for method, name in ARCHIVES.items():
        folder = trace / method
        measurement, lines = folder / "measurement.json", folder / "lines.json"
        if not measurement.exists():
            continue
        row = common.read(measurement)
        baseline = read_predictions(output / name)["DS29-0082"]
        if method == CONTROL and baseline["result"]["status"] != "ok" and (output / RETRY).exists():
            baseline = read_predictions(output / RETRY)["DS29-0082"]
        common.require_fields(row, {k: baseline[k] for k in trial.MATCH})
        follow[method] = dict(
            status=row["result"]["status"],
            exact_endpoints=(
                row["result"]["arms"] == baseline["result"]["arms"]
                if row["result"]["status"] == baseline["result"]["status"] == "ok"
                else None
            ),
            trace_source_sha256=row["trace_source_sha256"],
            compared_to=baseline.get("attempt", "primary"),
        )
        costs[method] = dict(
            traced=row["resources"],
            ordinary=baseline["resources"],
            wall_overhead_s=row["resources"]["wall_s"] - baseline["resources"]["wall_s"],
            cpu_overhead_s=row["resources"]["cpu_s"] - baseline["resources"]["cpu_s"],
        )
        if lines.exists():
            inventory[method] = common.read(lines)
    artifact = "trace-lines.json.gz"
    write(
        output / artifact,
        gzip.compress(json.dumps(inventory, sort_keys=True).encode(), mtime=0),
    )

    def tally(row, prefix):
        files = [value for path, value in row["files"].items() if path.startswith(prefix)]
        return dict(files=len(files), lines=sum(len(value["lines"]) for value in files))

    save_json(
        output / "trace-summary.json",
        dict(
            runs=follow,
            timing=costs,
            inventory={
                m: dict(
                    all_paths=tally(row, ""),
                    repository=tally(row, "tools/"),
                    frozen_v5=tally(row, "frozen-v5/"),
                    frozen_runner=tally(row, "frozen-runner/"),
                    virtualenv=tally(row, ".venv/"),
                    qualification_imports=row["qualification_imports"],
                )
                for m, row in inventory.items()
            },
            lines_file=artifact,
            lines_sha256=common.sha(output / artifact),
        ),
    )


def caps(output, work):
    from . import compact_entry_cap as cap

    target = output / "cap"
    target.mkdir(parents=True, exist_ok=True)
    stock = read_predictions(output / ARCHIVES[CONTROL])["DS26-0026"]
    files, runs = {}, {}
    for method in (CONTROL, RECEIVER):
        source = work / method
        row = common.read(source / "measurement.json")
        common.require_fields(row, {k: stock[k] for k in trial.MATCH})
        if (
            row["cpu"] != cap.CPU
            or row["id"] != stock["id"]
            or row["method"] != method
            or not row["live_limits_verified"]
            or int(row["systemd"]["MemoryPeak"]) != row["sampled_peak_bytes"]
        ):
            raise ValueError("memory cap properties differ from the measured pair")
        for item in ("measurement.json", "service.log"):
            name = f"{method}-{item}.gz"
            write(target / name, gzip.compress((source / item).read_bytes(), mtime=0))
            files[name] = common.sha(target / name)
        last = dict(line.split() for line in row["live"][-1]["memory.events"].splitlines())
        runs[method] = dict(
            wall_s=row["wall_s"],
            cgroup_cpu_s=int(row["systemd"]["CPUUsageNSec"]) / 1e9,
            service_runtime_max=next(
                s.split("=", 1)[1] for s in row["controls"] if s.startswith("RuntimeMaxSec=")
            ),
            status=row["systemd"]["Result"],
            sampled_oom_kills=int(last["oom_kill"]),
            sampled_peak_swap_bytes=max(int(s["memory.swap.current"]) for s in row["live"]),
            cgroup_peak_bytes=row["sampled_peak_bytes"],
            endpoint_present=row["result"] is not None,
        )
    save_json(
        target / "receipt.json",
        dict(
            cases=[stock["id"]],
            input_sha256=stock["input_sha256"],
            source_lock_sha256=common.sha(output / "source-lock.json"),
            cap_runner_sha256=common.sha(Path(cap.__file__)),
            files=files,
            runs=runs,
        ),
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    modes = p.add_subparsers(dest="operation", required=True)
    freeze = modes.add_parser("seal")
    freeze.add_argument("plan", type=Path)
    freeze.add_argument("work", type=Path)
    modes.add_parser("score")
    modes.add_parser("traces").add_argument("trace", type=Path)
    modes.add_parser("caps").add_argument("work", type=Path)
    p.add_argument("--out", type=Path, default=REPORT)
    args = p.parse_args()
    out = local_output(args.out)
    if args.operation == "seal":
        seal(args.plan, args.work, out)
    elif args.operation == "score":
        scores(out)
    elif args.operation == "traces":
        traces(out, args.trace)
    else:
        caps(out, args.work)


if __name__ == "__main__":
    main()
