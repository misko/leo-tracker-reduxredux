"""Seal and score the measured regional catalogue cost reduction."""

import argparse
import gzip
from difflib import unified_diff
from pathlib import Path

from .. import figure_books, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, validate_result
from . import compact_catalogue_trial as trial
from .full_held_scores import held_references
from .full_receiver_comparison import read, require_fields, sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from
from .winner_stream_results import scientific_result

REPORT = trial.REPORT
STOCK, CANDIDATE = (trial.METHODS[k] for k in trial.MODES)
GROUP = {"ordinary": "Ordinary", "capture-era": "Capture-era"}


def measure(row, lock):
    ident = row["id"]
    require_fields(row, lock["bindings"][ident])
    cohort, cpu, _ = lock["schedule"][ident]
    require_fields(row, dict(cohort=cohort, cpu=cpu))
    result = row["result"]
    validate_result(result)
    if set(result["arms"]) != set(ARMS):
        raise ValueError("invalid calibration roster")
    if row["exit_code"]:
        return
    measured = row["measurements"]
    require_fields(
        measured["proof"],
        dict(
            cpu=cpu,
            memory=lock["memory_bytes"],
            swap=lock["swap_bytes"],
            nice=lock["nice"],
        ),
    )
    require_fields(measured["finish"], dict(swap_current=0, oom_kill=0))
    if not 0 < measured["finish"]["cgroup_peak"] <= lock["memory_bytes"]:
        raise ValueError("receiver left the physical cgroup charge")
    origins = measured["origins"]
    root = Path(origins["tools"]).parent.parent
    mode = "stock" if row["method"] == STOCK else "regional"
    if root.name != mode or any(
        not Path(location).is_relative_to(root)
        or str(Path(location).relative_to(root)) not in lock["releases"][mode]
        for location in origins.values()
    ):
        raise ValueError("qualification loaded a project source outside its pinned install")


def compare(stock, candidate):
    first, second = (row["catalogue"] for row in (stock, candidate))
    if any(r["exit_code"] for r in (stock, candidate)):
        return dict(exact=None, constructions_saved=None, status="incomplete")
    if first is None or second is None:
        raise ValueError("successful receiver lacks the measured catalogue witness")
    if (
        first["offered"] != second["offered"]
        or first["constructed"] != first["offered"]
        or first["projected_snapshots"]
        or second["projected_snapshots"] <= 0
        or second["constructed"] >= first["constructed"]
    ):
        raise ValueError("overlays unexpectedly changed source record counts or work")
    if first["evidence_sha256"] != second["evidence_sha256"]:
        raise ValueError("regional catalogue, past history or phase forecast changed")
    exact = encoded(scientific_result(stock["result"])) == encoded(
        scientific_result(candidate["result"])
    )
    if not exact:
        raise ValueError("the candidate changed an original position, RF score or decision")
    return dict(
        exact=True,
        status="paired",
        constructions_saved=first["constructed"] - second["constructed"],
        snapshots_projected=second["projected_snapshots"],
        conserved_evidence_sha256=first["evidence_sha256"],
    )


def timing(row):
    measured = row["measurements"].get("finish", {})
    trace = row["catalogue"] or {}
    stages = row["result"]["metrics"].get("stage_s", {})
    return dict(
        id=row["id"],
        cohort=row["cohort"],
        cpu=row["cpu"],
        method=row["method"],
        status=row["result"]["status"],
        offered_records=trace.get("offered"),
        sgp4_constructions=trace.get("constructed"),
        projected_snapshots=trace.get("projected_snapshots"),
        parse_hits=trace.get("hits"),
        parse_misses=trace.get("misses"),
        native_preparation_wall_s=stages.get("native_preparation"),
        compact_initial_wall_s=stages.get("initial"),
        service_wall_s=row["wall_s"],
        cpu_s=measured.get("cgroup_cpu_s"),
        cgroup_peak_bytes=measured.get("cgroup_peak"),
        peak_rss_kib=measured.get("peak_rss_kib"),
    )


def stage(resources):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    roster = tuple(trial.SCHEDULE)
    lookup = {(row["id"], row["method"]): row for row in resources}
    fig, panels = plt.subplots(1, 2, figsize=(11.2, 4.0), layout="constrained")
    for ax, key, title, unit in zip(
        panels,
        ("sgp4_constructions", "cpu_s"),
        ("SGP4 object constructions", "Complete compact receiver CPU"),
        ("Objects, thousands", "CPU seconds"),
        strict=True,
    ):
        for j, (method, label, color) in enumerate(
            ((STOCK, "Phase release", "#71869e"), (CANDIDATE, "Regional projection", "#087568"))
        ):
            data = [lookup[ident, method][key] for ident in roster]
            ax.barh(
                [i + (j - 0.5) * 0.31 for i in range(len(roster))],
                [(x or 0) / (1000 if key == "sgp4_constructions" else 1) for x in data],
                color=color,
                height=0.30,
                label=label,
            )
            for i, value in enumerate(data):
                if value is None:
                    ax.text(0, i + (j - 0.5) * 0.31, "No result", va="center", fontsize=8)
        ax.set(yticks=range(len(roster)), yticklabels=roster, xlabel=unit, title=title)
        ax.invert_yaxis()
        ax.spines[["right", "top"]].set_visible(False)
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.30), frameon=False, ncols=2)
    for suffix in ("png", "pdf"):
        fig.savefig(REPORT / f"compact-cost.{suffix}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    names = ("resources.csv", "compact-cost.png", "compact-cost.pdf", "prediction-lock.json")
    save_json(REPORT / "stage-lock.json", dict(files={n: sha(REPORT / n) for n in names}))
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="compact-regional-catalogue-cost",
            title="Repeated causal orbit preparation",
            boundary="All stored native GLRT through both compact position arms",
            sample="Four matched ordinary and capture-era recordings; units on each axis",
            note="One pinned CPU per pair, physical 512 MiB with zero swap.",
            image="compact-cost.png",
            pdf="compact-cost.pdf",
            csv="resources.csv",
            seal="stage-lock.json",
        ),
    )


