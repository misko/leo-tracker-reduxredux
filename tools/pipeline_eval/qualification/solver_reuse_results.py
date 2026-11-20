"""Check fit operators, report performance and score the sealed capture-era pairs."""

import argparse
import gzip
from difflib import unified_diff
from unittest.mock import patch

from .. import cavity_runtime, figure_books, whole_iq
from ..__main__ import encoded, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km
from . import cavity_reuse_results as auditor
from . import solver_reuse_trial as trial
from .full_held_scores import held_references
from .full_receiver_comparison import read, sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT


def trace(row):
    return row["result"]["metrics"].get("endpoint_reuse", {})


def science(row):
    outcome = row["result"]
    incidental = {"endpoint_reuse", "stage_s", "compact_projections"}
    return encoded(
        dict(outcome, metrics={k: v for k, v in outcome["metrics"].items() if k not in incidental})
    )


def compare(stock, endpoint):
    if stock["exit_code"] or endpoint["exit_code"]:
        return dict(status="incomplete", scientific_exact=None, trajectory_exact=None)
    a, b = trace(stock), trace(endpoint)
    return dict(
        status="paired",
        scientific_exact=science(stock) == science(endpoint),
        trajectory_exact=a["fit_trajectory_sha256"] == b["fit_trajectory_sha256"],
        fits=[a["fits"], b["fits"]],
        optimizer_evaluations=[a["optimizer_evaluations"], b["optimizer_evaluations"]],
        reporting_calculations_saved=b.get("reporting_calculations_saved", 0),
        accepted_payloads=b.get("resolved_endpoints", 0),
        compact_projections=[
            r["result"]["metrics"]["compact_projections"] for r in (stock, endpoint)
        ],
    )


def resources(row):
    meta, t = row["measurements"].get("finish", {}), trace(row)
    metrics = row["result"]["metrics"]
    return dict(
        id=row["id"],
        mode=row["mode"],
        method=row["method"],
        cpu=row["cpu"],
        status=row["result"]["status"],
        wall_s=row["wall_s"],
        cpu_s=meta.get("cgroup_cpu_s"),
        peak_rss_kib=meta.get("peak_rss_kib"),
        peak_cgroup_bytes=meta.get("cgroup_peak"),
        fits=t.get("fits"),
        optimizer_evaluations=t.get("optimizer_evaluations"),
        reporting_calculations_saved=t.get("reporting_calculations_saved", 0),
        compact_projections=metrics.get("compact_projections"),
        **{f"{n}_wall_s": metrics.get("stage_s", {}).get(n) for n in auditor.TIMES},
    )


def stage(records):
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib import pyplot as plt

    ids = list(trial.SCHEDULE)
    fig, (work, cpu) = plt.subplots(1, 2, figsize=(10.6, 4.1), layout="constrained")
    stock, endpoint = records[::2], records[1::2]
    work.barh(ids, [r["reporting_calculations_saved"] for r in endpoint], color="#10746b")
    work.set(xlabel="Complete model calculations eliminated", title="Exact endpoint reuse")
    for j, (rows, label, color) in enumerate(
        ((stock, "Stock", "#6c7d93"), (endpoint, "Accepted endpoint", "#10746b"))
    ):
        y = [i + (j - 0.5) * 0.32 for i in range(len(ids))]
        cpu.barh(y, [r["cpu_s"] or 0 for r in rows], color=color, height=0.30, label=label)
        for index, row in enumerate(rows):
            if row["cpu_s"] is None:
                cpu.text(0, y[index], "No result", fontsize=8, va="center")
    cpu.set(yticks=range(len(ids)), yticklabels=ids, xlabel="CPU seconds", title="Complete worker")
    cpu.legend(loc="lower center", bbox_to_anchor=(0.5, -0.28), frameon=False, ncols=2)
    for axis in (work, cpu):
        axis.invert_yaxis()
        axis.spines[["right", "top"]].set_visible(False)
        axis.set_axisbelow(True)
        axis.grid(axis="x", alpha=0.2)
    for ext in ("png", "pdf"):
        fig.savefig(REPORT / f"solver-reuse.{ext}", dpi=150, bbox_inches="tight")
    plt.close(fig)
    files = ("resources.csv", "solver-reuse.png", "solver-reuse.pdf", "prediction-lock.json")
    save_json(REPORT / "stage-lock.json", dict(files={name: sha(REPORT / name) for name in files}))
    save_json(
        REPORT / "stage-figure.json",
        dict(
            version=1,
            id="compact-accepted-endpoint-resources",
            title="Accepted compact endpoint reuse",
            boundary="Original native GLRT through both phase-release positions",
            sample="Four original capture-era recordings, fresh matched same-core pairs",
            note="Bars count avoided reporting work. The original optimizer evaluations still run.",
            image="solver-reuse.png",
            pdf="solver-reuse.pdf",
            csv="resources.csv",
            seal="stage-lock.json",
        ),
    )


