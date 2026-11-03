"""Evaluate frozen ALGO02 results; reference GPS is confined to this reporter."""

import argparse
import csv
import math
import statistics
from collections import Counter
from pathlib import Path

from run_algo02_ds23 import DEFAULT_RUN, digest, read, write

REFERENCE = (37.849061591561885, -122.48574968092912)
ARMS = ("c0", "fitted_c")


def position_error(latlon, reference=REFERENCE):
    a, b = map(math.radians, (latlon[0], reference[0]))
    dlon = math.radians(latlon[1] - reference[1])
    h = math.sin((a-b)/2)**2 + math.cos(a)*math.cos(b)*math.sin(dlon/2)**2
    return 12742 * math.asin(math.sqrt(min(1., max(0., h))))


def quantile(values, p):
    values = sorted(values)
    j = (len(values)-1)*p
    lo, hi = math.floor(j), math.ceil(j)
    return values[lo] + (values[hi]-values[lo])*(j-lo)


def summarize(values, population):
    if not values:
        return dict(localized=0, population=population, failures_or_pending=population)
    return dict(localized=len(values), population=population,
        failures_or_pending=population-len(values), mean_km=statistics.mean(values),
        median_km=statistics.median(values), rms_km=math.sqrt(statistics.mean(v*v for v in values)),
        p90_km=quantile(values, .9), p95_km=quantile(values, .95), maximum_km=max(values),
        below_half_km=sum(v<=.5 for v in values), below_1km=sum(v<=1 for v in values),
        fraction_all_recordings_below_half_km=sum(v<=.5 for v in values)/population)


def rows_for_case(member, result=None, receipt=None):
    """Return both rows even for an unavailable or failed recording."""
    case = member["dataset_label"]
    status = (result or {}).get("status", "pending")
    if receipt and receipt.get("code", 0) != 0:
        status = "execution_failed"
    if result and result.get("case") != case:
        raise ValueError("result belongs to another recording")
    accepted = status == "accepted"
    if accepted:
        if result.get("GPS_used") is not False or result.get("future_TLE_used") is not False:
            raise ValueError("inference provenance is not GPS-free and causal")
        for arm in ARMS:
            point = result["policy_arms"][arm]["endpoint_latlon"]
            if len(point) != 2 or not all(math.isfinite(v) for v in point):
                raise ValueError("accepted pair has no finite position")
    rows = []
    for arm in ARMS:
        row = dict(case=case, recording_id=member["recording_id"],
            recording_format=member["recording_format"], arm=arm, status=status,
            reason=(result or {}).get("reason"), error_km=None, latitude=None, longitude=None,
            curved_points=None, predictive_linear_points=None, frequency_RMS_hz=None,
            linear_paired_valid=(result or {}).get("linear_paired_valid"),
            fallback=(result or {}).get("fallback"))
        if accepted:
            record = result["policy_arms"][arm]
            point = record["endpoint_latlon"]
            row.update(error_km=position_error(point), latitude=point[0], longitude=point[1],
                curved_points=record["active_points"],
                predictive_linear_points=result.get("linear_used_points", 0),
                frequency_RMS_hz=record["RMS_hz"])
        rows.append(row)
    return rows