def figures(rows):
    charts = []
    parents = ("prediction-lock.json", "resources.csv", "scores.csv", "parity.json")
    for group, label in GROUP.items():
        data = [row for row in rows if row["cohort"] == group]
        name, receipt = f"{group}-positions.jsonl.gz", f"{group}-figure-lock.json"
        pack(REPORT / name, data)
        ids = [row["id"] for row in data if row["method"] == STOCK]
        save_json(
            REPORT / receipt, dict(cases=ids, files={n: sha(REPORT / n) for n in (name, *parents)})
        )
        charts.append(
            dict(
                id=f"compact-regional-catalogue-{group}",
                method=CANDIDATE,
                scope="roof",
                cases="sealed",
                seal=receipt,
                title=f"{label} native factors with exact regional catalogue preparation",
                caption=(
                    "Both compact arms use the same recorded detections and causal TLEs. "
                    "The overlay avoids repeatedly constructing nonregional orbit objects. "
                    "The original v5 references use their archived capture-era requests."
                ),
                provenance=list(parents),
                series=[
                    dict(
                        file=name,
                        value=method,
                        key=key,
                        label=series,
                        native_authority="ordinary" if group == "ordinary" else "frozen",
                        match=["native_sha256", "input_sha256", "tile", "catalog_sha256"],
                    )
                    for method, key, series in (
                        (CANDIDATE, "one", "Regional catalogue projection"),
                        (STOCK, "stock", "Original phase-release solver"),
                    )
                ],
            )
        )
    save_json(REPORT / "figures.json", dict(version=2, charts=charts))
    figure_books.generate(REPORT / "charts", ARMS, panel="screening", evidence=REPORT)


def score():
    lock = read(REPORT / "source-lock.json")
    prediction = read(REPORT / "prediction-lock.json")
    for name, digest in prediction["files"].items():
        whole_iq.checked(REPORT / name, digest)
    rows = rows_from(REPORT / "positions.jsonl.gz")
    if [(r["id"], r["method"]) for r in rows] != [
        (ident, trial.METHODS[m]) for ident in trial.SCHEDULE for m in trial.MODES
    ]:
        raise ValueError("publication must retain both outcomes on every predeclared recording")
    for row in rows:
        measure(row, lock)
    comparisons = {a["id"]: compare(a, b) for a, b in zip(rows[::2], rows[1::2], strict=True)}
    save_json(REPORT / "parity.json", comparisons)
    csv_file(REPORT / "resources.csv", resources := [timing(row) for row in rows])
    _, reference = held_references(None, list(trial.SCHEDULE))
    refs = {row["id"]: row for row in reference}
    scores = []
    for row in rows:
        ref = refs[row["id"]]
        for arm, result in row["result"]["arms"].items():
            scores.append(
                dict(
                    id=row["id"],
                    cohort=row["cohort"],
                    method=row["method"],
                    arm=arm,
                    status=row["result"]["status"],
                    error_km=distance_km(result["latlon"], ref["truth"]),
                    conditional_rf_rms_hz=result.get("rf_rms_hz"),
                    **{
                        f"v5_{role}_error_km": ref["reference"][role][arm]["error_km"]
                        for role in ROLES
                    },
                )
            )
    csv_file(REPORT / "scores.csv", scores)
    stage(resources)
    figures(rows)


def seal(work):
    rows = []
    stamp = read(REPORT / "source-lock.json")
    published = trial.cavity_runtime.release_files(trial.cavity_runtime.RELEASE, trial.build.BASE)
    diff, footprints = [], {}
    for mode in trial.MODES:
        changed, net_lines = [], 0
        for name, original in sorted(published.items()):
            source = whole_iq.checked(work / mode / name, stamp["releases"][mode][name])
            if source.read_bytes() == original:
                continue
            before = original.decode().splitlines(keepends=True)
            after = source.read_text().splitlines(keepends=True)
            changed.append(name)
            net_lines += len(after) - len(before)
            if mode == "regional":
                diff.extend(
                    unified_diff(
                        before, after, fromfile=f"phase-release/{name}", tofile=f"regional/{name}"
                    )
                )
        footprints[mode] = dict(
            source_files=len(published),
            edited_sources=changed,
            net_lines=net_lines,
            added_compiled_objects=0,
        )
    write(REPORT / "installed-delta.patch", "".join(diff).encode())
    save_json(REPORT / "complexity.json", footprints)
    files = ["source-lock.json", "positions.jsonl.gz", "installed-delta.patch", "complexity.json"]
    for ident in trial.SCHEDULE:
        for mode in trial.MODES:
            output = work / ident / mode
            row = read(output / "attempt.json")
            if row["source_lock_sha256"] != sha(REPORT / "source-lock.json"):
                raise ValueError("attempt lock differs from the final measured source")
            log = whole_iq.checked(output / "stderr", row["log_sha256"])
            name = f"logs/{ident}-{mode}.log.gz"
            write(REPORT / name, gzip.compress(log.read_bytes(), mtime=0))
            files.append(name)
            rows.append(row)
    pack(REPORT / "positions.jsonl.gz", rows)
    save_json(
        REPORT / "prediction-lock.json",
        dict(cases=list(trial.SCHEDULE), files={name: sha(REPORT / name) for name in files}),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=local_output)
    args = cli.parse_args()
    if args.work:
        seal(args.work)
    score()
