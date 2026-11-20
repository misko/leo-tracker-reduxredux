"""Package and independently score the frozen winner-stream comparison."""

import argparse
import csv
import gzip
import io
import json
import tarfile
from hashlib import sha256
from pathlib import Path

from .. import corpus
from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import winner_stream_trial as trial
from .full_receiver_comparison import read, require_fields, seal, sha

ROWS = "positions.jsonl.gz"
PROVENANCE = "source-lock.json"
SOURCE = "as-measured-source.tar.gz"
PRODUCER = "producer-receipts.json"
MODES = ("stock", "winner")


def scientific_result(result):
    return dict(result, metrics={k: v for k, v in result["metrics"].items() if k != "stage_s"})


def check_attempt(row, plan, plan_sha, ident, role):
    require_fields(row, plan["cases"][ident])
    require_fields(
        row,
        dict(
            method=trial.METHODS[role],
            worker_mode=role,
            mode="matched-tile",
            source_lock_sha256=plan_sha,
        ),
    )
    pins = {i: int(cpu) for cpu, ids in plan["pins"].items() for i in ids}
    require_fields(row, dict(cpu=pins[ident]))
    validate_result(row["result"])
    if row["conversion"] is not None:
        require_fields(row["conversion"], {"native_sha256": row["native_sha256"]})
    limits = row["measurements"].get("proof")
    if limits:
        require_fields(limits, dict(cpu=row["cpu"], memory=plan["memory_bytes"], swap=0, nice=10))
    if row["exit_code"] != 0:
        return
    if not limits or not row["boundary"] or not row["measurements"].get("origins"):
        raise ValueError("a completed native replay lacks its physical boundary receipt")
    finish = row["measurements"]["finish"]
    require_fields(finish, dict(oom_kill=0, swap_current=0))
    if not 0 < finish["cgroup_peak"] <= plan["memory_bytes"]:
        raise ValueError("completed native replay exceeded the frozen charge boundary")


def compare(stock, winner):
    graph_a, graph_b = stock["boundary"], winner["boundary"]
    have_graph = graph_a is not None and graph_b is not None
    complete = stock["exit_code"] == winner["exit_code"] == 0
    return dict(
        graph_exact=(
            graph_a["tracks_sha256"] == graph_b["tracks_sha256"]
            and graph_a["track_counts"] == graph_b["track_counts"]
        )
        if have_graph
        else None,
        solver_exact=scientific_result(stock["result"]) == scientific_result(winner["result"])
        if complete
        else None,
    )