def report(run_dir, plots=True):
    sample = read(run_dir / "sample.json")
    protocol = read(run_dir / "protocol.json")
    if digest(run_dir / "sample.json") != protocol["sample_sha256"]:
        raise ValueError("membership changed after freeze")
    execution = read(run_dir / "execution.json") if (run_dir / "execution.json").exists() else {}
    receipts = {r["case"]: r for r in execution.get("receipts", [])}
    development = set(sample["development_cases"])
    rows = []
    for member in sample["selected"]:
        case = member["dataset_label"]
        path = run_dir / case / "algo02_result.json"
        result = read(path) if path.exists() else None
        receipt = receipts.get(case)
        if receipt and receipt.get("result_sha256") and digest(path) != receipt["result_sha256"]:
            raise ValueError("result digest changed: " + case)
        if result and result.get("engine_sha256") != protocol["source_sha256"]["tools/algo02_scan.py"]:
            raise ValueError("result uses another engine: " + case)
        for row in rows_for_case(member, result, receipt):
            row["development_scan"] = case in development
            rows.append(row)
    with (run_dir / "positions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    groups = {
        "all": lambda row: True,
        "original20_development": lambda row: row["development_scan"],
        "other393": lambda row: not row["development_scan"],
        "fast": lambda row: row["recording_format"] == "short_window_iq_recording",
        "adaptive": lambda row: row["recording_format"] == "starlink_adaptive_hop_iq"}
    summary = {}
    for name, predicate in groups.items():
        summary[name] = {}
        for arm in ARMS:
            group = [r for r in rows if r["arm"] == arm and predicate(r)]
            values = [r["error_km"] for r in group if r["error_km"] is not None]
            summary[name][arm] = summarize(values, len(group))
    all_terminal = bool(execution.get("all_terminal", False))
    write(run_dir / "summary.json", dict(position=summary, all_terminal=all_terminal,
        statuses=dict(Counter(r["status"] for r in rows if r["arm"] == "c0")),
        reference_GPS_used_only_in_reporting=REFERENCE,
        shared_reference_assumes_every_recording_at_the_supplied_stationary_site=True,
        protocol_sha256=digest(run_dir / "protocol.json"),
        goal_met=all(summary["all"][a].get("localized") == sample["population"] and
            summary["all"][a].get("mean_km", math.inf) <= .5 and
            summary["all"][a].get("median_km", math.inf) <= .5 for a in ARMS)))
    body = ["# ALGO02 — all sealed DS23 recordings", "",
        "Status: " + ("all recording jobs terminal" if all_terminal else "partial, run still pending") + ".",
        "All mean/median errors below are conditional on an accepted position. Missing positions remain in the coverage denominator.",
        "The supplied reference coordinate is used only for evaluation. Accuracy assumes all recordings were at that stationary site.", "",
        "| Subset | Arm | Localized / recordings | Mean km | Median km | P90 km | Within 0.5 km / all recordings |",
        "|---|---|---:|---:|---:|---:|---:|"]
    for group, arms in summary.items():
        for arm, stats in arms.items():
            mean, median, p90 = [f"{stats[k]:.3f}" if k in stats else "—" for k in ("mean_km", "median_km", "p90_km")]
            body.append(f"| {group} | {arm} | {stats['localized']} / {stats['population']} | {mean} | {median} | {p90} | {stats.get('below_half_km',0)} / {stats['population']} |")
    body += ["", "![Position error by scan](position_errors.png)", "![Error distribution](error_distribution.png)",
        "", "The original twenty scans are development data. The other 393 were outside that sample; this is the same dataset and site, not new-location validation.",
        "ALGO02 uses independent per-scan inference, the frozen regional box and causal TLEs. No position pooling, evaluation-driven satellite choice or threshold relaxation is applied.",
        "", "[Frozen protocol](protocol.json) · [All positions and failures](positions.csv) · [Summary](summary.json) · [Execution receipts](execution.json)", ""]
    (run_dir / "README.md").write_text("\n".join(body))
    if plots:
        plot(run_dir, rows)
    return summary


def plot(run_dir, rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 1, figsize=(15, 7), sharex=True, constrained_layout=True)
    for ax, arm in zip(axes, ARMS, strict=True):
        selected = [r for r in rows if r["arm"] == arm]
        accepted = [r for r in selected if r["error_km"] is not None]
        missing = [r for r in selected if r["error_km"] is None]
        ax.scatter([int(r["case"].split("-")[-1]) for r in accepted],
                   [r["error_km"] for r in accepted], s=13, label="Accepted position")
        fallback = [r for r in accepted if r["fallback"]]
        ax.scatter([int(r["case"].split("-")[-1]) for r in fallback],
                   [r["error_km"] for r in fallback], marker="s", facecolors="none", edgecolors="tab:orange", s=30,
                   label="Curved-pair fallback")
        ax.scatter([int(r["case"].split("-")[-1]) for r in missing], [0]*len(missing),
                   marker="x", color="crimson", s=14, transform=ax.get_xaxis_transform(), label="Failed / pending (no error value)")
        ax.axhline(.5, color="crimson", ls="--", lw=.8)
        ax.set(ylabel="Position error (km)", title=f"{arm}: {len(accepted)} / {len(selected)} positions")
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    axes[-1].set_xlabel("DS23 scan number")
    fig.suptitle("ALGO02 · independent per-scan estimates · reference GPS used only for evaluation")
    fig.savefig(run_dir / "position_errors.png", dpi=150)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(8, 5), constrained_layout=True)
    for arm in ARMS:
        selected = [r for r in rows if r["arm"] == arm]
        values = sorted(r["error_km"] for r in selected if r["error_km"] is not None)
        if values:
            ax.step(values, [(i+1)/len(selected) for i in range(len(values))], where="post", label=arm)
    ax.axvline(.5, color="crimson", ls="--", lw=.8)
    ax.set(xlabel="Position error (km)", ylabel="Fraction of all DS23 recordings", ylim=(0, 1.02),
        title="Unlocalized recordings remain outside the success fraction")
    ax.grid(alpha=.2)
    ax.legend()
    fig.savefig(run_dir / "error_distribution.png", dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, default=DEFAULT_RUN)
    args = parser.parse_args()
    report(args.run_dir)
