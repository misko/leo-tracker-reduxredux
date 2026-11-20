"""Validate and score the sealed standalone cavity reuse trial offline."""

import argparse
import csv
import gzip
import json
from hashlib import sha256
from pathlib import Path

from .. import corpus
from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, distance_km
from . import cavity_reuse_trial as trial
from .full_receiver_comparison import read, require_fields, seal, sha

METHODS, REPORT = trial.METHODS, trial.REPORT
TIMES = ("native_preparation", "initial", "signed", "family", "conservative", "cavity")
IGNORED = {"stage_s", "reuse_trace", "compact_projections"}
RUNNER = "measured-runner.py.gz"


def validate(row, ident, mode, plan, plan_sha):
    require_fields(row, plan["bindings"][ident])
    require_fields(
        row,
        dict(
            id=ident,
            mode=mode,
            method=METHODS[mode],
            cpu=plan["schedule"][ident][0],
            source_lock_sha256=plan_sha,
        ),
    )
    measured = row["measurements"]
    if row["result"]["status"] != "ok":
        if any(value.get("latlon") is not None for value in row["result"]["arms"].values()):
            raise ValueError("a failed attempt cannot supply a geographic result")
        return
    require_fields(
        measured["proof"],
        dict(cpu=row["cpu"], memory=plan["memory_bytes"], swap=0, nice=plan["nice"]),
    )
    require_fields(measured["finish"], dict(oom_kill=0, swap_current=0))
    if not 0 < measured["finish"]["cgroup_peak"] <= plan["memory_bytes"]:
        raise ValueError("invalid cgroup memory peak")
    if set(row["result"]["arms"]) != set(ARMS) or row["exit_code"] != 0:
        raise ValueError("incomplete successful result")
    origins = measured["origins"]
    module_root = Path(origins["tools"]).parent.parent
    release = plan["releases"][mode]
    allowed = set(release["files"]) | {"tools/__init__.py"}
    if (
        module_root.name != mode
        or not module_root.is_absolute()
        or any(
            not Path(location).is_relative_to(module_root)
            or str(Path(location).relative_to(module_root)) not in allowed
            for location in origins.values()
        )
    ):
        raise ValueError("standalone source origin escaped its installed release")


def parity(stock, candidate):
    original, result = stock["result"], candidate["result"]
    if {original["status"], result["status"]} != {"ok"}:
        return {"comparable": False, "exact": False}
    control, changed = (value["metrics"] for value in (original, result))
    same_science = {k: v for k, v in original.items() if k != "metrics"} == {
        k: v for k, v in result.items() if k != "metrics"
    } and {k: v for k, v in control.items() if k not in IGNORED} == {
        k: v for k, v in changed.items() if k not in IGNORED
    }
    saved = control["compact_projections"] - changed["compact_projections"]
    expected = changed["reuse_trace"]["hits"] if candidate["mode"] == "columns" else 0
    perf = {}
    a, b = (value["measurements"]["finish"] for value in (stock, candidate))
    for key in ("cgroup_cpu_s", "cgroup_peak", "peak_rss_kib"):
        perf[key] = dict(stock=a[key], candidate=b[key], ratio=b[key] / a[key])
    for key, values in (
        ("wall_s", [value["wall_s"] for value in (stock, candidate)]),
        (
            "native_preparation_wall_s",
            [v["stage_s"]["native_preparation"] for v in (control, changed)],
        ),
        ("initial_wall_s", [v["stage_s"]["initial"] for v in (control, changed)]),
    ):
        perf[key] = dict(stock=values[0], candidate=values[1], ratio=values[1] / values[0])
    return dict(
        comparable=True,
        exact=same_science and saved == expected,
        science_equal=same_science,
        projections_saved=saved,
        expected_projections_saved=expected,
        reuse=changed["reuse_trace"],
        measured=perf,
    )