def score():
    lock_path = REPORT / "source-lock.json"
    plan, lock = read(lock_path), read(REPORT / "prediction-lock.json")
    for name, checksum in lock["files"].items():
        whole_iq.checked(REPORT / name, checksum)
    rows = rows_from(REPORT / "positions.jsonl.gz")
    expected = [(ident, mode) for ident in trial.SCHEDULE for mode in trial.MODES]
    if [(r["id"], r["mode"]) for r in rows] != expected:
        raise ValueError("all original attempts must remain in the published denominator")
    with patch.object(auditor, "METHODS", trial.METHODS):
        for row in rows:
            auditor.validate(row, row["id"], row["mode"], plan, sha(lock_path))
    pairs = {a["id"]: compare(a, b) for a, b in zip(rows[::2], rows[1::2], strict=True)}
    save_json(REPORT / "parity.json", pairs)
    data = [resources(r) for r in rows]
    csv_file(REPORT / "resources.csv", data)
    _, refs = held_references(None, list(trial.SCHEDULE))
    roof = {r["id"]: r for r in refs}
    scores = []
    for row in rows:
        ref = roof[row["id"]]
        for arm in ARMS:
            record = row["result"]["arms"][arm]
            scores.append(
                dict(
                    id=row["id"],
                    arm=arm,
                    method=row["method"],
                    status=row["result"]["status"],
                    error_km=distance_km(record.get("latlon"), ref["truth"]),
                    conditional_rf_rms_hz=record.get("rf_rms_hz"),
                    frequency_score=row["result"]["metrics"].get(f"{arm}_frequency_score"),
                    **{
                        f"v5_{role}_error_km": ref["reference"][role][arm]["error_km"]
                        for role in ROLES
                    },
                )
            )
    csv_file(REPORT / "scores.csv", scores)
    provenance = ["prediction-lock.json", "resources.csv", "scores.csv", "parity.json"]
    files = ["positions.jsonl.gz", *provenance]
    save_json(
        REPORT / "figure-lock.json",
        dict(cases=list(trial.SCHEDULE), files={name: sha(REPORT / name) for name in files}),
    )
    spec = dict(
        id="compact-accepted-endpoint",
        method=trial.METHODS["endpoint"],
        scope="roof",
        cases="sealed",
        title="Reuse the accepted compact endpoint evaluation",
        caption="Four matched capture-era replays. Both calibration arms use identical inputs "
        "and solver budgets. The regional decision uses the original acceptance rules.",
        seal="figure-lock.json",
        provenance=provenance,
        series=[
            dict(
                file=files[0],
                key=key,
                value=trial.METHODS[mode],
                label=label,
                match=["native_sha256", "catalog_sha256", "input_sha256", "tile"],
            )
            for mode, key, label in (
                ("endpoint", "one", "Retained accepted evaluation"),
                ("stock", "stock", "Original phase release"),
            )
        ],
    )
    save_json(REPORT / "figures.json", dict(version=2, charts=[spec]))
    figure_books.generate(REPORT / "charts", ARMS, panel="screening", evidence=REPORT)
    stage(data)


def seal(work):
    plan = read(whole_iq.checked(work / "plan.json", sha(REPORT / "source-lock.json")))
    rows, files = [], ["source-lock.json", "positions.jsonl.gz"]
    for ident in trial.SCHEDULE:
        for mode in trial.MODES:
            destination = work / "runs" / ident / mode
            row = read(destination / "attempt.json")
            log = whole_iq.checked(destination / "stderr", row["worker_log_sha256"])
            name = f"logs/{ident}-{mode}.log.gz"
            write(REPORT / name, gzip.compress(log.read_bytes(), mtime=0))
            rows.append(row)
            files.append(name)
    pack(REPORT / "positions.jsonl.gz", rows)
    original = cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")
    edits, lines = [], []
    for name, digest in sorted(plan["releases"]["endpoint"]["files"].items()):
        after = whole_iq.checked(work / "endpoint" / name, digest).read_bytes()
        before = original.get(name, b"")
        if before != after:
            edits.append(name)
            lines.extend(
                unified_diff(
                    before.decode().splitlines(keepends=True),
                    after.decode().splitlines(keepends=True),
                    fromfile=f"phase-release/{name}",
                    tofile=f"endpoint/{name}",
                )
            )
    files += ["installed-delta.patch", "complexity.json"]
    write(REPORT / "installed-delta.patch", "".join(lines).encode())
    save_json(
        REPORT / "complexity.json",
        dict(
            original_sources=len(original),
            new_sources=len(plan["releases"]["endpoint"]["files"]),
            edited_and_added_sources=edits,
            compiled_libraries=plan["releases"]["endpoint"]["libraries"],
            external_runtime_dependencies_added=[],
        ),
    )
    save_json(
        REPORT / "prediction-lock.json",
        dict(
            cases=list(trial.SCHEDULE),
            files={name: sha(REPORT / name) for name in files},
        ),
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--work", type=local_output)
    args = cli.parse_args()
    if args.work:
        seal(args.work)
    score()