def csv_file(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def score(root, dest, *, records=None):
    plan_path = root / PROVENANCE
    plan, plan_sha = read(plan_path), sha(plan_path)
    ids = tuple(trial.ORDER)
    if set(plan["cases"]) != set(ids):
        raise ValueError("winner-stream roster differs from the frozen panel")
    require_fields(plan, dict(memory_bytes=512 * 1024**2, swap_bytes=0, limit_s=trial.LIMIT))
    packing = records is not None
    if not packing:
        receipt = seal(root, "prediction-lock.json", (ROWS, PROVENANCE, SOURCE, PRODUCER))
        require_fields(receipt, dict(cases=list(ids), source_lock_sha256=plan_sha))
        with gzip.open(root / ROWS, "rt") as handle:
            records = [json.loads(line) for line in handle]
    with tarfile.open(root / SOURCE, mode="r:gz") as archive:
        for name, pin in plan["source"].items():
            content = archive.extractfile(name)
            if content is None or sha256(content.read()).hexdigest() != pin:
                raise ValueError("archived winner-stream source differs from the paired plan")
    producer = read(root / PRODUCER)
    ordered = [(ident, mode) for ident in ids for mode in MODES]
    if [(r["id"], r["worker_mode"]) for r in records] != ordered:
        raise ValueError("winner-stream records do not contain all frozen attempts")
    lookup = dict(zip(ordered, records, strict=True))
    refs = {ref["id"]: ref for ref in corpus.references("roof16")}
    resources, errors, comparisons = [], [], {}
    for (ident, role), row in lookup.items():
        check_attempt(row, plan, plan_sha, ident, role)
        boundary = row["boundary"] or {}
        result, ref = row["result"], refs[ident]
        finish = row["measurements"].get("finish", {})
        conversion = row["conversion"] or {}
        cli = producer[ident]["native_export_converter_cli"] if role == "winner" else {}
        if cli:
            require_fields(cli, {"sha256": conversion["sha256"]})
        read_phase = boundary.get("native_read", {})
        graph = boundary.get("graph_preparation", {})
        resources.append(
            dict(
                id=ident,
                role=role,
                status=result["status"],
                reason=result.get("reason"),
                bytes=conversion.get("bytes", row["wide_input_bytes"]),
                load_wall_s=read_phase.get("wall_s"),
                graph_wall_s=graph.get("wall_s"),
                load_cpu_s=read_phase.get("cpu_s"),
                graph_cpu_s=graph.get("cpu_s"),
                load_peak_rss_kib=read_phase.get("rss_peak_kib"),
                graph_peak_rss_kib=graph.get("rss_peak_kib"),
                audit_wall_s=boundary.get("graph_audit", {}).get("wall_s"),
                rss_peak_kib=finish.get("peak_rss_kib"),
                charge_peak_bytes=finish.get("cgroup_peak"),
                swap_bytes=finish.get("swap_current"),
                oom_kill=finish.get("oom_kill"),
                solve_wall_s=row["wall_s"],
                solve_cpu_s=finish.get("cgroup_cpu_s"),
                convert_wall_s=conversion.get("wall_s"),
                convert_cpu_s=conversion.get("cpu_s"),
                convert_peak_rss_kib=conversion.get("peak_rss_kib"),
                cli_converter_wall_s=cli.get("wall_s"),
                cli_converter_cpu_s=cli.get("cpu_s"),
                cli_converter_rss_kib=cli.get("peak_rss_kib"),
                solve_plus_convert_wall_s=row["wall_s"] + conversion.get("wall_s", 0.0),
                solve_plus_convert_cpu_s=None
                if "cgroup_cpu_s" not in finish
                else (finish["cgroup_cpu_s"] + conversion.get("cpu_s", 0.0)),
                solve_plus_cli_wall_s=row["wall_s"] + cli.get("wall_s", 0.0),
                solve_plus_cli_cpu_s=None
                if "cgroup_cpu_s" not in finish
                else (finish["cgroup_cpu_s"] + cli.get("cpu_s", 0.0)),
            )
        )
        for arm in ARMS:
            value = result["arms"][arm]
            point = value.get("latlon")
            errors.append(
                dict(
                    id=ident,
                    role=role,
                    arm=arm,
                    status=result["status"],
                    error_km=distance_km(point, ref["truth"]) if point is not None else None,
                    conditional_rms_hz=value.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    **{policy: ref["reference"][policy][arm]["error_km"] for policy in ROLES},
                )
            )
        if role == "winner":
            comparisons[ident] = compare(lookup[ident, "stock"], row)
    dest.mkdir(exist_ok=True, parents=True)
    csv_file(dest / "resources.csv", resources)
    csv_file(dest / "scores.csv", errors)
    save_json(dest / "parity.json", comparisons)
    if packing:
        names = (ROWS, PROVENANCE, SOURCE, PRODUCER, "resources.csv", "scores.csv", "parity.json")
        save_json(
            dest / "prediction-lock.json",
            dict(
                cases=list(ids),
                source_lock_sha256=plan_sha,
                files={n: sha(dest / n) for n in names},
            ),
        )
    return comparisons


def pack(work, dest):
    dest.mkdir(exist_ok=True, parents=True)
    (dest / PROVENANCE).write_bytes((work / "plan.json").read_bytes())
    plan = read(dest / PROVENANCE)
    if not (dest / SOURCE).exists():
        workers = Path(__file__).parent
        paths = (
            workers / "winner_stream_trial.py",
            trial.OBSERVE,
            Path(trial.winner_stream.__file__),
            dest / "PROTOCOL.md",
        )
        require_fields(plan["source"], {path.name: sha(path) for path in paths})
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w") as archive:
            for path in (*paths, workers / "cavity_reuse_observe.py"):
                data = path.read_bytes()
                member = tarfile.TarInfo(path.name)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
        (dest / SOURCE).write_bytes(gzip.compress(output.getvalue(), mtime=0))
    records = []
    producer = {}
    for ident in trial.ORDER:
        for role in MODES:
            lane = work / "runs" / ident / role
            row = read(lane / "attempt.json")
            require_fields(row, {"worker_log_sha256": sha(lane / "stderr")})
            row["wide_input_bytes"] = Path(row["native"]).stat().st_size
            records.append(row)
            if role == "winner":
                producer[ident] = read(work / "input" / f"{ident}.producer.json")
                require_fields(
                    producer[ident],
                    {
                        "sha256": row["conversion"]["sha256"],
                        "bytes": row["conversion"]["bytes"],
                    },
                )
                staged = work / "input" / f"{ident}.cli"
                require_fields(row["conversion"], {"sha256": sha(staged)})
                cli_time = work / "input" / f"{ident}.cli-time.txt"
                wall, user, system, rss = (float(x) for x in cli_time.read_text().split())
                producer[ident]["native_export_converter_cli"] = dict(
                    sha256=sha(staged),
                    wall_s=wall,
                    cpu_s=user + system,
                    peak_rss_kib=int(rss),
                    pinned_cpu=row["cpu"],
                )
    save_json(dest / PRODUCER, producer)
    raw = "".join(json.dumps(row, sort_keys=True) + "\n" for row in records)
    (dest / ROWS).write_bytes(gzip.compress(raw.encode(), mtime=0))
    return score(dest, dest, records=records)


def plot(folder, dest):
    import matplotlib.pyplot as plt

    with (folder / "resources.csv").open(newline="") as handle:
        rows = {(r["id"], r["role"]): r for r in csv.DictReader(handle)}
    figure, axes = plt.subplots(1, 3, figsize=(11, 3.4), layout="constrained")
    views = (
        ("Handoff size", "MB", lambda r: int(r["bytes"]) / 1e6),
        (
            "Read + Graph + converter",
            "s wall",
            lambda r: sum(
                float(r[key] or 0)
                for key in ("load_wall_s", "graph_wall_s", "cli_converter_wall_s")
            ),
        ),
        ("Solve + converter", "s wall", lambda r: float(r["solve_plus_cli_wall_s"])),
    )
    for ax, (title, unit, measure) in zip(axes, views, strict=True):
        for i, ident in enumerate(trial.ORDER):
            for role, offset, color in (("stock", -0.18, "#526476"), ("winner", 0.18, "#16817c")):
                ax.barh(
                    i + offset,
                    measure(rows[ident, role]),
                    height=0.31,
                    color=color,
                    label=("Native factors" if role == "stock" else "Winner stream")
                    if i == 0
                    else None,
                )
        ax.set_title(title, loc="left", fontsize=10)
        ax.set_xlabel(unit)
        ax.set_yticks(range(len(trial.ORDER)), trial.ORDER if ax is axes[0] else [])
        ax.invert_yaxis()
        ax.grid(axis="x", alpha=0.25)
        ax.set_axisbelow(True)
    axes[0].legend(loc="lower right", fontsize=8, frameon=False)
    figure.savefig(dest / "resources.png", dpi=150)
    plt.close(figure)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=local_output)
    parser.add_argument("--out", default=trial.REPORT, type=local_output)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--pack", action="store_true")
    mode.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    if args.plot:
        plot(args.source, args.out)
    else:
        print(json.dumps((pack if args.pack else score)(args.source, args.out), indent=2))


if __name__ == "__main__":
    main()
