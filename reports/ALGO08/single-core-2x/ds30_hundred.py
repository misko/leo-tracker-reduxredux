"""Run one frozen 100-recording comparison in serial, checkpointing each pair."""

import argparse
import csv
import fcntl
import hashlib
import json
import os
import shutil
from pathlib import Path

from leo.contracts.algo08_region import Algo08Region
from leo.storage.fast_scan import immutable_json
from tools.pipeline_eval.scoring import distance_km, distribution

from . import ds30_stage as stage

COUNT = 100
ORDER_SHA256 = "a43621277db0a8e6fb90d5fa32589e66a76e6dbbd98f5d589bbbecba59f3a014"
BENCH = Path("/tmp/leo-algo08v2-2x-bench")
BUNDLE = BENCH / "integration-exact-curved-lookahead"
LAUNCHER = BUNDLE / "reports/ALGO08/single-core-2x/run-candidate"
CONFIG = BUNDLE / "spec.json"
OFFER = stage.pair.BASELINE.parent / "station/region.json"


def panel_manifest(assignments):
    labels = [a.name for a in assignments]
    if (len(set(labels)) != COUNT or len(labels) != COUNT or
            hashlib.sha256(("\n".join(labels) + "\n").encode()).hexdigest() != ORDER_SHA256):
        raise ValueError("The 100 assigned recordings differ from the frozen order")
    return dict(baseline=str(stage.pair.BASELINE), baseline_detector=stage.BASELINE_DETECTOR,
                candidate=stage.EXACT_CURVED_LOOKAHEAD, order_sha256=ORDER_SHA256,
                cases=[dict(case=a.name, rank=a.rank, order=a.order, raw_authority=a.raw_authority,
                            session=a.session, region=a.region, archive_digest=a.snapshots_sha256)
                       for a in assignments])


def summarize(rows, refs):
    details = []
    for row in rows:
        for label in stage.BUILDS:
            details.append(dict(
                case=row["case"], build=label, first=row["expected_order"][0],
                decision=row["audit"]["decisions"][label], elapsed_s=row["elapsed_s"][label],
                cpu_s=row["cpu_s"][label], input_blocks=row["input_blocks"][label],
                **{arm + "_error_km": distance_km(row["arms"][label][arm]["latlon"], refs[row["case"]])
                   for arm in stage.ARMS},
            ))
    timing = stage.observed_timing(rows)
    metrics = {}
    for label in stage.BUILDS:
        group = [r for r in details if r["build"] == label]
        metrics[label] = dict(
            fixes=sum(r["decision"] == "complete" for r in group),
            **{key: distribution([r[key] for r in group])
               for key in ("elapsed_s", "cpu_s", "fitted_c_error_km", "c0_error_km")},
        )
    return details, dict(assigned=COUNT, verified=len(rows), builds=metrics, timing=timing)


def write_report(rows, refs, output, *, candidate_label="Candidate"):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    details, summary = summarize(rows, refs)
    if not details:
        return
    with (output / "recordings.tmp").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(details[0]))
        writer.writeheader()
        writer.writerows(details)
    os.replace(output / "recordings.tmp", output / "recordings.csv")
    for file, title, axes in (
        ("runtime", "Time from raw I/Q through publication",
         (("elapsed_s", "Elapsed time (s)"), ("cpu_s", "Single-core CPU time (s)"))),
        ("position-error", "Horizontal error among returned positions",
         (("c0_error_km", "Calibration fixed at zero (km)"),
          ("fitted_c_error_km", "Fitted calibration (km)"))),
    ):
        fig, plots = plt.subplots(1, 2, figsize=(10, 4), layout="constrained")
        for ax, (field, axis) in zip(plots, axes, strict=True):
            values = [r[field] for r in details if r[field] is not None]
            bins = np.linspace(0, max(values, default=1.) * 1.025 or 1., 13)
            for build, name, color, style in (
                ("baseline", "ALGO08v2", "#354b70", "-"),
                ("candidate", candidate_label, "#00816c", "--"),
            ):
                samples = [r[field] for r in details if r["build"] == build and r[field] is not None]
                counts, _ = np.histogram(samples, bins=bins)
                ax.stairs(counts, bins, color=color, ls=style, lw=2,
                          label=f"{name} ({len(samples)}/{len(rows)})")
            ax.set(xlabel=axis, ylabel="Recordings", xlim=(0, bins[-1]))
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(axis="y", alpha=.18)
            ax.legend(frameon=False)
        if file == "runtime" and any(d["decision"] == "solver_failed" for d in details):
            title = "Time from raw I/Q through publication or solver failure"
        fig.suptitle(f"{title} · {len(rows)}/{COUNT} DS30 pairs verified")
        temp = output / (file + ".tmp")
        fig.savefig(temp, format="png", dpi=150)
        plt.close(fig)
        os.replace(temp, output / (file + ".png"))
    tmp = output / "progress.tmp"
    tmp.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
    os.replace(tmp, output / "progress.json")


def run(workspace, archive):
    archive.mkdir(parents=True, exist_ok=True)
    with (archive / "driver.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with stage.pair.single_core_slot(2):
            spec = stage.verify_build(LAUNCHER, CONFIG, stage.EXACT_CURVED_LOOKAHEAD)
            offer = Algo08Region.parse(stage.read(OFFER)).document()
            assignments = stage.frozen_assignments(COUNT, offer)
            immutable_json(archive / "panel.json", panel_manifest(assignments))
        rows = []
        for assigned in assignments:
            durable = archive / "publications" / assigned.name
            with stage.pair.single_core_slot(2):
                location = durable.parent if durable.is_dir() else workspace
                inventory = stage.inventory(location, [assigned], LAUNCHER, spec, cpu=2)
            if inventory["coverage"]["missing"]:
                stage.run_next(workspace, [assigned], inventory, assigned.name, LAUNCHER, CONFIG, OFFER,
                               cache_library=BENCH / "ds30-cache-residency.so", record_solver_failure=True)
            elif not inventory["coverage"]["verified"]:
                raise ValueError(f"Inspect the existing attempt for {assigned.name}: {inventory['cases']}")
            with stage.pair.single_core_slot(2):
                if not durable.is_dir():
                    # Publish the durable copy only after the complete directory was copied.
                    temporary = durable.with_name(assigned.name + ".copy-" + str(os.getpid()))
                    shutil.copytree(workspace / assigned.name, temporary)
                    checked = stage.verify_pair(temporary / "pair.json", assigned, LAUNCHER, spec, 2)
                    if checked["state"] != "verified":
                        raise ValueError(f"{assigned.name}: {checked}")
                    temporary.rename(durable)
                else:
                    checked = inventory["cases"][0]
                    if checked["state"] != "verified":
                        raise ValueError(f"{assigned.name}: {checked}")
                row = dict(checked, case=assigned.name, rank=assigned.rank, expected_order=assigned.order)
                immutable_json(archive / "audits" / (assigned.name + ".json"), row)
                rows.append(row)
                truth = stage.pinned(stage.OUT / "reference-audit.json", stage.REFERENCE_SHA256)
                refs = {r["dataset_label"]: (r["reference"]["latitude_deg"], r["reference"]["longitude_deg"])
                        for r in truth["cases"] if r["authority_eligible"]}
                prior_report = archive / "progress.json"
                if not prior_report.exists() or len(rows) >= stage.read(prior_report)["verified"]:
                    write_report(rows, refs, archive)
                print(f"{len(rows)}/{COUNT} verified: {assigned.name}", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    run(args.workspace.resolve(), args.archive.resolve())