def csv_file(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def prediction_name(mode):
    return f"{mode}-positions.jsonl.gz"


def schedule(plan):
    historical = plan.get("cohort") == "capture-era"
    expected = trial.HOLDOUT if historical else trial.CASES
    modes = trial.MODES[:2] if historical else trial.MODES
    require_fields(
        plan,
        dict(cases=list(expected), memory_bytes=512 * 1024**2, swap_bytes=0, nice=10),
    )
    require_fields(
        plan["schedule"], {name: [cpu, list(order)] for name, (cpu, order) in expected.items()}
    )
    return expected, modes, historical


def pack(work, dest):
    plan_path = work / "plan.json"
    plan = read(plan_path)
    cases, modes, historical = schedule(plan)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "source-lock.json").write_bytes(plan_path.read_bytes())
    if not (dest / RUNNER).exists():
        runner = Path(trial.__file__).read_bytes()
        require_fields(plan["code"], {"cavity_reuse_trial.py": sha256(runner).hexdigest()})
        (dest / RUNNER).write_bytes(gzip.compress(runner, mtime=0))
    collected = {}
    for mode in modes:
        collected[mode] = []
        for ident in cases:
            root = work / "runs" / ident / mode
            row = read(root / "attempt.json")
            require_fields(row, {"worker_log_sha256": sha(root / "stderr")})
            collected[mode].append(row)
        content = "".join(json.dumps(row, sort_keys=True) + "\n" for row in collected[mode])
        (dest / prediction_name(mode)).write_bytes(gzip.compress(content.encode(), mtime=0))
    if not historical:
        profiles = {}
        for ident in cases:
            path = work.parent / f"{ident}.profile.log"
            lines = [line for line in path.read_text().splitlines() if line.startswith("profile ")]
            if len(lines) != 1:
                raise ValueError(f"missing single diagnostic profile for {ident}")
            profiles[ident] = dict(log_sha256=sha(path), profile=json.loads(lines[0][8:]))
        save_json(dest / "profiling.json", profiles)
    return score(dest, dest, collected=collected, plan=plan)


def score(source, dest, *, collected=None, plan=None):
    source_lock = source / "source-lock.json"
    plan_sha = sha(source_lock)
    plan = read(source_lock) if plan is None else plan
    cases, modes, historical = schedule(plan)
    names = tuple(prediction_name(mode) for mode in modes)
    primary = (*names, "source-lock.json", RUNNER)
    if not historical:
        primary += ("profiling.json",)
    packing = collected is not None
    if not packing:
        receipt = seal(source, "prediction-lock.json", primary)
        require_fields(receipt, dict(cases=list(cases), source_lock_sha256=plan_sha))
        collected = {}
        for mode, name in zip(modes, names, strict=True):
            with gzip.open(source / name, "rt") as handle:
                collected[mode] = [json.loads(line) for line in handle]
    runner_hash = sha256(gzip.decompress((source / RUNNER).read_bytes())).hexdigest()
    require_fields(plan["code"], {"cavity_reuse_trial.py": runner_hash})
    resources, scores = [], []
    comparison = {ident: {} for ident in cases}
    refs = {ref["id"]: ref for ref in corpus.references("roof16")}
    for mode, attempts in collected.items():
        if [row["id"] for row in attempts] != list(cases):
            raise ValueError(f"unexpected {mode} roster")
        for index, row in enumerate(attempts):
            ident = row["id"]
            validate(row, ident, mode, plan, plan_sha)
            if mode != "stock":
                comparison[ident][mode] = parity(collected["stock"][index], row)
            result = row["result"]
            metrics = result.get("metrics", {})
            measured = row["measurements"].get("finish", {})
            resources.append(
                dict(
                    id=ident,
                    mode=mode,
                    method=row["method"],
                    status=result["status"],
                    reason=result.get("reason"),
                    core=row["cpu"],
                    wall_s=row["wall_s"],
                    cpu_s=measured.get("cgroup_cpu_s"),
                    peak_rss_kib=measured.get("peak_rss_kib"),
                    cgroup_peak_bytes=measured.get("cgroup_peak"),
                    swap_bytes=measured.get("swap_current"),
                    oom_kill=measured.get("oom_kill"),
                    **{f"{key}_wall_s": metrics.get("stage_s", {}).get(key) for key in TIMES},
                    projections=metrics.get("compact_projections"),
                    cache_hits=(metrics.get("reuse_trace") or {}).get("hits"),
                    cache_retained_bytes=(metrics.get("reuse_trace") or {}).get("retained_bytes"),
                )
            )
            ref = refs[ident]
            for arm in ARMS:
                value = result["arms"][arm]
                point = value.get("latlon")
                stock = collected["stock"][index]["result"]["arms"][arm].get("latlon")
                scores.append(
                    dict(
                        id=ident,
                        mode=mode,
                        method=row["method"],
                        arm=arm,
                        status=result["status"],
                        latitude_deg=point[0] if point else None,
                        longitude_deg=point[1] if point else None,
                        error_km=distance_km(point, ref["truth"]) if point else None,
                        shift_from_stock_m=1000 * distance_km(point, stock)
                        if point and stock
                        else None,
                        conditional_rf_rms_hz=value.get("rf_rms_hz"),
                        frequency_score=metrics.get(f"{arm}_frequency_score"),
                        **{role: ref["reference"][role][arm]["error_km"] for role in ROLES},
                    )
                )
    dest.mkdir(parents=True, exist_ok=True)
    csv_file(dest / "scores.csv", scores)
    csv_file(dest / "resources.csv", resources)
    save_json(dest / "comparison.json", comparison)
    if packing:
        artifacts = (*primary, "resources.csv", "scores.csv", "comparison.json")
        save_json(
            dest / "prediction-lock.json",
            dict(
                cases=list(cases),
                source_lock_sha256=plan_sha,
                files={n: sha(dest / n) for n in artifacts},
            ),
        )
    return comparison


def performance_figure(folder, output):
    """Plot measured same-core deltas and effective cgroup charge."""
    import matplotlib.pyplot as plt

    values = [
        (f"{ident} · {label}", mode, perf["measured"])
        for cohort in (folder, folder / "holdout")
        for ident, row in read(cohort / "comparison.json").items()
        for mode, label in (("columns", "columns"), ("checksum", "TLE checksums"))
        if (perf := row.get(mode, {})).get("comparable")
    ]
    fig, axes = plt.subplots(1, 3, figsize=(11, 4.4), layout="constrained", sharey=True)
    titles = (
        ("cgroup_cpu_s", "Worker CPU change", "% vs fresh stock"),
        ("wall_s", "Launch-to-exit wall change", "% vs fresh stock"),
        ("cgroup_peak", "Peak cgroup charge", "MiB under 512 MiB zero-swap limit"),
    )
    colors = {"columns": "#167d93", "checksum": "#ba6d28"}
    for ax, (key, title, unit) in zip(axes, titles, strict=True):
        for idx, (_, mode, measured) in enumerate(values):
            item = measured[key]
            if key == "cgroup_peak":
                ax.barh(idx, item["candidate"] / 1024**2, color=colors[mode], height=0.66)
                ax.plot(item["stock"] / 1024**2, idx, "|", color="#161822", markersize=14)
            else:
                ax.barh(idx, (item["ratio"] - 1) * 100, color=colors[mode], height=0.66)
        ax.axvline(512 if key == "cgroup_peak" else 0, color="#596173", lw=0.9)
        if key == "cgroup_peak":
            ax.set_xlim(0, 535)
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_xlabel(unit)
        ax.grid(axis="x", alpha=0.22)
        ax.set_axisbelow(True)
    axes[0].set_yticks(range(len(values)), [row[0] for row in values])
    axes[0].invert_yaxis()
    fig.suptitle("Exact reuse in the standalone compact cavity receiver", fontsize=14)
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=local_output)
    parser.add_argument("--out", default=REPORT, type=local_output)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--pack", action="store_true")
    mode.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    if args.plot:
        performance_figure(args.source, args.out / "resources.png")
    else:
        operation = pack if args.pack else score
        print(json.dumps(operation(args.source, args.out), indent=2))


if __name__ == "__main__":
    main()
